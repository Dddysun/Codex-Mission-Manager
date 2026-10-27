"""Local rule persistence and API changes never require live desktop access."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from guardian import Store
from rules import BOUNDS, effective_config, effective_rules, update_rules
from test_guardian import CONFIG
from ui import Application


class RulesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.store = Store(self.root / 'state')
        self.cfg = dict(CONFIG, state_dir=str(self.root / 'state'))

    def tearDown(self):
        self.store.close(); self.temp.cleanup()

    def test_persisted_cas_rules_apply_without_granting_control(self):
        self.store.put('supervisor_paused', True)
        self.store.put('auto_preferences', {'one': False})
        initial = effective_rules(self.store, self.cfg)
        self.assertEqual(set(initial['values']), set(BOUNDS))
        changed = update_rules(self.store, self.cfg, {'poll_seconds': 120, 'ui_poll_seconds': 7}, 0)
        self.assertEqual(changed['revision'], 1)
        other = Store(self.store.directory)
        try:
            self.assertEqual(effective_rules(other, self.cfg), changed)
        finally:
            other.close()
        self.assertEqual(effective_config(self.store, self.cfg)['poll_seconds'], 120)
        self.assertGreaterEqual(effective_config(self.store, self.cfg)['max_sample_age_seconds'], 180)
        self.assertTrue(self.store.get('supervisor_paused'))
        self.assertEqual(self.store.get('auto_preferences'), {'one': False})
        self.assertIsNone(self.store.get('control_revision'))
        with self.assertRaises(ValueError): update_rules(self.store, self.cfg, {'poll_seconds': 60}, 0)

    def test_invalid_bounds_types_relations_and_service_fields_never_persist(self):
        invalid = [{key: bounds['min'] - 1} for key, bounds in BOUNDS.items()]
        invalid += [{key: bounds['max'] + 1} for key, bounds in BOUNDS.items()]
        invalid += [{'pause_remaining': True}, {'poll_seconds': 30.0},
                    {'pause_remaining': 20, 'resume_remaining': 24},
                    {'poll_seconds': 10, 'near_limit_poll_seconds': 11},
                    {'resetsAt': 999}, {'availableCount': 7}, {}]
        for changes in invalid:
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError): update_rules(self.store, self.cfg, changes, 0)
                self.assertEqual(effective_rules(self.store, self.cfg)['revision'], 0)
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM events WHERE state='rules_updated'").fetchone()[0], 0)

    def test_legacy_invalid_optional_rules_fall_back_but_legal_settings_survive(self):
        cfg = dict(self.cfg, poll_seconds=45, recovery_confirm_seconds=0, ui_poll_seconds=200)
        current = effective_rules(self.store, cfg)
        self.assertEqual(current['values']['poll_seconds'], 45)
        self.assertEqual(current['values']['recovery_confirm_seconds'], 5)
        self.assertEqual(current['values']['ui_poll_seconds'], 5)

    def test_api_works_with_unhealthy_control_and_filters_cached_cloud_items(self):
        config = self.root / 'config.json'; config.write_text(json.dumps(self.cfg))
        self.store.put('chat_catalog', {'scope': 'same', 'items': [
            {'key': 'chatgpt:cloud:x', 'id': 'x', 'name': 'hidden', 'kind': 'chatgpt', 'host_id': 'cloud'}]})
        app = Application(config)
        result = app.action({'action': 'set_rules', 'rules_revision': 0, 'rules': {'ui_poll_seconds': 9}})
        self.assertEqual(result['rules']['values']['ui_poll_seconds'], 9)
        with mock.patch('ui.lock_held', return_value=False), \
                mock.patch('ui.desktop_compatibility', return_value={'supported': False}):
            state = app.state()
        self.assertFalse(state['healthy'])
        self.assertEqual(state['rules']['revision'], 1)
        self.assertEqual(state['rules']['values']['ui_poll_seconds'], 9)
        self.assertEqual(state['tasks'], [])
