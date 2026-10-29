"""Normal, malformed and exact-limit inputs using only synthetic ledgers."""
import json
import tempfile
import unittest
import uuid

from catalog import entry
from guardian import Store
from immediate import enqueue_dispatch
from plans import get_plan, set_plan
from quota import finite_number, parse_bucket, reset_credits
from quota_audit import _sample
from rules import BOUNDS, validate
from test_guardian import CONFIG, NOW, payload, sample


class NumericBoundaryTests(unittest.TestCase):
    def test_quota_fields_reject_malformed_nonfinite_and_overflowing_numbers(self):
        for field in ('usedPercent', 'windowDurationMins', 'resetsAt'):
            for value in (None, True, False, '10', [], {}, float('nan'),
                          float('inf'), -float('inf'), 10 ** 400, -(10 ** 400)):
                with self.subTest(field=field, value_type=type(value).__name__):
                    raw = payload()
                    raw['rateLimitsByLimitId']['codex']['primary'][field] = value
                    with self.assertRaises(ValueError):
                        parse_bucket(raw, 'codex', NOW)

    def test_quota_exact_percentage_and_stale_grace_boundaries(self):
        for used in (0, 100):
            raw = payload()
            raw['rateLimitsByLimitId']['codex']['primary']['usedPercent'] = used
            self.assertEqual(parse_bucket(raw, 'codex', NOW)['windows']['primary']['remaining'], 100 - used)
        for remaining in (-.001, 100.001):
            with self.assertRaises(ValueError):
                parse_bucket(payload(remaining=remaining), 'codex', NOW)
        parse_bucket(payload(reset=NOW - 90), 'codex', NOW)
        with self.assertRaises(ValueError):
            parse_bucket(payload(reset=NOW - 90.001), 'codex', NOW)

    def test_duration_must_be_positive_and_integral(self):
        for minutes in (0, -1, .5, 300.001):
            raw = payload()
            raw['rateLimitsByLimitId']['codex']['primary']['windowDurationMins'] = minutes
            with self.subTest(minutes=minutes), self.assertRaises(ValueError):
                parse_bucket(raw, 'codex', NOW)

    def test_optional_credit_timestamp_overflow_is_discarded(self):
        value = reset_credits({'rateLimitResetCredits': {'availableCount': 1, 'credits': [
            {'id': 'synthetic', 'grantedAt': 10 ** 400, 'expiresAt': 10 ** 400}]}})
        self.assertEqual(value['credits'][0]['id'], 'synthetic')
        self.assertNotIn('grantedAt', value['credits'][0])
        self.assertNotIn('expiresAt', value['credits'][0])
        self.assertFalse(finite_number(True))
        self.assertTrue(finite_number(0))

    def test_audit_rejects_overflowing_observation_without_replacing_baseline(self):
        value = sample(remaining=80)
        value.update(scope='synthetic', observed_at=10 ** 400)
        self.assertIsNone(_sample(value, CONFIG, NOW))

    def test_rule_numeric_bounds_and_bool_rejection(self):
        defaults = {key: value['default'] for key, value in BOUNDS.items()}
        self.assertEqual(validate(defaults), defaults)
        for key, bounds in BOUNDS.items():
            for bad in (bounds['min'] - 1, bounds['max'] + 1, True, 10.0, '10', None, 10 ** 400):
                with self.subTest(key=key, value_type=type(bad).__name__), self.assertRaises(ValueError):
                    validate(dict(defaults, **{key: bad}))


class InstructionBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(self.temp.name)
        self.addCleanup(self.store.close)
        self.chat = entry('synthetic', 'Synthetic')
        self.sample = dict(sample(remaining=80), scope='synthetic')

    def enqueue(self, prompt, request_id=None):
        return enqueue_dispatch(self.store, self.chat, prompt,
                                request_id or str(uuid.uuid4()), 0, self.sample, CONFIG, NOW)

    def test_empty_and_wrong_type_prompts_never_enqueue(self):
        for value in ('', ' \t\r\n', None, True, [], {}, 42):
            with self.subTest(value_type=type(value).__name__), self.assertRaises(ValueError):
                self.enqueue(value)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM requests').fetchone()[0], 0)

    def test_exact_8000_unicode_codepoints_are_preserved_and_8001_rejected(self):
        prompt = '界' * 8000
        request = self.enqueue(prompt)
        row = self.store.db.execute('SELECT value FROM requests WHERE id=?', (request,)).fetchone()
        self.assertEqual(json.loads(row[0])['prompt'], prompt)
        with self.assertRaises(ValueError):
            self.enqueue(prompt + '界')

    def test_schedule_uses_same_prompt_limit_and_preserves_previous_on_invalid_edit(self):
        plan = set_plan(self.store, self.chat, True, '界' * 8000, 0, self.sample, NOW)
        with self.assertRaises(ValueError):
            set_plan(self.store, self.chat, True, '界' * 8001, plan['revision'], self.sample, NOW)
        self.assertEqual(get_plan(self.store, self.chat['key']), plan)

    def test_noncanonical_or_malformed_request_ids_are_rejected(self):
        for value in (None, True, 'x', str(uuid.uuid4()).upper(), '{' + str(uuid.uuid4()) + '}'):
            with self.subTest(value_type=type(value).__name__), self.assertRaises(ValueError):
                enqueue_dispatch(self.store, self.chat, 'Synthetic', value, 0, self.sample, CONFIG, NOW)

    def test_sql_and_shell_like_text_is_stored_as_data(self):
        identifier = "x'); DROP TABLE tasks; --"
        text = "'; DROP TABLE requests; -- $(touch synthetic) <script>alert(1)</script>"
        self.store.save_task({'id': identifier, 'state': 'watching', 'name': text})
        self.assertEqual(self.store.get_task(identifier)['name'], text)
        request = self.enqueue(text)
        row = self.store.db.execute('SELECT value FROM requests WHERE id=?', (request,)).fetchone()
        self.assertEqual(json.loads(row[0])['prompt'], text)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM tasks').fetchone()[0], 1)
