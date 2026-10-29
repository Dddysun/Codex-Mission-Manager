#!/usr/bin/env python3
"""Make editable portrait inserts and a scratch-voice opening preview."""
from pathlib import Path
import argparse
import json
import subprocess
from PIL import Image, ImageDraw
from render_motion import W,H,FPS,font,text

ROOT=Path(__file__).resolve().parents[1]
TMP=ROOT/'tools/work'
TMP.mkdir(exist_ok=True)

def run(args):subprocess.run(args,check=True)

def duration(path):
    return float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','default=noprint_wrappers=1:nokey=1',str(path)]))

def overlay(name,title='',sub='',ai=False):
    out=TMP/(name+'.png')
    im=Image.new('RGBA',(W,H),(0,0,0,0));d=ImageDraw.Draw(im)
    if title:
        d.rounded_rectangle((65,225,1015,415),18,fill=(15,19,17,205))
        text(d,(105,248),title,66,'#F7E8C6')
        if sub:text(d,(105,340),sub,29,'#F7F3E9')
    if ai:
        d.rounded_rectangle((70,1710,780,1780),10,fill=(15,19,17,195))
        text(d,(95,1728),'AI 图像动效 · 店铺及食物为示意',26,'#F0EEE7')
    im.save(out)
    return out

FOOD=[
 ('01_贵阳街头粉店_AI示意','贵州 · 贵阳','街头这一碗',3.0),
 ('02_牛肉粉_AI示意','全家福牛肉粉','热气腾腾，先来一碗',3.0),
 ('03_加粉_AI示意','加 粉','再加一份米粉',2.2),
 ('04_加肉_AI示意','加 肉','牛肉，安排上',2.2),
 ('05_加煎蛋_AI示意','加 煎 蛋','再来一个煎蛋',2.8),
]

def food():
    for name,title,sub,secs in FOOD:
        source=ROOT/'03_贵阳牛肉粉'/(name+'.png')
        out=source.with_suffix('.mp4')
        if out.exists():continue
        label=overlay(name,title,sub,True)
        frames=round(secs*FPS)
        vf=f"[0:v]scale=1620:2880,zoompan=z='1.0+0.0005*on':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d={frames}:s={W}x{H}:fps={FPS}[photo];[photo][1:v]overlay=0:0:format=auto,format=yuv420p[v]"
        run(['ffmpeg','-v','error','-i',str(source),'-i',str(label),'-filter_complex',vf,'-map','[v]','-t',str(secs),'-an','-c:v','libx264','-preset','fast','-crf','18','-movflags','+faststart',str(out)])
        print(json.dumps({'food_clip':out.name,'seconds':secs},ensure_ascii=False),flush=True)
    source=ROOT/'03_贵阳牛肉粉/05_加煎蛋_AI示意.png'
    out=ROOT/'03_贵阳牛肉粉/06_吃到饱_AI示意.mp4'
    if not out.exists():
        label=overlay('eat','吃 到 饱','这碗，全家福。',True)
        vf=f"[0:v]scale=1620:2880,zoompan=z='1.08-0.0006*on':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=84:s={W}x{H}:fps={FPS}[photo];[photo][1:v]overlay=0:0:format=auto,format=yuv420p[v]"
        run(['ffmpeg','-v','error','-i',str(source),'-i',str(label),'-filter_complex',vf,'-map','[v]','-t','2.8','-an','-c:v','libx264','-preset','fast','-crf','18','-movflags','+faststart',str(out)])

def life():
    for source in sorted((ROOT/'02_生活素材').glob('*横屏原片.mp4')):
        name=source.stem.replace('_横屏原片','')
        out=source.with_name(name+'_竖屏适配.mp4')
        if out.exists():continue
        # Preserve the clock, hands and computer instead of cropping them out.
        label=overlay('stock_'+name,name[3:],'生活场景素材',False)
        vf='[0:v]split=2[a][b];[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,gblur=sigma=35[bg];[b]scale=1080:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2[mid];[mid][1:v]overlay=0:0,setsar=1,format=yuv420p[v]'
        run(['ffmpeg','-v','error','-i',str(source),'-i',str(label),'-filter_complex',vf,'-map','[v]','-t',str(min(8,duration(source))),'-r',str(FPS),'-an','-c:v','libx264','-preset','fast','-crf','20','-movflags','+faststart',str(out)])
        print(json.dumps({'life_clip':out.name},ensure_ascii=False),flush=True)

def maplink():
    out=ROOT/'03_贵阳牛肉粉/07_地图推进到粉店_衔接版.mp4'
    if out.exists():return
    run(['ffmpeg','-v','error','-i',str(ROOT/'03_贵阳牛肉粉/00_中国到贵州贵阳街区_地图动画_v2.mp4'),'-i',str(ROOT/'03_贵阳牛肉粉/01_贵阳街头粉店_AI示意.mp4'),'-filter_complex','[0:v][1:v]xfade=transition=zoomin:duration=0.4:offset=9.6,format=yuv420p[v]','-map','[v]','-an','-c:v','libx264','-preset','fast','-crf','18','-movflags','+faststart',str(out)])

