"""Subscription-independent quota decisions against synthetic service responses."""
import copy
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from account_display import display_snapshot
from catalog import entry
from control_policy import quota_usable
from guardian import Controller, Store, classify, parse_bucket, recovered
from immediate import ImmediateRunner, enqueue_dispatch, latest_dispatches
from plans import PlanRunner, get_plan, save_plan, set_plan
from test_guardian import CONFIG, NOW, FakeRpc


MISSING = object()


def meter(minutes, remaining=70, reset=NOW + 3600):
    return {"usedPercent": 100 - remaining, "windowDurationMins": minutes, "resetsAt": reset}


def limits(primary=MISSING, secondary=MISSING, allowed=True, **bucket_fields):
    bucket = dict(bucket_fields)
    if primary is not MISSING:
        bucket["primary"] = primary
    if secondary is not MISSING:
        bucket["secondary"] = secondary
    result = {"rateLimitsByLimitId": {"codex": bucket}}
    if allowed is not MISSING:
        result["ordinaryUsageAllowed"] = allowed
    return result


def read(raw):
    result = parse_bucket(raw, "codex", NOW)
    result["scope"] = "scope"
    return result


class SubscriptionPolicyTests(unittest.TestCase):
    def test_all_plan_names_use_actual_windows_instead_of_guessed_limits(self):
        for plan in ("free", "go", "plus", "pro", "business", "enterprise", "edu", "future-plan"):
            with self.subTest(plan=plan):
                value = read(limits(meter(60, 9), None, planType=plan))
                self.assertEqual(value["windows"]["primary"]["minutes"], 60)
                self.assertEqual(classify(value, CONFIG), "low")
                self.assertFalse(quota_usable(value, CONFIG))

    def test_pro_weekly_only_is_a_valid_metered_account(self):
        value = read(limits(None, meter(10080, 6), planType="pro"))
        self.assertEqual(value["quota_state"], "metered")
        self.assertNotIn("primary", value["windows"])
        self.assertEqual(classify(value, CONFIG), "normal")
        self.assertTrue(quota_usable(value, CONFIG))

    def test_weekly_in_primary_slot_is_not_treated_as_a_short_window(self):
        value = read(limits(meter(10080, 6), None))
        self.assertEqual(classify(value, CONFIG), "normal")
        self.assertTrue(quota_usable(value, CONFIG))
        exhausted = read(limits(meter(10080, 0), None))
        self.assertEqual(classify(exhausted, CONFIG), "blocked")
        self.assertFalse(quota_usable(exhausted, CONFIG))

    def test_short_window_in_secondary_slot_keeps_low_threshold(self):
        value = read(limits(meter(10080, 65), meter(300, 8)))
        self.assertEqual(classify(value, CONFIG), "low")
        self.assertFalse(quota_usable(value, CONFIG))

    def test_custom_windows_apply_pause_warning_and_resume_thresholds(self):
        for minutes in (15, 60, 1440):
            for remaining, phase in ((9, "low"), (10, "low"), (20, "warning"), (21, "normal")):
                with self.subTest(minutes=minutes, remaining=remaining):
                    value = read(limits(meter(minutes, remaining), None))
                    self.assertEqual(classify(value, CONFIG), phase)
                    self.assertEqual(quota_usable(value, CONFIG), remaining >= CONFIG["resume_remaining"])

    def test_all_reported_nonweekly_windows_constrain_recovery(self):
        value = read(limits(meter(300, 90), meter(1440, 8)))
        self.assertEqual(classify(value, CONFIG), "low")
        self.assertFalse(quota_usable(value, CONFIG))

    def test_missing_optional_weekly_window_does_not_create_a_zero_quota(self):
        value = read(limits(meter(300, 80)))
        self.assertEqual(value["quota_state"], "metered")
        self.assertTrue(quota_usable(value, CONFIG))

    def test_explicit_windowless_permission_can_run_without_invented_percentage(self):
        value = read(limits(None, None, planType="pro"))
        self.assertEqual(value["quota_state"], "service_only")
        self.assertEqual(value["windows"], {})
        self.assertEqual(classify(value, CONFIG), "normal")
        self.assertTrue(quota_usable(value, CONFIG))

    def test_absent_window_fields_never_imply_unlimited_permission(self):
        for raw in (limits(), limits(None), limits(secondary=None)):
            with self.subTest(raw=raw):
                value = read(raw)
                self.assertEqual(value["quota_state"], "unknown")
                self.assertFalse(quota_usable(value, CONFIG))

    def test_missing_or_false_permission_never_allows_windowless_send(self):
        for allowed in (MISSING, False, None):
            with self.subTest(allowed=allowed):
                value = read(limits(None, None, allowed=allowed, planType="pro"))
                self.assertNotEqual(value["quota_state"], "service_only")
                self.assertFalse(quota_usable(value, CONFIG))

    def test_malformed_optional_service_flags_cannot_allow_windowless_send(self):
        for field, values in (("ordinaryUsageAllowed", (1, "true", [], {})),
                              ("spendControlReached", (0, [], {})),
                              ("rateLimitReachedType", (0, False, []))):
            for value in values:
                with self.subTest(field=field, value=value):
                    raw = limits(None, None)
                    if field == "ordinaryUsageAllowed":
                        raw[field] = value
                    else:
                        raw["rateLimitsByLimitId"]["codex"][field] = value
                    with self.assertRaises(ValueError):
                        read(raw)

    def test_explicit_block_overrides_service_permission(self):
        value = read(limits(None, None, rateLimitReachedType="workspaceLimit"))
        self.assertTrue(value["blocked"])
        self.assertEqual(classify(value, CONFIG), "blocked")
        self.assertFalse(quota_usable(value, CONFIG))

    def test_bad_custom_window_cannot_be_ignored_beside_valid_weekly_window(self):
        for minutes in (True, 0, -1, 1.5, float("nan"), "60"):
            with self.subTest(minutes=minutes):
                with self.assertRaises(ValueError):
                    read(limits(meter(minutes), meter(10080)))

    def test_bad_values_and_expired_reset_fail_closed(self):
        for key, values in (("usedPercent", (True, None, float("nan"), -1, 101)),
                            ("resetsAt", (True, None, float("inf"), 0, NOW - 1000))):
            for val in values:
                with self.subTest(key=key, value=val):
                    raw = meter(60)
                    raw[key] = val
                    with self.assertRaises(ValueError):
                        read(limits(raw, None))

    def test_configured_bucket_never_borrows_another_bucket_or_legacy_value(self):
        raw = limits(None, None)
        raw["rateLimitsByLimitId"] = {"another": {"primary": meter(300)}}
        raw["rateLimits"] = {"limitId": "codex", "primary": meter(300)}
        with self.assertRaises(ValueError):
            read(raw)
        with self.assertRaises(ValueError):
            read({"ordinaryUsageAllowed": True, "rateLimits": {"limitId": "another", "primary": meter(300)}})

    def test_legacy_single_bucket_still_supports_custom_duration(self):
        value = read({"ordinaryUsageAllowed": True, "rateLimits": {"limitId": "codex", "primary": meter(60)}})
        self.assertEqual(value["windows"]["primary"]["minutes"], 60)
        self.assertTrue(quota_usable(value, CONFIG))

    def test_recovery_matches_duration_when_window_slots_reverse(self):
        old = read(limits(meter(300, 9), meter(10080, 60)))
        current = read(limits(meter(10080, 60), meter(300, 95, NOW + 18000)))
        self.assertTrue(recovered(current, old, CONFIG, NOW))

    def test_weekly_only_recovery_waits_for_actual_weekly_reset(self):
        old = read(limits(None, meter(10080, 0)))
        same = read(limits(None, meter(10080, 80)))
        new = read(limits(None, meter(10080, 80, NOW + 10000)))
        self.assertFalse(recovered(same, old, CONFIG, NOW))
        self.assertTrue(recovered(new, old, CONFIG, NOW))

    def test_custom_window_recovery_waits_for_its_actual_reset(self):
        old = read(limits(meter(60, 8), None))
        self.assertFalse(recovered(read(limits(meter(60, 90), None)), old, CONFIG, NOW))
        self.assertTrue(recovered(read(limits(meter(60, 90, NOW + 7200), None)), old, CONFIG, NOW))

    def test_disappearing_old_limit_is_not_recovery(self):
        old = read(limits(meter(300, 9), meter(10080, 60)))
        for current in (read(limits(None, None)), read(limits(None, meter(10080, 90)))):
            self.assertFalse(recovered(current, old, CONFIG, NOW))

    def test_legacy_pause_sample_without_new_metadata_remains_compatible(self):
        old = read(limits(meter(300, 9), meter(10080, 60)))
        old.pop("quota_state", None)
        new = read(limits(meter(300, 95, NOW + 18000), meter(10080, 60)))
        self.assertTrue(recovered(new, old, CONFIG, NOW))

    def test_fractional_legacy_duration_cannot_match_rounded_new_limit(self):
        old = read(limits(meter(60, 8), None))
        old.pop("quota_state", None)
        old["windows"]["primary"]["minutes"] = 60.5
        new = read(limits(meter(60, 95, NOW + 7200), None))
        self.assertFalse(recovered(new, old, CONFIG, NOW))

    def test_windowless_recovery_requires_fresh_explicit_service_reenable(self):
        old = read(limits(None, None, allowed=False))
        ready = read(limits(None, None))
        unknown = read(limits(None, None, allowed=MISSING))
        self.assertFalse(recovered(unknown, old, CONFIG, NOW))
        self.assertTrue(recovered(ready, old, CONFIG, NOW))
        self.assertFalse(recovered(ready, old, CONFIG, NOW + 1000))


