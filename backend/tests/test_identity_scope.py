"""Stable account namespaces and one-time migration of isolated V0.2 ledgers."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from guardian import Store, fingerprint
from identity_scope import stable_account_scope


IDENTITY = {"type": "chatgpt", "email": "fixture@example.invalid", "workspace": "workspace-fixture", "plan": "plus"}


class AccountScopeTests(unittest.TestCase):
    def test_subscription_changes_do_not_create_a_different_account(self):
        expected = stable_account_scope(IDENTITY)
        for plan in ("free", "go", "plus", "pro", "business", "enterprise", "edu", "future-plan", None):
            self.assertEqual(stable_account_scope(dict(IDENTITY, plan=plan)), expected)

    def test_different_account_workspace_or_auth_type_never_share_scope(self):
        expected = stable_account_scope(IDENTITY)
        for field, value in (("email", "other@example.invalid"), ("workspace", "other-workspace"), ("type", "apiKey")):
            self.assertNotEqual(stable_account_scope(dict(IDENTITY, **{field: value})), expected)

    def fixture(self, store, old):
        task = {"id": "one", "name": "Fixture", "scope": old, "state": "paused", "priority": 10,
                "manual_hold": True, "auto_resume": False, "control_revision": 7,
                "pause_sample": {"scope": old, "windows": {"primary": {"minutes": 300, "remaining": 8, "reset": 2000000300}}}}
        store.save_task(task)
        store.save_task({"id": "other", "name": "Unrelated fixture", "scope": "unrelated-scope", "state": "watching"})
        plan = {"id": "fixture-plan", "key": "codex:local:one", "thread_id": "one", "scope": old,
                "state": "needs_review", "prompt": "Keep the exact user instruction", "revision": 9,
                "armed_window_reset": 2000000300, "anchor_turn_id": "original-one"}
        with store.db:
            store.db.execute("INSERT INTO plans VALUES(?,?)", (plan["key"], json.dumps(plan)))
        request = store.enqueue("pause_all", {"scope": old, "ids": ["one"], "nested": [{"scope": old}]})
        with store.db:
            store.db.execute("UPDATE requests SET state='unknown',result=? WHERE id=?",
                             (json.dumps({"scope": old, "reason": "do not replay"}), request))
        store.put("last_report", {"quota": {"scope": old}, "phase": "normal"})
        store.put("last_low", {"scope": old, "windows": {}})
        store.put("chat_catalog", {"scope": old, "items": [{"id": "one", "scope": old}]})
        store.put("account_display", {"account": {"plan_type": "plus"}})
        return task, plan, request

    def test_same_account_legacy_scope_migration_preserves_all_control_intents(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(directory)
            try:
                old = fingerprint(IDENTITY)
                task, plan, request = self.fixture(store, old)
                before_events = store.db.execute("SELECT count(*) FROM events").fetchone()[0]
                scope = stable_account_scope(dict(IDENTITY, plan="pro"), store)
                expected_task = copy.deepcopy(task)
                expected_task["scope"] = scope
                expected_task["pause_sample"]["scope"] = scope
                self.assertEqual(store.get_task("one"), expected_task)
                self.assertEqual(store.get_task("other")["scope"], "unrelated-scope")
                actual_plan = json.loads(store.db.execute("SELECT value FROM plans").fetchone()[0])
                self.assertEqual(actual_plan, dict(plan, scope=scope))
                row = store.db.execute("SELECT * FROM requests WHERE id=?", (request,)).fetchone()
                self.assertEqual(row["id"], request)
                self.assertEqual(row["state"], "unknown")
                self.assertEqual(json.loads(row["value"]), {"scope": scope, "ids": ["one"], "nested": [{"scope": scope}]})
                self.assertEqual(json.loads(row["result"]), {"scope": scope, "reason": "do not replay"})
                self.assertEqual(store.get("last_report")["quota"]["scope"], scope)
                self.assertEqual(store.get("last_low")["scope"], scope)
                self.assertEqual(store.get("chat_catalog")["items"][0]["scope"], scope)
                self.assertEqual(store.db.execute("SELECT count(*) FROM events").fetchone()[0], before_events)
            finally:
                store.close()

    def test_unrelated_account_legacy_hash_is_not_migrated(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(directory)
            try:
                old = fingerprint(dict(IDENTITY, email="another@example.invalid"))
                task, plan, request = self.fixture(store, old)
                scope = stable_account_scope(IDENTITY, store)
                self.assertNotEqual(scope, old)
                self.assertEqual(store.get_task("one"), task)
                self.assertEqual(json.loads(store.db.execute("SELECT value FROM plans").fetchone()[0]), plan)
                self.assertEqual(store.get("last_report")["quota"]["scope"], old)
                self.assertIsNone(store.get("account_scope_migration_v2"))
            finally:
                store.close()

    def test_legacy_known_plan_hashes_migrate_only_for_current_verified_account(self):
        for plan in ("free", "go", "plus", "pro", "team", "business", "enterprise", "edu", None):
            with self.subTest(plan=plan), tempfile.TemporaryDirectory() as directory:
                store = Store(directory)
                try:
                    old = fingerprint(dict(IDENTITY, plan=plan))
                    self.fixture(store, old)
                    scope = stable_account_scope(dict(IDENTITY, plan="pro"), store)
                    self.assertEqual(store.get_task("one")["scope"], scope)
                finally:
                    store.close()

    def test_migration_is_idempotent_and_does_not_rearm_or_add_requests(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(directory)
            try:
                self.fixture(store, fingerprint(IDENTITY))
                expected = stable_account_scope(IDENTITY, store)
                before = list(store.db.iterdump())
                self.assertEqual(stable_account_scope(dict(IDENTITY, plan="pro"), store), expected)
                self.assertEqual(list(store.db.iterdump()), before)
                self.assertEqual(store.db.execute("SELECT count(*) FROM requests").fetchone()[0], 1)
            finally:
                store.close()
