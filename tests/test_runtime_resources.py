"""Portable verifier regressions; no signed app, desktop or private state."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

spec = importlib.util.spec_from_file_location('runtime_verifier',
    Path(__file__).resolve().parents[1]/'scripts/verify_dmg.py')
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


class RuntimeResourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.app = Path(self.temp.name)/'TokenMax.app'
        resources = self.app/'Contents/Resources'
        resources.mkdir(parents=True)
        (resources/'marker').write_text('sealed fixture')
        self.receipt = json.dumps({'bytecode_disabled': True, 'private_data_loaded': False})

    def test_writable_copy_is_checked_after_both_interpreters(self):
        with mock.patch.object(verifier.subprocess, 'check_output', return_value=self.receipt) as imports, \
                mock.patch.object(verifier.subprocess, 'run') as signature:
            report = verifier.verify_writable_runtime(self.app)
        self.assertEqual(imports.call_count, 2)
        self.assertTrue(report['resources_unchanged'])
        self.assertTrue(report['signature_integrity_after_imports'])
        signature.assert_called_once()
        self.assertEqual((self.app/'Contents/Resources/marker').read_text(), 'sealed fixture')

    def test_new_cache_invalidates_the_writable_copy_check(self):
        def import_and_write(command, **kwargs):
            if '--self-test' in command:
                copied_resources = Path(command[-2]).parent.parent
                cache = copied_resources/'backend/__pycache__/cold.pyc'
                cache.parent.mkdir(parents=True)
                cache.write_bytes(b'unexpected bytecode')
            return self.receipt
        with mock.patch.object(verifier.subprocess, 'check_output', side_effect=import_and_write), \
                mock.patch.object(verifier.subprocess, 'run') as signature:
            with self.assertRaisesRegex(RuntimeError, 'modified application resources'):
                verifier.verify_writable_runtime(self.app)
        signature.assert_not_called()
        self.assertFalse(list(self.app.rglob('*.pyc')))

    def test_owned_child_must_confirm_no_bytecode(self):
        with mock.patch.object(verifier.subprocess, 'check_output', side_effect=[
                self.receipt, json.dumps({'bytecode_disabled': False})]):
            with self.assertRaisesRegex(RuntimeError, 'Owned interpreter'):
                verifier.verify_writable_runtime(self.app)
