/* Isolated browser rendering for ten visual proposals; no live application. */
const fs=require('node:fs');
const path=require('node:path');
const {pathToFileURL}=require('node:url');
const {spawnSync}=require('node:child_process');
const {createHash}=require('node:crypto');
const assert=require('node:assert/strict');
const {chromium}=require('playwright');
const api=require('./core-discharge.js');

const length=points=>points.slice(1).reduce((sum,p,i)=>sum+Math.hypot(p[0]-points[i][0],p[1]-points[i][1]),0);
const metrics=api.scenes.map(scene=>({id:scene.id,name:scene.name,strokes:scene.strokes.length,
  root_count:scene.strokes.filter(s=>s.parent===null).length,
  longest_stroke:Math.max(...scene.strokes.map(s=>length(s.points))),
  curve_ratio:Math.max(...scene.strokes.filter(s=>s.parent===null).map(s=>length(s.points)/Math.hypot(s.points.at(-1)[0]-s.points[0][0],s.points.at(-1)[1]-s.points[0][1])))}));

async function main(){
  const directory=process.argv[2];if(!directory)throw Error('Pass a temporary frame directory.');
  const mainFrames=path.join(directory,'main'), galleryFrames=path.join(directory,'gallery');
  const clips=path.join(__dirname,'clips');
  for(const item of [mainFrames,galleryFrames,clips])fs.mkdirSync(item,{recursive:true});
  for(const item of [mainFrames,galleryFrames])for(const name of fs.readdirSync(item)){
    if(/^frame-\d{4}\.png$/.test(name))fs.unlinkSync(path.join(item,name));
  }
  const checks=[];
  assert.equal(api.scenes.length,10);
  assert.equal(new Set(api.scenes.map(s=>s.id)).size,10);
  assert(new Set(metrics.map(s=>s.strokes)).size>=4);
  assert(Math.max(...metrics.map(s=>s.longest_stroke))/Math.min(...metrics.map(s=>s.longest_stroke))>2);
  assert(metrics.filter(s=>s.curve_ratio>1.5).length>=8);
  for(const seed of [1,17,888,20261029])for(const event of api.buildSequence(seed).events){
    event.paths.forEach((item,index)=>{
      assert(item.points.every(point=>point.every(Number.isFinite)));
      if(item.parent!==null){
        assert(item.parent<index);
        assert(event.paths[item.parent].points.some(point=>point[0]===item.points[0][0]&&point[1]===item.points[0][1]));
      }
    });
  }
  assert.notDeepEqual(api.buildSequence(17).events.map(e=>e.id),api.buildSequence(888).events.map(e=>e.id));
  assert(new Set(api.buildSequence(17).events.map(e=>e.duration)).size>=6);
  checks.push('ten-distinct-topologies','varied-lengths-and-branch-counts','folded-macro-paths',
    'connected-multilevel-branches','seed-changes-order-and-geometry','unequal-event-durations');

  const browser=await chromium.launch({headless:true,
    ...(process.env.QJ_BROWSER_PATH?{executablePath:process.env.QJ_BROWSER_PATH}:{})});
  const sequence=api.buildSequence(20261029);
  let boxes;
  try{
    const page=await browser.newPage({viewport:{width:1280,height:1040},deviceScaleFactor:1,
      colorScheme:'dark',reducedMotion:'no-preference'});
    const errors=[];page.on('pageerror',error=>errors.push(error.message));
    const address=pathToFileURL(path.join(__dirname,'index.html')).href;
    await page.goto(address+'?capture=1');
    await page.evaluate(()=>document.fonts.ready);
    await page.waitForFunction(()=>document.querySelectorAll('#hero .discharge-event').length===10);
    assert.equal(await page.locator('#hero [data-layer^="energy-"]').count(),0);
    assert(await page.locator('#hero svg').evaluate(svg=>{
      const bolt=svg.querySelector('.bolt');
      return [...svg.querySelectorAll('.trunk')].every(group=>{
        const [x,y]=group.dataset.points.split(';')[0].split(',').map(Number);
        return bolt.isPointInFill(new DOMPoint(x,y));
      });
    }));
    assert(await page.locator('#hero .discharge-event').evaluateAll(nodes=>nodes.every(n=>getComputedStyle(n).transform==='none')));
    checks.push('all-trunks-originate-in-bolt','no-orbit-or-rotation-transform');
    async function setTime(time){await page.evaluate(seconds=>{
      for(const animation of document.getAnimations()){animation.pause();animation.currentTime=seconds*1000;}
    },time);}
    assert.equal(await page.locator('#hero .bolt-breathe').evaluate(node=>node.getAnimations()[0].effect.getTiming().duration),2000);
    const breath=[];
    for(const time of [0,.5,1,1.5,2]){
      await setTime(time);
      breath.push(await page.locator('#hero .bolt-breathe').evaluate(node=>Number(getComputedStyle(node).opacity)));
    }
    for(const [i,value] of [.58,.79,1,.79,.58].entries())assert(Math.abs(breath[i]-value)<.015);
    const hideArcs=await page.addStyleTag({content:'#hero .discharge-event{visibility:hidden!important}'});
    await setTime(0);const dimBolt=await page.locator('#hero').screenshot();
    await setTime(1);assert.notDeepEqual(dimBolt,await page.locator('#hero').screenshot());
    await hideArcs.evaluate(node=>node.remove());
    checks.push('center-bolt-breathes-every-two-seconds','gradual-dim-bright-dim-envelope','breathing-visible-in-rendered-frames');
    const first=sequence.events.find(event=>event.id===7), posterTime=first.start+Math.max(.12,first.rise+.04);
    await setTime(posterTime);
    const sample=await page.locator('#hero').screenshot();
    await setTime(first.start+first.duration+.05);
    assert.notDeepEqual(sample,await page.locator('#hero').screenshot());
    checks.push('rendered-frames-actually-differ');

    // Resume CSS to exercise the actual pause control, rather than just seek.
    await page.reload();await page.evaluate(()=>document.fonts.ready);
    await page.waitForTimeout(290);
    await page.locator('#pause').click();
    const freeze=await page.locator('#hero').screenshot();
    await page.waitForTimeout(170);
    assert.deepEqual(freeze,await page.locator('#hero').screenshot());
    await page.locator('#pause').click();
    await page.emulateMedia({reducedMotion:'reduce'});
    assert(await page.locator('#hero .discharge-event').evaluateAll(nodes=>nodes.every(n=>Number(getComputedStyle(n).opacity)===0)));
    assert.equal(await page.locator('#hero .bolt-breathe').evaluate(node=>getComputedStyle(node).animationName),'none');
    await page.emulateMedia({reducedMotion:'no-preference'});
    await page.locator('#reduce').check();
    assert(await page.locator('#hero .discharge-event').evaluateAll(nodes=>nodes.every(n=>Number(getComputedStyle(n).opacity)===0)));
    assert.equal(await page.locator('#hero .bolt-breathe').evaluate(node=>Number(getComputedStyle(node).opacity)),1);
    await page.locator('#reduce').uncheck();
    for(const state of ['idle','waiting','disconnected','error']){
      await page.selectOption('#state',state);
      assert.equal(await page.locator('#hero .discharge-event').count(),0);
      assert.equal(await page.locator('#hero').evaluate(el=>el.getAnimations({subtree:true}).length),0);
    }
    await page.selectOption('#state','working');
    checks.push('pause-freezes-rendered-frame','reduced-motion-system-and-manual','nonworking-states-static');

    // The live page changes seeds at the cycle boundary; exported media stays reproducible.
    const live=await browser.newPage({viewport:{width:1280,height:1040},reducedMotion:'no-preference'});
    live.on('pageerror',error=>errors.push(error.message));
    await live.goto(address);
    const previous=await live.evaluate(()=>window.preview.seed);
    await live.locator('#hero .bolt-breathe').evaluate(node=>{node.getAnimations()[0].currentTime=860;});
    const breathBefore=await live.locator('#hero .bolt-breathe').evaluate(node=>node.getAnimations()[0].currentTime);
    await live.locator('#shuffle').click();
    assert.notEqual(previous,await live.evaluate(()=>window.preview.seed));
    const breathAfter=await live.locator('#hero .bolt-breathe').evaluate(node=>node.getAnimations()[0].currentTime);
    assert(breathAfter>=breathBefore&&breathAfter-breathBefore<500);
    checks.push('breathing-phase-preserved-on-random-shuffle');
    const beforeCycle=await live.evaluate(()=>window.preview.seed);
    await live.evaluate(()=>{
      const clock=document.querySelector('#hero .discharge-event').getAnimations()[0];
      clock.currentTime=window.preview.sequence.cycleSeconds*1000-15;
    });
    await live.waitForFunction(seed=>window.preview.seed!==seed,beforeCycle,{timeout:2000});
    checks.push('live-shuffle-button-changes-seed','live-cycle-regenerates-sequence');
    await live.close();

    for(let frame=0;frame<Math.round(sequence.cycleSeconds*30);frame++){
      await setTime(posterTime+frame/30);
      await page.locator('#capture').screenshot({path:path.join(mainFrames,`frame-${String(frame).padStart(4,'0')}.png`)});
      if(frame%90===0)console.log(`Main motion: ${frame}/${Math.round(sequence.cycleSeconds*30)} frames`);
    }
    await setTime(posterTime);
    await page.locator('#capture').screenshot({path:path.join(__dirname,'preview-dark.png')});
    await page.selectOption('#theme','light');await setTime(posterTime);
    await page.locator('#capture').screenshot({path:path.join(__dirname,'preview-light.png')});
    await page.selectOption('#theme','dark');
    // Independent peak times let the still sheet show every complete topology.
    await page.evaluate(()=>{
      for(const scene of TokenMaxDischargePreview.scenes){
        const event=TokenMaxDischargePreview.buildSequence(34000+scene.id*97,scene.id).events[0];
        const seconds=event.start+Math.max(.125,event.rise+.045);
        for(const animation of document.getElementById('logo-'+scene.id).getAnimations({subtree:true})){
          animation.pause();animation.currentTime=seconds*1000;
        }
      }
    });
    await page.locator('#gallery').screenshot({path:path.join(__dirname,'contact-sheet.png')});
    boxes=await page.evaluate(()=>{
      const root=document.getElementById('gallery').getBoundingClientRect();
      return TokenMaxDischargePreview.scenes.map(scene=>{
        const rect=document.getElementById('logo-'+scene.id).getBoundingClientRect();
        return {id:scene.id,x:Math.round(rect.left-root.left),y:Math.round(rect.top-root.top),
          width:Math.round(rect.width),height:Math.round(rect.height)};
      });
    });
    for(let frame=0;frame<Math.round(api.buildSequence(34097,1).cycleSeconds*20);frame++){
      await setTime(.3+frame/20);
      await page.locator('#gallery').screenshot({path:path.join(galleryFrames,`frame-${String(frame).padStart(4,'0')}.png`)});
    }
    await page.setViewportSize({width:390,height:844});
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    assert.equal(errors.length,0,errors.join('\n'));
    checks.push('light-dark-rendered','ten-gallery-previews','mobile-no-overflow','browser-no-errors');
  }finally{await browser.close();}

  const ffmpeg=process.env.FFMPEG||'ffmpeg';
  function encode(args){
    const result=spawnSync(ffmpeg,['-hide_banner','-loglevel','error','-y',...args],{encoding:'utf8'});
    if(result.error||result.status!==0)throw Error(result.stderr||String(result.error));
  }
  function gif(input,fps,output,crop=''){
    const palette=path.join(directory,'palette-'+path.basename(output)+'.png');
    const filter=(crop?crop+',':'')+'fps=20';
    encode(['-framerate',String(fps),'-i',input,'-filter_threads','1','-vf',filter+',palettegen=max_colors=192:stats_mode=diff','-frames:v','1',palette]);
    encode(['-framerate',String(fps),'-i',input,'-i',palette,'-filter_complex_threads','1','-lavfi',filter+'[x];[x][1:v]paletteuse=dither=sierra2_4a:diff_mode=rectangle','-loop','0',output]);
  }
  const mainInput=path.join(mainFrames,'frame-%04d.png'), galleryInput=path.join(galleryFrames,'frame-%04d.png');
  gif(mainInput,30,path.join(__dirname,'core-discharge.gif'));
  encode(['-framerate','30','-i',mainInput,'-threads','2','-c:v','libx264','-crf','17','-preset','medium','-pix_fmt','yuv420p','-movflags','+faststart',path.join(__dirname,'core-discharge.mp4')]);
  // Revision-specific names avoid reusing a viewer's cached earlier preview.
  fs.copyFileSync(path.join(__dirname,'core-discharge.gif'),path.join(__dirname,'core-discharge-breathe.gif'));
  fs.copyFileSync(path.join(__dirname,'core-discharge.mp4'),path.join(__dirname,'core-discharge-breathe.mp4'));
  gif(galleryInput,20,path.join(__dirname,'gallery.gif'));
  for(const box of boxes){
    const name=String(box.id).padStart(2,'0');
    gif(galleryInput,20,path.join(clips,name+'.gif'),`crop=${box.width}:${box.height}:${box.x}:${box.y}`);
    fs.writeFileSync(path.join(clips,name+'.svg'),api.renderSVG({state:'working',theme:'dark',sceneId:box.id,seed:34000+box.id*97,static:true,animated:false}));
  }
  const gifFiles=fs.readdirSync(clips).filter(name=>/^\d{2}\.gif$/.test(name));
  assert.equal(gifFiles.length,10);
  assert.equal(new Set(gifFiles.map(name=>createHash('sha256').update(fs.readFileSync(path.join(clips,name))).digest('hex'))).size,10);
  checks.push('ten-independent-gif-outputs-are-distinct');
  fs.writeFileSync(path.join(__dirname,'core-discharge-animated.svg'),api.renderSVG({state:'working',theme:'auto',seed:20261029}));
  const archive=spawnSync(process.env.QJ_PYTHON||'python3',['-B','-c',
    'import pathlib,sys,zipfile\nroot=pathlib.Path(sys.argv[1])\nwith zipfile.ZipFile(sys.argv[2],"w",zipfile.ZIP_DEFLATED) as archive:\n for file in sorted(root.glob("*.gif")): archive.write(file,file.name)\nwith zipfile.ZipFile(sys.argv[2]) as archive: assert len(archive.namelist())==10 and archive.testzip() is None',
    clips,path.join(__dirname,'ten-discharge-clips.zip')],{encoding:'utf8'});
  if(archive.error||archive.status!==0)throw Error(archive.stderr||String(archive.error));
  checks.push('ten-gif-archive-integrity');
  fs.writeFileSync(path.join(__dirname,'verification.json'),JSON.stringify({proposal:api.version,result:'pass',checks,
    sequence:{seed:sequence.seed,cycle_seconds:sequence.cycleSeconds,events:sequence.events.map(e=>({id:e.id,start:e.start,duration:e.duration,rise:e.rise,length_scale:e.lengthScale}))},
    scenes:metrics,independent_gif_count:10,main_video_fps:30,gif_fps:20,
    breath:{cycle_seconds:2,dim_opacity:.58,bright_opacity:1,seconds_to_bright:1,seconds_to_dim:1,phase_preserved_on_shuffle:true},
    production_assets_changed:false,live_backend_started:false,private_data_loaded:false},null,2)+'\n');
  console.log(JSON.stringify({result:'pass',checks,cycle_seconds:sequence.cycleSeconds,independent_gifs:10}));
}
main().catch(error=>{console.error(error);process.exitCode=1;});
