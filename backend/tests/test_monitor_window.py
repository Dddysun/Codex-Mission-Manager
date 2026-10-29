"""Selected-window policies and status publication; no live desktop or user data."""
import asyncio
import sys
import contextlib
import io
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from catalog import entry
from guardian import Store, Controller, publish_cycle_status, confirmation_delay, run
from plans import set_plan
from quota import classify, pause_needed, quota_usable, monitoring_state, plan_window
from rules import effective_rules, effective_config, update_rules
from test_guardian import CONFIG, NOW, FakeRpc
from test_subscriptions import read, limits, meter
from ui import Application


class WindowPolicyTests(unittest.TestCase):
    def test_weekly_choice_applies_both_thresholds_at_the_boundaries(self):
        cfg = dict(CONFIG, monitor_window='weekly')
        for remaining, pause, resume in [(0, True, False), (1, True, False), (10, True, False),
                                         (11, False, False), (19, False, False), (20, False, True)]:
            with self.subTest(remaining=remaining):
                value = read(limits(meter(300, 80), meter(10080, remaining)))
                self.assertEqual(pause_needed(value, cfg), pause)
                self.assertEqual(quota_usable(value, cfg), resume)

    def test_only_the_selected_window_uses_the_reserve_but_every_hard_limit_applies(self):
        value = read(limits(meter(300, 8), meter(10080, 60)))
        self.assertTrue(pause_needed(value, dict(CONFIG, monitor_window='five_hour')))
        self.assertFalse(pause_needed(value, dict(CONFIG, monitor_window='weekly')))
        self.assertTrue(quota_usable(value, dict(CONFIG, monitor_window='weekly')))
        for cfg, sample in [(dict(CONFIG, monitor_window='weekly'), read(limits(meter(300, 0), meter(10080, 60)))),
                            (dict(CONFIG, monitor_window='five_hour'), read(limits(meter(300, 80), meter(10080, 0))))]:
            self.assertTrue(pause_needed(sample, cfg))
            self.assertFalse(quota_usable(sample, cfg))

    def test_pro_defaults_to_weekly_and_cannot_choose_a_five_hour_window(self):
        value = read(limits(meter(300, 80), meter(10080, 60), planType='pro'))
        state = monitoring_state(value, CONFIG)
        self.assertEqual(state['effective_window'], 'weekly')
        self.assertFalse(state['five_hour_available'])
        self.assertTrue(state['weekly_available'])
        self.assertEqual(classify(value, dict(CONFIG, monitor_window='five_hour')), 'unknown')

    def test_missing_selected_window_does_not_silently_switch_or_interrupt(self):
        value = read(limits(None, meter(10080, 80)))
        cfg = dict(CONFIG, monitor_window='five_hour')
        self.assertEqual(monitoring_state(value, cfg)['state'], 'unavailable')
        self.assertFalse(quota_usable(value, cfg))
        self.assertFalse(pause_needed(value, cfg))
        for bad in (True, [], 'primary', 'monthly'):
            self.assertEqual(classify(value, dict(CONFIG, monitor_window=bad)), 'unknown')

    def test_slot_order_does_not_change_the_monitor_or_a_new_schedule_anchor(self):
        for value in [read(limits(meter(300, 80), meter(10080, 9))),
                      read(limits(meter(10080, 9), meter(300, 80)))]:
            cfg = dict(CONFIG, monitor_window='weekly')
            self.assertEqual(plan_window(value, cfg)[1]['minutes'], 10080)
            self.assertEqual(classify(value, cfg), 'low')

    def test_existing_scheduled_instruction_is_not_retargeted_by_a_rule_change(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.closing(Store(directory)) as store:
            value = read(limits(meter(300, 80), meter(10080, 60)))
            chat = entry('demo', 'Synthetic task')
            first = set_plan(store, chat, True, 'Continue', 0, value, NOW,
                             config=dict(CONFIG, monitor_window='weekly'))
            updated = set_plan(store, chat, True, 'Updated instruction', 1, value, NOW+1,
                               config=dict(CONFIG, monitor_window='five_hour'))
            self.assertEqual(first['armed_window_minutes'], 10080)
            self.assertEqual(updated['armed_window_minutes'], 10080)
            other = set_plan(store, entry('other', 'Another fixture'), True, 'Continue', 0,
                             value, NOW+1, config=dict(CONFIG, monitor_window='five_hour'))
            self.assertEqual(other['armed_window_minutes'], 300)


class WindowRuleTests(unittest.TestCase):
    def test_rule_change_during_collection_cancels_the_old_cycle_before_control(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.closing(Store(directory)) as store:
            cfg = effective_config(store, CONFIG)
            rules = effective_rules(store, CONFIG)
            store.put('runtime_rules', dict(revision=1, values=rules['values'], monitor_window='weekly'))
            rpc = FakeRpc()
            controller = Controller(rpc, store, cfg, 'scope', clock=lambda: NOW)
            self.assertTrue(controller.cancelled())
            self.assertEqual(rpc.calls, [])

    def test_choice_and_numbers_are_revisioned_together_without_enabling_control(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.closing(Store(directory)) as store:
            store.put('supervisor_paused', True)
            sample = read(limits(meter(300, 80), meter(10080, 60)))
            sample['observed_at'] = time.time()
            store.put('last_report', {'quota': sample})
            old = effective_rules(store, CONFIG)
            store.put('runtime_rules', {'revision': 3, 'values': old['values']})
            self.assertEqual(effective_rules(store, CONFIG)['monitor_window'], 'auto')
            result = update_rules(store, CONFIG, {'pause_remaining': 12}, 3, 'weekly')
            self.assertEqual((result['revision'], result['monitor_window'], result['values']['pause_remaining']), (4, 'weekly', 12))
            self.assertEqual(effective_config(store, CONFIG)['monitor_window'], 'weekly')
            self.assertTrue(store.get('supervisor_paused'))
            with self.assertRaises(ValueError):
                update_rules(store, CONFIG, {}, 3, 'five_hour')
            self.assertEqual(effective_rules(store, CONFIG)['monitor_window'], 'weekly')

    def test_absent_stale_future_and_pro_window_choices_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.closing(Store(directory)) as store:
            with self.assertRaises(ValueError):
                update_rules(store, CONFIG, {}, 0, 'five_hour')
            for value, age in [(read(limits(None, meter(10080, 60), planType='pro')), 0),
                               (read(limits(meter(300, 80), None)), -1000),
                               (read(limits(meter(300, 80), None)), 1000)]:
                value['observed_at'] = time.time()+age
                store.put('last_report', {'quota': value})
                with self.assertRaises(ValueError):
                    update_rules(store, CONFIG, {}, 0, 'five_hour')
                self.assertEqual(effective_rules(store, CONFIG)['revision'], 0)
            for bad in [True, [], 'primary', 300]:
                with self.assertRaises(ValueError):
                    update_rules(store, CONFIG, {}, 0, bad)


class CollectionHealthTests(unittest.TestCase):
    def test_early_publication_uses_quota_read_time_and_never_masks_real_staleness(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.closing(Store(directory)) as store:
            now = time.time()
            cfg = dict(CONFIG, state_dir=directory, _path=str(Path(directory)/'config.json'))
            Path(cfg['_path']).write_text(json.dumps(cfg))
            store.put('supervisor_paused', False)
            sample = read(limits(meter(300, 80), meter(10080, 60)))
            sample['observed_at'] = now
            rpc = type('FixtureRpc', (), {})()
            publish_cycle_status(store, cfg, sample, 'normal', now-65, rpc, True, collecting=True)
            app = Application(cfg['_path'])
            with mock.patch('ui.lock_held', return_value=True), \
                    mock.patch('ui.desktop_compatibility', return_value={'supported': True}), \
                    mock.patch('ui.time.time', return_value=now+40):
                state = app.state()
                self.assertTrue(state['healthy'])
                self.assertTrue(state['collection_in_progress'])
                self.assertFalse(state['control_paused'])
            with mock.patch('guardian.time.time', return_value=now+50):
                report = publish_cycle_status(store, cfg, sample, 'normal', now-65, rpc, True)
            self.assertEqual(report['observed_at'], now)
            with mock.patch('ui.lock_held', return_value=True), \
                    mock.patch('ui.desktop_compatibility', return_value={'supported': True}), \
                    mock.patch('ui.time.time', return_value=now+100):
                self.assertFalse(app.state()['healthy'])
            self.assertFalse(store.get('supervisor_paused'))

    def test_confirmation_deadline_shortens_sleep_without_a_busy_retry_loop(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.closing(Store(directory)) as store:
            now = time.time()
            store.save_task({'id': 'demo', 'state': 'paused', 'auto_resume': True, 'recovery_first_seen': now})
            cfg = dict(CONFIG, recovery_confirm_seconds=5)
            self.assertEqual(confirmation_delay(store, cfg, 30, now), 5)
            self.assertEqual(confirmation_delay(store, cfg, 30, now+10), 10)
            task = store.get_task('demo'); task['manual_hold'] = True; store.save_task(task)
            self.assertEqual(confirmation_delay(store, cfg, 30, now), 30)

    def test_sampling_publishes_before_chat_collection_and_discovers_only_once(self):
        now = time.time()
        calls = []
        with tempfile.TemporaryDirectory() as directory:
            class Service:
                account_display = None
                control_available = True
                available = []
                hosts = {}
                async def start(self): pass
                async def close(self): pass
                async def call(self, method, params=None):
                    if method != 'account/rateLimits/read':
                        raise AssertionError('Unexpected RPC: '+method)
                    calls.append(method)
                    return limits(meter(300, 80, now+10000), meter(10080, 60, now+604800))
                async def refresh_control(self): pass
                async def discover(self):
                    report = json.loads((Path(directory)/'status.json').read_text())
                    if not report['collection_in_progress'] or report['supervisor_paused']:
                        raise AssertionError('Fresh status must be published before discovery')
                    calls.append('discover')
                    return []
            cfg = dict(CONFIG, state_dir=directory, mode='control', desktop_control_enabled=True,
                       desktop_auto_discover=True, power_guard_enabled=False, quota_notifications=False,
                       server_command=['unused'])
            with contextlib.closing(Store(directory)) as store: store.put('supervisor_paused', False)
            with mock.patch('guardian.Rpc', return_value=Service()), \
                    mock.patch('desktop.DesktopAdapter', side_effect=lambda rpc, config: rpc), \
                    mock.patch('guardian.identity_for', new=mock.AsyncMock(return_value='demo-scope')), \
                    mock.patch('guardian.deliver_notices', new=mock.AsyncMock()), \
                    mock.patch('catalog.refresh_catalog', new=mock.AsyncMock()), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(asyncio.run(run(cfg, once=True)), 0)
            self.assertEqual(calls.count('discover'), 1)
            self.assertEqual(calls.count('account/rateLimits/read'), 1)
            final = json.loads((Path(directory)/'status.json').read_text())
            self.assertFalse(final['collection_in_progress'])
            self.assertFalse(final['supervisor_paused'])


class SelectedWeeklyControlTests(unittest.IsolatedAsyncioTestCase):
    async def test_final_quota_check_keeps_pro_selection_when_bucket_omits_plan_type(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.closing(Store(directory)) as store:
            store.put('account_display', {'account': {'plan_type': 'pro'}})
            rpc = FakeRpc()
            rpc.quota = limits(meter(300, 80), meter(10080, 10))
            controller = Controller(rpc, store, CONFIG, 'scope', clock=lambda: NOW)
            fresh = await controller.read_quota()
            self.assertEqual(monitoring_state(fresh, CONFIG)['effective_window'], 'weekly')
            self.assertFalse(quota_usable(fresh, CONFIG))
            self.assertEqual(fresh['scope'], 'scope')

    async def test_weekly_ten_percent_interrupts_once_and_twenty_resumes_once(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.closing(Store(directory)) as store:
            rpc = FakeRpc()
            cfg = dict(CONFIG, monitor_window='weekly')
            controller = Controller(rpc, store, cfg, 'scope', clock=lambda: NOW)
            await controller.adopt('one')
            raw = limits(None, meter(10080, 10), planType='pro')
            rpc.quota = raw
            await controller.tick(read(raw))
            self.assertEqual(rpc.count('turn/interrupt'), 1)
            self.assertEqual(store.get_task('one')['state'], 'paused')
            low = limits(None, meter(10080, 19, NOW+9000), planType='pro')
            rpc.quota = low
            await controller.tick(read(low))
            self.assertEqual(rpc.count('turn/start'), 0)
            usable = limits(None, meter(10080, 20, NOW+9000), planType='pro')
            rpc.quota = usable
            await controller.tick(read(usable))
            await controller.tick(read(usable))
            self.assertEqual(rpc.count('turn/start'), 1)
            self.assertEqual(rpc.count('turn/interrupt'), 1)
