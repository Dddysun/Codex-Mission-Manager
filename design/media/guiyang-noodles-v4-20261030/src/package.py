from pathlib import Path
import subprocess,json,zipfile,hashlib
R=Path(__file__).resolve().parents[1];M=R/'01_独立镜头';P=R/'02_预览';D=R/'03_制作资料'
shots=json.loads((D/'镜头清单.json').read_text())
def run(args):subprocess.run(args,check=True)
def target(s):return M/f"{s['id']}_{s['name']}.mp4"
master=target(shots[0])
for s in shots[1:]:run(['ffmpeg','-v','error','-y','-ss',str(s['offset']),'-i',str(master),'-t',str(s['duration']),'-an','-c:v','libx264','-preset','fast','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',str(target(s))])
run(['ffmpeg','-v','error','-y','-ss','24','-i',str(master),'-frames:v','1',str(P/'最终构图_从实际视频提取.png')])
report=[]
for s in shots:
 f=target(s);data=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(f)]));v=data['streams'][0]
 assert len(data['streams'])==1 and v['codec_type']=='video'
 assert (v['width'],v['height'],v['r_frame_rate'])==(1080,1920,'30/1')
 assert abs(float(data['format']['duration'])-s['duration'])<.05
 run(['ffmpeg','-v','error','-i',str(f),'-f','null','-'])
 report.append({'file':str(f.relative_to(R)),'seconds':s['duration'],'width':1080,'height':1920,'fps':30,'audio':False,'decode':'pass','sha256':hashlib.sha256(f.read_bytes()).hexdigest()})
(D/'视频核验.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
old=R.parent/'motion-v3-20261030'
if old.exists():
 original=json.loads((old/'03_制作资料/镜头清单.json').read_text());parts=[]
 for s in original:
  if s['id']=='04_map':parts.append(master)
  elif s['id']=='05_noodles':continue
  else:parts.append(old/'01_独立镜头'/f"{s['id']}_{s['name']}.mp4")
 c=P/'concat-full.txt';c.write_text(''.join("file '"+str(f)+"'\n" for f in parts))
 full=P/'141秒_全部镜头串片_已替换贵阳段.mp4'
 run(['ffmpeg','-v','error','-y','-f','concat','-safe','0','-i',str(c),'-c','copy','-movflags','+faststart',str(full)])
 run(['ffmpeg','-v','error','-i',str(full),'-f','null','-'])
 seconds=float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',str(full)]));assert abs(seconds-141)<.05
z=R.parent/'TokenMax_贵阳牛肉面镜头V4_20261030.zip'
with zipfile.ZipFile(z,'w',zipfile.ZIP_DEFLATED,6) as f:
 for p in R.rglob('*'):
  if not p.is_file() or any(x in p.parts for x in ['node_modules','__pycache__']):continue
  if p.name in ['141秒_全部镜头串片_已替换贵阳段.mp4','concat-full.txt']:continue
  f.write(p,str(Path(R.name)/p.relative_to(R)))
with zipfile.ZipFile(z) as f:assert f.testzip() is None
print(json.dumps({'zip':str(z),'bytes':z.stat().st_size,'replacement_seconds':26,'full_reel_seconds':141},ensure_ascii=False))
