const fs=require('fs'),path=require('path'),http=require('http');
const {chromium}=require('playwright');const root=path.resolve(__dirname,'..');
const server=http.createServer((req,res)=>{const p=path.join(root,decodeURIComponent(new URL(req.url,'http://localhost').pathname));fs.readFile(p,(e,b)=>{if(e){res.writeHead(404);res.end();return}res.end(b)})});
(async()=>{
 await new Promise(r=>server.listen(0,'127.0.0.1',r));const browser=await chromium.launch({headless:true});const p=await browser.newPage({viewport:{width:1080,height:1920}});
 await p.goto(`http://127.0.0.1:${server.address().port}/index.html?render=1`);await p.evaluate(()=>assetsReady);
 const shots=await p.evaluate(()=>SHOTS),report={textOverflow:[],samples:[],url:null};
 for(let i=0;i<shots.length;i++){
  for(let t of [.3,shots[i].poster,shots[i].duration-1/30]){
   await p.evaluate(([i,t])=>renderFrame(i,t),[i,t]);
   const bad=await p.evaluate(()=>[...document.querySelectorAll('#frame text')].filter(x=>!x.closest('svg svg')).map(x=>({text:x.textContent,x:x.getBoundingClientRect().x,right:x.getBoundingClientRect().right,bottom:x.getBoundingClientRect().bottom})).filter(x=>x.x<20||x.right>1060||x.bottom>1890));
   for(let b of bad)report.textOverflow.push({shot:shots[i].id,time:t,...b});
  }
 }
 const extra=[[3,1.7],[3,6],[3,10.8],[4,.4],[4,3.1],[4,9.5],[5,2],[5,4],[5,6],[6,2],[6,4],[6,7],[8,1.6],[8,4.5],[8,7.5],[8,10.5],[9,1.2],[9,4.8],[9,6.3],[9,8],[11,2.3],[12,3.2],[13,3],[13,9]];
 fs.mkdirSync(path.join(root,'02_预览','动作检查'),{recursive:true});
 for(const [i,t] of extra){await p.evaluate(([i,t])=>renderFrame(i,t),[i,t]);const name=`${shots[i].id}_${t.toFixed(1)}.png`;await p.screenshot({path:path.join(root,'02_预览','动作检查',name)});report.samples.push(name)}
 report.url=await p.evaluate(()=>[...document.querySelectorAll('text')].find(x=>x.textContent.startsWith('https://'))?.textContent);
 fs.writeFileSync(path.join(root,'03_制作资料','layout-qa.json'),JSON.stringify(report,null,2));console.log(JSON.stringify({overflows:report.textOverflow,url:report.url,samples:report.samples.length}));await browser.close();server.close();
})().catch(e=>{console.error(e);process.exit(1)});
