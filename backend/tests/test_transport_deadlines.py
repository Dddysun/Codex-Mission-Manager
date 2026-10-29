"""Backpressure regressions using in-memory writers, never live transports."""
import asyncio
from types import SimpleNamespace
import time
import unittest

from desktop import DesktopIPC
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
