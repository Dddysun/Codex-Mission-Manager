// Deterministic browser rendering: renderFrame(frame / fps), capture, encode.
const fs=require('fs'),path=require('path'),http=require('http'),{spawn}=require('child_process');
const {once}=require('events');
const {chromium}=require('playwright');
const root=path.resolve(__dirname,'..');
const mime={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.png':'image/png','.jpg':'image/jpeg'};
const server=http.createServer((req,res)=>{let rel=decodeURIComponent(new URL(req.url,'http://localhost').pathname);let p=path.join(root,rel==='/'?'index.html':rel);if(!p.startsWith(root+path.sep)&&p!==path.join(root,'index.html')){res.writeHead(403);return res.end()}fs.readFile(p,(e,b)=>{if(e){res.writeHead(404);res.end();return}res.setHeader('Content-Type',mime[path.extname(p)]||'application/octet-stream');res.end(b)})});
async function main(){
 await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const browser=await chromium.launch({headless:true,args:['--disable-gpu','--font-render-hinting=none']});
 const page=await browser.newPage({viewport:{width:1080,height:1920},deviceScaleFactor:1});
 const errors=[];page.on('pageerror',e=>errors.push(String(e)));page.on('response',r=>{if(r.status()>=400)errors.push(`${r.status()} ${r.url()}`)});
 await page.goto(`http://127.0.0.1:${server.address().port}/?render=1`);await page.evaluate(()=>assetsReady);
 const shots=await page.evaluate(()=>SHOTS);fs.writeFileSync(path.join(root,'03_制作资料','镜头清单.json'),JSON.stringify(shots,null,2));
 const want=process.argv.find(x=>x.startsWith('--shots='));const indices=want?want.slice(8).split(',').map(Number):shots.map((_,i)=>i);
 const stills=process.argv.includes('--stills');
 for(const i of indices){const shot=shots[i],poster=path.join(root,'02_预览',`${shot.id}.png`);await page.evaluate(([i,t])=>renderFrame(i,t),[i,shot.poster]);await page.screenshot({path:poster});
  if(stills)continue;
  const out=path.join(root,'01_独立镜头',`${shot.id}_${shot.name}.mp4`);
  const ff=spawn('ffmpeg',['-hide_banner','-loglevel','error','-y','-f','image2pipe','-vcodec','mjpeg','-framerate','30','-i','-','-an','-c:v','libx264','-preset','fast','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',out],{stdio:['pipe','inherit','inherit']});
  let failed=null;ff.on('error',e=>failed=e);ff.stdin.on('error',e=>failed=e);
  console.log(`RENDER ${i+1}/${shots.length} ${shot.name} (${shot.duration}s)`);
  for(let f=0;f<shot.duration*30;f++){
   await page.evaluate(([i,t])=>renderFrame(i,t),[i,f/30]);
   const buffer=await page.screenshot({type:'jpeg',quality:96,timeout:30000});
   if(failed)throw failed;
   if(!ff.stdin.write(buffer))await once(ff.stdin,'drain');
   if(f%90===0)console.log(`  ${shot.id} frame ${f}/${shot.duration*30}`);
  }
  ff.stdin.end();const [code]=await once(ff,'close');if(code)throw new Error(`ffmpeg ${code}`);
  console.log(`DONE ${shot.id} ${fs.statSync(out).size} bytes`);
 }
 fs.writeFileSync(path.join(root,'03_制作资料',`browser-errors-${indices.join('-')}.json`),JSON.stringify(errors,null,2));
 await browser.close();server.close();if(errors.length)throw new Error(errors.join('\n'));
}
main().catch(e=>{console.error(e);server.close();process.exit(1)});
