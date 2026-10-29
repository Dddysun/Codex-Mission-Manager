// V4: map -> street stall -> one hero bowl -> three separate additions -> = ¥20.
// No ingredient is dropped into the hero bowl. The additions remain underneath it.
const SHOTS=[
 {id:'00_complete',name:'中国到贵阳面摊_牛肉面加料与20元',duration:26,poster:24,offset:0},
 {id:'01_map_stall',name:'中国贵州贵阳_推进牛肉面摊',duration:12,poster:11.5,offset:0},
 {id:'02_bowl_price',name:'主体牛肉面_下排加面加蛋加肉_等于20元',duration:14,poster:12,offset:12}
];
const STAGES=[
 {start:0,end:2,name:'中国'},
 {start:2,end:4.6,name:'贵州'},
 {start:4.6,end:7.2,name:'贵阳'},
 {start:7.2,end:9.6,name:'贵阳街头'},
 {start:9.6,end:12,name:'牛肉面摊'},
 {start:12,end:15.2,name:'牛肉面成为主体'},
 {start:15.2,end:17.2,name:'下方出现加面'},
 {start:17.2,end:19.2,name:'下方出现加蛋'},
 {start:19.2,end:21.3,name:'下方出现加肉'},
 {start:21.3,end:23,name:'等号与20元金币'},
 {start:23,end:26,name:'所有元素同屏停留'}
];
function cameraAt(t){
 const K=[[0,104,33,65],[1.25,104,33,65],[3.3,106.65,26.85,7.8],[4.1,106.65,26.85,7.8],[6.25,106.68,26.74,1.75],[6.85,106.68,26.74,1.75],[9.35,106.71,26.58,.032],[26,106.71,26.58,.032]];
 for(let i=0;i<K.length-1;i++){const a=K[i],b=K[i+1];if(t>=a[0]&&t<=b[0]){const p=ease((t-a[0])/(b[0]-a[0]));return [mix(a[1],b[1],p),mix(a[2],b[2],p),Math.exp(mix(Math.log(a[3]),Math.log(b[3]),p))]}}
 return K.at(-1).slice(1);
}
function mapLayer(t){
 const [lon,lat,span]=cameraAt(t),sx=960/span,sy=sx/Math.cos(lat*Math.PI/180);
 const project=p=>[540+(p[0]-lon)*sx,1020-(p[1]-lat)*sy];
 let m='';
 function region(r,city=false){
  if(span<.18)return;
  for(const pts of r.rings){
   const xs=pts.map(p=>p[0]),ys=pts.map(p=>p[1]);
   if(Math.max(...xs)<lon-span||Math.min(...xs)>lon+span||Math.max(...ys)<lat-span||Math.min(...ys)>lat+span)continue;
   const d='M'+pts.map(project).map(p=>p.map(v=>v.toFixed(1)).join(' ')).join('L')+'Z';
   const active=r.id===(city?520100:520000);
   m+=path(d,active?(city?'#BEE8D3':'#D3EEDD'):'#F0F3EF',active?C.green:'#BDCCC0',active?3:1.5);
  }
 }
 for(const r of GEO.provinces)region(r);
 if(span<13)for(const r of GEO.cities)region(r,true);
 if(span<.5){
  for(const r of GEO.roads){
   const pts=r.pts.map(project);if(!pts.some(p=>p[0]>-120&&p[0]<1200&&p[1]>350&&p[1]<1700))continue;
   const d='M'+pts.map(p=>p.map(v=>v.toFixed(1)).join(' ')).join('L');
   const major=['primary','secondary','trunk'].includes(r.kind);
   m+=path(d,'none',major?'#AFC5B7':'#D6E1D8',major?12:5);
   if(major)m+=path(d,'none','#FAFCF9',5);
  }
 }
 const pin=project([106.71,26.58]);
 if(t<9.8){
  m+=ellipse(pin[0],pin[1],32+wave(t,.8)*4,32+wave(t,.8)*4,'#D3EEDD','none',0);
  m+=ellipse(pin[0],pin[1],11,11,C.green,C.white,4);
  if(span>2)m+=txt(pin[0]+35,pin[1]-21,'贵阳',36,750,C.ink);
 }
 return `<svg x="42" y="416" width="996" height="1152" viewBox="42 416 996 1152" overflow="hidden">${m}</svg>`;
}
function noodleBundle(x,y,s=1,t=0){
 let b=ellipse(0,55,96,29,'#E2E7DE','none',0)+ellipse(0,43,91,30,C.white,C.ink,3);
 for(let i=0;i<13;i++){
  const xx=-72+i*12,yy=-22+(i%3)*6;
  b+=path(`M${xx} 33C${xx-48} -22 ${xx+41} -94 ${xx+10} -61C${xx-19} -32 ${xx+38} -2 ${xx+14} 31`,'none','#C98E3D',6);
  b+=path(`M${xx} 31C${xx-41} -17 ${xx+39} -89 ${xx+11} -59C${xx-16} -29 ${xx+35} -1 ${xx+15} 30`,'none','#F8D28A',3.5);
 }
 b+=path('M-112 -79L104 -43M-109 -91L108 -55','none','#7D5D35',5);
 return g(b,`translate(${x} ${y}) scale(${s})`);
}
function friedEgg(x,y,s=1){
 let b=ellipse(0,44,105,31,'#E2E7DE','none',0)+ellipse(0,31,105,34,C.white,C.ink,3);
 b+=path('M-92 2C-113 -32 -84 -61 -48 -61C-26 -90 16 -70 38 -55C83 -70 111 -35 96 -7C123 28 77 57 42 50C11 74 -16 52 -41 54C-88 71 -112 38 -92 2Z','#FFFAE8','#D4A54D',3);
 b+=ellipse(5,-3,44,37,'#F5B62C','#D69A23',3)+ellipse(-7,-14,17,9,'#FFE48F','none',0);
 for(let i=0;i<9;i++)b+=ellipse(-78+(i*43)%157,-35+(i*23)%68,2.5,2,'#DAB467','none',0);
 return g(b,`translate(${x} ${y}) scale(${s})`);
}
function beefSlices(x,y,s=1){
 let b=ellipse(0,53,107,28,'#E2E7DE','none',0)+ellipse(0,40,106,33,C.white,C.ink,3);
 for(let i=0;i<5;i++){
  const meat=path('M-44 -22Q-4 -44 40 -16L51 10Q33 40 -24 28L-49 11Z','#8E4430','#5F2D23',3)+path('M-29 -9Q-2 -20 26 7M-22 8Q-2 0 23 20','none','#DEA381',4)+path('M-24 -19L-18 18M0 -25L8 22','none','#AE654B',2);
  b+=g(meat,`translate(${-49+i*25} ${-11+(i%2)*25}) rotate(${-22+i*8})`);
 }
 b+=path('M-70 29Q-91 14 -81 7Q-61 11 -57 31M-57 29Q-42 3 -34 14Q-34 28 -57 34',C.green,'#257854',2);
 return g(b,`translate(${x} ${y}) scale(${s})`);
}
function heroBowl(x,y,s,t){
 // Main beef noodle bowl stays intact while the three additions appear separately below.
 let b=bowlArt(0,0,1,t,3);
 b+=path('M-189 67Q-152 102 -112 112','none','#FFFFFF',9);
 b+=path('M-165 -61L202 -120M-167 -48L206 -107','none','#715232',5);
 b+=path('M-164 -62L-105 -72M-165 -49L-106 -59','none','#AF8755',3);
 return g(b,`translate(${x} ${y}) scale(${s})`);
}
function street(t){
 let b=path('M54 1392H1026','none','#CAD4CB',5)+path('M83 1460H1000M126 1515H951','none','#E5EAE3',3);
 // Street context is deliberately quiet; the noodle stall remains the destination.
 for(const [x,w,h] of [[-70,225,470],[892,250,520]]){
  b+=rect(x,850-h*.3,w,h,6,'#F7F8F3','#CDD7CD',3)+rect(x+22,854-h*.3,w-44,85,6,'#E8EEE6');
  for(let i=0;i<2;i++)b+=rect(x+25+i*93,1000-h*.3,68,142,5,C.white,'#CAD6CB',3);
  b+=path(`M${x-10} ${940-h*.3}H${x+w+10}`,'none','#BECBBF',5);
 }
 b+=path('M102 1362V680Q102 640 151 640H195','none','#849B89',7)+path('M164 640L143 685H211L191 640Z','#F8F0CC','#849B89',4);
 return b;
}
function stall(t,s=1){
 let b=shadow(0,340,425,28,.65);
 // Open counter, striped canopy, menu, stockpot and vendor: a street food stall, not a house marker.
 b+=path('M-359 -380V270M359 -380V270','none',C.ink,9);
 b+=rect(-392,-404,784,131,15,C.white,C.ink,5)+txt(0,-318,'贵阳 · 牛肉面',67,800,C.ink,'middle');
 b+=path('M-391 -274H391L430 -204H-430Z','#F5EED8',C.ink,4);
 for(let i=0;i<10;i++){
  const x=-430+i*86;const top=-391+i*78.2;
  if(i%2===0)b+=path(`M${top} -272H${top+78.2}L${x+86} -204H${x}Z`,C.red,'none',0);
  b+=path(`M${x} -204H${x+86}V-182Q${x+43} -158 ${x} -182Z`,i%2===0?C.red:'#F5EED8',C.ink,3);
 }
 // Original cartoon cook peeking above the counter.
 let cook=ellipse(0,-75,57,67,C.white,C.ink,4)+path('M-57 -98Q-78 -151 -34 -153Q-12 -186 16 -155Q58 -174 61 -132L53 -98Z',C.white,C.ink,4)+rect(-54,-108,108,23,5,'#F8F6EE',C.ink,3)+ellipse(-19,-77,5,7,C.ink,'none',0)+ellipse(19,-77,5,7,C.ink,'none',0)+path('M-12 -52Q0 -40 12 -52','none',C.ink,3)+path('M-42 -10Q0 -29 42 -10L64 64H-64Z',C.white,C.ink,4)+path('M-27 -15V37H27V-15',C.mint,C.ink,3);
 b+=g(cook,`translate(-88 -73) rotate(${wave(t,.45)*1.2})`);
 b+=rect(-287,-145,99,153,8,'#FFF9E8',C.ink,3)+txt(-238,-104,'牛肉面',22,700,C.ink,'middle')+txt(-238,-65,'加 面',20,500,C.gray,'middle')+txt(-238,-30,'加 蛋',20,500,C.gray,'middle')+txt(-238,5,'加 肉',20,500,C.gray,'middle');
 b+=rect(-387,26,774,235,10,'#E6EFE6',C.ink,5)+rect(-412,12,824,30,8,'#F9F6ED',C.ink,5)+rect(-326,80,652,111,5,'#FAFCF7','#B3C7B5',3)+txt(0,151,'热 汤 · 现 煮',46,650,'#60826B','middle');
 b+=path('M-341 264V319M341 264V319','none',C.ink,9)+ellipse(-341,324,16,16,C.ink,'none',0)+ellipse(341,324,16,16,C.ink,'none',0);
 // Stockpot on the left and three condiments on the right.
 b+=path('M-345 -83H-194V-3Q-271 27 -345 -3Z','#DDE5DD',C.ink,4)+ellipse(-270,-83,76,20,'#F4F7F0',C.ink,4)+path('M-353 -63H-374V-25H-350M-187 -63H-170V-25H-190','none',C.ink,4)+path('M-290 -95Q-318 -126 -294 -158M-251 -98Q-225 -132 -250 -159','none','#93AA98',4);
 for(let i=0;i<3;i++)b+=rect(259+i*35,-46,27,57,5,[C.red,C.gold,'#568662'][i],C.ink,3)+rect(264+i*35,-57,17,13,3,C.ink);
 return g(b,`translate(540 1085) scale(${s})`);
}
function addition(i,t){
 const start=15.2+i*2,dt=t-start;if(dt<0)return '';
 const p=out(dt/.62),sc=1+.07*Math.exp(-dt*6)*Math.sin(dt*12),x=230+i*310;
 const icon=[noodleBundle,friedEgg,beefSlices][i](0,0,1.05,t);
 let b=ellipse(0,-2,126,104,['#FBF4E2','#FFF7DE','#F5EBE3'][i],'none',0)+icon+txt(0,163,['加面','加蛋','加肉'][i],54,750,C.ink,'middle');
 return g(b,`translate(${x} ${1220+50*(1-p)}) scale(${sc})`,`opacity="${p}"`);
}
function wholeScene(t){
 let b='';const pull=out((t-12)/2),arrive=out((t-9.35)/1.65);
 if(t<14){
  const name=t<2?'中国':t<4.6?'贵州':t<7.2?'贵阳':t<9.6?'贵阳街头':'牛肉面摊';
  b+=g(txt(84,176,'从中国，走到我的家乡。',29,550,C.gray)+txt(84,300,name,100,800,C.ink),'',`opacity="${1-pull}"`);
  if(t<11.1)b+=g(mapLayer(t),'',`opacity="${1-out((t-9.5)/1.6)}"`);
  if(t>9.35){b+=g(street(t),'',`opacity="${arrive*(1-pull)}"`)+g(stall(t,.18+.9*arrive),'',`opacity="${arrive*(1-pull)}"`);}
  const labels=['中国','贵州','贵阳','牛肉面摊'];
  let nav='';labels.forEach((s,i)=>{const active=t<[2,4.6,9.6,99][i]&&(i===0||t>=[0,2,4.6,9.6][i]);nav+=txt(105+i*238,1640,s,i===3?31:34,active?750:500,active?C.green:C.gray);if(i<3)nav+=txt(238+i*238,1640,'→',30,500,C.gray)});
  b+=g(nav,'',`opacity="${1-pull}"`);
  b+=g(txt(84,1780,'地图：China-GeoData · © OpenStreetMap contributors',21,450,C.gray)+txt(84,1820,'街景及面摊为动画示意',22,450,C.gray),'',`opacity="${1-pull}"`);
 }
 if(t>=9.35){
  const ss=.18+.9*arrive;
  const bx=mix(540+160*ss,540,pull),by=mix(1085-88*ss,740,pull),bs=mix(.68*ss,1.82,pull);
  b+=g(heroBowl(bx,by,bs,t),'',`opacity="${arrive}"`);
 }
 if(t>=12){
  b+=g(txt(540,177,'贵州 · 贵阳',31,600,C.gray,'middle')+txt(540,300,'全家福牛肉面',91,800,C.ink,'middle'),' ',`opacity="${out((t-12.8)/.8)}"`);
  for(let i=0;i<3;i++)b+=addition(i,t);
  if(t>=21.3){
   const p=out((t-21.3)/.75),q=spring(t-21.5,8,11);
   b+=g(line(392,1585,452,1585,C.ink,11)+line(392,1620,452,1620,C.ink,11),'',`opacity="${p}"`);
   const x=mix(895,630,p),y=mix(1578,1604,p)-Math.sin(p*Math.PI)*52;
   b+=coin(x,y,116*Math.max(.01,q),t,'20',(1-p)*Math.PI*2);
  }
 }
 return b;
}
window.SHOTS=SHOTS;window.STAGES=STAGES;
window.renderFrame=(index,time)=>{
 const shot=SHOTS[index],t=clamp(time,0,shot.duration-1/30)+shot.offset;
 document.getElementById('frame').innerHTML=defs+rect(0,0,1080,1920,0,C.white)+wholeScene(t);
 return {index,time,t};
};
