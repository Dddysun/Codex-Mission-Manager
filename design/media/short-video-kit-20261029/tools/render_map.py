#!/usr/bin/env python3
"""Render China -> Guizhou -> Guiyang -> streets from cached vector data."""
from pathlib import Path
import json
import math
import subprocess
from PIL import Image, ImageDraw
from render_motion import W,H,FPS,font,text,ease

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'tools/map-data'
PAPER='#EEECE3';INK='#26362F';LAND='#C5CFC0';EDGE='#869884';GOLD='#E6AE41'

def simplify(points,tol):
    if len(points)<6:return points
    a,b=points[0],points[-1]
    if a==b:
        k=len(points)//2
        return simplify(points[:k+1],tol)[:-1]+simplify(points[k:],tol)
    dx,dy=b[0]-a[0],b[1]-a[1]
    div=math.hypot(dx,dy)
    dist=lambda p:abs(dy*p[0]-dx*p[1]+b[0]*a[1]-b[1]*a[0])/div
    best=max(range(1,len(points)-1),key=lambda i:dist(points[i]))
    if dist(points[best])<=tol:return [a,b]
    return simplify(points[:best+1],tol)[:-1]+simplify(points[best:],tol)

def prep(features,tol):
    out=[]
    for f in features:
        g=f['geometry'];ps=g['coordinates'] if g['type']=='MultiPolygon' else [g['coordinates']]
        polygons=[]
        for p in ps:
            ring=simplify(p[0],tol)
            if len(ring)>2:
                xs=[v[0] for v in ring];ys=[v[1] for v in ring]
                polygons.append((ring,(min(xs),min(ys),max(xs),max(ys))))
        out.append((f['properties'],polygons))
    return out

provinces=prep(json.loads((DATA/'provinces.geojson').read_text())['features'],.013)
allcities=json.loads((DATA/'cities.geojson').read_text())['features']
cities=prep([f for f in allcities if str(f['properties'].get('adcode','')).startswith('52')],.002)
roads=json.loads((DATA/'guiyang-streets.json').read_text())['elements']

def camera(t):
    points=[(0,(104,29,65)),(.8,(104,29,65)),(3.0,(106.65,26.85,7.4)),(3.8,(106.65,26.85,7.4)),(5.7,(106.67,26.75,1.8)),(6.4,(106.67,26.75,1.8)),(9.1,(106.71,26.58,.028)),(10,(106.71,26.58,.028))]
    for (a,ca),(b,cb) in zip(points,points[1:]):
        if a<=t<=b:
            p=ease((t-a)/(b-a))
            return ca[0]+(cb[0]-ca[0])*p,ca[1]+(cb[1]-ca[1])*p,math.exp(math.log(ca[2])+(math.log(cb[2])-math.log(ca[2]))*p)
    return points[-1][1]

def frame(t):
    im=Image.new('RGB',(W,H),PAPER);d=ImageDraw.Draw(im)
    lon,lat,span=camera(t)
    sx=1000/span;sy=sx/math.cos(math.radians(lat))
    def project(p):return (540+(p[0]-lon)*sx,975-(p[1]-lat)*sy)
    def visible(b):
        return not (b[2]<lon-span*.56 or b[0]>lon+span*.56 or b[3]<lat-1000/sy or b[1]>lat+1000/sy)
    for props,polys in provinces:
        fill=GOLD if props.get('adcode')==520000 else LAND
        if span<.15:fill=PAPER
        for ring,bbox in polys:
            if visible(bbox):d.polygon([project(p) for p in ring],fill=fill,outline=EDGE,width=2)
    if span<14:
        for props,polys in cities:
            fill=GOLD if span>3.3 else '#AFBEA5' if props.get('adcode')!=520100 else '#DFA540'
            if span<.15:fill=PAPER
            for ring,bbox in polys:
                if visible(bbox):d.polygon([project(p) for p in ring],fill=fill,outline='#7B8C72',width=2)
    if span<.55:
        names=[]
        for road in roads:
            pts=road.get('geometry',[]);tags=road.get('tags',{})
            if len(pts)<2:continue
            xy=[project((p['lon'],p['lat'])) for p in pts]
            iswater='waterway' in tags
            kind=tags.get('highway','')
            width=9 if kind in ('primary','secondary','trunk') else 5
            width=max(2,int(width*min(1,.065/span)))
            d.line(xy,fill='#A5C7CC' if iswater else '#B8B8AB',width=width+3)
            if not iswater:d.line(xy,fill='#FFFEF7',width=width)
            name=tags.get('name','')
            m=xy[len(xy)//2]
            if name and kind in ('primary','secondary') and 100<m[0]<900 and 450<m[1]<1400 and name not in [a[0] for a in names]:
                if all(math.hypot(m[0]-a[1][0],m[1]-a[1][1])>180 for a in names):names.append((name,m))
        for name,m in names[:8]:text(d,m,name,23,'#737D73')
    if span>16:
        text(d,project((102,38)),'中国',65,INK,'mm')
    elif span>.8:
        for props,_ in cities:
            if props.get('adcode')==520100:continue
            c=props.get('center') or props.get('centroid')
            if c:
                q=project(c)
                name=props.get('name','').replace('市','')
                if name.startswith('黔'):name=name[:3]
                if 40<q[0]<1040 and 380<q[1]<1450:text(d,q,name,24,INK,'mm')
    pin=project((106.71,26.58))
    if 10<pin[0]<1070 and 350<pin[1]<1450:
        x,y=pin;r=14+4*math.sin(t*5)
        d.ellipse((x-r-12,y-r-12,x+r+12,y+r+12),outline=INK,width=2)
        d.ellipse((x-r,y-r,x+r,y+r),fill='#B4622B')
        label='贵阳街区' if span<.2 else '贵阳'
        text(d,(x+40,y-45),label,33,INK)
    d.rectangle((0,0,W,330),fill=PAPER)
    text(d,(80,125),'剩下的 20 元，带你回我的家乡',37,INK)
    stage='中国' if t<2.4 else '贵州省' if t<4.9 else '贵阳市' if t<7.7 else '贵阳 · 街头'
    text(d,(80,205),stage,65,INK)
    d.rectangle((0,1500,W,H),fill=PAPER)
    text(d,(80,1550),'中国  /  贵州  /  贵阳',37,INK)
    text(d,(80,1635),'从地图，走进一碗牛肉粉。',42,INK)
    text(d,(80,1740),'地理位置示意 · 无指定商家',25,'#737D73')
    text(d,(80,1790),'省市：China-GeoData · MIT',23,'#737D73')
    text(d,(80,1830),'街道：© OpenStreetMap contributors · ODbL',22,'#737D73')
    return im

out=ROOT/'03_贵阳牛肉粉/00_中国到贵州贵阳街区_地图动画_v2.mp4'
if out.exists():raise FileExistsError(out)
p=subprocess.Popen(['ffmpeg','-v','error','-f','rawvideo','-pix_fmt','rgb24','-s',f'{W}x{H}','-r',str(FPS),'-i','-','-an','-c:v','libx264','-preset','fast','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',str(out)],stdin=subprocess.PIPE)
for n in range(10*FPS):
    f=frame(n/FPS);p.stdin.write(f.tobytes())
    if n in [0,110,180,290]:f.save(ROOT/'04_预览与说明'/f'地图_{n:03d}.png')
p.stdin.close()
if p.wait()!=0:raise RuntimeError('Map encoding failed')
print(json.dumps({'map':str(out),'seconds':10,'size':out.stat().st_size},ensure_ascii=False))
