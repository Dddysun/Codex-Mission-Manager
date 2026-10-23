"""Local desktop coordination adapter. Uses the installed app's versioned IPC.

No app patching, injected JavaScript, credentials, or GUI keystrokes. The native
router performs owner discovery and routes each operation to the existing owner.
This is a private, version-pinned compatibility adapter, not a public OpenAI API.
"""
import asyncio
import contextlib
import hashlib
import json
import os
from pathlib import Path
import plistlib
import sqlite3
import stat
import struct
import time
import uuid
from stages import from_turn


VERSIONS = {"initialize": 0, "thread-owner-discovery": 1,
            "thread-follower-read-model-settings": 1, "thread-follower-interrupt-turn": 4,
            "thread-follower-start-turn": 2, "thread-stream-following-changed": 1}


class DesktopError(RuntimeError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def normalize_state(state):
    turns = list(state.get("turns") or [])
    history = (state.get("turnHistory") or {}).get("history") or {}
    turns += list((history.get("entitiesByKey") or {}).values())
    by_id = {t["turnId"]: t for t in turns if t.get("turnId")}
    turns = sorted(by_id.values(), key=lambda t: (t.get("turnStartedAtMs") or 0, t["turnId"]), reverse=True)
    result = []
    for turn in turns[:2]:
        info = (turn.get("error") or {}).get("codexErrorInfo")
        quota_error = "usageLimitExceeded" if info == "usageLimitExceeded" or (
            isinstance(info, dict) and "usageLimitExceeded" in info) else None
        result.append({"id": turn["turnId"], "status": turn.get("status"), "quota_error": quota_error,
            "started_at_ms": turn.get("turnStartedAtMs") or 0,
            "client_message_id": (turn.get("params") or {}).get("clientUserMessageId"), "items": [{
            "content_fingerprint": digest({"input": (turn.get("params") or {}).get("input"),
                "items": turn.get("items"), "error": turn.get("error"),
                "client_message_id": (turn.get("params") or {}).get("clientUserMessageId")})}]})
    status = state.get("threadRuntimeStatus") or {"type": "unknown"}
    if state.get("requests") or state.get("unconfirmedTurnSubmissions"):
        status = {"type": "active", "activeFlags": ["waitingOnUserInput"]}
    thread = {"id": state["id"], "name": state.get("title") or state["id"],
              "latest_message_id": state.get("latestTurnStartMessageId"),
              "ambiguous_active_turns": sum(t.get("status") == "inProgress" for t in turns) > 1,
              "cwd": state.get("cwd"), "updatedAt": state.get("updatedAt"), "status": status,
              "execution_stage": from_turn(turns[0]) if turns else None}
    return {"thread": thread, "turns": result, "goal": state.get("threadGoal")}


class DesktopIPC:
    def __init__(self, socket_path=None, timeout=30):
        self.path = Path(socket_path or Path.home() / ".codex/ipc/ipc.sock")
        self.timeout = timeout
        self.client_id = "initializing-client"
        self.pending, self.states, self.sequences, self.owners, self.known = {}, {}, {}, {}, {}
        self.snapshots = {}
        self.reader = self.writer = self.task = None
        self.changed = asyncio.Event()

    async def start(self):
        info, parent = self.path.lstat(), self.path.parent.stat()
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid() or parent.st_uid != os.getuid():
            raise DesktopError("desktop socket ownership mismatch")
        if parent.st_mode & 0o022 or info.st_mode & 0o077:
            raise DesktopError("desktop socket is not private to this user")
        self.reader, self.writer = await asyncio.open_unix_connection(str(self.path))
        self.task = asyncio.create_task(self._read())
        result = await self.call("initialize", {"clientType": "usage-guardian"})
        self.client_id = result["result"]["clientId"]

    async def send(self, value):
        data = json.dumps(value, ensure_ascii=False).encode()
        self.writer.write(struct.pack("<I", len(data)) + data)
        await self.writer.drain()

    async def _read(self):
        try:
            while True:
                size = struct.unpack("<I", await self.reader.readexactly(4))[0]
                if not 0 < size <= 64 * 1024 * 1024:
                    raise DesktopError("unexpected desktop frame size")
                value = json.loads(await self.reader.readexactly(size))
                kind = value.get("type")
                if kind == "response":
                    future = self.pending.get(value.get("requestId"))
                    if future and not future.done():
                        future.set_result(value)
                elif kind == "client-discovery-request":
                    await self.send({"type": "client-discovery-response", "requestId": value["requestId"],
                                     "response": {"canHandle": False}})
                elif kind == "broadcast":
                    params = value.get("params") or {}
                    tid, host = params.get("conversationId"), params.get("hostId", "local")
                    if tid:
                        self.known[tid] = host
                    if value.get("method") == "thread-stream-state-changed":
                        if value.get("version") != 11:
                            raise DesktopError("desktop snapshot protocol changed")
                        change = params.get("change") or {}
                        if change.get("type") == "snapshot":
                            view = normalize_state(change["conversationState"])
                            self.states[tid] = view
                            self.sequences[tid] = self.sequences.get(tid, 0) + 1
                            batch = self.snapshots.setdefault(tid, [])
                            batch.append((self.sequences[tid], time.monotonic(), view))
                            del batch[:-32]
                        self.changed.set()
                    elif value.get("method") == "client-status-changed" and params.get("status") == "disconnected":
                        departed = params.get("clientId")
                        self.owners = {k: v for k, v in self.owners.items() if v != departed}
        except (asyncio.CancelledError, Exception) as exc:
            for future in list(self.pending.values()):
                if not future.done():
                    future.set_exception(DesktopError(type(exc).__name__))

    async def call(self, method, params, host="local", target=None, timeout=None, version_override=None):
        if method not in VERSIONS:
            raise DesktopError("desktop operation not allowed")
        request_id = str(uuid.uuid4())
        request_timeout = self.timeout if timeout is None else timeout
        future = asyncio.get_running_loop().create_future()
        self.pending[request_id] = future
        version = VERSIONS[method] if version_override is None else version_override
        if host != "local" and method.startswith("thread-follower-"):
            version += 1
        value = {"type": "request", "requestId": request_id, "sourceClientId": self.client_id,
                 "method": method, "params": params, "version": version,
                 "timeoutMs": int(request_timeout * 1000)}
        if target:
            value["targetClientId"] = target
        if host != "local" and method.startswith("thread-follower-"):
            value["hostId"] = host
        try:
            await self.send(value)
            result = await asyncio.wait_for(future, request_timeout + .5)
            if result.get("resultType") != "success":
                # Known local protocol diagnostics only; never log conversation content.
                raise DesktopError(method + ": " + str(result.get("error", "unknown"))[:180])
            return result
        finally:
            self.pending.pop(request_id, None)

    async def owner(self, thread_id, host="local"):
        result = await self.call("thread-owner-discovery", {"conversationId": thread_id, "hostId": host}, timeout=3)
        owner = result["handledByClientId"]
        self.owners[thread_id] = owner
        self.known[thread_id] = host
        return owner

    async def snapshot(self, thread_id, host="local"):
        owner = self.owners.get(thread_id) or await self.owner(thread_id, host)
        before = self.sequences.get(thread_id, 0)
        await self.send({"type": "broadcast", "method": "thread-stream-following-changed", "version": 1,
            "sourceClientId": self.client_id, "targetClientIds": [owner],
            "params": {"conversationId": thread_id, "hostId": host, "following": True}})
        deadline = time.monotonic() + 5
        first_seen = None
        while time.monotonic() < deadline:
            batch = [entry for entry in self.snapshots.get(thread_id, []) if entry[0] > before]
            if batch:
                now = time.monotonic()
                first_seen = first_seen or now
                # The same desktop owner can emit an old cached view before the
                # live view. A newly emitted frame is not proof of current history.
                # Collect the burst and rank by the newest actual turn, rather
                # than choosing the first frame or blindly choosing the last.
                if now - batch[-1][1] >= .3 or now - first_seen >= 1:
                    selected = max(batch, key=lambda entry: self.snapshot_rank(entry[2]) + (entry[0],))[2]
                    self.states[thread_id] = selected
                    return selected
            await asyncio.sleep(.02)
        self.owners.pop(thread_id, None)
        raise DesktopError("fresh desktop snapshot unavailable")

    @staticmethod
    def snapshot_rank(view):
        latest = view["turns"][0] if view["turns"] else {}
        return (latest.get("started_at_ms", 0), latest.get("id", ""))

    async def interrupt(self, thread_id, turn_id, host="local"):
        owner = self.owners.get(thread_id) or await self.owner(thread_id, host)
        result = await self.call("thread-follower-interrupt-turn", {
            "conversationId": thread_id, "mode": "system", "expectedTurnId": turn_id}, host, owner)
        return result["result"]

    async def interrupt_goal(self, thread_id, host="local"):
        owner = self.owners.get(thread_id) or await self.owner(thread_id, host)
        result = await self.call("thread-follower-interrupt-turn", {
            "conversationId": thread_id, "mode": "system"}, host, owner, version_override=3)
        return result["result"]

    async def start_turn(self, thread_id, request, host="local"):
        owner = self.owners.get(thread_id) or await self.owner(thread_id, host)
        result = await self.call("thread-follower-start-turn", {"conversationId": thread_id,
            "turnStart": {"request": request, "context": {"inheritThreadSettings": True}}}, host, owner)
        return result["result"]

    async def close(self):
        if self.writer:
            self.writer.close()
            with contextlib.suppress(Exception):
                await self.writer.wait_closed()
        if self.task:
            self.task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.task


class DesktopAdapter:
    supports_expected_previous_turn = True
    def __init__(self, quota_rpc, config):
        self.quota = quota_rpc
        self.config = config
        self.ipc = DesktopIPC(config.get("desktop_socket"))
        self.hosts = {x["id"]: x.get("host_id", "local") for x in config.get("desktop_targets", [])}
        self.changed = quota_rpc.changed
        self.views, self.available = {}, []
        self.discovery_signatures = {}
        self.discovery_error = None
        self.account_display = None

    async def start(self):
        app = plistlib.loads(Path("/Applications/ChatGPT.app/Contents/Info.plist").read_bytes())
        if str(app.get("CFBundleVersion")) != self.config["desktop_app_build"]:
            raise DesktopError("installed desktop build changed; adapter must be revalidated")
        await self.quota.start()
        await self.ipc.start()

    async def discover(self):
        candidates = dict(self.hosts)
        candidates.update(self.ipc.known)
        signatures = {}
        db_path = Path(self.config.get("desktop_database", str(Path.home() / ".codex/state_5.sqlite")))
        self.discovery_error = None
        if db_path.exists():
            try:
                db = sqlite3.connect("file:" + str(db_path) + "?mode=ro", uri=True, timeout=1)
                try:
                    for row in db.execute("SELECT id,updated_at_ms FROM threads WHERE archived=0 AND source='vscode' ORDER BY updated_at DESC LIMIT 100"):
                        candidates[row[0]] = "local"
                        signatures[row[0]] = row[1]
                finally:
                    db.close()
            except sqlite3.Error as exc:
                # Discovery is optional. Registered native owners remain controllable.
                self.discovery_error = {"type": type(exc).__name__, "message": str(exc)}
        semaphore = asyncio.Semaphore(5)
        async def check(tid, host):
            if tid in self.ipc.owners:
                return tid
            previous = self.discovery_signatures.get(tid)
            if previous and previous[0] == signatures.get(tid) and time.monotonic() - previous[1] < 120:
                return None
            async with semaphore:
                try:
                    await self.ipc.owner(tid, host)
                    self.hosts[tid] = host
                    return tid
                except (DesktopError, asyncio.TimeoutError):
                    self.discovery_signatures[tid] = (signatures.get(tid), time.monotonic())
                    return None
        results = await asyncio.gather(*(check(tid, host) for tid, host in candidates.items()))
        self.available = [tid for tid in results if tid]
        return list(self.available)

    async def call(self, method, params=None):
        params = params or {}
        if method.startswith("account/"):
            if method == "account/rateLimits/read" and self.config.get("fresh_quota_reads"):
                from rpc import Rpc
                probe = Rpc(self.quota.command, self.quota.timeout)
                try:
                    await probe.start()
                    # Public display metadata comes from the same fresh session
                    # as these limits; the UI never starts its own polling loop.
                    try:
                        account = await probe.call("account/read", {"refreshToken": False})
                    except Exception:
                        account = None  # Optional display failure must not hide low quota.
                    result = await probe.call(method, params)
                    from account_display import display_snapshot
                    self.account_display = display_snapshot(account, result,
                        self.config.get("limit_id", "codex"), time.time())
                    return result
                finally:
                    await probe.close()
            return await self.quota.call(method, params)
        if method == "thread/loaded/list":
            return {"data": list(self.available)}
        tid = params.get("threadId")
        host = self.hosts.get(tid, "local")
        if method == "thread/read":
            self.views[tid] = await self.ipc.snapshot(tid, host)
            return {"thread": self.views[tid]["thread"]}
        if method == "thread/turns/list":
            return {"data": self.views[tid]["turns"]}
        if method == "thread/goal/get":
            return {"goal": self.views[tid]["goal"]}
        if method == "thread/goal/set":
            # Goals belong to the desktop's real database, not our isolated quota runtime.
            from rpc import Rpc
            command = self.config.get("goal_rpc_command") or [self.quota.command[0], "app-server", "--listen", "stdio://"]
            goal_rpc = Rpc(command, self.quota.timeout)
            try:
                await goal_rpc.start()
                return await goal_rpc.call(method, params)
            finally:
                await goal_rpc.close()
        if method == "turn/interrupt":
            if params.get("goal"):
                result = await self.ipc.interrupt_goal(tid, host)
                if not result.get("ok"):
                    raise DesktopError("desktop goal pause was rejected")
                return {}
            result = await self.ipc.interrupt(tid, params["turnId"], host)
            if not result.get("ok") or result.get("interruptedTurnId") != params["turnId"]:
                raise DesktopError("desktop did not interrupt the expected turn")
            return {}
        if method == "turn/start":
            before = await self.ipc.snapshot(tid, host)
            runtime = before["thread"]["status"]
            if (runtime["type"] not in ("idle", "systemError") or runtime.get("activeFlags")
                    or any(turn.get("status") == "inProgress" for turn in before["turns"])):
                raise DesktopError("desktop thread is no longer idle")
            prior = before["turns"][0]["id"] if before["turns"] else None
            if "_guardian_expected_turn_id" in params and params["_guardian_expected_turn_id"] != prior:
                raise DesktopError("conversation changed before dispatch")
            request = {k: v for k, v in params.items() if not k.startswith("_guardian_")}
            try:
                await self.ipc.start_turn(tid, request, host)
            except (DesktopError, asyncio.TimeoutError):
                # Never replay an ambiguous start; reconcile by its unique client message ID.
                view = await self.ipc.snapshot(tid, host)
                if view["turns"] and view["turns"][0].get("client_message_id") == params.get("clientUserMessageId"):
                    return {"turn": view["turns"][0]}
                raise
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                view = await self.ipc.snapshot(tid, host)
                if (view["turns"] and view["turns"][0]["id"] != prior
                        and (view["turns"][0].get("client_message_id") == params.get("clientUserMessageId")
                             or view["thread"].get("latest_message_id") == params.get("clientUserMessageId"))):
                    return {"turn": view["turns"][0]}
                await asyncio.sleep(.1)
            raise DesktopError("desktop continuation acknowledgement unavailable")
        raise DesktopError("unsupported adapter operation")

    async def verify_latest(self, thread_id, turn_id):
        # Read persisted metadata in a separate read-only request path, without
        # resuming the thread. This catches a stale desktop view before a plan.
        from rpc import Rpc
        command = self.config.get("history_rpc_command") or [self.quota.command[0], "app-server", "--listen", "stdio://"]
        probe = Rpc(command, self.quota.timeout)
        try:
            await probe.start()
            turns = (await probe.call("thread/turns/list", {"threadId": thread_id,
                "limit": 1, "sortDirection": "desc", "itemsView": "summary"}))["data"]
            return (turns[0]["id"] if turns else None) == turn_id
        finally:
            await probe.close()

    async def ensure_loaded(self, thread_id):
        try:
            await self.ipc.owner(thread_id)
            if thread_id not in self.available:
                self.available.append(thread_id)
            return
        except (DesktopError, asyncio.TimeoutError):
            pass
        # Reopen the existing desktop conversation, never a second executor.
        # Only callers processing an explicit UI action use this method.
        uuid.UUID(thread_id)
        process = await asyncio.create_subprocess_exec("/usr/bin/open", "codex://threads/" + thread_id,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        if await process.wait():
            raise DesktopError("desktop could not open the selected conversation")
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            try:
                await self.ipc.owner(thread_id)
                if thread_id not in self.available:
                    self.available.append(thread_id)
                return
            except (DesktopError, asyncio.TimeoutError):
                await asyncio.sleep(.5)
        raise DesktopError("selected conversation is not loaded yet")

    async def close(self):
        await self.ipc.close()
        await self.quota.close()
