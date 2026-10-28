"""Offline evidence tests; never read a user's quota ledger or consume credits."""
import copy
import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from guardian import Store
from quota_audit import ACTIVE_KEY, ANCHOR_PREFIX, observe_quota


T = 2000000000
CONFIG = {'limit_id': 'codex', 'max_sample_age_seconds': 90, 'mode': 'notify'}


def credit(identity='one', expiry=None, granted=T - 600, status='available'):
    return {'id': identity, 'status': status, 'resetType': 'quota',
            'grantedAt': granted, 'expiresAt': expiry}


def sample(at=T, remaining=10, reset=T + 18000, weekly=4,
           weekly_reset=T + 604800, count=0, credits=None, scope='a' * 64):
    return {'scope': scope, 'limit_id': 'codex', 'observed_at': at,
            'windows': {'primary': {'minutes': 300, 'remaining': remaining, 'reset': reset},
                        'secondary': {'minutes': 10080, 'remaining': weekly, 'reset': weekly_reset}},
            'reset_credits': {'supported': True, 'available_count': count,
                              'credits': [] if credits is None else credits}}


class QuotaAuditTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.directory.name))

    def tearDown(self):
        self.store.db.close()
        self.directory.cleanup()

    def observe(self, value, now=None, config=None):
        with mock.patch('quota_audit.time.time', return_value=value['observed_at'] if now is None else now):
            return observe_quota(self.store, value, CONFIG if config is None else config)

    def events(self):
        return self.store.db.execute("SELECT * FROM events WHERE state='quota_restored'").fetchall()

    def restored(self, previous=None, current=None):
        self.assertIsNone(self.observe(previous or sample()))
        result = self.observe(current or sample(at=T + 30, remaining=100))
        self.assertIsNotNone(result)
        self.assertEqual(len(self.events()), 1)
        self.assertIsNone(self.events()[0]['thread_id'])
        self.assertEqual(json.loads(self.events()[0]['detail']), result)
        self.assertIsNone(result['official_reason'])
        self.assertEqual(result['source'], 'account/rateLimits/read')
        self.assertFalse(result['reset_credits']['consumption_evidence']['confirmed'])
        return result

    def test_first_sample_is_baseline_and_ignores_legacy_last_report(self):
        self.store.put('last_report', {'sample': sample(remaining=0)})
        self.assertIsNone(self.observe(sample(remaining=100)))
        self.assertEqual(self.events(), [])
        self.assertIsNotNone(self.store.get(ACTIVE_KEY))

    def test_early_increase_with_unchanged_deadline_is_independent(self):
        result = self.restored()
        self.assertEqual(result['category'], 'official_independent_reset')
        self.assertEqual(result['scope'], 'a' * 64)
        self.assertEqual(result['limit_id'], 'codex')
        self.assertEqual([w['minutes'] for w in result['windows']], [300])

    def test_early_weekly_and_double_window_increases_are_recorded(self):
        result = self.restored(current=sample(at=T + 30, remaining=100, weekly=100))
        self.assertEqual(result['category'], 'official_independent_reset')
        self.assertEqual([w['minutes'] for w in result['windows']], [300, 10080])

    def test_scheduled_reset_requires_reached_deadline_and_credible_advance(self):
        result = self.restored(sample(reset=T + 30), sample(at=T + 30, remaining=100, reset=T + 18030))
        self.assertEqual(result['category'], 'official_scheduled_reset')

    def test_weekly_scheduled_reset_is_duration_aware(self):
        result = self.restored(sample(weekly_reset=T + 30),
                               sample(at=T + 30, weekly=100, weekly_reset=T + 604830))
        self.assertEqual(result['category'], 'official_scheduled_reset')
        self.assertEqual(result['windows'][0]['minutes'], 10080)

    def test_unused_full_window_rollover_is_recorded(self):
        result = self.restored(sample(remaining=100, reset=T + 30),
                               sample(at=T + 30, remaining=100, reset=T + 18030))
        self.assertEqual(result['category'], 'official_scheduled_reset')

    def test_complete_period_advance_records_reset_masked_by_new_consumption(self):
        result = self.restored(sample(remaining=98, reset=T + 30),
                               sample(at=T + 60, remaining=97, reset=T + 18030))
        self.assertEqual(result['category'], 'official_scheduled_reset')
        self.assertFalse(result['windows'][0]['net_balance_increased'])
        self.assertEqual(result['windows'][0]['remaining_delta'], -1)

    def test_cycle_without_net_increase_does_not_infer_user_from_credit_drop(self):
        result = self.restored(sample(remaining=98, reset=T + 30, count=1, credits=[credit()]),
                               sample(at=T + 60, remaining=97, reset=T + 18030))
        self.assertEqual(result['category'], 'unattributed')

    def test_small_deadline_advance_after_due_is_not_complete_cycle_evidence(self):
        self.observe(sample(remaining=98, reset=T + 30))
        self.assertIsNone(self.observe(sample(at=T + 60, remaining=97, reset=T + 35)))
        self.assertEqual(self.events(), [])

    def test_before_deadline_tolerance_band_does_not_claim_scheduled_or_early(self):
        result = self.restored(sample(reset=T + 60),
                               sample(at=T + 30, remaining=100, reset=T + 18060))
        self.assertEqual(result['category'], 'unattributed')

    def test_pure_deadline_jitter_or_advance_is_not_a_reset(self):
        self.observe(sample())
        for offset, remaining, reset in ((30, 10, T + 18002), (60, 11, T + 18003),
                                         (90, 11, T + 36000), (120, 10, T + 36002)):
            self.assertIsNone(self.observe(sample(at=T + offset, remaining=remaining, reset=reset)))
        self.assertEqual(self.events(), [])

    def test_small_positive_increase_with_credible_advance_is_unattributed(self):
        result = self.restored(sample(remaining=98), sample(at=T + 30, remaining=100, reset=T + 36000))
        self.assertEqual(result['category'], 'unattributed')
        self.assertEqual(result['windows'][0]['classification_basis'],
                         'small_balance_increase_with_deadline_advance')

    def test_fractional_positive_increase_with_credible_advance_is_not_dropped(self):
        result = self.restored(sample(remaining=98),
                               sample(at=T + 30, remaining=98.001, reset=T + 36000))
        self.assertEqual(result['category'], 'unattributed')

    def test_exact_five_point_threshold_and_four_point_noise(self):
        self.observe(sample(remaining=50))
        self.assertIsNone(self.observe(sample(at=T + 30, remaining=54)))
        result = self.observe(sample(at=T + 60, remaining=59))
        self.assertEqual(result['category'], 'official_independent_reset')

    def test_missing_credit_statistics_never_claim_official(self):
        for value in (None, {}, {'supported': False}, {'supported': True, 'available_count': None}):
            with self.subTest(value=value):
                self.store.db.execute('DELETE FROM kv')
                self.store.db.execute('DELETE FROM events')
                self.store.db.commit()
                previous, current = sample(), sample(at=T + 30, remaining=100)
                previous['reset_credits'] = current['reset_credits'] = value
                result = self.restored(previous, current)
                self.assertEqual(result['category'], 'unattributed')
                self.assertIsNone(result['reset_credits']['delta'])

    def test_counts_only_positive_inventory_is_not_complete(self):
        result = self.restored(sample(count=1), sample(at=T + 30, remaining=100, count=1))
        self.assertEqual(result['category'], 'unattributed')
        self.assertFalse(result['reset_credits']['consumption_evidence']['inventory_complete'])

    def test_nonexpiring_available_id_removal_and_count_drop_infers_user_reset(self):
        result = self.restored(sample(count=1, credits=[credit()]), sample(at=T + 30, remaining=100))
        self.assertEqual(result['category'], 'user_reset')
        self.assertEqual(result['classification_basis'], 'available_credit_decreased_with_balance_restoration')
        self.assertEqual(result['reset_credits']['delta'], -1)
        self.assertEqual(result['reset_credits']['consumption_evidence']['removed_nonexpired_available_ids'], ['one'])

    def test_future_expiry_available_removal_and_small_reset_increase_can_infer_user(self):
        result = self.restored(sample(remaining=98, count=1, credits=[credit(expiry=T + 300)]),
                               sample(at=T + 30, remaining=100, reset=T + 36000))
        self.assertEqual(result['category'], 'user_reset')

    def test_explicit_consumed_transition_is_observed_not_confirmed(self):
        result = self.restored(sample(count=1, credits=[credit()]),
                               sample(at=T + 30, remaining=100, credits=[credit(status='consumed')]))
        self.assertEqual(result['category'], 'user_reset')
        self.assertEqual(result['reset_credits']['consumption_evidence']['consumed_ids'], ['one'])

    def test_count_drop_without_comparable_list_is_unattributed(self):
        result = self.restored(sample(count=1), sample(at=T + 30, remaining=100))
        self.assertEqual(result['category'], 'unattributed')
        self.assertFalse(result['reset_credits']['consumption_evidence']['observed'])

    def test_credit_decrease_before_delayed_balance_increase_is_not_official(self):
        self.observe(sample(count=1, credits=[credit()]))
        self.assertIsNone(self.observe(sample(at=T + 30)))
        self.assertIsNone(self.observe(sample(at=T + 60)))
        result = self.observe(sample(at=T + 90, remaining=100))
        self.assertEqual(result['category'], 'unattributed')
        self.assertEqual(result['classification_basis'], 'recent_reset_credit_metadata_changed')
        self.assertTrue(result['reset_credits']['consumption_evidence']['recent_metadata_change'])
        self.assertEqual(result['reset_credits']['consumption_evidence']['metadata_changed_at'], T + 30)

    def test_credit_change_guard_survives_restart_at_exact_120_seconds(self):
        self.observe(sample(count=1, credits=[credit()]))
        self.observe(sample(at=T + 30))
        self.store.db.close()
        self.store = Store(Path(self.directory.name))
        result = self.observe(sample(at=T + 150, remaining=100))
        self.assertEqual(result['category'], 'unattributed')
        self.assertTrue(result['reset_credits']['consumption_evidence']['recent_metadata_change'])

    def test_prior_expiry_grant_and_metadata_loss_are_also_sticky(self):
        cases = [(sample(count=1, credits=[credit(expiry=T + 20)]), sample(at=T + 30)),
                 (sample(), sample(at=T + 30, count=1, credits=[credit(granted=T + 20)])),
                 (sample(count=1, credits=[credit()]), sample(at=T + 30, count=1))]
        for previous, intermediate in cases:
            with self.subTest(intermediate=intermediate):
                self.store.db.execute('DELETE FROM kv')
                self.store.db.execute('DELETE FROM events')
                self.store.db.commit()
                self.observe(previous)
                self.assertIsNone(self.observe(intermediate))
                current = copy.deepcopy(intermediate)
                current.update(observed_at=T + 60)
                current['windows']['primary']['remaining'] = 100
                result = self.observe(current)
                self.assertEqual(result['category'], 'unattributed')
                self.assertTrue(result['reset_credits']['consumption_evidence']['recent_metadata_change'])

    def test_expiry_and_near_expiry_removal_do_not_infer_user(self):
        for expiry in (T + 20, T + 45):
            with self.subTest(expiry=expiry):
                self.store.db.execute('DELETE FROM kv')
                self.store.db.execute('DELETE FROM events')
                self.store.db.commit()
                result = self.restored(sample(count=1, credits=[credit(expiry=expiry)]),
                                       sample(at=T + 30, remaining=100))
                self.assertEqual(result['category'], 'unattributed')
                self.assertFalse(result['reset_credits']['consumption_evidence']['observed'])

    def test_new_grant_offsetting_missing_available_id_is_ambiguous(self):
        result = self.restored(sample(count=1, credits=[credit()]),
            sample(at=T + 30, remaining=100, count=1, credits=[credit('two', granted=T + 20)]))
        self.assertEqual(result['category'], 'unattributed')
        self.assertFalse(result['reset_credits']['consumption_evidence']['observed'])

    def test_new_grant_offsetting_explicit_consumption_can_be_reconciled(self):
        result = self.restored(sample(count=1, credits=[credit()]), sample(at=T + 30, remaining=100,
            count=1, credits=[credit(status='consumed'), credit('two', granted=T + 20)]))
        self.assertEqual(result['category'], 'user_reset')
        self.assertEqual(result['reset_credits']['delta'], 0)

    def test_lost_expiry_or_changed_inventory_fields_cannot_infer_user(self):
        row = credit(status='consumed')
        del row['expiresAt']
        result = self.restored(sample(count=1, credits=[credit()]),
                               sample(at=T + 30, remaining=100, credits=[row]))
        self.assertEqual(result['category'], 'unattributed')
        self.assertTrue(result['reset_credits']['consumption_evidence']['fields_changed_or_lost'])

    def test_capped_inventory_never_infers_consumption(self):
        rows = [credit(str(i)) for i in range(32)]
        result = self.restored(sample(count=32, credits=rows),
                               sample(at=T + 30, remaining=100, count=31, credits=rows[1:]))
        self.assertEqual(result['category'], 'unattributed')
        self.assertTrue(result['reset_credits']['consumption_evidence']['lists_capped'])

    def test_unknown_status_duplicate_ids_and_inconsistent_counts_are_conservative(self):
        for rows, count in (([credit(status='used')], 0), ([credit(), credit()], 2), ([credit()], 0)):
            with self.subTest(rows=rows, count=count):
                self.store.db.execute('DELETE FROM kv')
                self.store.db.execute('DELETE FROM events')
                self.store.db.commit()
                result = self.restored(sample(count=1, credits=[credit()]),
                                       sample(at=T + 30, remaining=100, count=count, credits=rows))
                self.assertEqual(result['category'], 'unattributed')

    def test_slot_reorder_preserves_duration_identity(self):
        current = sample(at=T + 30, remaining=100, weekly=100)
        current['windows']['primary'], current['windows']['secondary'] = (
            current['windows']['secondary'], current['windows']['primary'])
        result = self.restored(current=current)
        self.assertEqual(result['category'], 'official_independent_reset')
        self.assertEqual([w['minutes'] for w in result['windows']], [300, 10080])

    def test_changed_or_missing_window_is_not_confidently_attributed(self):
        current = sample(at=T + 30, remaining=100)
        del current['windows']['secondary']
        result = self.restored(current=current)
        self.assertEqual(result['category'], 'unattributed')
        self.assertEqual(result['windows'][0]['classification_basis'], 'window_set_changed')

    def test_duplicate_duration_is_not_matched_arbitrarily(self):
        current = sample(at=T + 30, remaining=100)
        current['windows']['secondary']['minutes'] = 300
        self.observe(sample())
        self.assertIsNone(self.observe(current))
        self.assertEqual(self.events(), [])

    def test_long_offline_gap_records_restoration_without_attribution(self):
        result = self.restored(sample(reset=T + 100),
                               sample(at=T + 21601, remaining=100, reset=T + 40000))
        self.assertEqual(result['category'], 'unattributed')
        self.assertEqual(result['windows'][0]['classification_basis'], 'observation_gap_too_long')

    def test_account_switch_back_and_limit_switch_rebaseline(self):
        self.observe(sample())
        self.assertIsNone(self.observe(sample(at=T + 30, remaining=0, scope='b' * 64)))
        self.assertIsNone(self.observe(sample(at=T + 60, remaining=100)))
        other = sample(at=T + 90, remaining=0)
        other['limit_id'] = 'other'
        self.assertIsNone(self.observe(other, config={'max_sample_age_seconds': 90}))
        self.assertIsNone(self.observe(sample(at=T + 120, remaining=100)))
        self.assertEqual(self.events(), [])
        keys = self.store.db.execute('SELECT key FROM kv WHERE key LIKE ?', (ANCHOR_PREFIX + '%',)).fetchall()
        self.assertEqual(len(keys), 3)

    def test_stale_out_of_order_future_and_wrong_bucket_do_not_change_baseline(self):
        self.observe(sample())
        active = self.store.get(ACTIVE_KEY)
        self.assertIsNone(self.observe(sample(at=T + 30, remaining=100), now=T + 121))
        self.assertIsNone(self.observe(sample(at=T, remaining=100)))
        self.assertIsNone(self.observe(sample(at=T - 30, remaining=100)))
        self.assertIsNone(self.observe(sample(at=T + 30, remaining=100), now=T + 24))
        wrong = sample(at=T + 30, remaining=100)
        wrong['limit_id'] = 'wrong'
        self.assertIsNone(self.observe(wrong))
        self.assertEqual(self.store.get(ACTIVE_KEY), active)
        self.assertEqual(self.events(), [])

    def test_repeated_sample_and_restart_do_not_duplicate(self):
        current = sample(at=T + 30, remaining=100)
        self.restored(current=current)
        self.assertIsNone(self.observe(current))
        self.store.db.close()
        self.store = Store(Path(self.directory.name))
        self.assertIsNone(self.observe(current))
        self.assertIsNone(self.observe(sample(at=T + 60, remaining=100)))
        self.assertEqual(len(self.events()), 1)

    def test_insert_failure_rolls_back_baseline_and_allows_exact_retry(self):
        self.observe(sample())
        baseline = self.store.get(ACTIVE_KEY)
        self.store.db.executescript("""CREATE TRIGGER audit_failure BEFORE INSERT ON events
            WHEN NEW.state='quota_restored' BEGIN SELECT RAISE(ABORT, 'injected'); END;""")
        current = sample(at=T + 30, remaining=100)
        with self.assertRaises(sqlite3.IntegrityError):
            self.observe(current)
        self.assertEqual(self.store.get(ACTIVE_KEY), baseline)
        self.assertEqual(self.events(), [])
        self.store.db.execute('DROP TRIGGER audit_failure')
        self.store.db.commit()
        self.assertIsNotNone(self.observe(current))
        self.assertIsNone(self.observe(current))
        self.assertEqual(len(self.events()), 1)

    def test_caller_transaction_is_not_committed_or_rolled_back(self):
        self.store.db.execute('INSERT INTO kv VALUES (?,?)', ('pending', 'true'))
        with self.assertRaisesRegex(RuntimeError, 'committed caller'):
            self.observe(sample())
        self.assertTrue(self.store.db.in_transaction)
        self.assertEqual(self.store.get('pending'), True)
        self.store.db.rollback()
        self.assertIsNone(self.store.get('pending'))

    def test_audit_does_not_mutate_sample_or_task_permissions(self):
        previous, current = sample(), sample(at=T + 30, remaining=100)
        originals = copy.deepcopy((previous, current))
        self.store.put('last_low', {'unchanged': True})
        self.store.db.execute('INSERT INTO tasks VALUES (?,?)',
                              ('held', json.dumps({'id': 'held', 'state': 'held', 'manual_hold': True})))
        self.store.db.commit()
        result = self.restored(previous, current)
        self.assertIsNotNone(result)
        self.assertEqual((previous, current), originals)
        self.assertEqual(self.store.get('last_low'), {'unchanged': True})
        self.assertTrue(self.store.get_task('held')['manual_hold'])
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM notices').fetchone()[0], 0)

    def test_anchor_key_is_namespace_hash_and_excludes_raw_credit_titles(self):
        previous = sample(count=1, credits=[dict(credit(), title='private title', description='private description')])
        self.observe(previous)
        namespace = hashlib.sha256((previous['scope'] + '\0codex').encode()).hexdigest()
        anchor = self.store.get(ANCHOR_PREFIX + namespace)
        self.assertNotIn('title', anchor['reset_credits']['credits'][0])
        self.assertNotIn('description', anchor['reset_credits']['credits'][0])


if __name__ == '__main__':
    unittest.main()
