"""Behavioral acceptance cases for the Quota Monitor control port."""
import copy
import tempfile
import unittest
from control_policy import decision
from guardian import Controller, Store
from test_guardian import CONFIG, NOW, FakeRpc, sample, payload


class PortTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(self.temp.name)
        self.rpc = FakeRpc()
        self.clock = NOW
        self.cfg = dict(CONFIG, recovery_confirm_seconds=5, goal_control_enabled=True, require_service_allowed=True)
        self.c = Controller(self.rpc, self.store, self.cfg, "scope", clock=lambda: self.clock)
        await self.c.adopt("one")

    async def asyncTearDown(self):
        self.store.close()
        self.temp.cleanup()

    async def test_five_second_two_stage_confirmation(self):
        await self.c.tick(sample())
        healthy = sample(remaining=98, reset=NOW + 18000)
        await self.c.tick(healthy)
        self.clock += 4
        await self.c.tick(healthy)
        self.assertEqual(self.rpc.count("turn/start"), 0)
        self.clock += 1
        await self.c.tick(healthy)
        self.assertEqual(self.rpc.count("turn/start"), 1)

    async def test_recovery_confirmation_resets_when_quota_falls(self):
        await self.c.tick(sample())
        await self.c.tick(sample(remaining=98, reset=NOW + 18000))
        self.clock += 4
        await self.c.tick(sample())
        self.clock += 1
        await self.c.tick(sample(remaining=98, reset=NOW + 18000))
        self.assertEqual(self.rpc.count("turn/start"), 0)

    async def test_already_recovered_usage_error_is_registered_then_resumed(self):
        view = self.rpc.views["one"]
        view["turns"][0].update(status="failed", quota_error="usageLimitExceeded")
        view["thread"]["status"] = {"type": "idle"}
        healthy = sample(remaining=98, reset=NOW + 18000)
        await self.c.tick(healthy)
        self.assertEqual(self.store.get_task("one")["pause_source"], "quota")
        await self.c.tick(healthy)
        self.clock += 5
        await self.c.tick(healthy)
        self.assertEqual(self.rpc.count("turn/start"), 1)

    async def test_other_failures_and_completed_turns_never_restart(self):
        view = self.rpc.views["one"]
        view["thread"]["status"] = {"type": "idle"}
        for status in ("failed", "completed"):
            view["turns"][0]["status"] = status
            await self.c.tick(sample(remaining=98))
        self.assertEqual(self.rpc.count("turn/start"), 0)

    async def test_metadata_change_does_not_cancel_checkpoint(self):
        await self.c.tick(sample())
        self.rpc.views["one"]["thread"].update(name="renamed", updatedAt=999)
        healthy = sample(remaining=98, reset=NOW + 18000)
        await self.c.tick(healthy)
        self.clock += 5
        await self.c.tick(healthy)
        self.assertEqual(self.rpc.count("turn/start"), 1)

    async def test_hold_cannot_be_overwritten_by_inflight_callback(self):
        stale = self.store.get_task("one")
        self.store.permission("one", False)
        stale["state"] = "resume_intent"
        self.assertFalse(self.store.save_task(stale))
        await self.c.tick(sample())
        self.assertEqual(self.rpc.count("turn/interrupt"), 0)
        self.assertTrue(self.store.get_task("one")["manual_hold"])

    async def test_unreachable_task_does_not_block_other_task(self):
        await self.c.adopt("two")
        del self.rpc.views["one"]
        await self.c.tick(sample())
        self.assertEqual(self.store.get_task("two")["state"], "paused")
        self.assertIn("one", self.store.get("task_errors"))

    async def test_changed_goal_and_budget_limit_never_reactivate(self):
        view = copy.deepcopy(self.rpc.views["one"])
        goal = {"objective": "a", "createdAt": 1, "tokenBudget": 100, "updatedAt": 2, "status": "paused"}
        view.update(goal=goal)
        view["thread"]["status"] = {"type": "idle"}
        view["turns"][0]["status"] = "interrupted"
        task = dict(self.store.get_task("one"), state="paused", turn_id="original-one", paused_for_goal=True,
                    paused_goal=copy.deepcopy(goal), paused_goal_updated_at=2, pause_source="monitor")
        self.assertEqual(decision(task, view, sample(remaining=98), self.cfg), "recovery_ready")
        for field, value in (("objective", "changed"), ("status", "budgetLimited"), ("updatedAt", 3)):
            changed = copy.deepcopy(view); changed["goal"][field] = value
            self.assertEqual(decision(task, changed, sample(remaining=98), self.cfg), "user_changed")

    async def test_goal_pause_activate_then_resume_original_thread(self):
        goal = {"objective": "finish", "createdAt": 1, "tokenBudget": 100,
                "updatedAt": 1, "status": "active"}
        self.rpc.views["one"]["goal"] = goal
        original_call = self.rpc.call
        async def goal_rpc(method, params=None):
            if method == "turn/interrupt" and params.get("goal"):
                goal.update(status="paused", updatedAt=2)
            if method == "thread/goal/set":
                self.rpc.calls.append((method, copy.deepcopy(params)))
                goal.update(status=params["status"], updatedAt=3)
                return {"goal": copy.deepcopy(goal)}
            return await original_call(method, params)
        self.rpc.call = goal_rpc
        await self.c.tick(sample())
        paused = self.store.get_task("one")
        self.assertEqual(paused["state"], "paused")
        self.assertTrue(paused["paused_for_goal"])
        healthy = sample(remaining=98, reset=NOW + 18000)
        await self.c.tick(healthy)
        self.clock += 5
        await self.c.tick(healthy)
        self.assertEqual(self.rpc.count("thread/goal/set"), 1)
        self.assertEqual(self.rpc.count("turn/start"), 1)
        self.assertEqual(self.store.get_task("one")["state"], "running")

    async def test_unknown_service_permission_prevents_resume(self):
        await self.c.tick(sample())
        unknown = sample(remaining=98, reset=NOW + 18000)
        unknown["service_allowed"] = False
        for _ in range(3):
            self.clock += 5
            await self.c.tick(unknown)
        self.assertEqual(self.rpc.count("turn/start"), 0)

    async def test_restart_confirms_previous_delivery_without_resending(self):
        task = self.store.get_task("one")
        task.update(state="resume_intent", action_id="unique-delivery-marker")
        self.store.save_task(task)
        self.rpc.views["one"]["turns"][0].update(id="delivered-turn", client_message_id="unique-delivery-marker")
        await self.c.tick(sample(remaining=98))
        self.assertEqual(self.store.get_task("one")["state"], "running")
        self.assertEqual(self.rpc.count("turn/start"), 0)

    async def test_restart_confirms_previous_interruption_without_reinterrupting(self):
        await self.c.tick(sample())
        task = self.store.get_task("one"); task["state"] = "pause_intent"; self.store.save_task(task)
        before = self.rpc.count("turn/interrupt")
        await self.c.tick(sample())
        self.assertEqual(self.store.get_task("one")["state"], "paused")
        self.assertEqual(self.rpc.count("turn/interrupt"), before)
