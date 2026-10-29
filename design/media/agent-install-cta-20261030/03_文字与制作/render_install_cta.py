#!/usr/bin/env python3
"""24-second white portrait CTA: description arrow, then a static Agent prompt.
No voice, no music, and no installation commands are executed by this script.
"""
from pathlib import Path
from functools import lru_cache
import json,math,subprocess,zipfile
from PIL import Image,ImageDraw,ImageFont

ROOT=Path(__file__).resolve().parents[1]
W,H,FPS=1080,1920,30
FONT='/System/Library/Fonts/Hiragino Sans GB.ttc'
MONO='/System/Library/Fonts/Helvetica.ttc'
INK='#202023';GRAY='#747478';RED='#E64E47';WHITE='white'
URL='https://github.com/Dddysun/TokenMax-Zhazhiji'
SHORT=f'请读取 {URL} 的安装说明，查询执行时最新已发布的 Release（含预览版），按我的系统和芯片架构下载匹配的安装包，校验后安装，并保留已有数据；需要授权或登录时提示我。'
SCREEN_LINES=[
    '请读取上方仓库的安装说明，',
    '查询执行时最新已发布的',
    'Release（含预览版），按我的',
    '系统和芯片架构下载匹配的',
    '安装包，校验后安装，',
    '并保留已有数据；需要授权',
    '或登录时提示我。',
]

@lru_cache(None)
def font(size,mono=False):return ImageFont.truetype(MONO if mono else FONT,size)
def text(d,x,y,s,size=48,color=INK,anchor='mm',mono=False):
    d.text((x,y),s,font=font(size,mono),fill=color,anchor=anchor)
def line(d,points,width=7,color=INK):
    d.line(points,fill=color,width=width,joint='curve')
    r=width/2
    for x,y in (points[0],points[-1]):d.ellipse((x-r,y-r,x+r,y+r),fill=color)

def arrow(t):
    im=Image.new('RGB',(W,H),WHITE);d=ImageDraw.Draw(im)
    text(d,540,270,'想让 Agent 帮你安装？',62)
    text(d,540,450,'打开视频下方简介',64)
    text(d,540,565,'复制指令，发给你的 Agent',39,GRAY)
    # A simple copy-sheet pictogram; no platform-specific UI or fake buttons.
    d.rounded_rectangle((355,735,685,1045),20,outline=INK,width=7)
    d.rounded_rectangle((395,775,725,1085),20,fill=WHITE,outline=INK,width=7)
    for y,length in [(845,195),(910,195),(975,130)]:line(d,[(445,y),(445+length,y)],6)
    dy=20*math.sin(t*math.pi*1.3)
    line(d,[(540,1210+dy),(540,1590+dy)],15,RED)
    line(d,[(425,1470+dy),(540,1590+dy),(655,1470+dy)],15,RED)
    text(d,540,1740,'视频简介 ↓',40)
    return im

def card(t=0):
    im=Image.new('RGB',(W,H),WHITE);d=ImageDraw.Draw(im)
    text(d,540,210,'TokenMax · 额度榨汁机',41)
    text(d,540,335,'截图，发给你的 Agent',62)
    text(d,540,445,'也可以复制视频简介里的这句话',36,GRAY)
    # One continuous URL, never wrapped at the hyphen: robust to screenshot OCR.
    text(d,540,630,URL,42,mono=True)
    line(d,[(105,700),(975,700)],2,'#D9D9DC')
    for i,s in enumerate(SCREEN_LINES):text(d,118,800+i*82,s,49,anchor='lm')
    line(d,[(105,1410),(975,1410)],2,'#D9D9DC')
    text(d,310,1510,'Windows',44);text(d,775,1510,'macOS',44)
    text(d,310,1580,'x64',33,GRAY);text(d,775,1580,'Apple Silicon',33,GRAY)
    text(d,540,1705,'原生桌面应用',36)
    text(d,540,1775,'具体系统要求，以最新 Release 说明为准',25,GRAY)
    return im

def render(name,secs,fn):
    out=ROOT/'01_镜头'/(name+'.mp4')
    p=subprocess.Popen(['ffmpeg','-v','error','-y','-f','rawvideo','-pix_fmt','rgb24','-s','1080x1920','-r','30','-i','-','-an','-c:v','libx264','-preset','fast','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',str(out)],stdin=subprocess.PIPE)
    for i in range(round(secs*FPS)):p.stdin.write(fn(i/FPS).tobytes())
    p.stdin.close()
    if p.wait()!=0:raise RuntimeError(name)
    return out

def main():
    # Validate all important text bounds before rendering.
    d=ImageDraw.Draw(Image.new('RGB',(W,H)))
    assert d.textlength(URL,font=font(42,True))<930
    assert all(d.textlength(s,font=font(49))<850 for s in SCREEN_LINES)
    card().save(ROOT/'02_截图卡/给Agent的安装指令_1080x1920.png')
    arrow(0).save(ROOT/'02_截图卡/箭头指向简介_预览.png')
    a=render('01_箭头指向视频简介',6,arrow)
    c=render('02_截图给Agent_静止指令卡',18,card)
    listing=ROOT/'03_文字与制作/concat.txt';listing.write_text('\n'.join("file '"+str(p)+"'" for p in [a,c]))
    out=ROOT/'01_镜头/00_完整安装引导_24秒_无旁白.mp4'
    subprocess.run(['ffmpeg','-v','error','-y','-f','concat','-safe','0','-i',str(listing),'-c','copy','-an','-movflags','+faststart',str(out)],check=True)
    (ROOT/'03_文字与制作/一句话安装指令.txt').write_text(SHORT+'\n')
    (ROOT/'03_文字与制作/镜头时间轴.json').write_text(json.dumps([
        {'start':0,'end':6,'shot':a.name,'meaning':'打开下方简介，复制指令'},
        {'start':6,'end':24,'shot':c.name,'meaning':'截图页稳定停留18秒；同时展示Windows x64和Apple Silicon Mac支持'},
    ],ensure_ascii=False,indent=2))
    manifest=[]
    for p in sorted((ROOT/'01_镜头').glob('*.mp4')):
        data=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(p)]))
        vs=[s for s in data['streams'] if s['codec_type']=='video']
        assert len(vs)==1 and all(s['codec_type']!='audio' for s in data['streams'])
        assert (vs[0]['width'],vs[0]['height'],vs[0]['r_frame_rate'])==(W,H,'30/1')
        subprocess.run(['ffmpeg','-v','error','-i',str(p),'-f','null','-'],check=True,stderr=subprocess.PIPE)
        manifest.append({'file':p.name,'duration':float(data['format']['duration']),'resolution':'1080x1920','fps':30,'audio':False,'full_decode':'pass'})
    (ROOT/'03_文字与制作/media-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    print(json.dumps({'preview':str(out),'clips':manifest},ensure_ascii=False))

if __name__=='__main__':main()
