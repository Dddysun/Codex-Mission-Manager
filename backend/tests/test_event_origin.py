"""History provenance against synthetic ledgers and offline RPC fixtures only."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
import uuid
from unittest import mock

from catalog import entry
from event_origin import event_origin, origin_detail
from guardian import Controller, Store, main as guardian_main, requests
from immediate import ImmediateRunner, enqueue_dispatch
from plans import PlanRunner, get_plan, save_plan, set_plan
from rules import update_rules
from test_guardian import CONFIG, NOW, FakeRpc, sample
from ui import Application


class LegacyOriginTests(unittest.TestCase):
    def test_explicit_valid_origin_wins_and_invalid_origin_is_not_trusted(self):
        for origin in ('user', 'automatic'):
            self.assertEqual(event_origin('unrecognized', {'origin': origin}), origin)
        for bad in (None, True, 'admin', '', [], {}):
            self.assertEqual(event_origin('rules_updated', {'origin': bad}), 'user')
        self.assertEqual(event_origin('watching', {'origin': ['user']}), 'automatic')

    def test_legacy_manual_operations_and_their_immediate_results_are_user(self):
        records = [('supervisor_paused', {'source': 'local_ui'}),
                   ('supervisor_enabled', {'source': 'cli'}),
                   ('disabled', {'source': 'manual'}),
                   ('watching', {'automatic_control_allowed': True}),
                   ('paused', {'automatic_control_allowed': False}),
                   ('held', {'manual_hold': True}), ('disabled', {'manual_hold': False}),
                   ('pause_intent', {'pause_source': 'manual'}), ('paused', {'pause_source': 'manual'}),
                   ('rules_updated', {}), ('plan_armed', {}), ('plan_cancelled', {}),
                   ('immediate_pending', {}), ('immediate_sent', {}),
                   ('immediate_failed', {}), ('immediate_unknown', {})]
        for state, detail in records:
            with self.subTest(state=state, detail=detail):
                self.assertEqual(event_origin(state, detail), 'user')

    def test_legacy_background_phases_do_not_inherit_a_manual_pause_source(self):
        records = [('watching', {'pause_source': 'manual', 'manual_hold': True}),
                   ('running', {'pause_source': 'manual', 'manual_hold': False}),
                   ('needs_review', {'pause_source': 'manual'}),
                   ('resume_intent', {'pause_source': 'manual'}),
                   ('pause_intent', {'pause_source': 'monitor'}),
                   ('paused', {'pause_source': 'quota'}), ('unknown_future_state', {})]
        for state, detail in records:
            with self.subTest(state=state):
                self.assertEqual(event_origin(state, detail), 'automatic')

    def test_plan_dispatch_is_automatic_even_with_old_manual_labels(self):
        for state in ('plan_sending', 'plan_sent', 'plan_needs_review'):
            with self.subTest(state=state):
                self.assertEqual(event_origin(state, {'source': 'manual', 'manual_hold': True}), 'automatic')

    def test_quota_category_has_separate_user_and_background_grouping(self):
        for category in ('user_reset', 'official_scheduled_reset', 'official_independent_reset', 'unattributed', None):
            with self.subTest(category=category):
                expected = 'user' if category == 'user_reset' else 'automatic'
                self.assertEqual(event_origin('quota_restored', {'category': category,
                    'source': 'account/rateLimits/read', 'official_reason': None}), expected)

    def test_missing_malformed_evidence_is_safely_grouped_as_background(self):
        for state, detail in ((None, None), ({}, []), ('watching', {'source': []}),
                              ('paused', {'automatic_control_allowed': 'false'}),
                              ('paused', {'pause_source': 'unknown'})):
            with self.subTest(state=state, detail=detail):
                self.assertEqual(event_origin(state, detail), 'automatic')

    def test_detail_copy_preserves_audit_fields_without_mutating_input(self):
        original = {'reason': 'synthetic', 'request_id': 'request', 'origin': 'automatic'}
        self.assertEqual(origin_detail('rules_updated', original)['origin'], 'automatic')
        result = origin_detail('running', original, 'user')
        self.assertEqual(result, dict(original, origin='user'))
        self.assertEqual(original['origin'], 'automatic')
        with self.assertRaises(ValueError):
            origin_detail('running', original, 'invalid')


class PersistedOriginTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = Store(self.root / 'state')
        self.rpc = FakeRpc()
        self.config = copy.deepcopy(CONFIG)
        self.config['state_dir'] = str(self.root / 'state')
        self.controller = Controller(self.rpc, self.store, self.config, 'scope', clock=lambda: NOW)
        self.chat = entry('one', 'Demo chat')
        self.store.put('chat_catalog', {'scope': 'scope', 'items': [self.chat, entry('two', 'Second demo')]})

    async def asyncTearDown(self):
        self.store.close()
        self.temp.cleanup()

    def events(self):
        return [dict(row, detail=json.loads(row['detail'] or '{}')) for row in
                self.store.db.execute('SELECT * FROM events ORDER BY id')]

    async def test_explicit_adopt_request_is_user_but_discovery_is_automatic(self):
        self.store.enqueue('adopt', {'thread_id': 'one'})
        await requests(self.controller)
        await self.controller.adopt('two')
        events = self.events()
        self.assertEqual([(e['thread_id'], e['detail']['origin']) for e in events],
                         [('one', 'user'), ('two', 'automatic')])

    async def test_manual_pause_receipts_do_not_pollute_later_background_phases(self):
        await self.controller.adopt('one')
        task = self.store.get_task('one')
        await self.controller.pause(task, sample(), manual=True)
        task = self.store.get_task('one')
        self.assertEqual(task['state'], 'paused')
        self.assertNotIn('origin', task)
        pause_events = [e for e in self.events() if e['state'] in ('pause_intent', 'paused')]
        self.assertEqual([e['detail']['origin'] for e in pause_events], ['user', 'user'])
        self.store.permission('one', True)
        task = self.store.get_task('one')
        task['state'] = 'watching'
        self.store.save_task(task)
        self.controller.review(task, 'Unrelated later background check')
        self.assertEqual([e['detail']['origin'] for e in self.events()[-2:]], ['automatic', 'automatic'])

    async def test_manual_pause_failure_keeps_its_current_user_cause(self):
        await self.controller.adopt('one')
        original = self.rpc.call
        async def failing_interrupt(method, params=None):
            if method == 'turn/interrupt':
                raise TimeoutError('offline test fault')
            return await original(method, params)
        self.rpc.call = failing_interrupt
        await self.controller.pause(self.store.get_task('one'), sample(), manual=True)
        event = self.events()[-1]
        self.assertEqual(event['state'], 'needs_review')
        self.assertEqual(event['detail']['origin'], 'user')

    async def test_monitor_pause_and_resumption_are_automatic(self):
        await self.controller.adopt('one')
        await self.controller.tick(sample())
        await self.controller.tick(sample(remaining=98, reset=NOW + 18000))
        self.assertEqual(self.store.get_task('one')['state'], 'running')
        self.assertTrue(all(e['detail']['origin'] == 'automatic' for e in self.events()))

    async def test_permission_toggle_and_rules_update_are_persisted_user_events(self):
        await self.controller.adopt('one')
        self.store.permission('one', False)
        self.store.permission('one', True)
        update_rules(self.store, self.config, {'poll_seconds': 40}, 0)
        self.assertEqual([e['detail']['origin'] for e in self.events()[-3:]], ['user'] * 3)
        self.assertEqual(self.events()[-1]['detail']['revision'], 1)
        self.assertEqual(self.events()[-1]['detail']['values']['poll_seconds'], 40)

    async def test_cli_disable_and_release_keep_explicit_user_origin(self):
        await self.controller.adopt('one')
        path = self.root / 'config.json'
        path.write_text(json.dumps(self.config), encoding='utf-8')
        for command in ('disable', 'release'):
            with mock.patch('sys.argv', ['guardian', '--config', str(path), command, 'one']), \
                    mock.patch('builtins.print'):
                self.assertEqual(guardian_main(), 0)
            self.assertEqual(self.events()[-1]['detail']['origin'], 'user')
        self.assertEqual(self.store.get_task('one')['state'], 'watching')

    async def test_plan_save_cancel_are_user_but_actual_dispatch_and_task_run_are_automatic(self):
        await self.controller.adopt('one')
        self.rpc.views['one']['thread']['status'] = {'type': 'idle'}
        self.rpc.views['one']['turns'][0].update(status='completed', started_at_ms=(NOW - 100) * 1000)
        old, new = sample(remaining=70), sample(remaining=98, reset=NOW + 18000)
        old['scope'] = new['scope'] = 'scope'
        set_plan(self.store, self.chat, True, 'Demo instruction', 0, old, NOW)
        await PlanRunner(self.controller).tick(new)
        self.assertEqual(get_plan(self.store, self.chat['key'])['state'], 'sent')
        events = self.events()
        expected = {'plan_armed': 'user', 'plan_sending': 'automatic', 'plan_sent': 'automatic', 'running': 'automatic'}
        for state, origin in expected.items():
            matching = [e for e in events if e['state'] == state]
            self.assertTrue(matching, state)
            self.assertEqual(matching[-1]['detail']['origin'], origin)
        plan = get_plan(self.store, self.chat['key'])
        set_plan(self.store, self.chat, False, 'Demo instruction', plan['revision'], new, NOW)
        self.assertEqual(self.events()[-1]['detail']['origin'], 'user')
        plan = get_plan(self.store, self.chat['key'])
        plan['state'] = 'needs_review'
        save_plan(self.store, plan, plan['revision'])
        self.assertEqual(self.events()[-1]['detail']['origin'], 'automatic')

    async def test_immediate_request_success_and_task_running_are_user_then_followup_is_automatic(self):
        await self.controller.adopt('one')
        self.rpc.views['one']['thread']['status'] = {'type': 'idle'}
        self.rpc.views['one']['turns'][0].update(status='completed', started_at_ms=(NOW - 100) * 1000)
        quota = sample(remaining=70)
        quota['scope'] = 'scope'
        enqueue_dispatch(self.store, self.chat, 'Demo instruction', str(uuid.uuid4()), 0, quota, self.config, NOW)
        await ImmediateRunner(self.controller).tick(quota)
        self.assertEqual(self.store.get_task('one')['state'], 'running')
        self.assertEqual([e['detail']['origin'] for e in self.events()[-3:]], ['user'] * 3)
        self.rpc.views['one']['turns'][0]['status'] = 'completed'
        self.rpc.views['one']['thread']['status'] = {'type': 'idle'}
        await self.controller.tick(quota)
        self.assertEqual(self.events()[-1]['state'], 'watching')
        self.assertEqual(self.events()[-1]['detail']['origin'], 'automatic')

    async def test_immediate_ambiguous_delivery_result_remains_a_user_operation(self):
        self.rpc.views['one']['thread']['status'] = {'type': 'idle'}
        self.rpc.views['one']['turns'][0].update(status='completed', started_at_ms=(NOW - 100) * 1000)
        self.rpc.fail_start = True
        quota = sample(remaining=70)
        quota['scope'] = 'scope'
        enqueue_dispatch(self.store, self.chat, 'Demo instruction', str(uuid.uuid4()), 0, quota, self.config, NOW)
        await ImmediateRunner(self.controller).tick(quota)
        self.assertEqual(self.events()[-1]['state'], 'immediate_unknown')
        self.assertEqual(self.events()[-1]['detail']['origin'], 'user')

    async def test_api_serializes_legacy_and_new_origins_without_rewriting_old_rows(self):
        path = self.root / 'config.json'
        path.write_text(json.dumps(self.config), encoding='utf-8')
        (self.store.directory / 'status.json').write_text(json.dumps({'quota': {'scope': 'scope'},
            'observed_at': NOW, 'phase': 'normal'}), encoding='utf-8')
        old_details = [('quota_restored', {'scope': 'scope', 'limit_id': 'codex', 'category': 'user_reset'}),
                       ('quota_restored', {'scope': 'scope', 'limit_id': 'codex', 'category': 'unattributed'}),
                       ('rules_updated', {'revision': 1}),
                       ('supervisor_enabled', {'source': 'local_ui'})]
        for state, detail in old_details:
            self.store.db.execute('INSERT INTO events(created,state,detail) VALUES(?,?,?)',
                                  (NOW, state, json.dumps(detail)))
        self.store.db.commit()
        old_bytes = [row['detail'] for row in self.store.db.execute('SELECT detail FROM events ORDER BY id')]
        app = Application(path)
        app.action({'action': 'pause', 'revision': 0})
        with mock.patch('ui.desktop_compatibility', return_value={'supported': False}), \
                mock.patch('ui.lock_held', return_value=False):
            result = app.state()
        events = list(reversed(result['events']))
        self.assertEqual([e['origin'] for e in events], ['user', 'automatic', 'user', 'user', 'user'])
        self.assertEqual(events[-1]['detail']['origin'], 'user')
        after = [row['detail'] for row in self.store.db.execute('SELECT detail FROM events ORDER BY id')]
        self.assertEqual(after[:-1], old_bytes)


if __name__ == '__main__':
    unittest.main()
