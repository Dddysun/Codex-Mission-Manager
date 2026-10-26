"""Portable safety checks; fixtures never connect to the installed desktop."""
import asyncio
from contextlib import closing
import ctypes
import json
import os
from pathlib import Path
import sqlite3
import stat
import tempfile
import time
import unittest
from unittest import mock

import platform_support
from platform_support import lock_file, lock_held, open_lock, process_alive, python_command, sqlite_ro_uri
import compatibility
from compatibility import WINDOWS_PROFILES, windows_compatibility, verified_windows_cli
import guardian
from desktop import DesktopAdapter, DesktopError
from catalog import entry
from plans import get_plan, set_plan
from test_guardian import sample
import test_ui


class WindowsCliTrustTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.package = self.root/'package'
        self.bundled = self.package/'app/resources/codex.exe'
        self.bundled.parent.mkdir(parents=True)
        self.bundled.write_bytes(b'official package bytes')
        self.local = self.root/'local'
        self.cache = self.local/'OpenAI/Codex/bin'
        self.cache.mkdir(parents=True)
        env = mock.patch.dict(os.environ,{'LOCALAPPDATA':str(self.local)})
        env.start()
        self.addCleanup(env.stop)

    def cached(self,name='0123456789abcdef',data=None):
        directory = self.cache/name
        directory.mkdir(parents=True,exist_ok=True)
        path = directory/'codex.exe'
        path.write_bytes(self.bundled.read_bytes() if data is None else data)
        return path

    def test_client_cache_requires_exact_current_package_bytes(self):
        cached = self.cached()
        result = verified_windows_cli(self.package,self.cache)
        self.assertEqual(result['cli'],str(cached))
        self.assertEqual(result['cli_source'],'client-cache-sha256-match')
        self.assertEqual(result['bundled_cli'],str(self.bundled))

    def test_hash_mismatch_does_not_execute_a_plausibly_named_cache_file(self):
        cached = self.cached(data=b'not the official bytes')
        result = verified_windows_cli(self.package,self.cache)
        self.assertNotEqual(result['cli'],str(cached))
        self.assertEqual(result['cli'],str(self.bundled))
        self.assertEqual(result['cli_source'],'registered-package')

    def test_cache_enumeration_cannot_escape_its_fixed_root(self):
        outside = self.root/'outside'/'fedcba9876543210'
        outside.mkdir(parents=True)
        (outside/'codex.exe').write_bytes(self.bundled.read_bytes())
        with mock.patch.object(Path,'iterdir',return_value=iter([outside])):
            result = verified_windows_cli(self.package,self.cache)
        self.assertEqual(result['cli'],str(self.bundled))

    def test_unreadable_package_never_authenticates_a_cache_copy(self):
        self.cached()
        with mock.patch('compatibility._sha256_file',side_effect=PermissionError('fixture denied')):
            self.assertIsNone(verified_windows_cli(self.package,self.cache))

    def test_changed_package_bytes_invalidate_the_previous_cache_version(self):
        old = self.cached()
        self.assertEqual(verified_windows_cli(self.package,self.cache)['cli'],str(old))
        self.bundled.write_bytes(b'new official package!!')
        self.assertEqual(verified_windows_cli(self.package,self.cache)['cli'],str(self.bundled))
        current = self.cached('fedcba9876543210')
        self.assertEqual(verified_windows_cli(self.package,self.cache)['cli'],str(current))

    def test_metadata_ttl_does_not_cache_a_mutable_cli_trust_decision(self):
        cached = self.cached()
        metadata={'name':'OpenAI.Codex','version':'fixture-current','install_location':str(self.package),
                  'publisher':compatibility.WINDOWS_PUBLISHER}
        with mock.patch('compatibility._windows_cache',(time.monotonic(),metadata)), \
                mock.patch('compatibility.subprocess.run') as discovery:
            first = compatibility.windows_client()
            info = cached.stat()
            cached.write_bytes(b'x'*info.st_size)
            os.utime(cached,ns=(info.st_atime_ns,info.st_mtime_ns))
            second = compatibility.windows_client()
        self.assertEqual(first['cli'],str(cached))
        self.assertEqual(second['cli'],str(self.bundled))
        discovery.assert_not_called()

    def test_force_discovery_does_not_reuse_a_previous_package_version(self):
        old = self.cached()
        package2 = self.root/'package-v2'
        bundled2 = package2/'app/resources/codex.exe'
        bundled2.parent.mkdir(parents=True)
        bundled2.write_bytes(b'new package version bytes')
        current = self.cached('fedcba9876543210',data=bundled2.read_bytes())
        def result(version,path):
            value={'Name':'OpenAI.Codex','Version':version,'InstallLocation':str(path),
                   'Publisher':compatibility.WINDOWS_PUBLISHER,'PackageFamilyName':'fixture'}
            return mock.Mock(returncode=0,stdout=json.dumps(value).encode('utf-8'))
        with mock.patch('compatibility._windows_cache',None), \
                mock.patch('compatibility.subprocess.run',side_effect=[result('1.0',self.package),result('2.0',package2)]) as discovery:
            first = compatibility.windows_client(force=True)
            second = compatibility.windows_client(force=True)
        self.assertEqual(first['version'],'1.0')
        self.assertEqual(first['cli'],str(old))
        self.assertEqual(second['version'],'2.0')
        self.assertEqual(second['cli'],str(current))
        self.assertEqual(discovery.call_count,2)

    def test_display_only_compatibility_lookup_does_not_hash_cli_files(self):
        metadata={'name':'OpenAI.Codex','version':'fixture-current','install_location':str(self.package),
                  'publisher':compatibility.WINDOWS_PUBLISHER}
        with mock.patch('compatibility._windows_cache',(time.monotonic(),metadata)), \
                mock.patch('compatibility.os.name','nt'), \
                mock.patch('compatibility.verified_windows_cli',side_effect=AssertionError('display must not hash')):
            result = compatibility.desktop_compatibility()
        self.assertEqual(result['version'],'fixture-current')
        self.assertFalse(result['supported'])

    def test_windows_default_has_no_unverified_path_fallback(self):
        with mock.patch('guardian.IS_WINDOWS',True), \
                mock.patch('compatibility.windows_client',return_value={'cli':None}) as client, \
                mock.patch('guardian.shutil.which',return_value='untrusted-codex.exe') as which:
            with self.assertRaises(ValueError):
                guardian.server_command({'state_dir':str(self.root/'state')})
        client.assert_called_once_with(force=True)
        which.assert_not_called()

    def test_windows_start_requests_fresh_metadata_and_hash_selection(self):
        cached = self.cached()
        with mock.patch('guardian.IS_WINDOWS',True), \
                mock.patch('compatibility.windows_client',return_value={'cli':str(cached)}) as client:
            command = guardian.server_command({'state_dir':str(self.root/'state')})
        client.assert_called_once_with(force=True)
        self.assertEqual(command[0],str(cached))
        self.assertIn('app-server',command)

    def test_explicit_server_command_keeps_existing_user_configuration_semantics(self):
        explicit=['fixture-approved-server','stdio']
        with mock.patch('guardian.IS_WINDOWS',True), mock.patch('compatibility.windows_client') as client:
            self.assertEqual(guardian.server_command({'server_command':explicit}),explicit)
        client.assert_not_called()


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

    def test_exact_windows_profile_keeps_successor_blocked_and_live_claim_false(self):
        current = windows_compatibility({'version':'26.1021.3705.0'})
        self.assertTrue(current['supported'])
        self.assertFalse(current['live_control_tested'])
        self.assertEqual(current['profile'],{'snapshot':11,'start_turn':2,'interrupt_turn':4})
        self.assertFalse(windows_compatibility({'version':'26.1021.3706.0'})['supported'])


