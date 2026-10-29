/* Offline rendering of a visual proposal. No app or chat connection. */
const fs = require('node:fs');
const path = require('node:path');
const {pathToFileURL} = require('node:url');
const {spawnSync} = require('node:child_process');
const assert = require('node:assert/strict');
const {chromium} = require('playwright');
const {renderSVG, channels, cycleSeconds} = require('./core-discharge.js');

async function main() {
  const frames = process.argv[2];
  if (!frames) throw Error('Pass a temporary frame-output directory.');
  fs.mkdirSync(frames, {recursive:true});
  const browser = await chromium.launch({headless:true,
    ...(process.env.QJ_BROWSER_PATH ? {executablePath:process.env.QJ_BROWSER_PATH} : {})});
  const checks = [];
  try {
    const page = await browser.newPage({viewport:{width:1008,height:620}, deviceScaleFactor:1,
      colorScheme:'dark', reducedMotion:'no-preference'});
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(pathToFileURL(path.join(__dirname, 'index.html')).href);
    await page.evaluate(() => document.fonts.ready);
    await page.waitForFunction(() => document.getAnimations().length > 0);
    assert.equal(await page.locator('#hero [data-layer^="energy-"]').count(), 0);
    assert.equal(await page.locator('#hero .discharge').count(), 6);
    assert(await page.locator('#hero svg').evaluate(svg => {
      const bolt = svg.querySelector('.bolt');
      return [...svg.querySelectorAll('[data-origin]')].every(group => {
        const [x,y] = group.dataset.origin.split(',').map(Number);
        return bolt.isPointInFill(new DOMPoint(x,y));
      });
    }));
    for (const channel of channels) for (const branch of channel.branches) {
      assert(channel.points.some(point => point[0] === branch[0][0] && point[1] === branch[0][1]));
    }
    checks.push('six-trunks-rooted-inside-bolt','branches-rooted-at-trunk-vertices','no-perimeter-energy-groups');

    const alpha = () => page.locator('#hero .discharge').evaluateAll(nodes => nodes.map(node => getComputedStyle(node).opacity));
    await page.waitForTimeout(580);
    const moving = await alpha();
    await page.waitForTimeout(240);
    assert.notDeepEqual(moving, await alpha());
    await page.locator('#pause').click();
    const paused = await alpha();
    await page.waitForTimeout(160);
    assert.deepEqual(paused, await alpha());
    checks.push('visible-discharge-changes','pause-freezes-current-frame');
    await page.locator('#pause').click();
    await page.emulateMedia({reducedMotion:'reduce'});
    assert((await alpha()).every(value => Number(value) === 0));
    checks.push('system-reduced-motion-disables-discharge');
    await page.emulateMedia({reducedMotion:'no-preference'});
    await page.locator('#reduce').check();
    assert((await alpha()).every(value => Number(value) === 0));
    checks.push('manual-reduced-motion-disables-discharge');
    await page.locator('#reduce').uncheck();
    for (const state of ['idle','waiting','disconnected','error']) {
      await page.selectOption('#state', state);
      assert.equal(await page.locator('#hero .discharge').count(), 0);
      assert.equal(await page.locator('#hero').evaluate(element => element.getAnimations({subtree:true}).length), 0);
    }
    checks.push('nonworking-states-remain-static');
    await page.selectOption('#state', 'working');

    async function setTime(seconds) {
      await page.evaluate(time => {
        for (const animation of document.getAnimations()) {animation.pause();animation.currentTime=time*1000;}
      }, seconds);
    }
    const fps = 30;
    for (let frame = 0; frame < cycleSeconds * fps; frame++) {
      await setTime(.62 + frame/fps);
      await page.locator('#capture').screenshot({path:path.join(frames, `frame-${String(frame).padStart(4,'0')}.png`)});
    }
    await setTime(.62);
    await page.locator('#capture').screenshot({path:path.join(__dirname,'preview-dark.png')});
    await page.screenshot({path:path.join(__dirname,'preview-page.png'),fullPage:true});
    await page.selectOption('#theme','light');
    await setTime(.62);
    await page.locator('#capture').screenshot({path:path.join(__dirname,'preview-light.png')});
    await page.setViewportSize({width:390,height:844});
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    checks.push('light-dark-rendered','small-size-previews','mobile-no-horizontal-overflow');
    assert.equal(errors.length, 0, errors.join('\n'));
    checks.push('browser-no-errors');
  } finally {await browser.close();}
  fs.writeFileSync(path.join(__dirname,'core-discharge-static.svg'),renderSVG({state:'working',theme:'dark',static:true,animated:false}));
  fs.writeFileSync(path.join(__dirname,'core-discharge-animated.svg'),renderSVG({state:'working',theme:'auto'}));
  const ffmpeg = process.env.FFMPEG || 'ffmpeg';
  function encode(args) {
    const result = spawnSync(ffmpeg, ['-hide_banner','-loglevel','error','-y',...args], {encoding:'utf8'});
    if (result.error || result.status !== 0) throw Error(result.stderr || String(result.error));
  }
  const input = path.join(frames,'frame-%04d.png');
  const palette = path.join(frames,'palette.png');
  encode(['-framerate','30','-i',input,'-filter_threads','1','-vf','fps=20,palettegen=max_colors=192:stats_mode=diff','-frames:v','1',palette]);
  encode(['-framerate','30','-i',input,'-i',palette,'-filter_complex_threads','1','-lavfi','fps=20[x];[x][1:v]paletteuse=dither=sierra2_4a:diff_mode=rectangle','-loop','0',path.join(__dirname,'core-discharge.gif')]);
  encode(['-framerate','30','-i',input,'-threads','2','-c:v','libx264','-crf','17','-preset','medium','-pix_fmt','yuv420p','-movflags','+faststart',path.join(__dirname,'core-discharge.mp4')]);
  fs.writeFileSync(path.join(__dirname,'verification.json'),JSON.stringify({
    proposal:'1.3.0-proposal.1',checks,result:'pass',cycle_seconds:cycleSeconds,
    video_frames:108,video_fps:30,gif_fps:20,application_code_changed:false,
    live_backend_started:false,private_data_loaded:false,reference_image_copied:false
  },null,2)+'\n');
  console.log(JSON.stringify({result:'pass',checks,frames:108,output:__dirname}));
}
main().catch(error => {console.error(error);process.exitCode=1;});
