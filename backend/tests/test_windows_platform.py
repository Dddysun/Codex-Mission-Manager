"""Portable safety checks; fixtures never connect to the installed desktop."""
import asyncio
from contextlib import closing
import ctypes
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest import mock

import platform_support
from platform_support import lock_file, lock_held, open_lock, process_alive, python_command, sqlite_ro_uri
from compatibility import WINDOWS_PROFILES, windows_compatibility
from desktop import DesktopAdapter, DesktopError
from catalog import entry
from plans import get_plan, set_plan
from test_guardian import sample
import test_ui


class PlatformSafetyTests(unittest.TestCase):
    def test_instance_lock_is_exclusive_and_released_on_close(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)/'instance.lock'
            self.assertFalse(lock_held(path))
            with open_lock(path) as first:
                lock_file(first)
                self.assertTrue(lock_held(path))
            self.assertFalse(lock_held(path))

    def test_safe_current_process_query_and_invalid_ids(self):
        self.assertTrue(process_alive(os.getpid()))
        for pid in (-1, 0, None, 'bad'):
            self.assertFalse(process_alive(pid))

    def test_windows_process_query_never_sends_a_signal(self):
        kernel = mock.Mock()
        kernel.OpenProcess.return_value = 123
        kernel.WaitForSingleObject.return_value = 258
        with mock.patch('platform_support.os.name','nt'), mock.patch('platform_support.os.kill') as kill, \
                mock.patch('ctypes.WinDLL',return_value=kernel,create=True):
            self.assertTrue(process_alive(456))
        kill.assert_not_called()
        kernel.OpenProcess.assert_called_once_with(0x00100000, False, 456)
        kernel.CloseHandle.assert_called_once_with(123)

    def test_sqlite_uri_handles_spaces_and_reserved_characters(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)/'history space #%.sqlite'
            with closing(sqlite3.connect(path)) as db:
                db.execute('CREATE TABLE marker(value)')
                db.execute('INSERT INTO marker VALUES(42)')
                db.commit()
            with closing(sqlite3.connect(sqlite_ro_uri(path),uri=True)) as db:
                self.assertEqual(db.execute('SELECT value FROM marker').fetchone()[0],42)
                with self.assertRaises(sqlite3.OperationalError):
                    db.execute('INSERT INTO marker VALUES(43)')

    def test_python_child_explicitly_uses_utf8_and_isolation(self):
        command = python_command('worker.py','run',isolated=True)
        self.assertEqual(command[1:4],['-X','utf8','-I'])
        self.assertEqual(command[-2:],['worker.py','run'])

    def test_windows_profiles_do_not_inherit_mac_build_numbers(self):
        for version in ('20770','21828','future'):
            result = windows_compatibility({'version':version})
            self.assertFalse(result['supported'])
            self.assertEqual(result['status'],'update_required')
        self.assertEqual(windows_compatibility(None)['status'],'client_missing')


class WindowsMonitorTests(unittest.IsolatedAsyncioTestCase):
    async def test_unknown_desktop_profile_keeps_account_reads_and_blocks_mutation(self):
        class Quota:
            changed = asyncio.Event()
            async def start(self): pass
            async def close(self): pass
            async def call(self,method,params=None):
                self.last = method
                return {'account':{'type':'chatgpt'}}
        quota = Quota()
        adapter = DesktopAdapter(quota,{'desktop_control_enabled':True})
        with mock.patch('desktop.IS_WINDOWS',True), \
                mock.patch('compatibility.desktop_compatibility',return_value={'supported':False}):
            adapter.control_available = False
            await adapter.start()
            self.assertFalse(adapter.control_available)
            self.assertEqual(adapter.control_error,'desktop_version_not_verified')
            self.assertEqual(await adapter.call('account/read'),{'account':{'type':'chatgpt'}})
            with mock.patch('compatibility.require_supported',return_value={'supported':True}):
                with self.assertRaises(DesktopError):
                    await adapter.call('turn/interrupt',{'threadId':'fixture','turnId':'fixture'})
            await adapter.close()


