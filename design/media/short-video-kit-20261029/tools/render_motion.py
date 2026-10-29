#!/usr/bin/env python3
"""Render original portrait motion graphics. Requires Pillow and FFmpeg."""
from pathlib import Path
from functools import lru_cache
import argparse
import json
import math
import subprocess
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
FONT = '/System/Library/Fonts/Hiragino Sans GB.ttc'
W, H, FPS = 1080, 1920, 30
BG = '#101317'
WHITE = '#F3F0E8'
MUTED = '#939B9F'
GOLD = '#F1C76B'
GREEN = '#8DC4B3'
TRACK = '#2C3339'

@lru_cache(None)
def font(size):
    return ImageFont.truetype(FONT, size)

def text(d, xy, s, size=44, fill=WHITE, anchor=None):
    d.text(xy, s, font=font(size), fill=fill, anchor=anchor, stroke_width=0)

def center(d, y, s, size=44, fill=WHITE):
    text(d, (W/2,y), s, size, fill, 'mm')

def ease(t):
    t = min(1,max(0,t))
    return t*t*(3-2*t)

def base():
    im = Image.new('RGB',(W,H),BG)
    return im, ImageDraw.Draw(im)

def bar(d, y, p, color):
    x0,x1=100,980
    d.rounded_rectangle((x0,y,x1,y+50),radius=25,fill=TRACK)
    if p>0:
        end=x0+(x1-x0)*p
        if end-x0>=50:
            d.rounded_rectangle((x0,y,end,y+50),radius=25,fill=color)
        else:
            d.rectangle((x0,y,end,y+50),fill=color)

def quota(t, caption=True):
    im,d=base()
    p=min(1,max(0,(t-1)/5.5))
    short=1-p
    week=1-.1*p
    text(d,(100,280),'CODEX  /  使用额度',34,MUTED)
    text(d,(100,450),'五小时额度',62)
    text(d,(980,555),f'{round(short*100)}%',100,GOLD,'ra')
    text(d,(100,565),'剩余',34,MUTED)
    bar(d,675,short,GOLD)
    text(d,(100,865),'周额度',62)
    text(d,(980,970),f'{round(week*100)}%',100,GREEN,'ra')
    text(d,(100,980),'剩余',34,MUTED)
    bar(d,1090,week,GREEN)
    if caption:
        if t < 6.5:
            center(d,1360,'同时开始消耗',44)
        else:
            center(d,1325,'五小时额度已耗尽',49,GOLD)
            center(d,1410,'周额度还剩 90%',43)
    center(d,1630,'消耗比例仅为动画示意',28,MUTED)
    center(d,1680,'实际额度与重置时间以账号显示为准',26,MUTED)
    return im

def title(t):
    im,d=base()
    center(d,460,'CHATGPT PLUS',42,MUTED)
    n=round(150*ease(t/1.1))
    center(d,740,f'¥{n}',200,GOLD)
    center(d,920,'一个月，你用回本了吗？',50)
    center(d,1500,'20 美元 / 月 · 人民币金额为口播近似值',26,MUTED)
    return im

def members(t):
    im,d=base()
    text(d,(90,230),'150 元是什么概念？',57)
    names=['QQ 音乐会员','腾讯视频会员','B站大会员','爱奇艺会员','网易云音乐会员','优酷会员']
    for i,name in enumerate(names):
        enter=ease((t-.45*i)/.35)
        if enter<=0: continue
        y=440+i*122+round((1-enter)*28)
        text(d,(94,y),f'0{i+1}',28,GOLD)
        text(d,(190,y-9),name,48)
        d.line((190,y+81,980,y+81),fill=TRACK,width=2)
    if t>=3.2:
        center(d,1360,'这些会员加起来',37,MUTED)
        center(d,1450,'约 130 元',76)
    if t>=4.5:
        center(d,1600,'还剩约 20 元',69,GOLD)
    center(d,1770,'口播预算示意 · 套餐及价格以购买页面为准',25,MUTED)
    return im

def clock(t):
    im,d=base()
    text(d,(90,250),'额度恢复，不配合你的作息',50)
    p=ease((t-1)/4)
    minute=22*60+round(5*60*p)
    h=(minute//60)%24
    m=minute%60
    center(d,740,f'{h:02d}:{m:02d}',168,GOLD)
    center(d,1000,'晚上 22:00  →  次日 03:00',44)
    center(d,1120,'你还得设个闹钟？',52)
    bar(d,1325,p,GOLD)
    center(d,1610,'情境示例 · 重置时间以账号实际显示为准',25,MUTED)
    return im

def ten(t):
    im,d=base()
    text(d,(90,250),'假设每次约消耗周额度的 1/10',43)
    for i in range(10):
        col=i%5;row=i//5
        x=100+col*185;y=640+row*210
        active=t>(i*.36+.5)
        d.rounded_rectangle((x,y,x+140,y+150),22,fill=GOLD if active else TRACK)
        text(d,(x+70,y+74),str(i+1),52,BG if active else MUTED,'mm')
    center(d,1200,'大约要抓住 10 次机会',54)
    center(d,1350,'但一周只有 7 天',66,GOLD)
    center(d,1660,'算例假设 · 不是官方固定额度比例',26,MUTED)
    return im

SCENES={
    'quota':('01_五小时与周额度_带结论',9,lambda t:quota(t,True)),
    'quota-clean':('02_五小时与周额度_纯进度条',9,lambda t:quota(t,False)),
    'title':('03_150元开场',5,title),
    'members':('04_六个会员还剩20元',8,members),
    'clock':('05_晚上十点到凌晨三点',8,clock),
    'ten':('06_十次机会与七天',7,ten),
}

def render(key):
    name,duration,draw=SCENES[key]
    out=ROOT/'01_数字动画'/(name+'.mp4')
    out.parent.mkdir(parents=True,exist_ok=True)
    if out.exists(): raise FileExistsError(out)
    cmd=['ffmpeg','-v','error','-f','rawvideo','-pix_fmt','rgb24','-s',f'{W}x{H}','-r',str(FPS),'-i','-','-an','-c:v','libx264','-preset','fast','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',str(out)]
    p=subprocess.Popen(cmd,stdin=subprocess.PIPE)
    for n in range(duration*FPS):
        frame=draw(n/FPS)
        p.stdin.write(frame.tobytes())
        if n==int((duration-1)*FPS):
            frame.save(ROOT/'04_预览与说明'/(name+'.png'))
    p.stdin.close()
    if p.wait()!=0: raise RuntimeError(name)
    print(json.dumps({'file':str(out),'seconds':duration,'size':out.stat().st_size},ensure_ascii=False),flush=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('scenes',nargs='*',default=list(SCENES))
    args=ap.parse_args()
    for key in args.scenes: render(key)
