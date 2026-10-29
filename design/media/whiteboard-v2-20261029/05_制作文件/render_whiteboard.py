#!/usr/bin/env python3
"""White-background portrait inserts. Original articulated line animation; no TTS.
Requires Pillow and ffmpeg. External images are unmodified source screenshots/icons.
"""
from pathlib import Path
from functools import lru_cache
import argparse, json, math, subprocess
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[1]
W,H,FPS=1080,1920,30
INK='#202023';GRAY='#77777B';PALE='#EAEAEA';RED='#E64E47';GOLD='#F4C54E';WHITE='#FFFFFF'
FONT='/System/Library/Fonts/Hiragino Sans GB.ttc'
NAMES=['QQ音乐','腾讯视频','B站大会员','爱奇艺','网易云音乐','优酷']
SLUGS=['qqmusic','tencentvideo','bilibili','iqiyi','neteasemusic','youku']

@lru_cache(None)
def font(s): return ImageFont.truetype(FONT,max(8,round(s)))
def txt(d,x,y,s,z=48,fill=INK,anchor='mm'):
    d.text((x,y),s,font=font(z),fill=fill,anchor=anchor)
def ease(p):
    p=max(0,min(1,p));return p*p*(3-2*p)
def mix(a,b,p):return a+(b-a)*p
def canvas():
    im=Image.new('RGB',(W,H),WHITE);return im,ImageDraw.Draw(im)
def head(d,s): txt(d,540,300,s,64)
def foot(d,s):txt(d,540,1740,s,26,GRAY)
def line(d,pts,w=7,fill=INK):
    d.line(pts,fill=fill,width=max(1,round(w)),joint='curve')
    r=w/2
    for x,y in (pts[0],pts[-1]):d.ellipse((x-r,y-r,x+r,y+r),fill=fill)
def bezier(pts,n=24):
    out=[]
    for i in range(n+1):
        t=i/n;u=1-t
        out.append(tuple(u**3*pts[0][j]+3*u*u*t*pts[1][j]+3*u*t*t*pts[2][j]+t**3*pts[3][j] for j in range(2)))
    return out

class Pen:
    def __init__(self,d,x,y,s=1,flip=1):self.d=d;self.x=x;self.y=y;self.s=s;self.flip=flip
    def p(self,x,y):return self.x+x*self.s*self.flip,self.y+y*self.s
    def box(self,b):
        a=self.p(b[0],b[1]);c=self.p(b[2],b[3]);return min(a[0],c[0]),min(a[1],c[1]),max(a[0],c[0]),max(a[1],c[1])
    def ellipse(self,b,fill=WHITE,w=5,outline=INK):self.d.ellipse(self.box(b),fill=fill,outline=outline,width=max(1,round(w*self.s)))
    def rect(self,b,fill=WHITE,w=5,r=12,outline=INK):self.d.rounded_rectangle(self.box(b),radius=r*self.s,fill=fill,outline=outline,width=max(1,round(w*self.s)))
    def line(self,pts,w=6,fill=INK):line(self.d,[self.p(*p) for p in pts],w*self.s,fill)
    def curve(self,pts,w=6,fill=INK):self.line(bezier(pts),w,fill)
    def poly(self,pts,fill=WHITE,w=5):
        q=[self.p(*p) for p in pts];self.d.polygon(q,fill=fill);line(self.d,q+[q[0]],w*self.s)
    def text(self,x,y,s,z=40,fill=INK):txt(self.d,*self.p(x,y),s,z*self.s,fill)

