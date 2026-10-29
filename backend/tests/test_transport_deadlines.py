"""Backpressure regressions using in-memory writers, never live transports."""
import asyncio
from types import SimpleNamespace
import time
import unittest
from unittest import mock

from desktop import DesktopAdapter, DesktopIPC, DesktopError
from rpc import Rpc


class BlockedWriter:
    def write(self, data):
        pass

    def is_closing(self):
        return False

    def close(self):
        pass

    async def drain(self):
        await asyncio.Event().wait()

    async def wait_closed(self):
        await asyncio.Event().wait()


class TransportDeadlineTests(unittest.IsolatedAsyncioTestCase):
    async def test_quota_request_budget_includes_blocked_write(self):
        rpc = Rpc([], timeout=.03)
        rpc.process = SimpleNamespace(stdin=BlockedWriter())
        started = time.monotonic()
        with self.assertRaises(asyncio.TimeoutError):
            await asyncio.wait_for(rpc.call('initialize'), .5)
        self.assertLess(time.monotonic()-started, .35)
        self.assertEqual(rpc.pending, {})

    async def test_desktop_request_budget_includes_blocked_write(self):
        ipc = DesktopIPC(timeout=.03)
        ipc.writer = BlockedWriter()
        started = time.monotonic()
        with self.assertRaises(asyncio.TimeoutError):
            await asyncio.wait_for(ipc.call('initialize', {}), .8)
        self.assertLess(time.monotonic()-started, .7)
        self.assertEqual(ipc.pending, {})

    async def test_desktop_short_call_budget_overrides_long_default_write_budget(self):
        ipc = DesktopIPC(timeout=10)
        ipc.writer = BlockedWriter()
        started = time.monotonic()
        with self.assertRaises(asyncio.TimeoutError):
            await asyncio.wait_for(ipc.call('initialize', {}, timeout=.01), .9)
        self.assertLess(time.monotonic()-started, .8)
        self.assertEqual(ipc.pending, {})

    async def test_broadcast_write_is_bounded_without_a_request_future(self):
        ipc = DesktopIPC(timeout=.03)
        ipc.writer = BlockedWriter()
        started = time.monotonic()
        with self.assertRaises(asyncio.TimeoutError):
            await asyncio.wait_for(ipc.send({'type': 'broadcast'}), .5)
        self.assertLess(time.monotonic()-started, .35)

    async def test_desktop_close_cannot_wait_forever_for_a_stalled_peer(self):
        ipc = DesktopIPC()
        ipc.writer = BlockedWriter()
        await asyncio.wait_for(ipc.close(), 1.5)

    async def test_valid_slow_snapshot_uses_the_configured_transport_budget(self):
        ipc = DesktopAdapter(SimpleNamespace(changed=asyncio.Event()), {'rpc_timeout_seconds': 10}).ipc
        ipc.owners['synthetic'] = 'synthetic-owner'
        ipc.send = mock.AsyncMock()
        clock = [0.0]
        view = {'thread': {'status': {'type': 'idle'}},
                'turns': [{'id': 'synthetic-turn', 'started_at_ms': 1}]}

        async def advance_clock(_):
            clock[0] += .5
            if clock[0] == 6:
                ipc.snapshots['synthetic'] = [(1, clock[0], view)]

        with mock.patch('desktop.time.monotonic', side_effect=lambda: clock[0]), \
             mock.patch('desktop.asyncio.sleep', side_effect=advance_clock):
            self.assertEqual(await ipc.snapshot('synthetic'), view)

    async def test_missing_snapshot_still_expires_and_clears_its_owner(self):
        ipc = DesktopAdapter(SimpleNamespace(changed=asyncio.Event()), {'rpc_timeout_seconds': 10}).ipc
        ipc.owners['synthetic'] = 'synthetic-owner'
        ipc.send = mock.AsyncMock()
        clock = [0.0]

        async def advance_clock(_):
            clock[0] += .5

        with mock.patch('desktop.time.monotonic', side_effect=lambda: clock[0]), \
             mock.patch('desktop.asyncio.sleep', side_effect=advance_clock):
            with self.assertRaises(DesktopError):
                await ipc.snapshot('synthetic')
        self.assertNotIn('synthetic', ipc.owners)
        self.assertEqual(clock[0], 10)
