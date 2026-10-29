from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
import json,subprocess,zipfile,hashlib
R=Path(__file__).resolve().parents[1];P=R/'02_预览';M=R/'01_独立镜头';D=R/'03_制作资料'
shots=json.loads((D/'镜头清单.json').read_text())
def run(args):subprocess.run(args,check=True)
def clip(s):return M/f"{s['id']}_{s['name']}.mp4"
report=[]
for s in shots:
 f=clip(s)
 data=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(f)]))
 stream=data['streams'][0]
 assert len(data['streams'])==1 and stream['codec_type']=='video'
 assert (stream['width'],stream['height'],stream['r_frame_rate'])==(1080,1920,'30/1')
 assert abs(float(data['format']['duration'])-s['duration'])<.05
 run(['ffmpeg','-v','error','-i',str(f),'-f','null','-'])
 report.append({'file':str(f.relative_to(R)),'seconds':s['duration'],'width':1080,'height':1920,'fps':30,'audio':False,'full_decode':'pass','sha256':hashlib.sha256(f.read_bytes()).hexdigest()})
concat=P/'concat-all.txt';concat.write_text(''.join("file '../01_独立镜头/"+clip(s).name+"'\n" for s in shots))
full=P/'134秒_全部镜头串片.mp4'
run(['ffmpeg','-v','error','-y','-f','concat','-safe','0','-i',str(concat),'-c','copy','-movflags','+faststart',str(full)])
# 12+10+9+10+10+4+5 = 60 seconds, without speeding up the animation.
selected=[('03_balance',0,12),('04_map',0,10),('05_noodles',0,9),('06_quota',0,10),('09_alarm',0,10),('11_pay',1,4),('12_wait',1,5)]
tmp=P/'preview-parts';tmp.mkdir(exist_ok=True)
for i,(sid,start,duration) in enumerate(selected):
 s=next(s for s in shots if s['id']==sid)
 run(['ffmpeg','-v','error','-y','-ss',str(start),'-i',str(clip(s)),'-t',str(duration),'-an','-c:v','libx264','-preset','fast','-crf','19','-pix_fmt','yuv420p',str(tmp/f'{i}.mp4')])
parts=P/'concat-preview.txt';parts.write_text(''.join(f"file 'preview-parts/{i}.mp4'\n" for i in range(len(selected))))
run(['ffmpeg','-v','error','-y','-f','concat','-safe','0','-i',str(parts),'-c','copy','-movflags','+faststart',str(P/'60秒_重点镜头预览.mp4')])
for f in [full,P/'60秒_重点镜头预览.mp4']:run(['ffmpeg','-v','error','-i',str(f),'-f','null','-'])
font=ImageFont.truetype('/System/Library/Fonts/Hiragino Sans GB.ttc',19)
out=Image.new('RGB',(1400,((len(shots)+3)//4)*670),'#E8ECE8');d=ImageDraw.Draw(out)
for i,s in enumerate(shots):
 im=Image.open(P/(s['id']+'.png'));im.thumbnail((326,580));x=12+i%4*350;y=12+i//4*670;out.paste(im,(x,y));d.text((x,y+590),s['name'][:16],font=font,fill='#172620');d.text((x,y+619),f"{s['duration']} 秒",font=font,fill='#728079')
out.save(P/'新版全部分镜.jpg',quality=92)
(D/'media-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
(D/'duration.json').write_text(json.dumps({'clips':len(shots),'total_seconds':sum(s['duration'] for s in shots),'preview_seconds':60,'scope':'镜头素材串片，不含用户软件实录或口播'},ensure_ascii=False,indent=2))
# The ZIP keeps independent masters and a short preview. Full montage is a duplicate of the masters.
z=R.parent/'TokenMax_代码逐帧动画V3_20261030.zip'
with zipfile.ZipFile(z,'w',zipfile.ZIP_DEFLATED,6) as f:
 for p in R.rglob('*'):
  if not p.is_file() or any(x in p.parts for x in ['node_modules','preview-parts','动作检查','__pycache__']):continue
  if p.name in ['134秒_全部镜头串片.mp4','contact-sheet.jpg','动作检查总览.jpg','concat-all.txt','concat-preview.txt']:continue
  f.write(p,str(Path(R.name)/p.relative_to(R)))
with zipfile.ZipFile(z) as f:assert f.testzip() is None
print(json.dumps({'zip':str(z),'bytes':z.stat().st_size,'clips':len(shots),'total_seconds':sum(s['duration'] for s in shots)},ensure_ascii=False))
