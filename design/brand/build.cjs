const fs = require('node:fs');
const path = require('node:path');
const {renderSVG,states,palettes} = require('./quota-juicer.js');
const out = path.join(__dirname,'svg');
fs.mkdirSync(out,{recursive:true});
const entries = [];
for(const theme of ['light','dark']) for(const state of states) {
  const name = `${theme}-${state}.svg`;
  const svg = renderSVG({theme,state,animated:false,static:true});
  fs.writeFileSync(path.join(out,name),svg);
  // Figma import needs presentation attributes instead of CSS variables.
  const p = {...palettes[theme]};if(state==='disconnected'||state==='idle')p.blue=p.muted;
  const fill = {blue:p.blue,glass:p.glass,bolt:state==='working'?p.gold:p.gray,'error-mark':p.red};
  const stroke = {handle:p.blue,arcs:p.gold,'pause-mark':p.gold,'disconnect-mark':p.gray,'energy-core':p.core};
  let figma = svg.replace(/<style>[\s\S]*?<\/style>/,'').replace(/var\(--qj-(\w+)\)/g,(_,k)=>p[k]);
  figma = figma.replace(/class="([^"]+)"/g,(all,classes)=>{
    const cl=classes.split(' ');let attributes='';
    for(const c of cl){if(fill[c])attributes+=` fill="${fill[c]}"`;if(stroke[c])attributes+=` stroke="${stroke[c]}"`;}
    const opacity={'energy-glow':'.12','energy-halo':'.28','energy-filament':'.92','energy-core':'.95','branches':'.65'};
    for(const c of cl)if(opacity[c])attributes+=` opacity="${opacity[c]}"`;
    if(cl.includes('energy-trace'))attributes+=' stroke-dasharray="62 18 14 36"';
    return attributes;
  }).replace(/data-layer=/g,'id=');
  // Imported layers stay editable; the runtime file remains the animation source of truth.
  entries.push({theme,state,name,svg:figma});
}
for(const theme of ['light','dark','auto']) fs.writeFileSync(path.join(out,`${theme}-working-animated.svg`),renderSVG({theme,state:'working'}));
fs.writeFileSync(path.join(__dirname,'figma-assets.json'),JSON.stringify(entries,null,2));
console.log('Built 10 static states + 3 animated SVGs');
