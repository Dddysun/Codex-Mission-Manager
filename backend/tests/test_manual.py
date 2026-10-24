"""Batch pause lifecycle using in-memory fake turns and isolated local ledgers."""
import asyncio
import json
import tempfile
import unittest

from guardian import Controller,Store
from manual import pause_requests
from test_guardian import CONFIG,NOW,FakeRpc,sample


class ManualPauseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.store=Store(self.temp.name)
        self.rpc=FakeRpc()
        self.controller=Controller(self.rpc,self.store,CONFIG,'scope-one',clock=lambda:NOW)
        await self.controller.adopt('one')
        await self.controller.adopt('two')
        self.rpc.calls.clear()
        self.store.put('supervisor_paused',True)

    async def asyncTearDown(self):
        self.store.close()
        self.temp.cleanup()

    def queue(self,ids=None,scope='scope-one',state='pending'):
        request=self.store.enqueue('pause_all',{'ids':ids or ['one','two'],'scope':scope})
        if state!='pending':
            with self.store.db:self.store.db.execute('UPDATE requests SET state=? WHERE id=?',(state,request))
        return request

    async def test_manual_pause_works_while_global_automation_is_paused_and_persists_holds(self):
        request=self.queue()
        await pause_requests(self.controller,sample())
        self.assertEqual(self.rpc.count('turn/interrupt'),2)
        self.assertTrue(self.store.get('supervisor_paused'))
        for tid in ['one','two']:
            task=self.store.get_task(tid)
            self.assertEqual(task['state'],'paused')
            self.assertEqual(task['pause_source'],'manual')
            self.assertTrue(task['manual_hold'])
            self.assertFalse(task['auto_resume'])
        self.assertEqual(self.store.get('bulk_pause_result')['paused'],2)
        self.assertEqual(self.store.db.execute('SELECT state FROM requests WHERE id=?',(request,)).fetchone()[0],'done')
        self.store.put('supervisor_paused',False)
        await self.controller.tick(sample(remaining=98,reset=NOW+18000))
        self.assertEqual(self.rpc.count('turn/start'),0)

    async def test_manual_hold_is_durable_before_interrupt_is_dispatched(self):
        call=self.rpc.call
        intents=[]
        async def inspect_dispatch(method,params=None):
            if method=='turn/interrupt':
                intents.append(self.store.get_task(params['threadId']))
            return await call(method,params)
        self.rpc.call=inspect_dispatch
        self.queue(['one'])
        await pause_requests(self.controller,sample())
        self.assertEqual(len(intents),1)
        self.assertEqual(intents[0]['state'],'pause_intent')
        self.assertEqual(intents[0]['pause_source'],'manual')
        self.assertTrue(intents[0]['manual_hold'])
        self.assertFalse(intents[0]['auto_resume'])

    async def test_failed_post_confirmation_permission_update_cannot_release_manual_hold(self):
        def fail_permission_update(*args,**kwargs):
            raise RuntimeError('Post-confirmation update failed')
        self.store.permission=fail_permission_update
        self.queue(['one'])
        await pause_requests(self.controller,sample())
        self.assertEqual(self.rpc.count('turn/interrupt'),1)
        task=self.store.get_task('one')
        self.assertEqual(task['state'],'paused')
        self.assertTrue(task['manual_hold'])
        self.assertFalse(task['auto_resume'])
        self.assertEqual(self.store.get('bulk_pause_result')['failed'],1)
        self.store.put('supervisor_paused',False)
        await self.controller.tick(sample(remaining=98,reset=NOW+18000))
        await self.controller.tick(sample(remaining=98,reset=NOW+18000))
        self.assertEqual(self.rpc.count('turn/start'),0)
        self.assertTrue(self.store.get_task('one')['manual_hold'])

    async def test_approval_idle_opt_out_and_unmanaged_targets_are_not_interrupted(self):
        self.rpc.views['one']['thread']['status']['activeFlags']=['waitingForApproval']
        self.rpc.views['two']['thread']['status']={'type':'idle'}
        self.rpc.views['two']['turns'][0]['status']='completed'
        self.queue(['one','two','unknown'])
        await pause_requests(self.controller,sample())
        self.assertEqual(self.rpc.count('turn/interrupt'),0)
        self.assertEqual(self.store.get('bulk_pause_result')['skipped'],3)

    async def test_permission_revocation_wins_before_dispatch(self):
        self.queue()
        self.store.permission('two',False)
        await pause_requests(self.controller,sample())
        interrupted=[params['threadId'] for method,params in self.rpc.calls if method=='turn/interrupt']
        self.assertEqual(interrupted,['one'])
        self.assertEqual(self.store.get('bulk_pause_result')['skipped'],1)

    async def test_revocation_during_fresh_read_wins_before_interrupt(self):
        call=self.rpc.call
        revoked=False
        async def revoke_during_read(method,params=None):
            nonlocal revoked
            result=await call(method,params)
            if method=='thread/read' and not revoked:
                revoked=True
                self.store.permission('one',False)
            return result
        self.rpc.call=revoke_during_read
        self.queue(['one'])
        await pause_requests(self.controller,sample())
        self.assertEqual(self.rpc.count('turn/interrupt'),0)
        self.assertTrue(self.store.get_task('one')['manual_hold'])

    async def test_restart_never_replays_processing_pause_request(self):
        request=self.queue(state='processing')
        await pause_requests(self.controller,sample())
        self.assertEqual(self.rpc.count('turn/interrupt'),0)
        row=self.store.db.execute('SELECT state,result FROM requests WHERE id=?',(request,)).fetchone()
        self.assertEqual(row['state'],'unknown')
        self.assertIn('not replayed',json.loads(row['result'])['error'])
        self.assertEqual(self.store.get('bulk_pause_result')['state'],'unknown')

    async def test_account_change_refuses_every_target_without_reading_or_interrupting_it(self):
        self.queue(scope='different-account')
        await pause_requests(self.controller,sample())
        await pause_requests(self.controller,sample())
        self.assertEqual(self.rpc.calls,[])
        self.assertEqual(self.store.get('bulk_pause_result')['failed'],2)
        self.assertTrue(all(x['reason']=='Account changed' for x in self.store.get('bulk_pause_result')['items']))

    async def test_fresh_account_check_mismatch_blocks_mutation_and_is_not_replayed(self):
        checks=[]
        async def identity_check():
            checks.append('checked')
            return 'new-account'
        self.controller.identity_check=identity_check
        request=self.queue()
        await pause_requests(self.controller,sample())
        await pause_requests(self.controller,sample())
        self.assertEqual(self.rpc.count('turn/interrupt'),0)
        self.assertEqual(self.store.get('bulk_pause_result')['failed'],2)
        self.assertEqual(len(checks),2)
        self.assertEqual(self.store.db.execute('SELECT state FROM requests WHERE id=?',(request,)).fetchone()[0],'done')

    async def test_unavailable_fresh_identity_blocks_every_pause(self):
        async def identity_check():
            raise RuntimeError('Identity check unavailable')
        self.controller.identity_check=identity_check
        self.queue()
        await pause_requests(self.controller,sample())
        self.assertEqual(self.rpc.count('turn/interrupt'),0)
        self.assertEqual(self.store.get('bulk_pause_result')['failed'],2)
        self.assertTrue(all('Identity check unavailable' in item['reason'] for item in self.store.get('bulk_pause_result')['items']))

    async def test_account_change_between_targets_stops_the_next_target(self):
        readings=iter(['scope-one','new-account'])
        async def identity_check():return next(readings)
        self.controller.identity_check=identity_check
        self.queue()
        await pause_requests(self.controller,sample())
        self.assertEqual(self.rpc.count('turn/interrupt'),1)
        self.assertTrue(self.store.get_task('one')['manual_hold'])
        self.assertEqual(self.store.get_task('two')['state'],'watching')
        self.assertEqual(self.store.get('bulk_pause_result')['failed'],1)

    async def test_expired_sample_refuses_pause(self):
        self.queue()
        value=sample()
        value['observed_at']=NOW-CONFIG['max_sample_age_seconds']-1
        await pause_requests(self.controller,value)
        self.assertEqual(self.rpc.count('turn/interrupt'),0)
        self.assertEqual(self.store.get('bulk_pause_result')['failed'],2)

    async def test_stopped_application_does_not_interrupt_tasks(self):
        self.queue()
        self.store.put('stop_requested',True)
        await pause_requests(self.controller,sample())
        self.assertEqual(self.rpc.count('turn/interrupt'),0)
        self.assertEqual(self.store.get('bulk_pause_result')['failed'],2)

    async def test_unconfirmed_pause_is_reported_and_never_repeated(self):
        call=self.rpc.call
        async def uncertain(method,params=None):
            if method=='turn/interrupt':
                self.rpc.calls.append((method,dict(params)))
                raise asyncio.TimeoutError()
            return await call(method,params)
        self.rpc.call=uncertain
        self.queue(['one'])
        await pause_requests(self.controller,sample())
        await pause_requests(self.controller,sample())
        self.assertEqual(self.rpc.count('turn/interrupt'),1)
        self.assertEqual(self.store.get('bulk_pause_result')['failed'],1)
        self.assertEqual(self.store.get_task('one')['state'],'needs_review')
