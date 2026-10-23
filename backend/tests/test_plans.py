import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from catalog import entry
from guardian import Controller, Store
from plans import PlanRunner, get_plan, has_plan, set_plan, save_plan
from test_guardian import CONFIG, NOW, FakeRpc, sample


class PlanTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(self.temp.name)
        self.rpc = FakeRpc()
        self.clock = NOW
        self.config = copy.deepcopy(CONFIG)
        self.controller = Controller(self.rpc, self.store, self.config, "scope", clock=lambda: self.clock)
        self.runner = PlanRunner(self.controller)
        self.chat = entry("one", "One")
        self.key = self.chat["key"]
        self.rpc.views["one"]["thread"]["status"] = {"type": "idle"}
        self.rpc.views["one"]["turns"][0].update(status="completed", started_at_ms=(NOW - 100) * 1000)
        self.old = sample(remaining=70)
        self.old["scope"] = "scope"
        self.new = sample(remaining=98, reset=NOW + 18000)
        self.new["scope"] = "scope"

    async def asyncTearDown(self):
        self.store.close()
        self.temp.cleanup()

    def arm(self, prompt="继续任务"):
        return set_plan(self.store, self.chat, True, prompt, 0, self.old, NOW)

    def sends(self):
        return [p for method,p in self.rpc.calls if method == "turn/start"]

    async def test_completed_idle_chat_runs_custom_prompt_once_after_next_window(self):
        self.arm("请整理项目交付清单")
        await self.runner.tick(self.new)
        self.assertEqual(get_plan(self.store, self.key)["state"], "sent")
        self.assertIn("请整理项目交付清单", self.sends()[0]["input"][0]["text"])
        await self.runner.tick(self.new)
        self.assertEqual(len(self.sends()), 1)

    async def test_available_quota_in_same_window_does_not_start_early(self):
        self.arm()
        await self.runner.tick(self.old)
        self.assertEqual(self.sends(), [])
        self.assertEqual(get_plan(self.store, self.key)["state"], "armed")

    async def test_waits_for_original_active_turn_to_finish(self):
        self.arm()
        self.rpc.views["one"]["thread"]["status"] = {"type": "active", "activeFlags": []}
        self.rpc.views["one"]["turns"][0]["status"] = "inProgress"
        await self.runner.tick(self.new)
        self.assertEqual(self.sends(), [])
        self.rpc.views["one"]["thread"]["status"] = {"type": "idle"}
        self.rpc.views["one"]["turns"][0]["status"] = "completed"
        await self.runner.tick(self.new)
        self.assertEqual(len(self.sends()), 1)

    async def test_new_user_turn_after_arming_requires_review(self):
        self.arm()
        self.rpc.views["one"]["turns"][0].update(id="new-user-turn", started_at_ms=(NOW + 1) * 1000)
        await self.runner.tick(self.new)
        self.assertEqual(self.sends(), [])
        self.assertEqual(get_plan(self.store, self.key)["state"], "needs_review")
        self.assertTrue(has_plan(self.store, "one"))

    async def test_manual_hold_is_independent_but_global_pause_blocks_plan(self):
        self.store.save_task({"id":"one", "name":"one", "scope":"scope", "state":"disabled", "auto_resume":False, "priority":100})
        self.arm()
        self.store.put("supervisor_paused", True)
        await self.runner.tick(self.new)
        self.assertEqual(self.sends(), [])
        self.store.put("supervisor_paused", False)
        await self.runner.tick(self.new)
        self.assertEqual(len(self.sends()), 1)
        self.assertEqual(self.store.get_task("one")["state"], "disabled")

    async def test_cancellation_during_fresh_quota_read_wins(self):
        self.arm()
        self.rpc.on_quota_read = lambda: set_plan(self.store,self.chat,False,"继续任务",1,{},NOW)
        await self.runner.tick(self.new)
        self.assertEqual(self.sends(), [])
        self.assertEqual(get_plan(self.store, self.key)["state"], "cancelled")

    async def test_account_change_never_sends(self):
        self.arm()
        self.controller.identity = "other"
        await self.runner.tick(self.new)
        self.assertEqual(self.sends(), [])
        self.assertEqual(get_plan(self.store, self.key)["state"], "needs_review")

    async def test_missing_service_permission_or_weekly_quota_waits(self):
        self.arm()
        for field in ("permission", "weekly"):
            value=copy.deepcopy(self.new)
            if field=="permission":value["service_allowed"]=False
            else:value["windows"]["secondary"]["remaining"]=0
            await self.runner.tick(value)
        self.assertEqual(self.sends(), [])

    async def test_two_stage_confirmation_and_fresh_second_read(self):
        self.config["recovery_confirm_seconds"]=5
        self.arm()
        await self.runner.tick(self.new)
        self.assertEqual(self.sends(), [])
        self.clock+=6
        await self.runner.tick(self.new)
        self.assertEqual(len(self.sends()), 1)

    async def test_ambiguous_send_is_never_retried(self):
        self.arm()
        self.rpc.fail_start=True
        await self.runner.tick(self.new)
        await self.runner.tick(self.new)
        self.assertEqual(len(self.sends()), 1)
        self.assertEqual(get_plan(self.store, self.key)["state"], "needs_review")

    async def test_manual_plan_prevents_default_automatic_resume(self):
        await self.controller.adopt("one")
        self.arm()
        task=self.store.get_task("one")
        task.update(state="paused")
        self.store.save_task(task)
        await self.controller.resume(task)
        self.assertEqual(self.sends(), [])
        await self.runner.tick(self.new)
        self.assertEqual(len(self.sends()),1)
        self.assertEqual(self.store.get_task("one")["state"],"running")

    async def test_edit_keeps_original_target_window_and_cas_revision(self):
        self.arm()
        plan=set_plan(self.store,self.chat,True,"新指令",1,self.new,NOW+100)
        self.assertEqual(plan["armed_window_reset"],self.old["windows"]["primary"]["reset"])
        with self.assertRaises(ValueError):set_plan(self.store,self.chat,False,"继续任务",1,{},NOW)

    async def test_readonly_chatgpt_cannot_be_armed(self):
        with self.assertRaises(ValueError):set_plan(self.store,entry("x","ChatGPT","chatgpt","chatgpt"),True,"继续任务",0,self.old,NOW)

    async def test_archived_chat_is_not_reopened(self):
        self.arm()
        self.store.put("chat_catalog",{"items":[],"scope":"scope"})
        await self.runner.tick(self.new)
        self.assertEqual(self.sends(),[])
        self.assertEqual(get_plan(self.store,self.key)["state"],"needs_review")

    async def test_waiting_for_approval_is_not_bypassed(self):
        self.arm()
        self.rpc.views["one"]["thread"]["status"]={"type":"active","activeFlags":["waitingOnApproval"]}
        await self.runner.tick(self.new)
        self.assertEqual(self.sends(),[])

    async def test_restart_confirms_marker_without_a_second_send(self):
        plan=self.arm()
        plan.update(state="sending",action_id="unique-marker")
        save_plan(self.store,plan,1)
        self.rpc.views["one"]["turns"][0].update(client_message_id="unique-marker")
        await self.runner.tick(self.new)
        self.assertEqual(self.sends(),[])
        self.assertEqual(get_plan(self.store,self.key)["state"],"sent")

    async def test_unknown_restart_send_is_not_reissued(self):
        plan=self.arm()
        plan.update(state="sending",action_id="unknown-marker")
        save_plan(self.store,plan,1)
        await self.runner.tick(self.new)
        self.assertEqual(self.sends(),[])
        self.assertEqual(get_plan(self.store,self.key)["state"],"needs_review")

    async def test_fresh_quota_drop_and_stale_sample_block_dispatch(self):
        self.arm()
        self.rpc.quota["rateLimitsByLimitId"]["codex"]["primary"]["usedPercent"]=99
        await self.runner.tick(self.new)
        stale=copy.deepcopy(self.new);stale["observed_at"]-=1000
        await self.runner.tick(stale)
        self.assertEqual(self.sends(),[])

    async def test_catalog_outage_waits_without_opening_a_chat(self):
        self.arm()
        self.store.put("chat_catalog",{"items":[],"local_error":"OperationalError"})
        await self.runner.tick(self.new)
        self.assertEqual(self.sends(),[])
        self.assertEqual(get_plan(self.store,self.key)["state"],"armed")

    async def test_stale_native_view_cannot_override_persisted_newer_turn(self):
        self.arm()
        async def newer(*args):return False
        self.rpc.verify_latest=newer
        await self.runner.tick(self.new)
        self.assertEqual(self.sends(),[])
        self.assertEqual(get_plan(self.store,self.key)["state"],"needs_review")
