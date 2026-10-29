"""Real isolated process trees; no desktop, credentials or quota calls."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

import owned_process
from owned_process import OwnedProcess
from platform_support import process_alive


def stopped(pid):
    if os.name == 'nt':
        return not process_alive(pid)
    result = subprocess.run(['ps', '-p', str(pid), '-o', 'stat='], capture_output=True, text=True)
    return not result.stdout.strip() or result.stdout.strip().startswith('Z')


class OwnedProcessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.marker = self.root / 'pids.json'
        self.script = self.root / 'fixture.py'
        self.script.write_text(
            "import json,os,signal,subprocess,sys,time\nfrom pathlib import Path\n"
            "signal.signal(signal.SIGTERM,signal.SIG_IGN)\n"
            "child=subprocess.Popen([sys.executable,'-c',"
            "'import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(90)'])\n"
            "marker=Path(sys.argv[1]);temporary=marker.with_suffix('.tmp')\n"
            "temporary.write_text(json.dumps({'parent':os.getpid(),'child':child.pid}));temporary.replace(marker)\n"
            "if len(sys.argv)>2:os._exit(0)\n"
            "while True:time.sleep(.1)\n", encoding='utf-8')

    def tearDown(self):
        self.temp.cleanup()

    def launched(self, exit_leader=False):
        args = [self.marker] + (['exit'] if exit_leader else [])
        owner = OwnedProcess(self.script, args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(lambda: owner.stop(deadline=time.monotonic() + 1, grace_seconds=0)
                        if not owner.job or owner.job.handle else None)
        end = time.monotonic() + 5
        while not self.marker.exists() and time.monotonic() < end:
            if owner.process.poll() is not None and not self.marker.exists():
                self.fail('Fixture exited before writing its process IDs')
            time.sleep(.02)
        self.assertTrue(self.marker.exists())
        # The atomicity of a fixture's tiny write is not part of process cleanup.
        for _ in range(30):
            try:
                return owner, json.loads(self.marker.read_text())
            except ValueError:
                time.sleep(.01)
        self.fail('Fixture process IDs were not readable')

    def assert_stopped(self, *pids):
        end = time.monotonic() + 2
        while time.monotonic() < end and not all(stopped(pid) for pid in pids):
            time.sleep(.02)
        self.assertTrue(all(stopped(pid) for pid in pids), 'Only fixture processes should have exited')

    def test_hung_owned_parent_and_rpc_are_killed_within_budget(self):
        owner, ids = self.launched()
        started = time.monotonic()
        result = owner.stop(deadline=started + 1.5, grace_seconds=.05)
        self.assertLess(time.monotonic() - started, 1.8)
        self.assertTrue(result['forced'])
        self.assert_stopped(ids['parent'], ids['child'])

    def test_rpc_is_cleaned_even_if_its_leader_already_exited(self):
        owner, ids = self.launched(exit_leader=True)
        owner.process.wait(timeout=2)
        owner.stop(deadline=time.monotonic() + 1.5, grace_seconds=0)
        self.assert_stopped(ids['parent'], ids['child'])

    def test_unrelated_process_with_same_python_executable_is_not_signalled(self):
        outsider = subprocess.Popen([sys.executable, '-c', 'import time;time.sleep(90)'],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            owner, ids = self.launched()
            owner.stop(deadline=time.monotonic() + 1.5, grace_seconds=0)
            self.assert_stopped(ids['parent'], ids['child'])
            self.assertIsNone(outsider.poll())
        finally:
            outsider.kill()
            outsider.wait(timeout=2)

    def test_bootstrap_eof_cannot_run_the_fixture(self):
        result = subprocess.run([sys.executable, '-I', owned_process.__file__, '--bootstrap',
                                 str(self.script), str(self.marker)], stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.marker.exists())

    def test_owned_interpreter_preserves_writable_resource_tree(self):
        module = self.root/'cold_module.py'
        module.write_text('value=42\n')
        script = self.root/'import_probe.py'
        script.write_text('import sys\nfrom pathlib import Path\n'
                          'sys.path.insert(0,str(Path(__file__).parent))\n'
                          'import cold_module\nassert cold_module.value==42\n'
                          'assert sys.dont_write_bytecode\n')
        owner = OwnedProcess(script, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        try:
            owner.process.wait(timeout=5)
            error = owner.process.stderr.read()
            self.assertEqual(owner.process.returncode, 0, error)
            self.assertFalse(list(self.root.rglob('*.pyc')))
        finally:
            owner.process.stderr.close()
            owner.stop(deadline=time.monotonic()+1, grace_seconds=0)

    def test_job_assignment_failure_never_releases_the_startup_gate(self):
        job = mock.Mock()
        job.assign.side_effect = PermissionError('isolated assignment denied')
        original = subprocess.Popen
        started = []
        def launch(*args, **kwargs):
            if os.name != 'nt':
                kwargs.pop('creationflags', None)
                kwargs['start_new_session'] = True
            process = original(*args, **kwargs)
            started.append(process)
            return process
        with mock.patch('owned_process.IS_WINDOWS', True), \
                mock.patch('owned_process.WindowsJob', return_value=job), \
                mock.patch.object(subprocess, 'CREATE_NO_WINDOW', 0, create=True), \
                mock.patch('owned_process.subprocess.Popen', side_effect=launch):
            with self.assertRaises(PermissionError):
                OwnedProcess(self.script, [self.marker], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.assertFalse(self.marker.exists())
        self.assertIsNotNone(started[0].poll())
        job.close.assert_called_once()

    @unittest.skipUnless(os.name == 'nt', 'Windows kill-on-job-close')
    def test_closing_windows_job_handle_reaps_parent_and_rpc(self):
        owner, ids = self.launched()
        owner.job.close()
        owner.process.wait(timeout=2)
        self.assert_stopped(ids['parent'], ids['child'])