def rabbit(d,x,y,s=1,t=0,pose='idle',mood='normal',flip=1):
    # Deliberately small pose vocabulary: crisp holds, blinks, arm actions, ear reactions.
    p=Pen(d,x,y,s,flip); sleepy=mood in ('sleep','tired');hit=math.sin(t*17)
    p.ellipse((-56,-30,-3,4),WHITE,5);p.ellipse((3,-30,56,4),WHITE,5)
    p.ellipse((-65,-180,65,-12),WHITE,5)
    if sleepy:
        p.poly([(-64,-264),(-112,-338),(-111,-365),(-89,-370),(-47,-292)],WHITE,5)
        p.poly([(27,-267),(53,-354),(75,-367),(95,-351),(69,-267)],WHITE,5)
    else:
        p.ellipse((-67,-408,-18,-252),WHITE,5)
        p.ellipse((15,-423,64,-251),WHITE,5)
        p.line([(-43,-377),(-43,-301)],3,PALE);p.line([(40,-390),(40,-302)],3,PALE)
    p.ellipse((-88,-302,88,-148),WHITE,5)
    p.poly([(-61,-163),(56,-163),(37,-137),(-42,-143)],RED,3)
    p.poly([(30,-144),(64,-109),(39,-110),(18,-141)],RED,3)
    blink=(t%4.1)>3.94
    if sleepy or blink:
        p.line([(-49,-224),(-28,-224)],5);p.line([(28,-224),(49,-224)],5)
        if sleepy:
            p.line([(-49,-213),(-28,-210)],2,GRAY);p.line([(28,-210),(49,-213)],2,GRAY)
    else:
        p.ellipse((-46,-236,-33,-214),INK,1);p.ellipse((33,-236,46,-214),INK,1)
        if mood=='shock':
            p.line([(-51,-249),(-27,-257)],5);p.line([(27,-257),(51,-249)],5)
    if mood=='shock':p.ellipse((-12,-200,12,-174),WHITE,4)
    elif sleepy:p.line([(-14,-181),(14,-181)],4)
    else:
        p.curve([(-18,-191),(-8,-178),(8,-178),(18,-191)],4)
    if pose=='type':
        p.line([(-54,-132),(-81,-101),(-8,-97+7*hit)],7)
        p.line([(54,-132),(82,-101),(28,-97-7*hit)],7)
    elif pose=='pay':
        p.line([(-54,-130),(-84,-91),(-53,-73)],7)
        p.line([(55,-130),(100,-123),(139,-152+9*hit)],7)
        p.rect((-90,-105,-18,-58),'#FCF5DF',4,5)
    elif pose=='eat':
        p.line([(-54,-132),(-82,-92),(-24,-81)],7)
        p.line([(55,-132),(94,-143),(51,-190+8*math.sin(t*5))],7)
        p.line([(48,-193),(3,-195)],3);p.line([(47,-201),(3,-203)],3)
    elif pose=='game':
        p.line([(-54,-132),(-75,-93),(-36,-85)],7);p.line([(54,-132),(75,-93),(36,-85)],7)
        p.rect((-48,-105,48,-62),WHITE,4,15)
        p.line([(-32,-84),(-16,-84)],3);p.line([(-24,-92),(-24,-76)],3)
        p.ellipse((22,-92,29,-85),RED,1);p.ellipse((31,-83,38,-76),INK,1)
    elif pose=='phone':
        p.line([(-54,-132),(-76,-76)],7);p.line([(54,-132),(91,-119),(88,-184)],7)
        p.rect((67,-227,112,-162),WHITE,4,5);p.line([(80,-170),(96,-170)],2)
    elif pose=='wait':
        p.line([(-54,-132),(-85,-83),(-13,-71)],7);p.line([(54,-132),(83,-77),(10,-70)],7)
    else:
        p.line([(-54,-132),(-76,-75)],7);p.line([(54,-132),(76,-75)],7)

