from platform_support import open_lock, lock_file
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest

from app_host import legacy_service, make_config, migrate_legacy, read_host_input
from guardian import Store, load_config, process_alive


class PackagingHostTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_fresh_install_has_portable_paused_private_state(self):
        path = make_config(self.root / "app", self.root / "home", 54321, 123)
        config = load_config(path)
        self.assertEqual(config["ui_port"], 54321)
        self.assertTrue(config["native_notifications"])
        self.assertFalse(config["power_guard_enabled"])
        self.assertTrue(config["desktop_database"].startswith(str(self.root / "home")))
        store = Store(config["state_dir"])
        self.assertTrue(store.get("supervisor_paused"))
        self.assertEqual(store.tasks(), [])
        store.close()

    def test_existing_service_is_attached_without_writes_or_second_executor(self):
        state = self.root / ".codex/usage-guardian/state"
        state.mkdir(parents=True)
        (state / "ui-8769.json").write_text(json.dumps({"url": "http://127.0.0.1:8769"}))
        with open_lock(state / "daemon.lock") as daemon, open_lock(state / "ui-8769.lock") as ui:
            lock_file(daemon)
            lock_file(ui)
            result = legacy_service(self.root)
            self.assertTrue(result["external"])
            self.assertFalse(result["owned"])
            self.assertEqual(result["url"], "http://127.0.0.1:8769")

    def test_migration_refuses_live_source_or_existing_destination(self):
        source = self.root / ".codex/usage-guardian/state"
        old = Store(source)
        old.put("sent_marker", "do-not-replay")
        old.close()
        target = self.root / "app"
        with open_lock(source / "daemon.lock") as lock:
            lock_file(lock)
            with self.assertRaises(RuntimeError): migrate_legacy(target, self.root)
        migrate_legacy(target, self.root)
        copied = Store(target / "state")
        self.assertEqual(copied.get("sent_marker"), "do-not-replay")
        copied.close()
        with self.assertRaises(RuntimeError): migrate_legacy(target, self.root)

    def test_missing_host_process_is_detected(self):
        self.assertFalse(process_alive(-999999999))

    def test_host_ignores_non_stop_input_without_stopping_backend(self):
        stop, detail = threading.Event(), {}
        def messages():
            yield '\n'
            self.assertFalse(stop.is_set())
            yield 'status\n'
            self.assertFalse(stop.is_set())
            yield 'stop\n'
            self.fail('Host continued reading after explicit stop')
        read_host_input(messages(), stop, detail)
        self.assertTrue(stop.is_set())
        self.assertEqual(detail['reason'], 'requested')

    def test_parent_eof_stops_host_with_an_explicit_diagnostic_reason(self):
        stop, detail = threading.Event(), {}
        read_host_input(iter(()), stop, detail)
        self.assertTrue(stop.is_set())
        self.assertEqual(detail['reason'], 'parent_input_closed')
