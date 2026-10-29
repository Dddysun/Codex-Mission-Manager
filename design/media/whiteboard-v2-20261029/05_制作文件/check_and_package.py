#!/usr/bin/env python3
from pathlib import Path
import json,subprocess,zipfile

ROOT=Path(__file__).resolve().parents[1]
source=ROOT/'03_独立动画/07_兔子上班吃饭睡觉娱乐.mp4'
for i,name in enumerate(['上班','吃饭','睡觉','娱乐']):
    out=ROOT/'03_独立动画'/f'07{i+1}_兔子{name}_单镜头.mp4'
    subprocess.run(['ffmpeg','-v','error','-y','-ss',str(i*2.5),'-i',str(source),'-t','2.5','-an','-c:v','libx264','-preset','fast','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',str(out)],check=True)

manifest=[]
for p in sorted(ROOT.rglob('*.mp4')):
    data=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(p)]))
    videos=[s for s in data['streams'] if s['codec_type']=='video']
    assert len(videos)==1 and all(s['codec_type']!='audio' for s in data['streams']),p
    v=videos[0];assert (v['width'],v['height'],v['r_frame_rate'])==(1080,1920,'30/1'),p
    subprocess.run(['ffmpeg','-v','error','-i',str(p),'-f','null','-'],check=True,stderr=subprocess.PIPE)
    manifest.append({'file':str(p.relative_to(ROOT)),'seconds':float(data['format']['duration']),'size':p.stat().st_size,'video':'1080x1920 H.264 30fps','audio':False,'full_decode':'pass'})
(ROOT/'05_制作文件/media-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
out=ROOT.parent/'TokenMax_白底兔子新版素材包_20261029.zip'
with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for p in sorted(ROOT.rglob('*')):
        if not p.is_file() or '__pycache__' in p.parts or p.name=='concat.txt' or p.name.endswith('-lookup.json') or p.name=='logo-check.jpg':continue
        z.write(p,str(p.relative_to(ROOT.parent)))
print(json.dumps({'videos':len(manifest),'zip':str(out),'bytes':out.stat().st_size,'verified':'all full-decode, 1080x1920/30fps, no audio'},ensure_ascii=False))