def ai(d,x,y,s=1,t=0,work=True):
    p=Pen(d,x,y,s);wave=math.sin(t*23)
    p.line([(-29,-30),(-32,1),(-57,1)],8);p.line([(29,-30),(32,1),(57,1)],8)
    p.rect((-69,-174,69,-33),WHITE,5,17)
    p.line([(0,-314),(0,-337)],5);p.ellipse((-10,-354,10,-334),GOLD if work else WHITE,4)
    p.rect((-95,-315,95,-176),WHITE,5,30)
    p.text(0,-279,'AI',42)
    if work:
        p.ellipse((-43,-245,-28,-229),INK,1);p.ellipse((28,-245,43,-229),INK,1)
        p.line([(-13,-207),(13,-207)],4)
        p.line([(-60,-142),(-100,-106),(-18,-95+10*wave)],7)
        p.line([(60,-142),(104,-103),(36,-95-10*wave)],7)
    else:
        p.line([(-47,-238),(-24,-232)],5);p.line([(24,-232),(47,-238)],5)
        p.curve([(-19,-198),(-10,-211),(10,-211),(19,-198)],4)
        p.line([(-61,-137),(-91,-94),(-42,-79)],7);p.line([(61,-137),(91,-94),(42,-79)],7)
        bowl(d,*p.p(0,-77),s*.8,False)
        p.text(0,-58,'额度',24)

def laptop(d,x,y,s=1,t=0,empty=False):
    p=Pen(d,x,y,s)
    p.rect((-132,-165,132,-15),WHITE,5,8)
    if empty:
        p.text(0,-103,'额度耗尽',25,RED);p.text(0,-56,'0%',27)
    else:
        for k in range(4):p.line([(-104,-130+k*25),(-33+((int(t*4)+k)%3)*39,-130+k*25)],3,GRAY)
    p.poly([(-132,-15),(132,-15),(157,8),(-157,8)],WHITE,5)
def desk(d,x,y,s=1):
    p=Pen(d,x,y,s);p.line([(-220,0),(220,0)],7);p.line([(-185,0),(-185,167)],6);p.line([(185,0),(185,167)],6)
def typing_paws(d,x,y,s,t):
    for sign in [-1,1]:
        yy=y+7*s*math.sin(t*19+sign*math.pi/2)
        xx=x+sign*48*s
        d.ellipse((xx-17*s,yy-12*s,xx+17*s,yy+9*s),fill=WHITE,outline=INK,width=max(2,round(4*s)))
        if math.sin(t*19+sign*math.pi/2)<-.4:
            line(d,[(xx-11*s,yy-25*s),(xx-20*s,yy-38*s)],3*s)
            line(d,[(xx+11*s,yy-25*s),(xx+20*s,yy-38*s)],3*s)
def bowl(d,x,y,s=1,food=True):
    p=Pen(d,x,y,s)
    p.curve([(-85,0),(-66,80),(64,80),(85,0)],5)
    p.ellipse((-85,-17,85,17),'#FFF5D7' if food else WHITE,4)
    if food:
        for k in range(4):p.curve([(-54+k*27,-9),(-75+k*27,12),(-36+k*27,13),(-42+k*27,-8)],2,'#AA8E53')
    p.line([(-24,61),(24,61)],4)
def coin(d,x,y,r=52,label='¥',angle=0):
    rx=max(r*.18,r*abs(math.cos(angle)))
    d.ellipse((x-rx+7,y-r,x+rx+7,y+r),fill='#D69A2E',outline=INK,width=3)
    d.ellipse((x-rx,y-r,x+rx,y+r),fill=GOLD,outline=INK,width=3)
    if rx>r*.6:
        d.ellipse((x-rx+8,y-r+8,x+rx-8,y+r-8),outline='#BD8A28',width=2)
        txt(d,x,y,label,round(r*(.72 if len(label)>1 else 1.05)))
