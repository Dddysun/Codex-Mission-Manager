"""Restoration evidence and execution use fixtures, never desktop sessions."""
import copy
import json
import tempfile
import unittest
from account_display import display_snapshot
from catalog import entry
from guardian import Controller, Store
from plans import PlanRunner, get_plan, set_plan, save_plan
from quota import parse_bucket, recovered, reset_credits, restoration_reason
from test_guardian import CONFIG, NOW, FakeRpc, payload, sample


class RestorationEvidenceTests(unittest.TestCase):
    def test_unchanged_or_earlier_timestamp_can_show_balance_restoration(self):
        old = sample()
        for reset in (NOW + 300, NOW + 200):
            current = sample(remaining=98, reset=reset)
            self.assertEqual(restoration_reason(current, old, CONFIG, NOW), 'balance_restored')

    def test_small_corrections_or_elapsed_clock_are_not_restoration(self):
        old = sample()
        self.assertFalse(recovered(sample(remaining=10), old, CONFIG, NOW))
        self.assertFalse(recovered(sample(), old, CONFIG, NOW + 80))

    def test_account_bucket_stale_permission_and_missing_window_fail_closed(self):
        old = sample(); old['scope'] = 'a'
        for change in ('account', 'bucket', 'stale', 'permission', 'missing', 'weekly'):
            with self.subTest(change=change):
                current = sample(remaining=98); current['scope'] = 'a'
                if change == 'account': current['scope'] = 'b'
                if change == 'bucket': current['limit_id'] = 'other'
                if change == 'stale': current['observed_at'] -= 1000
                if change == 'permission': current['service_allowed'] = False
                if change == 'missing': current['windows'].pop('secondary')
                if change == 'weekly': current['windows']['secondary']['remaining'] = 0
                self.assertFalse(recovered(current, old, CONFIG, NOW))

    def test_unused_reset_credits_are_not_available_quota(self):
        raw = payload(); raw['rateLimitResetCredits'] = {'availableCount': 3, 'credits': []}
        current = parse_bucket(raw, 'codex', NOW)
        self.assertEqual(current['reset_credits']['available_count'], 3)
        self.assertFalse(recovered(current, sample(), CONFIG, NOW))

    def test_credit_count_is_authoritative_details_are_nullable_and_allowlisted(self):
        raw = {'rateLimitResetCredits': {'availableCount': 7, 'credits': [
            {'id': 'credit', 'resetType': 'weekly', 'status': 'available', 'grantedAt': NOW,
             'expiresAt': None, 'title': None, 'description': 'x' * 2000,
             'accessToken': 'never expose', 'unrecognized': 'omit'}]}}
        parsed = reset_credits(raw)
        self.assertEqual(parsed['available_count'], 7)
        self.assertEqual(len(parsed['credits']), 1)
        self.assertEqual(len(parsed['credits'][0]['description']), 1000)
        self.assertIsNone(parsed['credits'][0]['expiresAt'])
        self.assertNotIn('accessToken', json.dumps(parsed))
        view = display_snapshot({'account': {'id': 'fixture'}}, dict(payload(), **raw), 'codex', NOW)
        self.assertEqual(view['reset_credits'], parsed)
        for value in ({}, {'rateLimitResetCredits': None}):
            self.assertIsNone(reset_credits(value)['available_count'])
        self.assertEqual(reset_credits({'rateLimitResetCredits': {'availableCount': 0, 'credits': None}})['available_count'], 0)
        self.assertIsNone(reset_credits({'rateLimitResetCredits': {'availableCount': True}})['available_count'])


class EarlyExecutionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.store = Store(self.temp.name)
        self.rpc = FakeRpc(); self.clock = NOW
        self.cfg = dict(CONFIG, recovery_confirm_seconds=5)
        self.controller = Controller(self.rpc, self.store, self.cfg, 'scope', clock=lambda: self.clock)

    async def asyncTearDown(self):
        self.store.close(); self.temp.cleanup()

    def sends(self):
        return [args for method, args in self.rpc.calls if method == 'turn/start']

    async def test_proactively_paused_task_resumes_once_after_two_early_samples(self):
        await self.controller.adopt('one')
        await self.controller.tick(sample())
        self.rpc.quota = payload(remaining=98, reset=NOW + 200)
        fresh = sample(remaining=98, reset=NOW + 200)
        await self.controller.tick(fresh)
        self.assertEqual(self.sends(), [])
        self.clock += 6
        await self.controller.tick(fresh)
        self.assertEqual(len(self.sends()), 1)
        task = self.store.get_task('one')
        self.assertEqual(task['recovery_reason'], 'balance_restored')
        self.assertIsNone(task['recovery_evidence']['official_reason'])
        await self.controller.tick(fresh)
        self.assertEqual(len(self.sends()), 1)
        details = [json.loads(row[0]) for row in self.store.db.execute('SELECT detail FROM events')]
        self.assertTrue(any(d.get('recovery_reason') == 'balance_restored' for d in details))

    def arm(self, remaining=70):
        self.rpc.views['one']['thread']['status'] = {'type': 'idle'}
        self.rpc.views['one']['turns'][0].update(status='completed', started_at_ms=(NOW - 100) * 1000)
        old = sample(remaining=remaining); old['scope'] = 'scope'
        return set_plan(self.store, entry('one', 'one'), True, 'Explicit instruction', 0, old, NOW)

    async def test_armed_plan_early_restore_requires_large_stable_drop_and_sends_once(self):
        self.arm(); runner = PlanRunner(self.controller)
        self.rpc.quota = payload(remaining=95, reset=NOW + 200)
        current = sample(remaining=95, reset=NOW + 200); current['scope'] = 'scope'
        await runner.tick(current)
        self.assertEqual(self.sends(), [])
        self.clock += 6
        await runner.tick(current); await runner.tick(current)
        self.assertEqual(len(self.sends()), 1)
        self.assertEqual(get_plan(self.store, 'codex:local:one')['recovery_reason'], 'balance_restored')

    async def test_plan_armed_while_low_uses_resume_threshold_evidence(self):
        self.arm(8); runner = PlanRunner(self.controller)
        current = dict(sample(remaining=20), scope='scope')
        self.rpc.quota = payload(remaining=20)
        await runner.tick(current); self.clock += 6; await runner.tick(current)
        self.assertEqual(len(self.sends()), 1)

    async def test_plan_small_change_missing_window_and_legacy_anchor_do_not_send_early(self):
        plan = self.arm(); runner = PlanRunner(self.controller)
        small = sample(remaining=89); small['scope'] = 'scope'
        self.assertFalse(runner.ready(plan, small))
        missing = sample(remaining=98); missing['scope'] = 'scope'; missing['windows'].pop('secondary')
        self.assertFalse(runner.ready(plan, missing))
        plan.pop('armed_window_remaining'); plan.pop('armed_windows')
        save_plan(self.store, plan, plan['revision'])
        await runner.tick(dict(sample(remaining=98), scope='scope'))
        self.assertEqual(self.sends(), [])
        self.assertTrue(runner.ready(plan, dict(sample(remaining=98, reset=NOW + 18000), scope='scope')))

    async def test_early_restore_still_respects_manual_hold_and_global_pause(self):
        await self.controller.adopt('one'); await self.controller.tick(sample())
        task = self.store.get_task('one'); task['manual_hold'] = True; self.store.save_task(task)
        fresh = sample(remaining=98)
        self.rpc.quota = payload(remaining=98)
        await self.controller.tick(fresh); self.clock += 6; await self.controller.tick(fresh)
        self.assertEqual(self.sends(), [])
        self.arm(); self.store.put('supervisor_paused', True)
        await PlanRunner(self.controller).tick(dict(fresh, scope='scope'))
        self.assertEqual(self.sends(), [])

    async def test_early_restore_respects_auto_off_and_approval(self):
        await self.controller.adopt('one'); await self.controller.tick(sample())
        task = self.store.get_task('one'); task['auto_resume'] = False; self.store.save_task(task)
        fresh = sample(remaining=98); self.rpc.quota = payload(remaining=98)
        await self.controller.tick(fresh); self.clock += 6; await self.controller.tick(fresh)
        self.assertEqual(self.sends(), [])
        task = self.store.get_task('one'); task['auto_resume'] = True; self.store.save_task(task)
        self.rpc.views['one']['thread']['status'] = {'type': 'active', 'activeFlags': ['waitingOnApproval']}
        await self.controller.tick(fresh); self.clock += 6; await self.controller.tick(fresh)
        self.assertEqual(self.sends(), [])

    async def test_early_plan_second_read_must_still_show_restored_balance(self):
        self.arm(); runner = PlanRunner(self.controller)
        current = dict(sample(remaining=95), scope='scope')
        self.rpc.quota = payload(remaining=89)
        await runner.tick(current); self.clock += 6; await runner.tick(current)
        self.assertEqual(self.sends(), [])
        self.assertIsNone(get_plan(self.store, 'codex:local:one')['recovery_first_seen'])

    async def test_rule_change_during_confirmation_prevents_dispatch_under_old_rules(self):
        from rules import update_rules
        self.arm(); runner = PlanRunner(self.controller)
        current = dict(sample(remaining=95), scope='scope')
        self.rpc.quota = payload(remaining=95)
        await runner.tick(current); self.clock += 6
        self.rpc.on_quota_read = lambda: update_rules(self.store, self.cfg, {'resume_remaining': 95}, 0)
        await runner.tick(current)
        self.assertEqual(self.sends(), [])
        self.assertEqual(get_plan(self.store, 'codex:local:one')['state'], 'armed')

    async def test_remote_chat_cannot_be_adopted_or_controlled_from_legacy_task(self):
        self.rpc.hosts = {'one': 'remote-host'}
        with self.assertRaises(ValueError):
            await self.controller.adopt('one')
        self.store.save_task({'id': 'one', 'name': 'old remote', 'scope': 'scope',
                              'state': 'watching', 'priority': 100, 'auto_resume': True})
        await self.controller.tick(sample())
        self.assertEqual(self.rpc.calls, [])
