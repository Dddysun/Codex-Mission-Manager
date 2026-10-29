"""Real competing SQLite connections; no client sessions or runtime data."""
import concurrent.futures
import contextlib
import tempfile
import threading
import unittest

from guardian import Store


class BeforeTaskWrite:
    """Schedule a competing UI action after the background read has finished."""

    def __init__(self, connection, before_write):
        self.connection = connection
        self.before_write = before_write

    def __enter__(self):
        return self.connection.__enter__()

    def __exit__(self, *args):
        return self.connection.__exit__(*args)

    def __getattr__(self, name):
        return getattr(self.connection, name)

    def execute(self, statement, *args):
        if statement.startswith("INSERT OR REPLACE INTO tasks"):
            self.before_write()
        return self.connection.execute(statement, *args)


class StoreConcurrencyTests(unittest.TestCase):
    def test_revocation_cannot_be_lost_between_background_read_and_write(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.closing(Store(directory)) as store:
            store.save_task({"id": "synthetic", "state": "watching",
                             "auto_resume": True, "control_revision": 0})
            stale = store.get_task("synthetic")
            stale["state"] = "running"
            ready, revoke, attempted = (threading.Event() for _ in range(3))

            def user_revokes():
                other = Store(directory)
                try:
                    ready.set()
                    if not revoke.wait(3):
                        raise AssertionError("background write was never reached")
                    other.db.set_trace_callback(
                        lambda sql: attempted.set() if sql == "BEGIN IMMEDIATE" else None)
                    other.permission("synthetic", False, expected_revision=0)
                finally:
                    other.close()

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                result = executor.submit(user_revokes)
                self.assertTrue(ready.wait(3))

                def before_write():
                    revoke.set()
                    self.assertTrue(attempted.wait(3))
                    # The former deferred read allowed the revocation to finish
                    # here. The background write then silently overwrote it.
                    try:
                        result.result(timeout=.1)
                    except concurrent.futures.TimeoutError:
                        pass  # An atomic read/update keeps the other writer waiting.

                store.db = BeforeTaskWrite(store.db, before_write)
                try:
                    self.assertTrue(store.save_task(stale))
                finally:
                    revoke.set()
                result.result(timeout=3)
            current = store.get_task("synthetic")
            self.assertIs(current.get("manual_hold"), True)
            self.assertFalse(current["auto_resume"])
            self.assertEqual(current["control_revision"], 1)
            # An older callback must also stay rejected after the revocation.
            self.assertFalse(store.save_task(stale))

    def test_failed_save_rolls_back_and_does_not_block_user_action(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(directory)
            try:
                store.save_task({"id": "synthetic", "state": "watching"})
                with self.assertRaises(TypeError):
                    store.save_task({"id": "synthetic", "state": "running", "bad": object()})
                self.assertFalse(store.db.in_transaction)
                store.permission("synthetic", False, expected_revision=0)
                self.assertTrue(store.get_task("synthetic")["manual_hold"])
            finally:
                store.close()

    def test_disabled_state_stays_disabled_even_with_matching_revision(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(directory)
            try:
                store.save_task({"id": "synthetic", "state": "disabled", "control_revision": 4})
                self.assertFalse(store.save_task({"id": "synthetic", "state": "running",
                                                  "control_revision": 4}))
                self.assertEqual(store.get_task("synthetic")["state"], "disabled")
                self.assertFalse(store.db.in_transaction)
            finally:
                store.close()

    def test_parallel_chat_opt_outs_preserve_every_preference(self):
        with tempfile.TemporaryDirectory() as directory:
            # Initialize schema before launching independent request workers.
            Store(directory).close()

            def opt_out(index):
                other = Store(directory)
                try:
                    other.configure_auto('synthetic-' + str(index), False, 0, 'scope')
                finally:
                    other.close()

            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                list(executor.map(opt_out, range(24)))
            with contextlib.closing(Store(directory)) as store:
                preferences = store.get('auto_preferences')
                self.assertEqual(len(preferences), 24)
                self.assertTrue(all(value is False for value in preferences.values()))

    def test_pending_adoption_cannot_reenable_a_newer_manual_hold(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.closing(Store(directory)) as store:
            store.save_task({'id': 'synthetic', 'state': 'watching'})
            store.configure_auto('synthetic', True, 0, None)
            store.permission('synthetic', False, expected_revision=1)
            with self.assertRaises(ValueError):
                store.permit_adoption('synthetic')
            self.assertTrue(store.get_task('synthetic')['manual_hold'])
            self.assertIs(store.get('auto_preferences')['synthetic'], False)

    def test_cancelled_unmanaged_adoption_is_not_registered_by_late_callback(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.closing(Store(directory)) as store:
            store.configure_auto('synthetic', True, 0, 'scope')
            store.configure_auto('synthetic', False, 0, 'scope')
            self.assertFalse(store.save_task({'id': 'synthetic', 'state': 'watching', 'scope': 'scope'},
                                             respect_auto_preference=True))
            self.assertIsNone(store.get_task('synthetic'))
            self.assertEqual(store.db.execute("SELECT state FROM requests WHERE kind='adopt'").fetchone()[0],
                             'cancelled')

    def test_toggle_rolls_back_permission_preference_and_intent_on_failure(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.closing(Store(directory)) as store:
            store.save_task({'id': 'synthetic', 'state': 'watching', 'scope': 'scope'})
            store.put('auto_preferences', {'unrelated': False})
            store.db.execute("CREATE TRIGGER fail_preference BEFORE INSERT ON kv "
                             "WHEN NEW.key='auto_preferences' BEGIN SELECT RAISE(ABORT,'synthetic failure'); END")
            import sqlite3
            with self.assertRaises(sqlite3.IntegrityError):
                store.configure_auto('synthetic', False, 0, 'scope')
            self.assertEqual(store.get_task('synthetic').get('control_revision', 0), 0)
            self.assertEqual(store.get('auto_preferences'), {'unrelated': False})
            self.assertEqual(store.db.execute('SELECT count(*) FROM requests').fetchone()[0], 0)
            self.assertFalse(store.db.in_transaction)