def clock(d,x,y,r=100,hour=3,minute=0,t=0,ring=False):
    wobble=8*math.sin(t*35) if ring else 0
    x+=wobble
    d.ellipse((x-r,y-r,x+r,y+r),fill=WHITE,outline=INK,width=7)
    for k in range(12):
        a=k*math.pi/6;line(d,[(x+math.sin(a)*r*.8,y-math.cos(a)*r*.8),(x+math.sin(a)*r*.9,y-math.cos(a)*r*.9)],4)
    a=(hour+minute/60)*math.pi/6;b=minute*math.pi/30
    line(d,[(x,y),(x+math.sin(a)*r*.47,y-math.cos(a)*r*.47)],7)
    line(d,[(x,y),(x+math.sin(b)*r*.72,y-math.cos(b)*r*.72)],5)
    if ring:
        for sign in [-1,1]:
            d.arc((x+sign*r-r*.5,y-r*1.1,x+sign*r+r*.5,y-r*.2),190 if sign<0 else 250,280 if sign<0 else 340,fill=INK,width=5)

@lru_cache(None)
def img(name):return Image.open(ROOT/name).convert('RGB')
def paste(im,source,box,crop=None):
    a=source.crop(tuple(round(v) for v in crop)) if crop else source
    b=tuple(round(v) for v in box)
    if b[2]<=b[0] or b[3]<=b[1]:return
    a=a.resize((b[2]-b[0],b[3]-b[1]),Image.Resampling.LANCZOS);im.paste(a,b[:2])
def logo(im,slug,x,y,size):
    src=ROOT/'02_Logo'/(slug+'-brand.png')
    a=img(str(src.relative_to(ROOT))) if src.exists() else img('02_Logo/'+slug+'.jpg')
    paste(im,a,(x-size/2,y-size/2,x+size/2,y+size/2))

def official(t):
    im,d=canvas();head(d,'ChatGPT Plus')
    if t<1.5:
        a=img('01_官网与汇率截图/openai_00_官方说明.png');paste(im,a,(50,650,1030,1201))
    else:
        p=ease((t-1.8)/1.8)
        crop=[mix(a,b,p) for a,b in zip((115,0,850,210),(133,43,417,95))]
        h=950*(crop[3]-crop[1])/(crop[2]-crop[0]);paste(im,img('01_官网与汇率截图/openai_01_月费20美元.png'),(65,900-h/2,1015,900+h/2),crop)
        if t>3.5:line(d,[(340,1010),(340+360*ease((t-3.5)/.5),1010)],9,RED)
    txt(d,540,1350,'每个月',45)
    foot(d,'OpenAI 官网截图 · help.openai.com')
    return im

def exchange(t):
    im,d=canvas();head(d,'换成人民币呢？')
    if t<2:
        f='google_00_搜索前.png' if t<.6 else 'google_01_输入查询.png'
        paste(im,img('01_官网与汇率截图/'+f),(40,630,1040,1192))
    else:
        p=ease((t-2)/1.1);crop=[mix(a,b,p) for a,b in zip((0,0,1280,720),(80,0,800,440))]
        h=1000*(crop[3]-crop[1])/(crop[2]-crop[0]);paste(im,img('01_官网与汇率截图/google_02_汇率结果.png'),(40,600,1040,600+h),crop)
        if t>3.6:txt(d,540,1440,'一百三十多块钱',62)
    foot(d,'查询截图 · 2026.10.29 · 结算金额以实际账单为准')
    return im

def members(t):
    im,d=canvas();head(d,'这笔钱，还能买什么？')
    for i,(slug,name) in enumerate(zip(SLUGS,NAMES)):
        p=ease((t-i*.65)/.3)
        if p<=0:continue
        x=240+i%3*300;y=730+i//3*420
        size=185*(1+.10*math.sin(p*math.pi))
        logo(im,slug,x,y+45*(1-p),size*p)
        if p>.9:txt(d,x,y+155,name,35)
    if t>4.2:txt(d,540,1510,'一个、两个……六个。',44)
    return im

