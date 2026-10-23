import copy
import json
import tempfile
import unittest
import uuid
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from catalog import entry
from guardian import Controller, Store, requests
from immediate import ImmediateRunner, enqueue_dispatch, latest_dispatches
from plans import set_plan, get_plan
from test_guardian import CONFIG, NOW, FakeRpc, sample, payload


class ImmediateTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(self.temp.name)
        self.rpc = FakeRpc()
        self.clock = NOW
        self.config = copy.deepcopy(CONFIG)
        self.controller = Controller(self.rpc, self.store, self.config, "scope", clock=lambda: self.clock)
        self.runner = ImmediateRunner(self.controller)
        self.chat = entry("one", "One")
        self.chat["execution_stage"] = {"turn_id": "original-one"}
        self.store.put("chat_catalog", {"scope": "scope", "items": [self.chat]})
        self.rpc.views["one"]["thread"]["status"] = {"type": "idle"}
        self.rpc.views["one"]["turns"][0].update(status="completed", started_at_ms=(NOW - 100) * 1000)
        self.sample = sample(remaining=70)
        self.sample["scope"] = "scope"

    async def asyncTearDown(self):
        self.store.close()
        self.temp.cleanup()

    def enqueue(self, prompt="只回复：即时执行验证成功", request_id=None):
        return enqueue_dispatch(self.store, self.chat, prompt, request_id or str(uuid.uuid4()),
            0, self.sample, self.config, NOW)

    def receipt(self):
        return latest_dispatches(self.store)[self.chat["key"]]

    async def test_manual_click_sends_same_window_once_even_with_auto_paused(self):
        self.store.put("supervisor_paused", True)
        request_id = self.enqueue()
        await self.runner.tick(self.sample)
        self.assertEqual(self.receipt()["state"], "sent")
        self.assertEqual(self.receipt()["turn_id"], "resumed-one")
        call = next(p for m, p in self.rpc.calls if m == "turn/start")
        self.assertIn("即时执行验证成功", call["input"][0]["text"])
        self.assertEqual(call["clientUserMessageId"], request_id)
        await self.runner.tick(self.sample)
        self.assertEqual(self.rpc.count("turn/start"), 1)
        self.assertEqual(self.rpc.count("turn/interrupt"), 0)

    async def test_duplicate_submission_is_idempotent_and_different_pending_rejected(self):
        request_id = self.enqueue()
        self.assertEqual(self.enqueue(request_id=request_id), request_id)
        with self.assertRaises(ValueError):
            self.enqueue()
        with self.assertRaises(ValueError):
            self.enqueue(prompt="different", request_id=request_id)
        await requests(self.controller)
        self.assertEqual(self.receipt()["state"], "pending")

    async def test_active_turn_and_approval_are_never_interrupted(self):
        self.enqueue()
        self.rpc.views["one"]["thread"]["status"] = {"type": "active", "activeFlags": ["waitingOnUserInput"]}
        await self.runner.tick(self.sample)
        self.assertEqual(self.receipt()["state"], "failed")
        self.assertEqual(self.rpc.count("turn/start"), 0)
        self.assertEqual(self.rpc.count("turn/interrupt"), 0)

    async def test_low_quota_on_second_read_fails_instead_of_waiting_for_future_reset(self):
        self.enqueue()
        self.rpc.quota = payload(remaining=8)
        await self.runner.tick(self.sample)
        self.assertEqual(self.receipt()["state"], "failed")
        self.assertEqual(self.rpc.count("turn/start"), 0)

    async def test_new_user_turn_and_expired_requests_are_rejected(self):
        self.enqueue()
        self.rpc.views["one"]["turns"][0]["id"] = "new-user-turn"
        await self.runner.tick(self.sample)
        self.assertEqual(self.receipt()["state"], "failed")
        self.enqueue()
        self.clock += 91
        await self.runner.tick(self.sample)
        self.assertEqual(self.receipt()["state"], "failed")
        self.assertEqual(self.rpc.count("turn/start"), 0)

    async def test_identity_change_during_check_does_not_send(self):
        self.enqueue()
        async def other_account():
            return "other-account"
        self.controller.identity_check = other_account
        await self.runner.tick(self.sample)
        self.assertEqual(self.receipt()["state"], "failed")
        self.assertEqual(self.rpc.count("turn/start"), 0)

    async def test_ambiguous_delivery_is_never_retried(self):
        self.enqueue()
        self.rpc.fail_start = True
        await self.runner.tick(self.sample)
        await self.runner.tick(self.sample)
        self.assertEqual(self.receipt()["state"], "unknown")
        self.assertEqual(self.rpc.count("turn/start"), 1)

    async def test_restart_reconciles_matching_message_without_sending(self):
        request_id = self.enqueue()
        with self.store.db:
            self.store.db.execute("UPDATE requests SET state='sending' WHERE id=?", (request_id,))
        self.rpc.views["one"]["thread"]["latest_message_id"] = request_id
        self.rpc.views["one"]["turns"][0]["status"] = "completed"
        await self.runner.tick(self.sample)
        self.assertEqual(self.receipt()["state"], "sent")
        self.assertEqual(self.rpc.count("turn/start"), 0)

    async def test_independent_future_plan_is_preserved(self):
        set_plan(self.store, self.chat, True, "下期整理交付清单", 0, self.sample, NOW)
        self.enqueue()
        await self.runner.tick(self.sample)
        future = get_plan(self.store, self.chat["key"])
        self.assertEqual(future["state"], "armed")
        self.assertEqual(future["prompt"], "下期整理交付清单")
        self.assertEqual(future["armed_window_reset"], self.sample["windows"]["primary"]["reset"])
        self.assertEqual(future["anchor_turn_id"], "resumed-one")

    async def test_cloud_low_quota_and_stop_rejected_before_enqueue(self):
        cloud = entry("cloud", "Cloud", "chatgpt", "chatgpt")
        with self.assertRaises(ValueError):
            enqueue_dispatch(self.store, cloud, "test", str(uuid.uuid4()), 0, self.sample, self.config, NOW)
        self.sample["windows"]["primary"]["remaining"] = 8
        with self.assertRaises(ValueError):
            self.enqueue()
        self.sample["windows"]["primary"]["remaining"] = 70
        self.store.put("stop_requested", True)
        with self.assertRaises(ValueError):
            self.enqueue()