def make_bridge():
    out=ROOT/'01_数字动画/07_转入五小时额度.mp4'
    if out.exists():return out
    image=Image.new('RGB',(W,H),'#101317');d=ImageDraw.Draw(image)
    text(d,(540,650),'它不只是贵',65,'#F3F0E8','mm')
    text(d,(540,820),'还有五小时额度',72,'#F1C76B','mm')
    still=TMP/'bridge.png';image.save(still)
    run(['ffmpeg','-v','error','-loop','1','-i',str(still),'-t','3','-an','-r',str(FPS),'-c:v','libx264','-preset','fast','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',str(out)])
    return out

def preview():
    make_bridge()
    plan=[
      ('01_数字动画/03_150元开场.mp4','一百五十块钱的 GPT Plus，你用回本了吗？',5),
      ('01_数字动画/04_六个会员还剩20元.mp4','一百五十块钱，你可以买QQ音乐会员、腾讯视频会员、B站大会员、爱奇艺会员、网易云音乐会员，甚至再加一个优酷会员。买完这么多会员，还剩大概二十块钱。',14),
      ('03_贵阳牛肉粉/00_中国到贵州贵阳街区_地图动画_v2.mp4','这二十块钱，在我的家乡，贵州省贵阳市的街头，',10),
      ('03_贵阳牛肉粉/01_贵阳街头粉店_AI示意.mp4','可以买一碗全家福牛肉粉。',3),
      ('03_贵阳牛肉粉/02_牛肉粉_AI示意.mp4','看这一碗，热气腾腾。',3),
      ('03_贵阳牛肉粉/03_加粉_AI示意.mp4','加粉！',2.2),
      ('03_贵阳牛肉粉/04_加肉_AI示意.mp4','加肉！',2.2),
      ('03_贵阳牛肉粉/05_加煎蛋_AI示意.mp4','再加一个煎蛋！',2.8),
      ('03_贵阳牛肉粉/06_吃到饱_AI示意.mp4','吃到饱！',2.8),
      ('01_数字动画/07_转入五小时额度.mp4','而 Codex 不只是贵，它还有五小时额度。',3),
      ('01_数字动画/01_五小时与周额度_带结论.mp4','两个额度同时消耗。五小时额度已经见底，周额度却只用掉了一点点。这里的比例，只是举个例子。',9),
    ]
    segments=[];clean_segments=[];timeline=[];cursor=0
    for i,(file,spoken,minimum) in enumerate(plan):
        txt=TMP/f'voice-{i:02d}.txt';aif=TMP/f'voice-{i:02d}.aiff'
        txt.write_text(spoken)
        if not aif.exists():run(['say','-v','Tingting','-r','260','-f',str(txt),'-o',str(aif)])
        length=max(minimum,duration(aif)+.4)
        out=TMP/f'preview-{i:02d}.mp4'
        if not out.exists():
            run(['ffmpeg','-v','error','-i',str(ROOT/file),'-i',str(aif),'-t',str(length),'-vf',f'tpad=stop_mode=clone:stop_duration=30,fps={FPS},setsar=1','-af','apad','-c:v','libx264','-preset','fast','-crf','19','-pix_fmt','yuv420p','-c:a','aac','-b:a','160k','-ar','48000','-ac','2','-movflags','+faststart',str(out)])
        segments.append(out)
        timeline.append({'start':round(cursor,3),'duration':round(length,3),'file':file,'scratch_narration':spoken})
        cursor+=length
    listing=TMP/'concat-preview.txt';listing.write_text(''.join("file '"+str(p)+"'\n" for p in segments))
    out=ROOT/'04_预览与说明/00_开场到五小时额度_临时机器配音预览.mp4'
    if not out.exists():run(['ffmpeg','-v','error','-f','concat','-safe','0','-i',str(listing),'-c','copy','-movflags','+faststart',str(out)])
    silent=out.with_name('01_开场到五小时额度_无配音预览.mp4')
    if not silent.exists():run(['ffmpeg','-v','error','-i',str(out),'-an','-c:v','copy','-movflags','+faststart',str(silent)])
    (ROOT/'04_预览与说明/preview-timeline.json').write_text(json.dumps(timeline,ensure_ascii=False,indent=2)+'\n')
    def tc(s):
        ms=round(s*1000);return f'{ms//3600000:02d}:{ms//60000%60:02d}:{ms//1000%60:02d},{ms%1000:03d}'
    srt=[]
    for i,row in enumerate(timeline):srt.append(f"{i+1}\n{tc(row['start'])} --> {tc(row['start']+row['duration'])}\n{row['scratch_narration']}\n")
    (ROOT/'04_预览与说明/参考口播.srt').write_text('\n'.join(srt))
    print(json.dumps({'preview_seconds':round(cursor,2),'voice':'macOS Tingting scratch voice','file':str(out)},ensure_ascii=False),flush=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('steps',nargs='*',default=['food','life','maplink','preview']);args=ap.parse_args()
    for step in args.steps:globals()[step]()
