import asyncio
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from guardian import (Controller, Store, classify, load_config, parse_bucket, recovered)
from rpc import Rpc

CONFIG = load_config(Path(__file__).resolve().parents[1] / "config.example.json")
CONFIG["recovery_confirm_seconds"] = 0  # Delay behavior has separate clock-controlled tests.
NOW = 2_000_000_000


def payload(remaining=9, reset=NOW + 300, weekly=65, weekly_reset=NOW + 6000):
    return {"ordinaryUsageAllowed": True, "rateLimitsByLimitId": {"codex": {"primary": {
        "usedPercent": 100 - remaining, "windowDurationMins": 300, "resetsAt": reset},
        "secondary": {"usedPercent": 100 - weekly, "windowDurationMins": 10080,
                      "resetsAt": weekly_reset}, "rateLimitReachedType": None}}}


def sample(**kwargs):
    return parse_bucket(payload(**kwargs), "codex", NOW)


class PolicyTests(unittest.TestCase):
    def test_threshold_crossing_does_not_require_exact_ten(self):
        self.assertEqual(classify(sample(remaining=21), CONFIG), "normal")
        self.assertEqual(classify(sample(remaining=20), CONFIG), "warning")
        self.assertEqual(classify(sample(remaining=10), CONFIG), "low")
        self.assertEqual(classify(sample(remaining=7), CONFIG), "low")

    def test_secondary_exhaustion_blocks_five_hour_recovery(self):
        self.assertEqual(classify(sample(remaining=98, weekly=0), CONFIG), "blocked")
        self.assertFalse(recovered(sample(remaining=98, reset=NOW + 18000, weekly=0), sample(), CONFIG, NOW))

    def test_clock_alone_does_not_resume(self):
        old = sample()
        self.assertFalse(recovered(sample(), old, CONFIG, NOW))
        self.assertFalse(recovered(sample(remaining=95, reset=NOW + 18000), old, CONFIG, NOW + 100))

    def test_fresh_new_window_recovers(self):
        self.assertTrue(recovered(sample(remaining=95, reset=NOW + 18000), sample(), CONFIG, NOW))

    def test_weekly_block_accepts_recovered_balance_or_new_window(self):
        old = sample(remaining=95, weekly=0)
        self.assertTrue(recovered(sample(remaining=95, weekly=65), old, CONFIG, NOW))
        self.assertTrue(recovered(sample(remaining=95, weekly=65, weekly_reset=NOW + 10000), old, CONFIG, NOW))

    def test_missing_values_are_unknown_not_zero(self):
        for value in (None, True, "10", -1, 101, float("nan")):
            raw = payload()
            raw["rateLimitsByLimitId"]["codex"]["primary"]["usedPercent"] = value
            with self.assertRaises(ValueError):
                parse_bucket(raw, "codex", NOW)

    def test_multi_bucket_precedes_legacy(self):
        raw = payload(remaining=5)
        raw["rateLimits"] = {"limitId": "codex", "primary": {"usedPercent": 1}}
        self.assertEqual(parse_bucket(raw, "codex", NOW)["windows"]["primary"]["remaining"], 5)
        with self.assertRaises(ValueError):
            parse_bucket(raw, "unavailable_bucket", NOW)

    def test_invalid_duration_or_expired_read_is_rejected(self):
        raw = payload()
        raw["rateLimitsByLimitId"]["codex"]["primary"]["windowDurationMins"] = 0
        with self.assertRaises(ValueError):
            parse_bucket(raw, "codex", NOW)
        with self.assertRaises(ValueError):
            parse_bucket(payload(reset=NOW - 1000), "codex", NOW)

    def test_missing_secondary_after_pause_does_not_resume(self):
        current = sample(remaining=95, reset=NOW + 18000)
        current["windows"].pop("secondary")
        self.assertFalse(recovered(current, sample(), CONFIG, NOW))


