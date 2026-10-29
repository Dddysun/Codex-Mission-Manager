const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {pathToFileURL} = require('node:url');
const {renderSVG,states,palettes} = require('./quota-juicer.js');
// Resolve Playwright through the caller's NODE_PATH; no runtime dependency for users.
const {chromium} = require('playwright');
(async()=>{
 const browser=await chromium.launch({headless:true,...(process.env.QJ_BROWSER_PATH?{executablePath:process.env.QJ_BROWSER_PATH}:{})});
 try {
  const page=await browser.newPage({viewport:{width:1280,height:1160},deviceScaleFactor:1,colorScheme:'dark',reducedMotion:'no-preference'});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(pathToFileURL(path.join(__dirname,'index.html')).href);
  await page.waitForFunction(()=>document.getElementById('hero').shadowRoot.querySelector('.symbol-motion'));
  await page.waitForFunction(()=>document.getElementById('hero').shadowRoot.querySelector('.symbol-motion').getAnimations().some(a=>a.currentTime>0&&!a.pending));
  const rotor=()=>page.locator('#hero').evaluate(el=>{const n=el.shadowRoot.querySelector('.symbol-motion');return n?{transform:getComputedStyle(n).transform,name:getComputedStyle(n).animationName,play:getComputedStyle(n).animationPlayState}:null;});
  const a=await rotor();await page.waitForTimeout(170);const b=await rotor();assert.notEqual(a.transform,b.transform);
  await page.locator('#animate').uncheck();await page.waitForTimeout(60);const paused=await rotor();await page.waitForTimeout(180);assert.equal(paused.transform,(await rotor()).transform);assert.equal(paused.play,'paused');
  await page.selectOption('#state','idle');assert.equal((await rotor()).name,'none');
  await page.selectOption('#state','working');assert.equal((await rotor()).play,'paused');
  await page.locator('#animate').check();assert.equal((await rotor()).play,'running');
  await page.emulateMedia({reducedMotion:'reduce'});assert.equal((await rotor()).name,'none');
  await page.selectOption('#state','error');await page.selectOption('#state','working');assert.equal((await rotor()).name,'none');
  await page.emulateMedia({reducedMotion:'no-preference'});await page.locator('#reduce').check();assert.equal((await rotor()).name,'none');await page.locator('#reduce').uncheck();assert.equal((await rotor()).name,'qj-breathe');
  for(const s of states){await page.selectOption('#state',s);const names=await page.locator('#hero').evaluate(el=>[...el.shadowRoot.querySelectorAll('.motion')].map(n=>getComputedStyle(n).animationName));if(s!=='working')assert(names.every(n=>n==='none'));}
  await page.selectOption('#state','working');await page.selectOption('#theme','auto');
  await page.emulateMedia({colorScheme:'dark'});
  assert.equal(await page.locator('#hero').evaluate(el=>getComputedStyle(el.shadowRoot.querySelector('.blue')).fill),'rgb(72, 120, 175)');
  assert.equal(await page.locator('#hero').evaluate(el=>getComputedStyle(el.shadowRoot.querySelector('.bolt')).fill),'rgb(231, 180, 60)');
  await page.emulateMedia({colorScheme:'light'});assert.equal(await page.locator('#hero').evaluate(el=>getComputedStyle(el.shadowRoot.querySelector('.blue')).fill),'rgb(33, 104, 213)');
  await page.selectOption('#theme','dark');await page.emulateMedia({colorScheme:'dark'});
  await page.screenshot({path:path.join(__dirname,'preview-dark.png'),fullPage:true});
  await page.selectOption('#theme','light');await page.screenshot({path:path.join(__dirname,'preview-light.png'),fullPage:true});
  // Capture two actual rendered working frames; this verifies visible motion, not just CSS existence.
  await page.selectOption('#theme','dark');await page.locator('#hero').screenshot({path:path.join(__dirname,'motion-frame-1.png')});await page.waitForTimeout(480);await page.locator('#hero').screenshot({path:path.join(__dirname,'motion-frame-2.png')});
  assert.notDeepEqual(fs.readFileSync(path.join(__dirname,'motion-frame-1.png')),fs.readFileSync(path.join(__dirname,'motion-frame-2.png')));
  await page.setViewportSize({width:390,height:844});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  const one=renderSVG({state:'working',theme:'light'}),two=renderSVG({state:'working',theme:'dark'});
  await page.setContent(one+two);
  const fills=await page.locator('svg').evaluateAll(nodes=>nodes.map(n=>getComputedStyle(n.querySelector('.blue')).fill));assert.deepEqual(fills,['rgb(33, 104, 213)','rgb(72, 120, 175)']);
  const ids=await page.locator('[id]').evaluateAll(nodes=>nodes.map(n=>n.id));assert.equal(new Set(ids).size,ids.length);
  for(const theme of ['light','dark'])for(const state of states){const source=fs.readFileSync(path.join(__dirname,'svg',`${theme}-${state}.svg`),'utf8');assert(!source.includes('@keyframes'));assert(!source.includes('vortex'));assert(!source.includes('status-badge'));if(['waiting','disconnected','error'].includes(state))assert(!source.includes('class="bolt"'));assert(source.includes(`data-state="${state}"`));}
  assert(renderSVG({label:'<script>bad</script>'}).includes('&lt;script&gt;bad&lt;/script&gt;'));
  assert(renderSVG({decorative:true}).includes('aria-hidden="true"'));
  assert.equal(errors.length,0,errors.join('\n'));
  fs.writeFileSync(path.join(__dirname,'verification.json'),JSON.stringify({result:'pass',checks:['working-motion-changes','pause-freezes-frame','state-change-retains-pause','only-working-animates','system-reduced-motion','manual-reduced-motion','auto-dark-light-theme','muted-dark-blue-and-gold','independent-inline-colors','unique-clip-ids','static-svg-no-keyframes','accessible-label-escaping','mobile-no-horizontal-overflow','browser-no-errors'],states:5,staticAssets:10,animatedAssets:3},null,2));
  console.log('PASS: animation, pause, reduced motion, themes, isolation, accessibility, static exports and responsive preview');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
