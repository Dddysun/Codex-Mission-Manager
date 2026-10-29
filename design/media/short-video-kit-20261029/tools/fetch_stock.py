#!/usr/bin/env python3
"""Download only the public, selected, licensed sources for this video."""
from pathlib import Path
import hashlib
import json
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
UA='TokenMaxVideoProduction/1.0 (+https://github.com/Dddysun/TokenMax-Zhazhiji)'
ASSETS=[
 ('02_伸手关闹钟','https://assets.mixkit.co/videos/50753/50753-720.mp4','https://mixkit.co/free-stock-video/a-young-man-turns-off-the-alarm-clock-by-the-50753/','Mixkit Stock Video Free License'),
 ('03_放下手机睡觉','https://assets.mixkit.co/videos/31412/31412-720.mp4','https://mixkit.co/free-stock-video/boy-puts-his-cell-phone-aside-so-he-can-go-31412/','Mixkit Stock Video Free License'),
 ('04_电脑打字特写','https://assets.mixkit.co/videos/1781/1781-720.mp4','https://mixkit.co/free-stock-video/typing-on-a-laptop-close-up-1781/','Mixkit Stock Video Free License'),
 ('05_白天办公室','https://assets.mixkit.co/videos/914/914-720.mp4','https://mixkit.co/free-stock-video/open-office-space-914/','Mixkit Stock Video Free License'),
 ('06_深夜电脑前工作','https://videos.pexels.com/video-files/34492302/14614656_3840_2160_30fps.mp4','https://www.pexels.com/video/focused-man-working-on-multiple-screens-at-night-34492302/','Pexels License'),
]

def get(url,target,limit=100*1024*1024):
    if target.exists():return
    req=urllib.request.Request(url,headers={'User-Agent':UA})
    with urllib.request.urlopen(req,timeout=40) as r:
        data=r.read(limit+1)
    if len(data)>limit:raise ValueError('File exceeded size limit')
    if target.suffix=='.mp4' and b'ftyp' not in data[:40]:raise ValueError('Expected MP4')
    if target.suffix=='.json':json.loads(data)
    target.write_bytes(data)

def main():
    records=[]
    for local,remote in [('provinces.geojson','china_province_full.geojson'),('cities.geojson','china_province_city_full.geojson')]:
        get('https://raw.githubusercontent.com/Supeset/China-GeoData/main/geojson/'+remote,ROOT/'tools/map-data'/local,8*1024*1024)
    first=ROOT/'02_生活素材/01_睡前设闹钟_横屏原片.mp4'
    # The delivered kit contains the browser-downloaded Full HD version.
    # A fresh rebuild can use the public preview-resolution download instead.
    get('https://assets.mixkit.co/videos/31410/31410-720.mp4',first)
    for name,url,page,lic in ASSETS:
        out=ROOT/'02_生活素材'/(name+'_横屏原片.mp4')
        get(url,out)
        records.append({'file':str(out.relative_to(ROOT)),'download':url,'source_page':page,'license':lic,'license_page':'https://www.pexels.com/license/' if 'Pexels' in lic else 'https://mixkit.co/license/','sha256':hashlib.sha256(out.read_bytes()).hexdigest()})
        print(json.dumps({'downloaded':name,'bytes':out.stat().st_size},ensure_ascii=False),flush=True)
    records.insert(0,{'file':'02_生活素材/01_睡前设闹钟_横屏原片.mp4','source_page':'https://mixkit.co/free-stock-video/man-setting-his-alarm-clock-before-going-to-sleep-31410/','license':'Mixkit Stock Video Free License','license_page':'https://mixkit.co/license/','retrieval':'Original kit: Full HD browser download; fresh rebuild: 720p fallback','fallback_url':'https://assets.mixkit.co/videos/31410/31410-720.mp4'})
    (ROOT/'04_预览与说明/stock-sources.json').write_text(json.dumps(records,ensure_ascii=False,indent=2)+'\n')
    out=ROOT/'tools/map-data/guiyang-streets.json'
    if not out.exists():
        url='https://api.openstreetmap.org/api/0.6/map?bbox=106.70,26.57,106.72,26.59'
        xml=ROOT/'tools/map-data/guiyang-streets.osm'
        get(url,xml,8*1024*1024)
        root=ET.parse(xml).getroot()
        nodes={n.attrib['id']:{'lon':float(n.attrib['lon']),'lat':float(n.attrib['lat'])} for n in root.findall('node')}
        ways=[]
        for w in root.findall('way'):
            tags={t.attrib['k']:t.attrib['v'] for t in w.findall('tag') if t.attrib['k'] in ('name','highway','waterway')}
            if not any(k in tags for k in ('highway','waterway')):continue
            ways.append({'id':int(w.attrib['id']),'tags':tags,'geometry':[nodes[n.attrib['ref']] for n in w.findall('nd') if n.attrib['ref'] in nodes]})
        out.write_text(json.dumps({'source':url,'license':'ODbL 1.0','copyright':'OpenStreetMap contributors','elements':ways},ensure_ascii=False))
    print(json.dumps({'map_roads':len(json.loads(out.read_bytes())['elements'])}),flush=True)

if __name__=='__main__':main()