class FakeRpc:
    def __init__(self):
        self.calls = []
        self.loaded = ["one", "two"]
        self.fail_start = False
        self.on_quota_read = None
        self.quota = payload(remaining=98, reset=NOW + 18000)
        self.views = {key: {"thread": {"id": key, "name": key, "cwd": "/tmp", "updatedAt": 1,
                      "status": {"type": "active", "activeFlags": []}},
                      "turns": [{"id": "original-" + key, "status": "inProgress", "items": []}],
                      "goal": None} for key in self.loaded}

    async def call(self, method, params=None):
        params = params or {}
        self.calls.append((method, copy.deepcopy(params)))
        key = params.get("threadId")
        if method == "thread/loaded/list":
            return {"data": self.loaded}
        if method == "thread/read":
            return {"thread": copy.deepcopy(self.views[key]["thread"])}
        if method == "thread/turns/list":
            return {"data": copy.deepcopy(self.views[key]["turns"])}
        if method == "thread/goal/get":
            return {"goal": self.views[key]["goal"]}
        if method == "turn/interrupt":
            self.views[key]["turns"][0]["status"] = "interrupted"
            self.views[key]["thread"]["status"] = {"type": "idle"}
            return {}
        if method == "account/rateLimits/read":
            if self.on_quota_read:
                self.on_quota_read()
            return copy.deepcopy(self.quota)
        if method == "turn/start":
            if self.fail_start:
                raise asyncio.TimeoutError()
            turn = {"id": "resumed-" + key, "status": "inProgress", "items": []}
            self.views[key]["turns"].insert(0, turn)
            self.views[key]["thread"]["status"] = {"type": "active", "activeFlags": []}
            return {"turn": turn}
        raise AssertionError(method)

    def count(self, method):
        return sum(m == method for m, p in self.calls)


class LifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(self.temp.name)
        self.rpc = FakeRpc()
        self.controller = Controller(self.rpc, self.store, CONFIG, "scope-one", clock=lambda: NOW)
        await self.controller.adopt("one")

    async def asyncTearDown(self):
        self.store.close()
        self.temp.cleanup()

    async def test_interrupt_is_confirmed_then_resume_once(self):
        await self.controller.tick(sample())
        self.assertEqual(self.store.get_task("one")["state"], "paused")
        await self.controller.tick(sample(remaining=98, reset=NOW + 18000))
        await self.controller.tick(sample(remaining=98, reset=NOW + 18000))
        self.assertEqual(self.rpc.count("turn/interrupt"), 1)
        self.assertEqual(self.rpc.count("turn/start"), 1)

    async def test_user_message_after_pause_cancels_auto_resume(self):
        await self.controller.tick(sample())
        self.rpc.views["one"]["turns"].insert(0, {"id": "manual", "status": "completed", "items": []})
        await self.controller.tick(sample(remaining=98, reset=NOW + 18000))
        self.assertEqual(self.rpc.count("turn/start"), 0)
        self.assertEqual(self.store.get_task("one")["state"], "needs_review")

    async def test_restart_with_ambiguous_intent_never_repeats_action(self):
        task = self.store.get_task("one")
        task["state"] = "resume_intent"
        self.store.save_task(task)
        await self.controller.tick(sample(remaining=98, reset=NOW + 18000))
        self.assertEqual(self.rpc.count("turn/start"), 0)
        self.assertEqual(self.store.get_task("one")["state"], "needs_review")

    async def test_ambiguous_start_not_retried(self):
        await self.controller.tick(sample())
        self.rpc.fail_start = True
        await self.controller.tick(sample(remaining=98, reset=NOW + 18000))
        await self.controller.tick(sample(remaining=98, reset=NOW + 18000))
        self.assertEqual(self.rpc.count("turn/start"), 1)
        self.assertEqual(self.store.get_task("one")["state"], "needs_review")

    async def test_only_one_task_resumes_concurrently(self):
        await self.controller.adopt("two")
        await self.controller.tick(sample())
        for _ in range(3):
            await self.controller.tick(sample(remaining=98, reset=NOW + 18000))
        self.assertEqual(self.rpc.count("turn/start"), 1)
        self.rpc.views["one"]["turns"][0]["status"] = "completed"
        self.rpc.views["one"]["thread"]["status"] = {"type": "idle"}
        await self.controller.tick(sample(remaining=98, reset=NOW + 18000))
        self.assertEqual(self.rpc.count("turn/start"), 2)

    async def test_manual_pause_and_disable_win(self):
        self.store.put("supervisor_paused", True)
        await self.controller.tick(sample())
        self.assertEqual(self.rpc.count("turn/interrupt"), 0)
        self.store.put("supervisor_paused", False)
        await self.controller.tick(sample())
        task = self.store.get_task("one")
        task["state"] = "disabled"
        self.store.save_task(task)
        await self.controller.tick(sample(remaining=98, reset=NOW + 18000))
        self.assertEqual(self.rpc.count("turn/start"), 0)

    async def test_revocation_during_quota_read_wins(self):
        await self.controller.tick(sample())
        def disable():
            task = self.store.get_task("one")
            task["state"] = "disabled"
            self.store.save_task(task)
        self.rpc.on_quota_read = disable
        await self.controller.tick(sample(remaining=98, reset=NOW + 18000))
        self.assertEqual(self.rpc.count("turn/start"), 0)
        self.assertEqual(self.store.get_task("one")["state"], "disabled")

    async def test_new_user_turn_during_quota_read_wins(self):
        await self.controller.tick(sample())
        def user_action():
            self.rpc.views["one"]["turns"].insert(0, {"id": "new-user-turn", "status": "completed", "items": []})
        self.rpc.on_quota_read = user_action
        await self.controller.tick(sample(remaining=98, reset=NOW + 18000))
        self.assertEqual(self.rpc.count("turn/start"), 0)

    async def test_account_switch_immediately_before_resume_wins(self):
        await self.controller.tick(sample())
        async def switched():
            return "changed-account"
        self.controller.identity_check = switched
        await self.controller.tick(sample(remaining=98, reset=NOW + 18000))
        self.assertEqual(self.rpc.count("turn/start"), 0)

    async def test_account_change_does_not_resume(self):
        await self.controller.tick(sample())
        self.controller.identity = "another-account"
        await self.controller.tick(sample(remaining=98, reset=NOW + 18000))
        self.assertEqual(self.rpc.count("turn/start"), 0)

    async def test_unloaded_session_is_not_adopted(self):
        with self.assertRaises(ValueError):
            await self.controller.adopt("desktop-unreachable")

    async def test_waiting_for_approval_is_not_interrupted(self):
        self.rpc.views["one"]["thread"]["status"]["activeFlags"] = ["waitingOnApproval"]
        await self.controller.tick(sample())
        self.assertEqual(self.rpc.count("turn/interrupt"), 0)

    async def test_new_goal_is_not_silently_controlled(self):
        self.rpc.views["one"]["goal"] = {"status": "active"}
        await self.controller.tick(sample())
        self.assertEqual(self.rpc.count("turn/interrupt"), 0)

    async def test_quota_falls_again_before_dispatch(self):
        await self.controller.tick(sample())
        self.rpc.quota = payload(remaining=5, reset=NOW + 18000)
        await self.controller.tick(sample(remaining=98, reset=NOW + 18000))
        self.assertEqual(self.rpc.count("turn/start"), 0)


class PersistenceTests(unittest.TestCase):
    def test_notice_deduplication_survives_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(directory)
            store.notice("window:low", "low", "10%")
            store.close()
            store = Store(directory)
            store.notice("window:low", "low", "9%")
            self.assertEqual(store.db.execute("SELECT count(*) FROM notices").fetchone()[0], 1)
            store.close()


class TransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_bidirectional_rpc_without_auto_approvals(self):
        rpc = Rpc([sys.executable, str(Path(__file__).with_name("fake_server.py"))], timeout=3)
        try:
            await rpc.start()
            quota = await rpc.call("account/rateLimits/read")
            self.assertEqual(parse_bucket(quota, "codex", __import__("time").time())["windows"]["primary"]["remaining"], 9)
            self.assertEqual((await rpc.call("test/approval"))["approved"], False)
        finally:
            await rpc.close()


if __name__ == "__main__":
    unittest.main()
