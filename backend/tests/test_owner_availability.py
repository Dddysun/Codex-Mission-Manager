"""Absent conversation owners are distinct from transport or snapshot failure."""
import asyncio
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from desktop import DesktopAdapter, DesktopError, DesktopIPC, DesktopOwnerUnavailable
from guardian import Controller, Store
from test_guardian import CONFIG, FakeRpc, NOW, sample


class OwnerProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_negative_reply_has_time_to_arrive_and_a_specific_type(self):
        ipc = DesktopIPC()
        requests = []
        async def reply(value):
            requests.append(value)
            ipc.pending[value['requestId']].set_result({
                'resultType': 'error', 'error': 'no-client-found'})
        ipc.send = reply
        with self.assertRaises(DesktopOwnerUnavailable):
            await ipc.owner('fixture-unopened')
        self.assertGreater(requests[0]['timeoutMs'], 10_000,
                           'Supported router may finish a negative discovery after ten seconds')
        self.assertEqual(ipc.pending, {})

    async def test_other_router_errors_remain_errors(self):
        ipc = DesktopIPC()
        async def reply(value):
            ipc.pending[value['requestId']].set_result({
                'resultType': 'error', 'error': 'protocol-version-mismatch'})
        ipc.send = reply
        with self.assertRaises(DesktopError) as result:
            await ipc.owner('fixture')
        self.assertNotIsInstance(result.exception, DesktopOwnerUnavailable)

    async def test_silence_remains_timeout_not_unopened(self):
        ipc = DesktopIPC()
        ipc.send = mock.AsyncMock()
        with self.assertRaises(asyncio.TimeoutError):
            await ipc.owner('fixture', timeout=.01)
        self.assertEqual(ipc.pending, {})


class UnloadedAdapterTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        quota = FakeRpc()
        quota.changed = asyncio.Event()
        self.adapter = DesktopAdapter(quota, dict(CONFIG, desktop_database='/nonexistent/fixture.sqlite'))
        self.adapter.control_available = True
        self.adapter.ipc.snapshot = mock.AsyncMock(side_effect=DesktopOwnerUnavailable('not loaded'))

    async def test_definitive_absence_is_cached_without_old_view(self):
        self.adapter.views['one'] = {'thread': {'status': {'type': 'active'}}}
        for _ in range(2):
            with self.assertRaises(DesktopOwnerUnavailable):
                await self.adapter.call('thread/read', {'threadId': 'one'})
        self.assertEqual(self.adapter.ipc.snapshot.await_count, 1)
        self.assertNotIn('one', self.adapter.views)

    async def test_connection_loss_is_not_hidden_by_absence_cache(self):
        self.adapter.unloaded.add('one')
        self.adapter.ipc.disconnected = True
        self.adapter.ipc.last_error = 'fixture disconnected'
        with self.assertRaises(DesktopError) as result:
            await self.adapter.call('thread/read', {'threadId': 'one'})
        self.assertNotIsInstance(result.exception, DesktopOwnerUnavailable)

    async def test_expired_negative_discovery_can_find_a_new_owner(self):
        self.adapter.hosts['one'] = 'local'
        self.adapter.unloaded.add('one')
        self.adapter.discovery_signatures['one'] = (None, -1000)
        async def found(tid, host, timeout):
            self.adapter.ipc.owners[tid] = 'fixture-owner'
            return 'fixture-owner'
        self.adapter.ipc.owner = found
        self.assertEqual(await self.adapter.discover(), ['one'])
        self.assertNotIn('one', self.adapter.unloaded)

    async def test_absence_cache_expires_even_outside_directory_candidates(self):
        self.adapter.unloaded.add('older-managed-chat')
        self.adapter.discovery_signatures['older-managed-chat'] = (None, -1000)
        self.adapter.ipc.snapshot.return_value = {'thread': {'status': {'type': 'idle'}}}
        self.adapter.ipc.snapshot.side_effect = None
        result = await self.adapter.call('thread/read', {'threadId': 'older-managed-chat'})
        self.assertEqual(result['thread']['status']['type'], 'idle')
        self.assertNotIn('older-managed-chat', self.adapter.unloaded)


class UnloadedControllerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(self.temp.name)
        self.rpc = FakeRpc()
        self.controller = Controller(self.rpc, self.store, CONFIG, 'scope-one', clock=lambda: NOW)
        await self.controller.adopt('one')
        self.original = self.rpc.call

    async def asyncTearDown(self):
        self.store.close()
        self.temp.cleanup()

    def fail_read(self, error):
        async def call(method, params=None):
            if method == 'thread/read':
                raise error
            return await self.original(method, params)
        self.rpc.call = call

    async def test_monitoring_unopened_chat_never_sends_or_pauses(self):
        self.fail_read(DesktopOwnerUnavailable('not loaded'))
        await self.controller.tick(sample())
        self.assertEqual(self.store.get('task_errors'), {})
        self.assertEqual(self.store.get('task_runtime')['one']['status'], {'type': 'notLoaded'})
        task = self.store.get_task('one')
        self.assertEqual(task['state'], 'watching')
        self.assertTrue(task.get('auto_resume', True))
        self.assertEqual(self.rpc.count('turn/start'), 0)
        self.assertEqual(self.rpc.count('turn/interrupt'), 0)
        self.rpc.call = self.original
        await self.controller.tick(sample(remaining=98, reset=NOW + 18000))
        self.assertEqual(self.store.get('task_runtime')['one']['status']['type'], 'active')

    async def test_real_timeout_still_requires_attention(self):
        self.fail_read(asyncio.TimeoutError())
        await self.controller.tick(sample())
        self.assertEqual(self.store.get('task_errors')['one']['type'], 'TimeoutError')
        self.assertNotIn('one', self.store.get('task_runtime'))

    async def test_missing_owner_does_not_clear_unconfirmed_send(self):
        task = self.store.get_task('one')
        task.update(state='resume_intent', action_id='fixture-action')
        self.store.save_task(task)
        self.fail_read(DesktopOwnerUnavailable('not loaded'))
        await self.controller.tick(sample())
        self.assertEqual(self.store.get_task('one')['state'], 'resume_intent')
        self.assertIn('one', self.store.get('task_errors'))
        self.assertEqual(self.rpc.count('turn/start'), 0)