class WindowsControlGateTests(unittest.TestCase):
    def setUp(self):
        test_ui.InterfaceTests.setUp(self)
        platform = mock.patch('ui.IS_WINDOWS',True)
        platform.start()
        self.addCleanup(platform.stop)
        compatibility = mock.patch('ui.desktop_compatibility',return_value={'supported':True,'status':'supported','build':'fixture'})
        compatibility.start()
        self.addCleanup(compatibility.stop)

    def tearDown(self):
        test_ui.InterfaceTests.tearDown(self)

    def request(self,*args,**kwargs):
        return test_ui.InterfaceTests.request(self,*args,**kwargs)

    def test_unverified_transport_leaves_quota_readable_but_controls_off(self):
        self.store.put('supervisor_paused',False)
        state = json.loads(self.request()[2])
        self.assertTrue(state['healthy'])
        self.assertFalse(state['control_available'])
        self.assertFalse(state['control_enabled'])
        self.assertFalse(state['tasks'][0]['can_control'])

    def test_forged_control_requests_cannot_bypass_backend_gate(self):
        for action in ('enable','release','set_auto','set_plan','execute_now','pause_all'):
            status,_,body = self.request('POST','/api/action',{'action':action,'revision':0,'enabled':True})
            self.assertEqual(status,409,action)
            self.assertIn('Windows',json.loads(body)['error'])
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM requests').fetchone()[0],0)

    def test_global_pause_remains_available_without_control_transport(self):
        status,_,_ = self.request('POST','/api/action',{'action':'pause','revision':0})
        self.assertEqual(status,200)
        self.assertTrue(self.store.get('supervisor_paused'))

    def cached_local_plan_without_backend(self):
        current = sample(remaining=98)
        current.update(scope='test', observed_at=1)
        chat = entry('task-1','Local fixture')
        old = set_plan(self.store,chat,True,'Keep the existing instruction',0,current)
        readonly = dict(chat,can_control=False)
        self.store.put('chat_catalog',{'scope':'test','items':[readonly]})
        self.store.put('last_report',{'quota':current})
        (self.store.directory/'status.json').write_text(json.dumps({
            'phase':'unknown','observed_at':1,'stage':'connect','control_available':False}),encoding='utf-8')
        task = self.store.get_task('task-1')
        task.update(auto_resume=True,manual_hold=False,control_revision=0)
        self.store.save_task(task)
        self.store.put('auto_preferences',{'task-1':True})
        self.lease.close()
        return chat,old

    def test_cached_same_account_plan_can_be_cancelled_without_backend(self):
        chat,old = self.cached_local_plan_without_backend()
        before_task = self.store.get_task(chat['id'])
        self.assertFalse(json.loads(self.request()[2])['healthy'])
        status,_,body = self.request('POST','/api/action',{'action':'set_plan','key':chat['key'],
            'enabled':False,'prompt':old['prompt'],'revision':old['revision']})
        self.assertEqual(status,200,body)
        cancelled = get_plan(self.store,chat['key'])
        self.assertEqual(cancelled['state'],'cancelled')
        self.assertEqual(cancelled['id'],old['id'])
        self.assertEqual(cancelled['scope'],old['scope'])
        self.assertEqual(cancelled['prompt'],old['prompt'])
        self.assertEqual(cancelled['revision'],old['revision']+1)
        self.assertEqual(self.store.get_task(chat['id']),before_task)
        self.assertFalse(self.store.get('chat_catalog')['items'][0]['can_control'])
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM requests').fetchone()[0],0)

    def test_cached_same_account_auto_permission_can_be_revoked_without_backend(self):
        chat,old = self.cached_local_plan_without_backend()
        (self.store.directory/'status.json').unlink()
        status,_,body = self.request('POST','/api/action',{'action':'set_auto','key':chat['key'],
            'enabled':False,'revision':0})
        self.assertEqual(status,200,body)
        task = self.store.get_task(chat['id'])
        self.assertFalse(task['auto_resume'])
        self.assertTrue(task['manual_hold'])
        self.assertFalse(self.store.get('auto_preferences')[chat['id']])
        self.assertEqual(get_plan(self.store,chat['key']),old)
        self.assertFalse(self.store.get('chat_catalog')['items'][0]['can_control'])
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM requests').fetchone()[0],0)

    def test_cached_cancellation_cannot_modify_another_account_plan(self):
        chat,old = self.cached_local_plan_without_backend()
        foreign = dict(old,scope='another-account')
        with self.store.db:
            self.store.db.execute('UPDATE plans SET value=? WHERE key=?',(json.dumps(foreign),chat['key']))
        status,_,_ = self.request('POST','/api/action',{'action':'set_plan','key':chat['key'],
            'enabled':False,'prompt':old['prompt'],'revision':old['revision']})
        self.assertEqual(status,409)
        self.assertEqual(get_plan(self.store,chat['key']),foreign)

    def test_cached_revocation_requires_a_verified_account_scope(self):
        chat,old = self.cached_local_plan_without_backend()
        self.store.put('last_report',{'quota':{}})
        self.store.put('chat_catalog',{'scope':None,'items':[dict(chat,can_control=False)]})
        for action,revision in (('set_plan',old['revision']),('set_auto',0)):
            status,_,_ = self.request('POST','/api/action',{'action':action,'key':chat['key'],
                'enabled':False,'prompt':old['prompt'],'revision':revision})
            self.assertEqual(status,409)
        self.assertEqual(get_plan(self.store,chat['key']),old)
        self.assertTrue(self.store.get_task(chat['id'])['auto_resume'])
