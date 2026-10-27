from platform_support import open_lock, lock_file
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
import io
import signal
import subprocess
import sys
import time
from unittest import mock

import app_host
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

    def test_reopening_preserves_existing_config_rules_and_runtime_rule_overrides(self):
        directory = self.root / 'app'
        path = make_config(directory, self.root / 'home', 10001)
        config = json.loads(path.read_text())
        config.update(poll_seconds=90, near_limit_poll_seconds=15, ui_poll_seconds=8)
        path.write_text(json.dumps(config))
        store = Store(directory / 'state')
        from rules import update_rules, effective_config
        update_rules(store, config, {'poll_seconds': 120, 'ui_poll_seconds': 9}, 0)
        store.put('supervisor_paused', True)
        store.close()
        reopened = load_config(make_config(directory, self.root / 'home', 10002))
        self.assertEqual(reopened['poll_seconds'], 90)
        self.assertEqual(reopened['ui_poll_seconds'], 8)
        self.assertEqual(reopened['ui_port'], 10002)
        store = Store(directory / 'state')
        try:
            self.assertEqual(effective_config(store, reopened)['poll_seconds'], 120)
            self.assertEqual(effective_config(store, reopened)['ui_poll_seconds'], 9)
            self.assertTrue(store.get('supervisor_paused'))
        finally:
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

    def test_windows_preflight_stops_before_executor_for_unwritable_existing_data(self):
        for relative in ('native-preferences.json', 'state/guardian.sqlite3'):
            with self.subTest(relative=relative):
                directory = self.root / relative.replace('/', '-')
                marker = directory / relative
                marker.parent.mkdir(parents=True)
                marker.write_bytes(b'preserve existing private bytes')
                original_open = Path.open
                def checked_open(path, mode='r', *args, **kwargs):
                    if path == marker and mode == 'r+b':
                        raise PermissionError('fixture existing file ACL')
                    return original_open(path, mode, *args, **kwargs)
                with mock.patch('app_host.IS_WINDOWS', True), \
                        mock.patch.object(Path, 'open', checked_open), \
                        mock.patch('platform_support.open_lock') as lock, \
                        mock.patch('app_host.run_owned') as owned, \
                        mock.patch('app_host.subprocess.Popen') as child:
                    with self.assertRaisesRegex(RuntimeError, 'app_data_not_writable'):
                        app_host.run(directory)
                lock.assert_not_called()
                owned.assert_not_called()
                child.assert_not_called()
                self.assertEqual(marker.read_bytes(), b'preserve existing private bytes')
                self.assertFalse((directory / 'config.json').exists())

    def test_windows_preflight_reports_uncreatable_directory_before_executor(self):
        with mock.patch('app_host.IS_WINDOWS', True), \
                mock.patch('app_host.private_directory', side_effect=PermissionError('fixture parent ACL')), \
                mock.patch('app_host.run_owned') as owned:
            with self.assertRaisesRegex(RuntimeError, 'app_data_not_writable.*restore write access'):
                app_host.run(self.root / 'blocked')
        owned.assert_not_called()

    def test_mac_startup_does_not_gain_windows_write_preflight(self):
        with mock.patch('app_host.IS_WINDOWS', False), \
                mock.patch('app_host.preflight_application_data') as preflight, \
                mock.patch('app_host.run_owned', return_value='existing Mac behavior') as owned:
            self.assertEqual(app_host.run(self.root, False), 'existing Mac behavior')
        preflight.assert_not_called()
        owned.assert_called_once_with(self.root, False, None)

    def test_legacy_shared_service_is_only_detached_on_stop_or_eof(self):
        existing = {'url': 'http://127.0.0.1:54321', 'external': True, 'owned': False,
                    'state_dir': str(self.root / 'shared'), 'config': str(self.root / 'shared/config.json')}
        for text in ('stop\n', ''):
            with self.subTest(text=text), mock.patch('app_host.IS_WINDOWS', False), \
                    mock.patch('app_host.legacy_service', return_value=existing), \
                    mock.patch('app_host.sys.stdin', io.StringIO(text)), \
                    mock.patch('app_host.sys.stdout', io.StringIO()), \
                    mock.patch('app_host.subprocess.run') as command, \
                    mock.patch('app_host.OwnedProcess') as owned:
                app_host.run_owned(self.root)
            command.assert_not_called()
            owned.assert_not_called()

    def test_busy_ledger_and_hung_http_cannot_block_shutdown_or_late_stop_new_owner(self):
        directory = self.root / 'app'
        make_config(directory, self.root / 'home')
        store = Store(directory / 'state')
        store.put('last_report', {'pid': 123})
        store.put('stop_requested', False)
        store.put('intent_marker', 'preserve')
        owner = mock.Mock()
        owner.process.pid = 123
        owner.process.poll.return_value = None
        owner.stop.return_value = {'forced': True, 'daemon_exit_code': -9, 'errors': []}
        release, ledger_done = threading.Event(), threading.Event()
        server = mock.Mock()
        server.shutdown.side_effect = lambda: release.wait(2)
        original_stop = app_host.request_owned_stop
        def stopped(*args):
            try:
                return original_stop(*args)
            finally:
                ledger_done.set()
        busy = sqlite3.connect(str(directory / 'state/guardian.sqlite3'))
        try:
            busy.execute('BEGIN IMMEDIATE')
            start = time.monotonic()
            with mock.patch('app_host.request_owned_stop', side_effect=stopped):
                result = app_host.shutdown_owned(owner, server, directory, budget=.1, grace_seconds=0)
            self.assertLess(time.monotonic() - start, .5)
            self.assertIn('http_shutdown_timeout', result['errors'])
            # A replacement owner's false flag must survive a cancelled worker.
            busy.execute("INSERT OR REPLACE INTO kv VALUES('stop_requested','false')")
            busy.commit()
            self.assertTrue(ledger_done.wait(1))
            self.assertFalse(store.get('stop_requested'))
            self.assertEqual(store.get('intent_marker'), 'preserve')
        finally:
            busy.close(); store.close(); release.set()

    def test_stop_flag_requires_our_live_reported_daemon(self):
        make_config(self.root / 'app', self.root / 'home')
        store = Store(self.root / 'app/state')
        try:
            store.put('last_report', {'pid': 456})
            process = mock.Mock(pid=123)
            process.poll.return_value = None
            self.assertFalse(app_host.request_owned_stop(self.root / 'app', process, threading.Event()))
            self.assertIsNone(store.get('stop_requested'))
            store.put('last_report', {'pid': 123})
            self.assertTrue(app_host.request_owned_stop(self.root / 'app', process, threading.Event()))
            self.assertTrue(store.get('stop_requested'))
        finally:
            store.close()

    def run_isolated_host_quit(self, use_signal=False, use_eof=False):
        fixture = self.root / 'hanging-rpc.py'
        marker = self.root / 'pids.json'
        fixture.write_text(
            'import json,os,signal,subprocess,sys,time\nfrom pathlib import Path\n'
            'signal.signal(signal.SIGTERM,signal.SIG_IGN)\n'
            "child=subprocess.Popen([sys.executable,'-c','import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(90)'])\n"
            "marker=Path(sys.argv[1]);temporary=marker.with_suffix('.tmp')\n"
            'temporary.write_text(json.dumps([os.getpid(),child.pid]));temporary.replace(marker)\n'
            'while True:time.sleep(.1)\n')
        launcher = self.root / 'host-fixture.py'
        launcher.write_text(
            'import sys\nfrom pathlib import Path\n'
            'sys.path.insert(0,sys.argv[1])\nimport app_host\n'
            'original=app_host.OwnedProcess\n'
            'app_host.OwnedProcess=lambda script,args,**kw:original(Path(sys.argv[3]),[sys.argv[4]],**kw)\n'
            'app_host.run_owned(Path(sys.argv[2]),attach=False,home=Path(sys.argv[2])/"fake-home")\n')
        process = subprocess.Popen([sys.executable, str(launcher), str(app_host.ROOT), str(self.root / 'isolated'),
                                    str(fixture), str(marker)], stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 5
            while not marker.exists() and time.monotonic() < deadline and process.poll() is None:
                time.sleep(.02)
            self.assertTrue(marker.exists(), 'Isolated host did not release its test fixture')
            pids = json.loads(marker.read_text())
            start = time.monotonic()
            if use_signal:
                process.send_signal(signal.SIGTERM)
                output, error = process.communicate(timeout=6)
            else:
                output, error = process.communicate(b'' if use_eof else b'stop\n', timeout=6)
            self.assertLess(time.monotonic() - start, 6)
            if not use_signal or sys.platform != 'win32':
                self.assertIn(b'host_exit', error)
            for pid in pids:
                end = time.monotonic() + 2
                while time.monotonic() < end:
                    if sys.platform == 'win32':
                        ended = not process_alive(pid)
                    else:
                        state = subprocess.run(['ps', '-p', str(pid), '-o', 'stat='], capture_output=True, text=True).stdout.strip()
                        ended = not state or state.startswith('Z')
                    if ended:
                        break
                    time.sleep(.02)
                self.assertTrue(ended, 'An isolated owned fixture survived host exit')
        finally:
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=2)

    def test_stdin_quit_reaps_hung_owned_rpc_within_six_seconds(self):
        self.run_isolated_host_quit()

    def test_signal_quit_reaps_only_owned_fixture_family(self):
        self.run_isolated_host_quit(use_signal=True)

    def test_parent_eof_reaps_hung_owned_rpc_within_six_seconds(self):
        self.run_isolated_host_quit(use_eof=True)
