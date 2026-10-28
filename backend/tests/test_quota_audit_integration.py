"""Exercise the actual sampling loop with an isolated service and ledger."""
import asyncio
import contextlib
import io
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest import mock

from guardian import Store, run
from test_guardian import CONFIG


class SamplingAuditTests(unittest.TestCase):
    def test_recovery_is_recorded_without_tasks_control_or_notifications(self):
        now = time.time()

        def response(remaining, weekly, reset):
            return {'ordinaryUsageAllowed': True, 'rateLimitsByLimitId': {'codex': {
                'primary': {'usedPercent': 100 - remaining, 'windowDurationMins': 300, 'resetsAt': reset},
                'secondary': {'usedPercent': 100 - weekly, 'windowDurationMins': 10080,
                              'resetsAt': reset + 604800}}},
                'rateLimitResetCredits': {'availableCount': 1, 'credits': [
                    {'id': 'demo-credit', 'status': 'available', 'resetType': 'codexRateLimits',
                     'expiresAt': now + 86400}]}}

        calls = []
        replies = [response(50, 5, now + 10000), response(95, 99, now + 18000)]

        class Service:
            account_display = None

            async def start(self):
                pass

            async def close(self):
                pass

            async def call(self, method):
                calls.append(method)
                return replies[0]

        with tempfile.TemporaryDirectory() as directory:
            config = dict(CONFIG, state_dir=directory, mode='notify', desktop_control_enabled=False,
                          quota_notifications=False, power_guard_enabled=False, server_command=['unused'])
            with contextlib.closing(Store(directory)) as store:
                store.put('supervisor_paused', True)
            with mock.patch('guardian.Rpc', return_value=Service()), \
                    mock.patch('guardian.identity_for', new=mock.AsyncMock(return_value='demo-scope')), \
                    mock.patch('guardian.deliver_notices', new=mock.AsyncMock()), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(asyncio.run(run(config, once=True)), 0)
                replies.pop(0)
                self.assertEqual(asyncio.run(run(config, once=True)), 0)
                # A separate process-style loop start must not log the same
                # service snapshot as another recovery.
                self.assertEqual(asyncio.run(run(config, once=True)), 0)
            with contextlib.closing(Store(directory)) as store:
                events = store.db.execute("SELECT * FROM events WHERE state='quota_restored'").fetchall()
                self.assertEqual(len(events), 1)
                self.assertIsNone(events[0]['thread_id'])
                detail = json.loads(events[0]['detail'])
                self.assertEqual(detail['category'], 'official_independent_reset')
                self.assertEqual(store.tasks(), [])
                self.assertTrue(store.get('supervisor_paused'))
                self.assertEqual(store.db.execute('SELECT count(*) FROM notices').fetchone()[0], 0)
                self.assertTrue((Path(directory) / 'status.json').exists())
            self.assertEqual(calls, ['account/rateLimits/read'] * 3)
