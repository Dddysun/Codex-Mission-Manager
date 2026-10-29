"""Synthetic native-UI scenarios; never reads installed app data or Codex history."""
import copy
import datetime as dt
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BASE = json.loads((ROOT/'tests/fixtures/native-brand.json').read_text())
NIGHT = dt.datetime(2026, 10, 29, 22, tzinfo=dt.timezone(dt.timedelta(hours=4))).timestamp()
DAWN = NIGHT + 5*3600
PROMPT = '继续开发设置页面，补齐边界测试，并整理明天的验收清单。'


def snapshot(remaining=72, mode='active', epoch=NIGHT, prompt='', plan='off'):
    s = copy.deepcopy(BASE)
    s.update(observed_at=epoch, now=epoch, running=True, healthy=True, stale=False,
             control_paused=False, control_enabled=True, control_available=True,
             service_error='', quota_phase='low' if remaining<=10 else 'normal')
    reset = DAWN if epoch < DAWN else DAWN+5*3600
    s['usage'].update(observed_at=epoch, stale=False, quota_state='metered', service_allowed=True, blocked=False)
    s['usage']['account'] = {'id':'demo-tokenmax-account', 'name':'演示账号 · 模拟数据',
                             'email':'demo@example.invalid', 'type':'chatgpt', 'plan_type':'plus'}
    s['usage']['windows'] = {'five_hour':{'remaining':remaining,'reset':reset},
                              'weekly':{'remaining':61,'reset':NIGHT+5*86400}}
    s['usage'].pop('reset_credits', None)
    s['catalog'] = {'observed_at':epoch}
    tasks=[]
    for i,title in enumerate(('开发个人作品展示网站','补齐登录模块自动测试')):
        active = i == 0 and mode in ('active','pause_intent','running','resume_intent')
        state = mode if i == 0 and mode in ('paused','pause_intent','resume_intent','running') else 'watching'
        text = ('已完成首页布局、移动端适配和自动测试，等待人工验收。' if mode=='completed' else
                '正在实现首页组件，随后检查移动端布局与交互。' if active else
                '当前任务已暂停，等待额度恢复后继续。' if state=='paused' else
                '测试清单已准备，等待下一步安排。')
        task={'id':'demo-site' if i==0 else 'demo-tests','key':'codex:local:'+('demo-site' if i==0 else 'demo-tests'),
              'name':title,'state':state,'auto_resume':True,'manual_hold':False,'revision':3,
              'can_control':True,'managed':True,'category':'codex','kind':'codex','host_id':'local',
              'source_label':'Codex · 本机','auto_connection':'connected','connection_error':None,
              'runtime':{'type':'active' if active else 'idle','activeFlags':[]},
              'execution_stage':{'text':text,'phase':'progress' if active else 'final_answer','updated_at':epoch},
              'plan':{'state':plan if i==0 else 'off','prompt':prompt if i==0 else '继续任务',
                      'revision':4 if plan!='off' else 3,'armed_window_minutes':300,'armed_window_reset':DAWN}}
        tasks.append(task)
    s['tasks']=tasks
    return s


def restored_event(number, stamp, previous=8, remaining=86):
    return {'id':number,'created':stamp,'state':'quota_restored','thread_id':None,'name':'全局额度事件',
            'origin':'automatic','detail':{'origin':'automatic','category':'official_scheduled_reset',
            'classification_basis':'observed_due_window_rollover_and_stable_credit_inventory',
            'official_reason':None,'previous_observed_at':stamp-30,'observed_at':stamp,
            'windows':[{'minutes':300,'previous_remaining':previous,'remaining':remaining,
                        'previous_reset':stamp,'reset':stamp+5*3600,'classification':'official_scheduled_reset'}],
            'reset_credits':{'previous_available_count':1,'available_count':1,'delta':0}}}


def step(at, **kwargs):
    settings={k:kwargs.pop(k) for k in list(kwargs) if k in ('notice','theme','accent','section','filter','expanded','typing','cursor')}
    return {'at':at,'snapshot':snapshot(**kwargs),**settings}


