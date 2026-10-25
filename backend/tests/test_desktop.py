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
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from desktop import DesktopAdapter, DesktopIPC, DesktopError, normalize_state
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


@unittest.skipIf(os.name == "nt", "Unix socket regressions; Windows named-pipe transport is checked separately")
class NativeProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.compatibility_patch = mock.patch("compatibility.require_supported", return_value={"supported": True})
        self.compatibility_patch.start()
        self.addCleanup(self.compatibility_patch.stop)
        self.temp = tempfile.TemporaryDirectory(prefix="ug-ipc-", dir="/tmp")
        self.socket = str(Path(self.temp.name) / "app.sock")
        self.state, self.requests = state(), []
        self.snapshot_burst = None
        self.server = await asyncio.start_unix_server(self.handle, path=self.socket)
        os.chmod(self.socket, 0o600)
        self.adapter = DesktopAdapter(Quota(), {"desktop_app_build": "20770"})
        self.adapter.ipc = DesktopIPC(self.socket, timeout=2)
        # Avoid depending on the host app build in protocol fixture tests.
        await self.adapter.ipc.start()
        self.adapter.available = ["one"]
        self.store = Store(Path(self.temp.name) / "state")
        self.controller = Controller(self.adapter, self.store, CONFIG, "scope-one", clock=lambda: NOW)

    async def asyncTearDown(self):
        await self.adapter.close()
        self.server.close()
        await self.server.wait_closed()
        self.store.close()
        self.temp.cleanup()

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


if __name__ == "__main__":
    unittest.main()