def scale(t):
    im,d=canvas();head(d,'一边是 Plus，一边是……')
    landing=max(0,t-2.7)
    ang=.15 if t<2.7 else .15*math.exp(-2.4*landing)*math.cos(landing*7)
    cy=790;lx=250;rx=825;ly=cy+math.sin(ang)*290;ry=cy-math.sin(ang)*290
    # Central support, moving beam, independently hanging pans.
    line(d,[(540,800),(540,1370)],10)
    d.polygon([(540,780),(520,820),(560,820)],fill=INK)
    line(d,[(lx,ly),(rx,ry)],10)
    d.ellipse((526,776,554,804),fill=GOLD,outline=INK,width=3)
    for x,y in [(lx,ly),(rx,ry)]:
        line(d,[(x,y),(x-165,y+420)],3);line(d,[(x,y),(x+165,y+420)],3)
        line(d,[(x-175,y+420),(x+175,y+420)],8)
        d.arc((x-175,y+380,x+175,y+490),0,180,fill=INK,width=6)
    line(d,[(385,1380),(695,1380)],12)
    logo(im,'chatgpt',lx,ly+240,158);txt(d,lx,ly+355,'Plus',46)
    for i,slug in enumerate(SLUGS):
        logo(im,slug,rx-102+i%3*102,ry+220+i//3*111,85)
    p=ease((t-4.7)/1.4)
    cx=mix(rx,540,p);yy=mix(ry+100,1540,p);rr=mix(56,115,p)
    if t>2.7:coin(d,cx,yy,rr,'¥20')
    if t>6.4:txt(d,540,490,'还留出一碗粉的钱',48)
    foot(d,'分镜预算示意 · 六项会员套餐合计待核价')
    return im

def coin_bridge(t):
    im,d=canvas();p=ease(t/1.6)
    coin(d,540,mix(1540,820,p),mix(115,155,p),'¥20')
    if t>1.6:
        txt(d,540,1200,'这 20 块钱',65)
        txt(d,540,1310,'带你回我的家乡',44)
    if t>2.8:
        txt(d,540,1510,'贵阳 · 牛肉粉',60)
        # A route line grows toward the next map shot.
        line(d,[(540,1040),(540,1040+90*ease((t-2.8)/.6))],5,GRAY)
    return im

def quota(t):
    im,d=canvas();head(d,'五小时额度')
    p=max(0,min(1,(t-1)/5.5));a=1-p;b=1-.1*p
    for y,name,value in [(720,'五小时额度',a),(1110,'周额度',b)]:
        txt(d,110,y-110,name,49,anchor='lm');txt(d,960,y-110,f'{round(value*100)}%',68,anchor='rm')
        d.rounded_rectangle((110,y,970,y+50),25,fill=WHITE,outline=INK,width=4)
        if value>.005:d.rectangle((116,y+6,116+848*value,y+44),fill=RED if name=='五小时额度' else INK)
    if t>6.5:txt(d,540,1450,'这边没了，那边才用一点。',43)
    foot(d,'消耗比例为示意 · 实际额度以账号显示为准')
    return im

def life(t):
    im,d=canvas();phase=min(3,int(t/2.5));local=t-phase*2.5
    head(d,['要上班','要吃饭','要睡觉','也要有自己的娱乐'][phase])
    if phase==0:
        rabbit(d,530,1290,1.42,local,'type');desk(d,540,1185,1.4);laptop(d,540,1174,1.17,local)
        typing_paws(d,540,1170,1.1,local)
        clock(d,825,650,67,10)
    elif phase==1:
        rabbit(d,540,1300,1.42,local,'eat');desk(d,540,1200,1.4);bowl(d,540,1165,1.6)
        for k in range(3):
            x=485+k*55;line(d,bezier([(x,1100),(x-18,1070),(x+15,1055),(x,1025)]),3,GRAY)
    elif phase==2:
        # Rabbit curled in bed; the head and floppy ears remain visibly the same character.
        rabbit(d,380,1270,1.25,local,'wait','sleep')
        d.rounded_rectangle((255,1120,870,1330),45,fill=WHITE,outline=INK,width=7)
        line(d,[(230,1350),(900,1350)],8);line(d,[(250,1350),(250,1430)],7);line(d,[(880,1350),(880,1430)],7)
        txt(d,665,900-12*math.sin(local*2),'Z',66);txt(d,745,820-10*math.sin(local*2),'z',44)
        d.arc((790,610,900,720),35,300,fill=INK,width=6)
    else:
        rabbit(d,540,1310,1.55,local,'game')
        for k in range(3):
            x=285+k*250;y=610+15*math.sin(local*3+k)
            line(d,[(x,y),(x,y-42),(x+19,y-32)],4,GRAY)
            d.ellipse((x-17,y-4,x+1,y+9),fill=GRAY)
    return im

def night(t):
    im,d=canvas();p=ease((t-1.6)/2.2);islate=t>=4.3
    minutes=1320+round(300*p);hour=minutes//60%24;minute=minutes%60
    txt(d,540,350,f'{hour:02d}:{minute:02d}',134)
    if not islate:
        rabbit(d,420,1260,1.4,t,'type',mood='tired' if t>1.2 else 'normal');desk(d,510,1165,1.2);laptop(d,600,1155,1,t,True)
        if t>1:txt(d,540,1520,'下一次：凌晨 03:00',46)
    else:
        rabbit(d,420,1260,1.5,t,'phone','tired');clock(d,820,1080,110,3,0,t,True)
        txt(d,540,1510,'人醒了。',63)
        if t>6.2:txt(d,540,1600,'脑子还没醒。',45)
    foot(d,'22:00 → 03:00 为情境示例，非固定重置规则')
    return im

def office(t):
    im,d=canvas();head(d,'人在公司，心在家里。')
    rabbit(d,350,1370,1.3,t,'type' if t<3.4 else 'phone','normal' if t<3.4 else 'tired')
    desk(d,340,1270,1.1);laptop(d,340,1250,.94,t)
    if t<3.4:typing_paws(d,340,1250,.85,t)
    # A separate home screen makes the remote-control relationship explicit.
    line(d,[(685,680),(810,575),(940,680)],6)
    d.rectangle((710,680,920,900),fill=WHITE,outline=INK,width=5)
    laptop(d,817,835,.6,t,True);txt(d,817,963,'家里的电脑',30)
    for k in range(6):line(d,[(530+k*37,1090-k*25),(546+k*37,1079-k*25)],3,GRAY)
    if t>3.4:
        clock(d,800,1230,86,15,0,t,True);txt(d,540,1540,'还得再定一个闹钟。',46)
    return im

def paying(t):
    im,d=canvas();head(d,'花钱，请 AI 干活。')
    rabbit(d,285,1320,1.2,t,'pay');ai(d,785,1320,1.2,t,True)
    desk(d,790,1220,.92);laptop(d,790,1208,.78,t)
    typing_paws(d,790,1207,.95,t)
    txt(d,280,1430,'我',46);txt(d,785,1430,'AI',46)
    for k in range(3):
        p=(t*.7+k/3)%1;coin(d,mix(430,695,p),880-150*math.sin(p*math.pi),32,'¥',p*5)
    txt(d,795,725,['咣咣咣','咣咣','咣咣咣'][int(t*4)%3],34)
    return im

def waiting(t):
    im,d=canvas();head(d,'结果，现在反过来了。')
    rabbit(d,285,1320,1.22,t,'wait','tired');ai(d,785,1320,1.22,t,False)
    txt(d,285,1450,'我在等 AI',45);txt(d,785,1450,'AI 在等额度',42)
    # Thoughts emerge as actions stop: robot's empty allowance bowl, owner's trailing coins.
    txt(d,785,700,'还没轮到我吃饭……',29,GRAY)
    txt(d,285,735,'还要多久？',36)
    for k in range(3):
        p=(t*.35+k/3)%1;coin(d,540+32*math.sin(k),mix(1070,1590,p),27,'¥',p*4)
    if t>2.3:txt(d,540,1650,'钱还在花。',48)
    return im

SCENES={
 'official':('01_官网20美元_截图推进',6,official),
 'exchange':('02_搜索汇率_真实截图',7,exchange),
 'members':('03_六个会员Logo依次出现',6,members),
 'scale':('04_会员天秤与20元金币',8,scale),
 'coin':('05_金币居中_引向贵阳',4,coin_bridge),
 'quota':('06_双额度进度条_白底',9,quota),
 'life':('07_兔子上班吃饭睡觉娱乐',10,life),
 'night':('08_晚上十点到凌晨三点',9,night),
 'office':('09_公司遥控家里电脑再设闹钟',8,office),
 'paying':('10_我付钱AI敲键盘',7,paying),
 'waiting':('11_AI等额度我等AI钱继续花',8,waiting),
}

def render(key,force=False):
    name,dur,fn=SCENES[key];out=ROOT/'03_独立动画'/(name+'.mp4')
    if out.exists() and not force:raise FileExistsError(out)
    p=subprocess.Popen(['ffmpeg','-v','error','-y','-f','rawvideo','-pix_fmt','rgb24','-s',f'{W}x{H}','-r',str(FPS),'-i','-','-an','-c:v','libx264','-preset','fast','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',str(out)],stdin=subprocess.PIPE)
    for n in range(round(dur*FPS)):
        frame=fn(n/FPS);p.stdin.write(frame.tobytes())
    p.stdin.close()
    if p.wait()!=0:raise RuntimeError(name)
    print(json.dumps({'file':out.name,'seconds':dur,'bytes':out.stat().st_size},ensure_ascii=False),flush=True)

def sheets():
    samples=[('official',5),('exchange',5),('members',5),('scale',4.5),('coin',3.5),('quota',8),('life',1),('life',3.5),('life',6),('life',8.7),('night',7),('office',6),('paying',4),('waiting',5)]
    sheet=Image.new('RGB',(4*300,4*580),'#E6E6E6');d=ImageDraw.Draw(sheet)
    for i,(k,t) in enumerate(samples):
        f=SCENES[k][2](t);f.save(ROOT/'04_预览'/f'分镜_{i+1:02d}.png');f=f.resize((270,480),Image.Resampling.LANCZOS)
        x=(i%4)*300+15;y=(i//4)*580+15;sheet.paste(f,(x,y));txt(d,x+135,y+515,f'{i+1:02d} · {SCENES[k][0][3:]}',17)
    sheet.save(ROOT/'04_预览/新版分镜总览.jpg',quality=93)

def preview():
    paths=[ROOT/'03_独立动画'/(v[0]+'.mp4') for v in SCENES.values()]
    manifest=ROOT/'05_制作文件/concat.txt';manifest.write_text('\n'.join("file '"+str(p)+"'" for p in paths))
    out=ROOT/'04_预览/82秒_新版镜头试剪_无旁白.mp4'
    subprocess.run(['ffmpeg','-v','error','-y','-f','concat','-safe','0','-i',str(manifest),'-c','copy','-an','-movflags','+faststart',str(out)],check=True)
    timeline=[];start=0
    for name,dur,_ in SCENES.values():timeline.append({'start':start,'end':start+dur,'file':name+'.mp4'});start+=dur
    (ROOT/'05_制作文件/timeline.json').write_text(json.dumps(timeline,ensure_ascii=False,indent=2))
    print(json.dumps({'preview':str(out),'seconds':start},ensure_ascii=False),flush=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('scenes',nargs='*');ap.add_argument('--sheets',action='store_true');ap.add_argument('--preview',action='store_true');ap.add_argument('--force',action='store_true');a=ap.parse_args()
    if a.sheets:sheets()
    for k in a.scenes:render(k,a.force)
    if a.preview:preview()
