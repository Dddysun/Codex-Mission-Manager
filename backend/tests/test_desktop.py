import asyncio
import copy
import json
import os
import sqlite3
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import uuid
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from desktop import DesktopAdapter, DesktopIPC, DesktopError, MAX_DESKTOP_FRAME_BYTES, normalize_state, windows_pipe_address
from guardian import Controller, Store
from test_guardian import CONFIG, NOW, payload, sample


def state():
    return {"id": "one", "title": "test", "cwd": "/tmp", "updatedAt": 1,
            "hostId": "local", "threadRuntimeStatus": {"type": "active", "activeFlags": []},
            "requests": [], "turns": [], "turnHistory": {"kind": "canonical", "history": {
                "entitiesByKey": {"first": {"turnId": "original-one", "status": "inProgress",
                    "turnStartedAtMs": 10, "params": {"input": [{"text": "test"}]}, "items": []}}}}}


class NormalizeTests(unittest.TestCase):
    def test_canonical_history_turns_are_read(self):
        result = normalize_state(state())
        self.assertEqual(result["turns"][0]["id"], "original-one")
        self.assertEqual(result["turns"][0]["status"], "inProgress")

    def test_pending_approval_is_not_automatically_interrupted(self):
        value = state()
        value["requests"] = [{"method": "requestApproval"}]
        result = normalize_state(value)
        self.assertEqual(result["thread"]["status"]["activeFlags"], ["waitingOnUserInput"])

    def test_input_change_changes_anchor_without_copying_input(self):
        a = state()
        b = copy.deepcopy(a)
        b["turnHistory"]["history"]["entitiesByKey"]["first"]["params"]["input"] = [{"text": "cancel"}]
        self.assertNotEqual(normalize_state(a)["turns"], normalize_state(b)["turns"])
        self.assertNotIn("cancel", json.dumps(normalize_state(b)))


class PipeEndpointTests(unittest.TestCase):
    def test_default_is_the_real_client_pipe_but_explicit_local_endpoints_are_supported(self):
        self.assertEqual(windows_pipe_address(), r'\\.\pipe\codex-ipc')
        endpoint = r'\\.\pipe\cmm-test-' + uuid.uuid4().hex
        self.assertEqual(windows_pipe_address(endpoint), endpoint)

    def test_remote_or_filesystem_paths_cannot_replace_a_local_pipe(self):
        for endpoint in (r'\\remote\pipe\codex-ipc', r'C:\temp\app.sock', '/tmp/app.sock',
                         r'\\.\pipe\nested\codex-ipc', '\\\\.\\pipe\\'):
            with self.assertRaises(DesktopError):
                windows_pipe_address(endpoint)


class Quota:
    def __init__(self):
        self.changed = asyncio.Event()

    async def start(self):
        pass

    async def close(self):
        pass

    async def call(self, method, params=None):
        if method == "account/rateLimits/read":
            return payload(remaining=98, reset=NOW + 18000)
        raise AssertionError(method)


class NativeProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.compatibility_patch = mock.patch("compatibility.require_supported", return_value={"supported": True})
        self.compatibility_patch.start()
        self.addCleanup(self.compatibility_patch.stop)
        self.temp = tempfile.TemporaryDirectory(prefix="ug-ipc-", dir=None if os.name == 'nt' else '/tmp')
        self.socket = (r'\\.\pipe\cmm-test-' + uuid.uuid4().hex if os.name == 'nt'
                       else str(Path(self.temp.name) / 'app.sock'))
        self.state, self.requests = state(), []
        self.snapshot_burst = None
        self.connections = set()
        self.handler_errors = []
        self.pipe_servers = []
        self.attestation = None
        if os.name == 'nt':
            self.assertNotEqual(self.socket, r'\\.\pipe\codex-ipc')
            loop = asyncio.get_running_loop()
            def protocol():
                return asyncio.StreamReaderProtocol(asyncio.StreamReader(),self.accept)
            self.pipe_servers = await loop.start_serving_pipe(protocol,self.socket)
            package = mock.patch('compatibility.windows_client',return_value={
                'install_location':self.temp.name,'version':'framed-fixture'})
            self.package_lookup = package.start()
            self.addCleanup(package.stop)
            attestation = mock.patch('platform_support.verify_windows_pipe_server',return_value={
                'pid':os.getpid(),'same_user':True,'installed_package_path':True})
            self.attestation = attestation.start()
            self.addCleanup(attestation.stop)
            self.server = None
        else:
            self.server = await asyncio.start_unix_server(self.accept,path=self.socket)
            os.chmod(self.socket, 0o600)
        self.adapter = DesktopAdapter(Quota(), {"desktop_app_build": "20770"})
        self.adapter.ipc = DesktopIPC(self.socket, timeout=2)
        # Avoid depending on the host app build in protocol fixture tests.
        await self.adapter.ipc.start()
        if self.attestation is not None:
            self.attestation.assert_called_once()
            self.package_lookup.assert_called_once_with(verify_cli=False)
            self.assertEqual(self.attestation.call_args.args[1],self.temp.name)
            self.assertEqual(self.adapter.ipc.pipe_address,self.socket)
            self.assertTrue(self.adapter.ipc.server_identity['same_user'])
        self.adapter.control_available = True  # Only this isolated fake transport.
        self.adapter.available = ["one"]
        self.store = Store(Path(self.temp.name) / "state")
        self.controller = Controller(self.adapter, self.store, CONFIG, "scope-one", clock=lambda: NOW)

    async def asyncTearDown(self):
        await self.adapter.close()
        if self.server is not None:
            self.server.close()
            await self.server.wait_closed()
        for server in self.pipe_servers:
            server.close()
        if self.connections:
            await asyncio.gather(*list(self.connections),return_exceptions=True)
        await asyncio.sleep(0)  # Let cancelled pipe accepts release their handles.
        self.store.close()
        self.temp.cleanup()
        if self.handler_errors:
            raise self.handler_errors[0]

    def accept(self, reader, writer):
        task = asyncio.create_task(self.handle(reader,writer))
        self.connections.add(task)
        def done(value):
            self.connections.discard(value)
            if not value.cancelled():
                error = value.exception()
                if error is not None:
                    self.handler_errors.append(error)
        task.add_done_callback(done)

    async def send(self, writer, value):
        data = json.dumps(value).encode()
        writer.write(struct.pack("<I", len(data)) + data)
        await writer.drain()

    async def handle(self, reader, writer):
        try:
            while True:
                size = struct.unpack("<I", await reader.readexactly(4))[0]
                value = json.loads(await reader.readexactly(size))
                if value["type"] == "broadcast":
                    if value["method"] == "thread-stream-following-changed":
                        for current in self.snapshot_burst or [self.state]:
                            await self.send(writer, {"type": "broadcast", "method": "thread-stream-state-changed",
                                "version": 11, "params": {"conversationId": "one", "hostId": "local",
                                "change": {"type": "snapshot", "revision": 1, "conversationState": current}}})
                            await asyncio.sleep(.03)
                    continue
                self.requests.append(value)
                method, params = value["method"], value["params"]
                if method == "initialize":
                    result = {"clientId": "guardian-client"}
                elif method == "thread-owner-discovery":
                    result = {"supportsUntrustedAppInput": True}
                elif method == "thread-follower-interrupt-turn":
                    self.assertEqual(value["version"], 4)
                    self.assertEqual(params["expectedTurnId"], "original-one")
                    self.state["turnHistory"]["history"]["entitiesByKey"]["first"]["status"] = "interrupted"
                    self.state["threadRuntimeStatus"] = {"type": "idle"}
                    result = {"ok": True, "interruptedTurnId": "original-one"}
                elif method == "thread-follower-start-turn":
                    self.assertEqual(value["version"], 2)
                    self.assertTrue(params["turnStart"]["context"]["inheritThreadSettings"])
                    self.assertNotIn("useUserMessageAdmission", params["turnStart"]["context"])
                    self.state["turnHistory"]["history"]["entitiesByKey"]["continued"] = {
                        "turnId": "continued-one", "status": "inProgress", "turnStartedAtMs": 20,
                        "items": [], "params": params["turnStart"]["request"]}
                    self.state["threadRuntimeStatus"] = {"type": "active", "activeFlags": []}
                    result = {"result": None}
                else:
                    raise AssertionError(method)
                await self.send(writer, {"type": "response", "requestId": value["requestId"],
                    "resultType": "success", "method": method, "handledByClientId": "desktop-owner", "result": result})
        except (asyncio.IncompleteReadError, ConnectionResetError, BrokenPipeError):
            pass
        finally:
            writer.close()
            await writer.wait_closed()

    async def test_client_update_blocks_every_mutating_operation_before_transport(self):
        with mock.patch("compatibility.require_supported", side_effect=RuntimeError("unsupported build")) as guard:
            for method in ("turn/start", "turn/interrupt", "thread/goal/set"):
                before = len(self.requests)
                with self.assertRaisesRegex(RuntimeError, "unsupported build"):
                    await self.adapter.call(method, {"threadId": "one", "turnId": "original-one"})
                self.assertEqual(len(self.requests), before)
            self.assertEqual(guard.call_count, 3)
        # Reads are still transport-only and must not trigger a mutation guard.
        with mock.patch("compatibility.require_supported", side_effect=RuntimeError("unsupported build")) as guard:
            result = await self.adapter.call("account/rateLimits/read")
            self.assertIn("rateLimitsByLimitId", result)
            guard.assert_not_called()

    @unittest.skipUnless(os.name == 'nt','Windows pipe server identity rejection')
    async def test_rejected_windows_pipe_identity_receives_no_protocol_frames(self):
        before = len(self.requests)
        refused = DesktopIPC(self.socket,timeout=2)
        try:
            with mock.patch('platform_support.verify_windows_pipe_server',side_effect=PermissionError('fixture wrong owner')):
                with self.assertRaises(PermissionError):
                    await refused.start()
        finally:
            await refused.close()
        await asyncio.sleep(0)
        self.assertEqual(len(self.requests),before)

    async def test_full_controller_through_native_framed_socket(self):
        await self.controller.adopt("one")
        await self.controller.tick(sample())
        self.assertEqual(self.store.get_task("one")["state"], "paused")
        await self.controller.tick(sample(remaining=98, reset=NOW + 18000))
        self.assertEqual(self.store.get_task("one")["state"], "running")
        self.assertEqual(self.store.get_task("one")["resumed_turn_id"], "continued-one")
        await self.controller.tick(sample(remaining=98, reset=NOW + 18000))
        self.assertEqual(sum(v["method"] == "thread-follower-start-turn" for v in self.requests), 1)

    async def test_immediate_dispatch_uses_native_start_and_receives_ack(self):
        from catalog import entry
        from immediate import ImmediateRunner, enqueue_dispatch, latest_dispatches
        import uuid
        chat = entry("one", "Native dispatch test")
        self.state["threadRuntimeStatus"] = {"type": "idle"}
        self.state["turnHistory"]["history"]["entitiesByKey"]["first"]["status"] = "completed"
        self.store.put("chat_catalog", {"scope": "scope-one", "items": [chat]})
        value = sample(remaining=98, reset=NOW + 18000)
        value["scope"] = "scope-one"
        enqueue_dispatch(self.store, chat, "只回复即时执行验证成功", str(uuid.uuid4()), 0, value, CONFIG, NOW)
        # Persisted-history verification is tested separately; this fixture owns
        # only a native framed IPC socket and must not start a real app server.
        with mock.patch.object(self.adapter, "verify_latest", new=mock.AsyncMock(return_value=True)):
            await ImmediateRunner(self.controller).tick(value)
        receipt = latest_dispatches(self.store)[chat["key"]]
        self.assertEqual(receipt["state"], "sent")
        self.assertEqual(receipt["turn_id"], "continued-one")
        self.assertEqual(sum(r["method"] == "thread-follower-start-turn" for r in self.requests), 1)
        self.assertFalse(any(r["method"] == "thread-follower-interrupt-turn" for r in self.requests))

    async def test_manual_input_change_blocks_native_continuation(self):
        await self.controller.adopt("one")
        await self.controller.tick(sample())
        self.state["turnHistory"]["history"]["entitiesByKey"]["manual"] = {
            "turnId": "manual", "status": "completed", "turnStartedAtMs": 30, "items": [], "params": {}}
        await self.controller.tick(sample(remaining=98, reset=NOW + 18000))
        self.assertEqual(self.store.get_task("one")["state"], "needs_review")
        self.assertFalse(any(v["method"] == "thread-follower-start-turn" for v in self.requests))

    async def test_discovery_database_error_keeps_registered_owner_available(self):
        database = Path(self.temp.name) / "unreadable.sqlite"
        database.touch()
        self.adapter.config["desktop_database"] = str(database)
        self.adapter.hosts["one"] = "local"
        with mock.patch("desktop.sqlite3.connect", side_effect=sqlite3.OperationalError("unable to open database file")):
            self.assertEqual(await self.adapter.discover(), ["one"])
        self.assertEqual(self.adapter.discovery_error["type"], "OperationalError")
        await self.controller.adopt("one")
        await self.controller.tick(sample())
        await self.controller.tick(sample(remaining=98, reset=NOW + 18000))
        self.assertEqual(self.store.get_task("one")["state"], "running")

    async def test_old_error_snapshot_before_live_snapshot_does_not_hide_active_turn(self):
        old = copy.deepcopy(self.state)
        turn = old["turnHistory"]["history"]["entitiesByKey"]["first"]
        turn.update(turnId="old-turn", turnStartedAtMs=1, status="failed")
        old["threadRuntimeStatus"] = {"type": "systemError"}
        self.snapshot_burst = [old, self.state]
        await self.controller.adopt("one")
        await self.controller.tick(sample())
        self.assertEqual(self.store.get_task("one")["state"], "paused")
        interrupts = [v for v in self.requests if v["method"] == "thread-follower-interrupt-turn"]
        self.assertEqual(len(interrupts), 1)
        self.assertEqual(interrupts[0]["params"]["expectedTurnId"], "original-one")

    async def test_old_snapshot_arriving_last_cannot_overwrite_current_turn(self):
        old = copy.deepcopy(self.state)
        turn = old["turnHistory"]["history"]["entitiesByKey"]["first"]
        turn.update(turnId="old-turn", turnStartedAtMs=1, status="completed")
        old["threadRuntimeStatus"] = {"type": "idle"}
        self.snapshot_burst = [self.state, old]
        view = await self.adapter.ipc.snapshot("one")
        self.assertEqual(view["turns"][0]["id"], "original-one")
        self.assertEqual(view["thread"]["status"]["type"], "active")

    async def test_runtime_error_does_not_override_a_current_active_turn(self):
        self.state["threadRuntimeStatus"] = {"type": "systemError"}
        await self.controller.adopt("one")
        await self.controller.tick(sample())
        self.assertEqual(self.store.get_task("one")["state"], "paused")

    async def test_current_approval_still_blocks_pause_after_stale_error_snapshot(self):
        old = copy.deepcopy(self.state)
        old["turnHistory"]["history"]["entitiesByKey"]["first"].update(turnStartedAtMs=1, status="failed")
        old["threadRuntimeStatus"] = {"type": "systemError"}
        self.state["requests"] = [{"method": "requestApproval"}]
        self.snapshot_burst = [old, self.state]
        await self.controller.adopt("one")
        await self.controller.tick(sample())
        self.assertEqual(self.store.get_task("one")["state"], "watching")
        self.assertFalse(any(v["method"] == "thread-follower-interrupt-turn" for v in self.requests))

    async def test_expected_previous_turn_guard_prevents_new_input_race(self):
        self.state["threadRuntimeStatus"]={"type":"idle"}
        self.state["turnHistory"]["history"]["entitiesByKey"]["first"]["status"]="completed"
        with self.assertRaises(DesktopError):
            await self.adapter.call("turn/start",{"threadId":"one","_guardian_expected_turn_id":"older-turn", "input":[]})
        self.assertFalse(any(v["method"]=="thread-follower-start-turn" for v in self.requests))

    async def test_large_history_snapshot_does_not_disconnect_other_chats(self):
        # A long real conversation crossed 64 MiB. Exercise the framed stream,
        # parser and subsequent request, rather than only checking the constant.
        self.state["fixturePadding"] = "x" * (64 * 1024 * 1024)
        # Use the production transport budget for this large Windows pipe
        # transfer; the two-second small-fixture budget is not a size contract.
        self.adapter.ipc.timeout = CONFIG['rpc_timeout_seconds']
        view = await self.adapter.ipc.snapshot("one")
        self.assertEqual(view["thread"]["status"]["type"], "active")
        self.assertNotIn("fixturePadding", json.dumps(view))
        self.assertFalse(self.adapter.ipc.disconnected)
        self.assertEqual(await self.adapter.ipc.owner("another"), "desktop-owner")

    async def test_closed_transport_fails_immediately_then_reconnects_on_mac(self):
        ipc = self.adapter.ipc
        await ipc.close()
        self.assertTrue(ipc.disconnected)
        with self.assertRaises(DesktopError):
            await asyncio.wait_for(ipc.owner("one"), .25)
        self.adapter.config.update(desktop_control_enabled=True, desktop_socket=self.socket)
        self.adapter.discovery_signatures["one"] = (1, 1)
        with mock.patch("desktop.IS_WINDOWS", False), mock.patch("compatibility.desktop_compatibility", return_value={"supported": True}):
            # The transport remains platform-native on Windows CI; only the
            # adapter's formerly Mac-skipped reconnection branch is exercised.
            if os.name == 'nt':
                replacement = mock.Mock()
                replacement.disconnected = False
                replacement.start = mock.AsyncMock()
                replacement.close = mock.AsyncMock()
                with mock.patch("desktop.DesktopIPC", return_value=replacement):
                    self.assertTrue(await self.adapter.refresh_control())
            else:
                self.assertTrue(await self.adapter.refresh_control())
                self.assertEqual((await self.adapter.ipc.snapshot("one"))["thread"]["status"]["type"], "active")
        self.assertEqual(self.adapter.discovery_signatures, {})
        self.assertIsNone(self.adapter.control_error)


class FrameLimitTests(unittest.IsolatedAsyncioTestCase):
    async def test_oversized_header_is_rejected_without_allocating_its_body(self):
        ipc = DesktopIPC()
        ipc.reader = asyncio.StreamReader()
        ipc.reader.feed_data(struct.pack("<I", MAX_DESKTOP_FRAME_BYTES + 1))
        ipc.writer = mock.Mock()
        ipc.owners['old'] = 'owner'
        ipc.states['old'] = {'thread': {'status': {'type': 'active'}}}
        await asyncio.wait_for(ipc._read(), .25)
        self.assertTrue(ipc.disconnected)
        self.assertIn('exceeds supported limit', ipc.last_error)
        self.assertEqual(ipc.owners, {})
        self.assertEqual(ipc.states, {})
        ipc.writer.close.assert_called_once()
        with self.assertRaises(DesktopError):
            await asyncio.wait_for(ipc.owner('old'), .25)


if __name__ == "__main__":
    unittest.main()
