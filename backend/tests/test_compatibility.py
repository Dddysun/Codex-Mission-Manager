"""Compatibility policy checks with synthetic app metadata only."""
import os
import plistlib
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from compatibility import desktop_compatibility, require_supported


@unittest.skipIf(os.name == "nt", "macOS plist compatibility profiles have separate Windows checks")
class CompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'Info.plist'

    def metadata(self,build):
        self.path.write_bytes(plistlib.dumps({'CFBundleVersion':build,'CFBundleShortVersionString':'fixture'}))
        return desktop_compatibility(self.path)

    def test_known_builds_share_explicit_protocol_profile_and_validation_level(self):
        old=self.metadata('20770')
        current=self.metadata('21828')
        self.assertTrue(old['supported'])
        self.assertTrue(current['supported'])
        self.assertEqual(current['profile'],{'snapshot':11,'start_turn':2,'interrupt_turn':4})
        self.assertEqual(old['profile'],current['profile'])
        self.assertTrue(old['live_control_tested'])
        self.assertFalse(current['live_control_tested'])

    def test_unknown_build_is_never_assumed_supported(self):
        value=self.metadata('99999')
        self.assertFalse(value['supported'])
        self.assertEqual(value['status'],'update_required')
        self.assertIsNone(value['profile'])
        with mock.patch('compatibility.APP_INFO',self.path):
            with self.assertRaisesRegex(RuntimeError,'99999'):
                require_supported()

    def test_missing_or_invalid_client_is_explicitly_unknown(self):
        self.assertEqual(desktop_compatibility(self.path)['status'],'client_missing')
        self.path.write_text('not a plist')
        self.assertFalse(desktop_compatibility(self.path)['supported'])
        self.assertEqual(desktop_compatibility(self.path)['status'],'client_missing')

    def test_current_metadata_is_rechecked_between_calls(self):
        self.metadata('21828')
        with mock.patch('compatibility.APP_INFO',self.path):
            self.assertEqual(require_supported()['build'],'21828')
            self.metadata('99999')
            with self.assertRaises(RuntimeError):require_supported()