class PrivateDirectoryTests(unittest.TestCase):
    def test_windows_creation_inherits_acl_without_posix_mode_or_chmod(self):
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / 'app' / 'state'
            original_mkdir = Path.mkdir
            modes = []
            def checked_mkdir(path, mode=0o777, *args, **kwargs):
                modes.append(mode)
                return original_mkdir(path, mode, *args, **kwargs)
            with mock.patch('platform_support.IS_WINDOWS', True), \
                    mock.patch.object(Path, 'mkdir', checked_mkdir), \
                    mock.patch('platform_support.os.chmod') as chmod:
                platform_support.private_directory(target, enforce_mode=True)
                marker = target / 'config.json'
                marker.write_bytes(b'private fixture')
                platform_support.private_file_permissions(marker)
            self.assertTrue(target.is_dir())
            self.assertTrue(modes)
            self.assertTrue(all(mode == 0o777 for mode in modes))
            chmod.assert_not_called()

    @unittest.skipIf(os.name == 'nt', 'POSIX mode contract')
    def test_posix_directory_and_file_modes_are_unchanged(self):
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / 'state'
            target.mkdir(mode=0o755)
            marker = target / 'ledger'
            marker.write_bytes(b'fixture')
            platform_support.private_directory(target, enforce_mode=True)
            platform_support.private_file_permissions(marker)
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(marker.stat().st_mode), 0o600)

    def test_preflight_writes_syncs_and_removes_probe_without_changing_data(self):
        with tempfile.TemporaryDirectory() as root:
            target = Path(root)
            marker = target / 'config.json'
            original = b'keep the existing private data'
            marker.write_bytes(original)
            with mock.patch('platform_support.os.fsync', wraps=os.fsync) as sync:
                platform_support.check_writable_directory(target, ('config.json', 'missing.log'))
            sync.assert_called_once()
            self.assertEqual(marker.read_bytes(), original)
            self.assertEqual(sorted(p.name for p in target.iterdir()), ['config.json'])

    def test_preflight_reports_existing_file_denial_without_repairing_permissions(self):
        with tempfile.TemporaryDirectory() as root:
            target = Path(root)
            marker = target / 'native-preferences.json'
            marker.write_bytes(b'preserve preferences')
            original_open = Path.open
            def checked_open(path, mode='r', *args, **kwargs):
                if path == marker and mode == 'r+b':
                    raise PermissionError('fixture ACL denies write')
                return original_open(path, mode, *args, **kwargs)
            with mock.patch.object(Path, 'open', checked_open), \
                    mock.patch('platform_support.os.chmod') as chmod:
                with self.assertRaisesRegex(RuntimeError, 'app_data_not_writable.*native-preferences.json') as failure:
                    platform_support.check_writable_directory(target, (marker.name,))
            self.assertIsInstance(failure.exception.__cause__, PermissionError)
            self.assertIn('restore write access', str(failure.exception))
            self.assertEqual(marker.read_bytes(), b'preserve preferences')
            chmod.assert_not_called()

    def test_preflight_reports_denied_probe_without_trying_acl_repair(self):
        with tempfile.TemporaryDirectory() as root:
            with mock.patch('platform_support.tempfile.TemporaryFile', side_effect=PermissionError('fixture denied')), \
                    mock.patch('platform_support.os.chmod') as chmod:
                with self.assertRaisesRegex(RuntimeError, 'app_data_not_writable'):
                    platform_support.check_writable_directory(root)
            chmod.assert_not_called()

    def test_windows_store_and_atomic_config_do_not_apply_posix_permissions(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root) / 'state'
            with mock.patch('platform_support.IS_WINDOWS', True), \
                    mock.patch('platform_support.os.chmod') as chmod:
                store = guardian.Store(directory)
                try:
                    store.put('preserved', True)
                    guardian.atomic_json(directory / 'config.json', {'fixture': True})
                    self.assertTrue(store.get('preserved'))
                finally:
                    store.close()
            self.assertEqual(json.loads((directory / 'config.json').read_text()), {'fixture': True})
            chmod.assert_not_called()

    @unittest.skipUnless(os.name == 'nt', 'Windows inherited DACL regression')
    def test_windows_private_directory_dacl_matches_default_inheritance(self):
        from ctypes import wintypes
        advapi = ctypes.WinDLL('advapi32', use_last_error=True)
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        advapi.GetNamedSecurityInfoW.argtypes = (
            wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD,
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p))
        advapi.GetNamedSecurityInfoW.restype = wintypes.DWORD
        advapi.ConvertSecurityDescriptorToStringSecurityDescriptorW.argtypes = (
            ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD,
            ctypes.POINTER(wintypes.LPWSTR), ctypes.POINTER(wintypes.ULONG))
        advapi.ConvertSecurityDescriptorToStringSecurityDescriptorW.restype = wintypes.BOOL
        kernel.LocalFree.argtypes = (ctypes.c_void_p,)
        kernel.LocalFree.restype = ctypes.c_void_p
        def dacl(path):
            descriptor = ctypes.c_void_p()
            code = advapi.GetNamedSecurityInfoW(str(path), 1, 4, None, None, None, None, ctypes.byref(descriptor))
            if code:
                raise ctypes.WinError(code)
            text = wintypes.LPWSTR()
            try:
                if not advapi.ConvertSecurityDescriptorToStringSecurityDescriptorW(
                        descriptor, 1, 4, ctypes.byref(text), None):
                    raise ctypes.WinError(ctypes.get_last_error())
                return text.value
            finally:
                if text:
                    kernel.LocalFree(text)
                kernel.LocalFree(descriptor)
        with tempfile.TemporaryDirectory() as root:
            inherited = Path(root) / 'default'
            inherited.mkdir()
            private = platform_support.private_directory(Path(root) / 'application', enforce_mode=True)
            self.assertEqual(dacl(private), dacl(inherited))


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