def scenarios():
    scenes=[
        {'key':'01_额度与任务总览','title':'Codex 额度，一眼看清','subtitle':'五小时窗口 · 周额度 · 任务状态',
         'duration':10,'focus':[10,305,280,280],'steps':[step(0),step(5,remaining=68)]},
        {'key':'02_低额度自动暂停','title':'额度不足，按规则暂停','subtitle':'保留暂停状态，等待额度恢复',
         'duration':12,'focus':[310,295,485,300],
         'steps':[step(0,remaining=14),step(2,remaining=11),step(4,remaining=8,mode='pause_intent'),
                  step(5.5,remaining=8,mode='paused',notice='已确认暂停，等待额度恢复。')]},
        {'key':'03_额度恢复自动续接','title':'等额度恢复，接着做','subtitle':'重新核验后，续接原来的任务',
         'duration':12,'focus':[310,295,485,300],
         'steps':[step(0,remaining=8,mode='paused'),step(3,remaining=86,mode='paused',epoch=DAWN),
                  step(6,remaining=86,mode='resume_intent',epoch=DAWN+5),
                  step(8,remaining=85,mode='running',epoch=DAWN+8,notice='额度已重新核验可用，继续已有任务。')]},
        {'key':'04_提前写好预约指令','title':'睡前，把下一步写好','subtitle':'恢复后执行一次，避免重复发送',
         'duration':16,'focus':[788,310,480,340],
         'steps':[step(0,remaining=8,mode='paused',typing=True),
                  step(10,remaining=8,mode='paused',prompt=PROMPT,plan='armed',notice='已保存指令，等待下一窗口恢复。')]},
        {'key':'05_第二天检查执行结果','title':'第二天，再检查结果','subtitle':'执行进展可查看，交付仍需人工验收',
         'duration':8,'focus':[310,315,500,245],
         'steps':[step(0,remaining=67,mode='completed',epoch=DAWN+4*3600),
                  step(4,remaining=67,mode='completed',epoch=DAWN+4*3600+4)]},
        {'key':'06_额度恢复历史记录','title':'恢复了多少，都有记录','subtitle':'查看前后余额、时间与来源推断',
         'duration':12,'focus':[310,145,540,470],
         'steps':[step(0,remaining=86,epoch=DAWN,section='events'),
                  step(4,remaining=86,epoch=DAWN,section='events',filter='automatic'),
                  step(7,remaining=86,epoch=DAWN,section='events',filter='automatic',expanded=True)]},
        {'key':'07_暂停与恢复运行规则','title':'按自己的习惯设置','subtitle':'暂停 10% · 恢复 20% · 复核 5 秒',
         'duration':8,'focus':[370,70,810,690],
         'steps':[step(0,section='rules')]},
        {'key':'08_深浅外观与主题色','title':'白天、夜晚，都顺眼','subtitle':'原生窗口 · 深浅外观 · 四种主题色',
         'duration':10,'focus':[0,0,1280,800],
         'steps':[step(0,theme='light',accent='blue'),step(3,theme='dark',accent='blue'),
                  step(6,theme='dark',accent='purple'),step(8,theme='light',accent='green')]},
        {'key':'09_菜单面板与后台运行','title':'关掉窗口，后台继续','subtitle':'保持电脑、客户端和网络正常运行',
         'duration':8,'view':'menu','focus':[0,0,400,570],
         'steps':[step(0,remaining=62)]},
        {'key':'10_新版闪电Logo特写','title':'TokenMax','subtitle':'TOKEN榨汁机 · 开源 Codex 额度管家',
         'duration':14,'view':'brand','theme':'dark','focus':[270,120,740,600],
         'steps':[step(0,theme='dark')]},
    ]
    for scene in scenes:
        scene.setdefault('view','app')
        for current in scene['steps']:
            s=current['snapshot']
            if scene['key'].startswith('03_') and current['at']>=3:
                s['tasks'][0]['recovery_first_seen']=DAWN
            if scene['key'].startswith('06_'):
                s['events']=[{'id':107,'created':DAWN+8,'state':'running','thread_id':'demo-site','name':'开发个人作品展示网站','origin':'automatic','detail':{'origin':'automatic','recovery_reason':'window_advanced'}},restored_event(106,DAWN),
                    {'id':105,'created':NIGHT+30,'state':'plan_armed','thread_id':'demo-site','name':'开发个人作品展示网站','origin':'user','detail':{'origin':'user'}},
                    restored_event(104,DAWN-5*3600,5,94),restored_event(103,DAWN-10*3600,9,100)]
            else:
                s['events']=[]
    return {'schema':1,'product':'TokenMax','version':'0.4.2 build 13','brand':'1.3.0',
            'simulation':True,'live_chat_messages_sent':0,'live_tasks_interrupted':0,
            'prompt':PROMPT,'scenes':scenes}


if __name__ == '__main__':
    import sys
    Path(sys.argv[1]).write_text(json.dumps(scenarios(),ensure_ascii=False,indent=2)+'\n')
