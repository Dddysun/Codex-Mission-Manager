#!/usr/bin/env python3
"""Decode delivered videos, record metadata, and package selected deliverables."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import subprocess
import zipfile

ROOT=Path(__file__).resolve().parents[1]

def selected():
    return sorted(p for p in ROOT.rglob('*') if p.is_file()
      and 'work' not in p.relative_to(ROOT).parts
      and '__pycache__' not in p.relative_to(ROOT).parts
      and p.name!='00_中国到贵州贵阳街区_地图动画.mp4'
      and p.suffix not in ('.zip','.pyc'))

def inspect(path):
    meta=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration:stream=codec_type,codec_name,width,height,r_frame_rate','-of','json',str(path)]))
    check=subprocess.run(['ffmpeg','-v','error','-i',str(path),'-f','null','-'],capture_output=True,text=True)
    if check.returncode or check.stderr.strip():raise RuntimeError(f'Decode failed: {path.name}: {check.stderr}')
    video=next(s for s in meta['streams'] if s['codec_type']=='video')
    source='横屏原片' in path.name
    if not source and (video['width'],video['height'])!=(1080,1920):raise ValueError(f'Bad portrait format: {path}')
    return {'file':str(path.relative_to(ROOT)),'seconds':round(float(meta['format']['duration']),3),'width':video['width'],'height':video['height'],'fps':video['r_frame_rate'],'codec':video['codec_name'],'audio':any(s['codec_type']=='audio' for s in meta['streams']),'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'full_decode':'passed'}

if __name__=='__main__':
    files=selected();videos=[p for p in files if p.suffix=='.mp4']
    with ThreadPoolExecutor(max_workers=3) as pool:records=list(pool.map(inspect,videos))
    doc={'created_local_date':'2026-10-29','timezone':'Asia/Dubai','video_count':len(records),'image_count':len(list((ROOT/'03_贵阳牛肉粉').glob('*.png'))),'videos':records,'sources':'stock-sources.json','notes':'AI food clips are animated still images, not live-action food preparation. Quota proportions and budget figures are illustrative.'}
    (ROOT/'04_预览与说明/media-manifest.json').write_text(json.dumps(doc,ensure_ascii=False,indent=2)+'\n')
    out=ROOT.parent/'TokenMax_竖屏视频素材包_20261029.zip'
    with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=1) as z:
        for p in selected():z.write(p,str(Path(ROOT.name)/p.relative_to(ROOT)))
    print(json.dumps({'videos':len(records),'ai_source_images':doc['image_count'],'decode':'all passed','zip':str(out),'zip_mb':round(out.stat().st_size/1024**2,1)},ensure_ascii=False))
