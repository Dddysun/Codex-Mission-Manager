"""Durable, explicitly requested pause of opted-in managed sessions only."""
import json
from control_policy import active_turn, blocked_input

async def pause_requests(controller, sample):
    store=controller.store
    with store.db:
        recovered=store.db.execute("UPDATE requests SET state='unknown',result=? WHERE kind='pause_all' AND state='processing'",(json.dumps({'error':'Previous pause result requires review; not replayed'}),)).rowcount
    if recovered:
        store.put('bulk_pause_result',{'state':'unknown','total':0,'paused':0,'skipped':0,'failed':recovered})
    for row in store.db.execute("SELECT * FROM requests WHERE kind='pause_all' AND state='pending'").fetchall():
        value=json.loads(row['value']);result={'state':'processing','total':len(value['ids']),'paused':0,'skipped':0,'failed':0,'items':[]}
        with store.db:store.db.execute("UPDATE requests SET state='processing' WHERE id=?",(row['id'],))
        store.put('bulk_pause_result',result)
        for tid in value['ids']:
            task=store.get_task(tid)
            status='skipped';reason=None
            try:
                if store.get('stop_requested',False):raise RuntimeError('Application stopped')
                if value.get('scope')!=controller.identity:raise ValueError('Account changed')
                if not task or task['scope']!=controller.identity or not task.get('auto_resume',True) or task.get('manual_hold') or task['state'] in ('disabled','needs_review','paused','pause_intent','resume_intent'):
                    reason='Task is not eligible for managed pause'
                else:
                    view=await controller.view(tid)
                    if blocked_input(view) or not (active_turn(view) or (view.get('goal') or {}).get('status')=='active'):
                        reason='Task is idle or awaiting input'
                    elif controller.clock()-sample['observed_at']>controller.config['max_sample_age_seconds']:
                        raise ValueError('Usage reading expired')
                    else:
                        if controller.identity_check and await controller.identity_check() != controller.identity:
                            raise ValueError('Account changed before pause')
                        await controller.pause(task,sample,manual=True)
                        current=store.get_task(tid)
                        if current['state']=='paused':
                            store.permission(tid,False,expected_revision=current.get('control_revision',0))
                            status='paused'
                        else:
                            status='failed';reason='Pause could not be confirmed'
            except Exception as exc:
                status='failed';reason=str(exc)[:180]
            result[status]+=1
            result['items'].append({'thread_id':tid,'state':status,'reason':reason})
            store.put('bulk_pause_result',result)
        result['state']='completed'
        with store.db:store.db.execute("UPDATE requests SET state='done',result=? WHERE id=?",(json.dumps(result),row['id']))
        store.put('bulk_pause_result',result)
