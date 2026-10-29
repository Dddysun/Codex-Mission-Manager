"""Small stdio client for the installed Codex App Server protocol; no SDK/key needed."""
import asyncio
import contextlib
import json
import os
import subprocess
from mission_version import VERSION


class RpcError(RuntimeError):
    def __init__(self, method, code):
        self.method, self.code = method, code
        super().__init__("%s failed (code %s)" % (method, code))


class Rpc:
    def __init__(self, command, timeout=25):
        self.command, self.timeout = command, timeout
        self.pending, self.serial = {}, 0
        self.process = self.reader = None
        self.changed = asyncio.Event()
        self.turn_events = {}

    async def start(self):
        self.process = await asyncio.create_subprocess_exec(
            *self.command, stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
            limit=16 * 1024 * 1024,
            **({'creationflags':subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}))
        self.reader = asyncio.create_task(self._read())
        result = await self.call("initialize", {"clientInfo": {
            "name": "usage_guardian", "title": "TokenMax", "version": VERSION}})
        await self.send({"method": "initialized"})
        return result

    async def send(self, message):
        self.process.stdin.write((json.dumps(message, ensure_ascii=False) + "\n").encode())
        await self.process.stdin.drain()

    async def _read(self):
        try:
            while True:
                line = await self.process.stdout.readline()
                if not line:
                    raise ConnectionError("Codex transport closed")
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                if "method" in obj and "id" in obj:
                    # The supervisor never grants tool permissions or supplies user answers.
                    await self.send({"id": obj["id"], "error": {
                        "code": -32601, "message": "Use the original client for approvals/input"}})
                elif "id" in obj:
                    future = self.pending.get(obj["id"])
                    if future is not None and not future.done():
                        future.set_result(obj)
                elif obj.get("method") in ("account/rateLimits/updated", "turn/completed",
                                           "turn/started", "thread/status/changed"):
                    params = obj.get("params") or {}
                    if obj["method"] in ("turn/started", "turn/completed") and params.get("turn"):
                        self.turn_events[(params.get("threadId"), params["turn"]["id"])] = params["turn"]
                        if len(self.turn_events) > 128:
                            self.turn_events.pop(next(iter(self.turn_events)))
                    self.changed.set()
        except (asyncio.CancelledError, Exception) as exc:
            for future in list(self.pending.values()):
                if not future.done():
                    future.set_exception(ConnectionError(type(exc).__name__))

    async def call(self, method, params=None):
        self.serial += 1
        request_id = self.serial
        future = asyncio.get_running_loop().create_future()
        self.pending[request_id] = future
        try:
            await self.send({"id": request_id, "method": method, "params": params or {}})
            obj = await asyncio.wait_for(future, self.timeout)
            if "error" in obj:
                raise RpcError(method, obj["error"].get("code"))
            return obj["result"]
        finally:
            self.pending.pop(request_id, None)

    async def close(self):
        if self.reader:
            self.reader.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.reader
        if self.process and self.process.returncode is None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), 3)
            except asyncio.TimeoutError:
                self.process.kill()
                await self.process.wait()