class SubscriptionDisplayTests(unittest.TestCase):
    def view(self, raw, plan="pro"):
        return display_snapshot({"account": {"type": "chatgpt", "email": "fixture@example.invalid", "planType": plan}},
                                raw, "codex", NOW, Path("/nonexistent/subscription-fixture-auth.json"))

    def test_weekly_only_pro_has_actual_meter_and_no_five_hour_bar(self):
        view = self.view(limits(None, meter(10080, 42)))
        self.assertEqual(view["account"]["plan_type"], "pro")
        self.assertIsNone(view["windows"]["five_hour"])
        self.assertEqual(view["windows"]["weekly"]["remaining"], 42)
        self.assertEqual([(w["kind"], w["minutes"]) for w in view["quota_windows"]], [("weekly", 10080)])
        self.assertTrue(view["scheduling_available"])
        self.assertEqual(view["scheduling_window"]["minutes"], 10080)

    def test_custom_window_is_visible_with_its_actual_duration(self):
        view = self.view(limits(meter(1440, 13), None), "enterprise")
        self.assertIsNone(view["windows"]["five_hour"])
        self.assertIsNone(view["windows"]["weekly"])
        self.assertEqual(view["quota_windows"][0]["kind"], "custom")
        self.assertEqual(view["quota_windows"][0]["minutes"], 1440)
        self.assertEqual(view["quota_windows"][0]["remaining"], 13)
        self.assertEqual(view["scheduling_window"]["minutes"], 1440)

    def test_service_only_display_has_no_fake_meter_or_schedule(self):
        view = self.view(limits(None, None))
        self.assertEqual(view["quota_state"], "service_only")
        self.assertEqual(view["quota_windows"], [])
        self.assertFalse(view["scheduling_available"])
        self.assertTrue(view["service_allowed"])

    def test_unknown_display_does_not_inherit_plan_based_allowance(self):
        for raw in (limits(), limits(None, None, allowed=MISSING)):
            view = self.view(raw)
            self.assertEqual(view["quota_state"], "unknown")
            self.assertEqual(view["quota_windows"], [])
            self.assertFalse(view["scheduling_available"])

    def test_plan_change_uses_service_metadata_without_changing_percentages(self):
        view = self.view(limits(meter(60, 11), None, planType="future-plan"), "plus")
        self.assertEqual(view["account"]["plan_type"], "future-plan")
        self.assertEqual(view["quota_windows"][0]["remaining"], 11)

    def test_malformed_window_display_cannot_claim_permission_or_unlimited(self):
        view = self.view(limits({"usedPercent": float("nan"), "windowDurationMins": 300, "resetsAt": NOW + 1000}, None))
        self.assertEqual(view["quota_state"], "unknown")
        self.assertEqual(view["quota_windows"], [])
        self.assertFalse(view["scheduling_available"])


class SubscriptionLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(self.temp.name)
        self.rpc = FakeRpc()
        self.config = copy.deepcopy(CONFIG)
        self.controller = Controller(self.rpc, self.store, self.config, "scope", clock=lambda: NOW)
        self.chat = entry("one", "Subscription fixture")
        self.chat["execution_stage"] = {"turn_id": "original-one"}
        self.store.put("chat_catalog", {"scope": "scope", "items": [self.chat]})
        self.rpc.views["one"]["thread"]["status"] = {"type": "idle"}
        self.rpc.views["one"]["turns"][0].update(status="completed", started_at_ms=(NOW - 100) * 1000)

    async def asyncTearDown(self):
        self.store.close()
        self.temp.cleanup()

    async def test_weekly_only_plan_executes_once_after_weekly_refresh(self):
        old = read(limits(None, meter(10080, 60)))
        set_plan(self.store, self.chat, True, "Prepare fixture report", 0, old, NOW)
        runner = PlanRunner(self.controller)
        await runner.tick(old)
        self.assertEqual(self.rpc.count("turn/start"), 0)
        raw = limits(None, meter(10080, 90, NOW + 9000))
        self.rpc.quota = raw
        await runner.tick(read(raw))
        await runner.tick(read(raw))
        self.assertEqual(self.rpc.count("turn/start"), 1)
        self.assertEqual(get_plan(self.store, self.chat["key"])["state"], "sent")

    async def test_custom_plan_waits_for_matching_window_across_slot_reversal(self):
        old = read(limits(meter(60, 70), meter(10080, 60)))
        set_plan(self.store, self.chat, True, "Prepare fixture report", 0, old, NOW)
        raw = limits(meter(10080, 60), meter(60, 90, NOW + 7200))
        self.rpc.quota = raw
        await PlanRunner(self.controller).tick(read(raw))
        self.assertEqual(self.rpc.count("turn/start"), 1)

    async def test_legacy_five_hour_plan_is_not_reinterpreted_as_weekly(self):
        plan = {"id": "legacy-plan", "key": self.chat["key"], "thread_id": "one", "name": "Fixture",
                "kind": "codex", "host_id": "local", "scope": "scope", "armed_at": NOW,
                "armed_window_reset": NOW + 3600, "state": "armed", "prompt": "Continue", "revision": 1}
        save_plan(self.store, plan, 0)
        raw = limits(None, meter(10080, 90, NOW + 9000))
        self.rpc.quota = raw
        await PlanRunner(self.controller).tick(read(raw))
        self.assertEqual(self.rpc.count("turn/start"), 0)

    async def test_explicit_save_rearms_changed_window_with_fresh_identity_and_anchor(self):
        old = set_plan(self.store, self.chat, True, "Continue original fixture", 0,
                       read(limits(meter(60, 70), None)), NOW)
        current = read(limits(None, meter(10080, 70, NOW + 9000)))
        plan = set_plan(self.store, self.chat, True, "Continue updated fixture", 1, current, NOW + 100)
        self.assertNotEqual(plan["id"], old["id"])
        self.assertEqual(plan["armed_at"], NOW + 100)
        self.assertEqual(plan["armed_window_minutes"], 10080)
        self.assertEqual(plan["armed_window_reset"], NOW + 9000)
        self.assertEqual(plan["revision"], 2)
        self.assertFalse(PlanRunner(self.controller).ready(plan, current))
        with self.assertRaises(ValueError):
            set_plan(self.store, self.chat, True, "Stale edit", 1, current, NOW + 101)

    async def test_explicit_save_rearms_old_account_plan_without_carrying_old_scope(self):
        old = set_plan(self.store, self.chat, True, "Continue original fixture", 0,
                       read(limits(meter(300, 70), None)), NOW)
        current = read(limits(meter(300, 70, NOW + 9000), None))
        current["scope"] = "new-account"
        plan = set_plan(self.store, self.chat, True, "New verified account instruction", 1, current, NOW + 100)
        self.assertNotEqual(plan["id"], old["id"])
        self.assertEqual(plan["scope"], "new-account")
        self.assertEqual(plan["armed_at"], NOW + 100)
        self.assertEqual(plan["armed_window_reset"], NOW + 9000)

    async def test_no_timed_window_cannot_arm_but_existing_plan_can_cancel(self):
        service = read(limits(None, None))
        with self.assertRaisesRegex(ValueError, "刷新窗口"):
            set_plan(self.store, self.chat, True, "Continue", 0, service, NOW)
        self.assertIsNone(get_plan(self.store, self.chat["key"]))
        set_plan(self.store, self.chat, True, "Continue", 0, read(limits(meter(300), None)), NOW)
        result = set_plan(self.store, self.chat, False, "Continue", 1, service, NOW)
        self.assertEqual(result["state"], "cancelled")

    async def test_service_only_immediate_can_send_once_with_fresh_permission(self):
        raw = limits(None, None)
        value = read(raw)
        self.rpc.quota = raw
        request = str(uuid.uuid4())
        enqueue_dispatch(self.store, self.chat, "Continue fixture", request, 0, value, self.config, NOW)
        runner = ImmediateRunner(self.controller)
        await runner.tick(value)
        await runner.tick(value)
        self.assertEqual(self.rpc.count("turn/start"), 1)
        self.assertEqual(latest_dispatches(self.store)[self.chat["key"]]["state"], "sent")

    async def test_service_only_immediate_refuses_revoked_second_read(self):
        value = read(limits(None, None))
        enqueue_dispatch(self.store, self.chat, "Continue fixture", str(uuid.uuid4()), 0, value, self.config, NOW)
        self.rpc.quota = limits(None, None, allowed=False)
        await ImmediateRunner(self.controller).tick(value)
        self.assertEqual(self.rpc.count("turn/start"), 0)
        self.assertEqual(latest_dispatches(self.store)[self.chat["key"]]["state"], "failed")

    async def test_unknown_quota_cannot_enqueue_immediate_instruction(self):
        value = read(limits(None, None, allowed=MISSING))
        with self.assertRaises(ValueError):
            enqueue_dispatch(self.store, self.chat, "Continue fixture", str(uuid.uuid4()), 0, value, self.config, NOW)
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM requests").fetchone()[0], 0)

    async def test_weekly_only_auto_pause_and_resume_retains_account_guards(self):
        await self.controller.adopt("one")
        self.rpc.views["one"]["thread"]["status"] = {"type": "active", "activeFlags": []}
        self.rpc.views["one"]["turns"][0]["status"] = "inProgress"
        await self.controller.tick(read(limits(None, meter(10080, 0))))
        self.assertEqual(self.rpc.count("turn/interrupt"), 1)
        self.assertEqual(self.store.get_task("one")["state"], "paused")
        raw = limits(None, meter(10080, 80, NOW + 9000))
        self.rpc.quota = raw
        async def another_account():
            return "changed-account"
        self.controller.identity_check = another_account
        await self.controller.tick(read(raw))
        self.assertEqual(self.rpc.count("turn/start"), 0)

