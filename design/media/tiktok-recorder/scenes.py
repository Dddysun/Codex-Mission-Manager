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


def original_scenarios():
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


def scenarios(assets):
    base = original_scenarios()
    previous = base['scenes']

    def native(index, key, **changes):
        result = copy.deepcopy(previous[index-1])
        result.update(key=key, **changes)
        return result

    def codex(key, title, subtitle, number, focus):
        image = assets/(str(number)+'.jpeg')
        if not image.is_file():
            raise FileNotFoundError('Run fetch_codex_assets.py before creating the full recording plan')
        return {'key':key, 'title':title, 'subtitle':subtitle, 'duration':8,
                'view':'public', 'media':str(image.resolve()), 'focus':focus,
                'sourceCredit':'Codex 官方公开截图 · 来源 OpenAI', 'steps':[step(0)],
                'source_url':'https://developers.openai.com/blog/run-long-horizon-tasks-with-codex',
                'source_type':'official_screenshot_with_camera_motion'}

    scenes = [
        codex('01_Codex桌面与写代码','用 Codex 写代码','Codex 桌面界面 · OpenAI 官方公开示例',4,[190,60,940,670]),
        codex('02_Codex代码修改','任务在继续，代码在变化','查看代码修改与检查过程',6,[130,65,920,680]),
        native(1,'03_五小时与周额度',title='五小时窗口，还有周额度',subtitle='查看剩余额度和下一次刷新时间'),
        native(1,'04_晚上十点与凌晨三点',title='晚上十点用完，凌晨三点恢复',subtitle='刷新时间，未必配合你的作息',duration=10,
               steps=[step(0,remaining=8,mode='paused')]),
        codex('05_Codex等待下一步','AI 在等额度，你在等 AI','不用一直惦记下一次刷新',4,[475,510,600,190]),
        native(10,'06_TokenMax登场',title='TokenMax / Token榨汁机',subtitle='开源工具，让额度调度自动进行',duration=10),
        native(1,'07_额度与任务监控',title='剩余额度，一眼看清',subtitle='五小时窗口 · 周额度 · 任务状态'),
        native(2,'08_低额度自动暂停'),
        native(3,'09_额度恢复自动续接'),
        native(4,'10_睡前写好预约指令'),
        native(4,'11_一次性预约已保存',title='下一步，提前安排好',subtitle='额度恢复并符合条件后，执行一次',duration=8,
               steps=[step(0,remaining=8,mode='paused',prompt=PROMPT,plan='armed')]),
        native(9,'12_后台运行条件',subtitle='保持电脑、客户端、网络正常运行'),
        native(5,'13_第二天检查执行结果'),
        codex('14_Codex检查测试结果','第二天，检查执行结果','测试与交付结果仍需人工验收',5,[0,220,800,350]),
        native(6,'15_额度恢复历史记录'),
        native(7,'16_按规则调度不增加额度',title='不增加官方额度',subtitle='阈值控制调度，官方余额与刷新时间只读'),
        native(1,'17_官方余额与刷新只读',title='不用自己的时间，守着刷新',subtitle='按账号实际返回的额度窗口工作',duration=8),
        native(8,'18_日夜外观与主题',title='白天、夜晚，都能安排好',subtitle='在符合条件时，把会员权益用到位'),
        native(1,'19_高斯模糊动态Logo片尾',title='Token榨汁机 / TokenMax',subtitle='把会员权益，用到位。',view='outro',
               duration=16,focus=[415,0,450,800]),
    ]
    cues = [
        '尤其是经常用 Codex 写代码的朋友', 'Codex 写代码与任务执行的补充镜头',
        '除了周额度之外，还有一个五小时额度窗口', '晚上十点用完，下一次恢复是凌晨三点',
        'AI 在等额度，我们在等 AI', '最近发现了开源工具 TokenMax / Token榨汁机',
        '监控 Codex 的剩余额度', '在符合条件时自动暂停任务', '等额度恢复，再自动接续原来的工作',
        '睡觉之前，提前写好下一条指令', '预约在额度恢复之后执行',
        '只要电脑和客户端保持正常运行，账号额度和任务状态符合要求',
        '第二天起床，检查执行结果', '次日检查与人工验收的补充镜头',
        '记录额度恢复历史，知道什么时候恢复、恢复多少', '不是破解限制，也不会增加官方额度',
        '不用自己的时间迁就 AI 的额度刷新时间', '能多利用一点，就多利用一点', '这才叫真正把会员权益用到位',
    ]
    for scene, cue in zip(scenes, cues):
        scene['script_cue'] = cue
    base.update(scenes=scenes, edition=2, branding='TokenMax / Token榨汁机',
                order='narration_sequence', codex_media='official_public_screenshots_with_camera_motion')
    return base


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('output',type=Path)
    parser.add_argument('--assets',type=Path,required=True)
    args = parser.parse_args()
    args.output.write_text(json.dumps(scenarios(args.assets),ensure_ascii=False,indent=2)+'\n')
