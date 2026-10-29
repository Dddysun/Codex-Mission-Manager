// Original SVG artwork. Every pose is a pure function of the requested frame time.
const C={ink:'#172620',red:'#F45145',green:'#36AC82',mint:'#DDF4E9',gold:'#F6C84D',goldDark:'#B58120',gray:'#728079',light:'#E8ECE9',white:'#FFFFFF'};
const clamp=(x,a=0,b=1)=>Math.max(a,Math.min(b,x));
const mix=(a,b,p)=>a+(b-a)*p;
const ease=p=>{p=clamp(p);return p*p*(3-2*p)};
const out=p=>1-Math.pow(1-clamp(p),3);
const spring=(t,d=7,w=13)=>t<0?0:1-Math.exp(-d*t)*Math.cos(w*t);
const wave=(t,f=1)=>Math.sin(t*Math.PI*2*f);
const esc=s=>String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;');
const g=(body,transform='',extra='')=>`<g transform="${transform}" ${extra}>${body}</g>`;
const path=(d,fill='none',stroke=C.ink,sw=5,extra='')=>`<path d="${d}" fill="${fill}" stroke="${stroke}" stroke-width="${sw}" stroke-linecap="round" stroke-linejoin="round" ${extra}/>`;
const line=(x1,y1,x2,y2,color=C.ink,sw=5,extra='')=>path(`M${x1} ${y1}L${x2} ${y2}`,'none',color,sw,extra);
const ellipse=(x,y,rx,ry,fill=C.white,stroke=C.ink,sw=5,extra='')=>`<ellipse cx="${x}" cy="${y}" rx="${rx}" ry="${ry}" fill="${fill}" stroke="${stroke}" stroke-width="${sw}" ${extra}/>`;
const rect=(x,y,w,h,r=0,fill=C.white,stroke='none',sw=0,extra='')=>`<rect x="${x}" y="${y}" width="${Math.max(0,w)}" height="${Math.max(0,h)}" rx="${r}" fill="${fill}" stroke="${stroke}" stroke-width="${sw}" ${extra}/>`;
const txt=(x,y,s,size=48,weight=600,fill=C.ink,anchor='start',extra='')=>`<text x="${x}" y="${y}" font-size="${size}" font-weight="${weight}" fill="${fill}" text-anchor="${anchor}" ${extra}>${esc(s)}</text>`;
const num=(x,y,s,size=120,fill=C.ink,anchor='start')=>txt(x,y,s,size,750,fill,anchor,'font-family="Arial, Helvetica, sans-serif" letter-spacing="-5"');
const img=(name,x,y,w,h,extra='')=>`<image href="assets/${name}" x="${x}" y="${y}" width="${w}" height="${h}" preserveAspectRatio="xMidYMid meet" ${extra}/>`;
const logoFile=s=>['tencentvideo','bilibili'].includes(s)?`${s}.png`:`${s}.jpg`;
const logo=(s,x,y,size)=>img(logoFile(s),x-size/2,y-size/2,size,size);
const shadow=(x,y,rx=170,ry=16,alpha=.7)=>ellipse(x,y,rx,ry,C.light,'none',0,`opacity="${alpha}"`);
const spark=(x,y,s=1)=>g(path('M0 -18L0 18M-18 0L18 0','none',C.gold,5),`translate(${x} ${y}) rotate(18) scale(${s})`);
const arrow=(x1,y1,x2,y2,c=C.red,w=8)=>line(x1,y1,x2,y2,c,w)+path(`M${x2-18} ${y2-25}L${x2} ${y2}L${x2+18} ${y2-25}`,'none',c,w);
function header(kicker,lines,t=5){
 let s=txt(84,177,kicker,25,600,C.gray);
 lines.forEach((v,i)=>{let p=out((t-i*.13)/.65);s+=g(txt(84,290+i*112,v,91,800),`translate(0 ${38*(1-p)})`,`opacity="${p}"`)});
 return s;
}
const footer=s=>txt(84,1772,s,25,450,C.gray);
function pill(x,y,w,s,fill=C.white,ink=C.ink){return rect(x,y,w,56,28,fill,ink===C.ink?C.light:'none',2)+txt(x+w/2,y+37,s,27,600,ink,'middle')}
function coin(x,y,r=90,t=0,label='20',turn=0){
 const sx=Math.max(.13,Math.abs(Math.cos(turn)));
 let body=ellipse(8,4,r,r,'#BA8420',C.ink,3)+ellipse(0,0,r,r,'url(#gold)',C.ink,3)+ellipse(0,0,r-12,r-12,'none','#B98826',2);
 for(let k=0;k<24;k++){let a=k*Math.PI/12;body+=line(Math.cos(a)*(r-4),Math.sin(a)*(r-4),Math.cos(a)*(r-8),Math.sin(a)*(r-8),'#D6A42C',2)}
 body+=txt(0,-r*.28,'¥',r*.3,700,'#8C6318','middle')+num(0,r*.43,label,r*.82,'#73501B','middle');
 body+=path(`M${-r*.67} ${-r*.18}Q${-r*.6} ${-r*.65} ${-r*.12} ${-r*.72}`,'none','#FFF4BA',r*.065);
 return g(body,`translate(${x} ${y}) scale(${sx} 1)`);
}
function laptop(x,y,s=1,t=0,empty=false){
 let b=rect(-150,-180,300,176,16,C.white,C.ink,6)+rect(-132,-161,264,135,6,empty?'#FFF0EB':'#EFF6F2');
 b+=ellipse(0,-171,2,2,C.gray,'none',0);
 if(empty)b+=txt(0,-95,'额度耗尽',28,700,C.red,'middle')+num(0,-49,'0%',36,C.red,'middle');
 else for(let k=0;k<5;k++){let len=50+((Math.floor(t*6)+k*7)%5)*30;b+=rect(-109,-140+k*23,len,6,3,k===2?C.green:C.gray);}
 b+=path('M-150 -4L-178 18Q-179 26 -164 26H164Q179 26 178 18L150 -4Z','#E8EEEA',C.ink,5)+path('M-34 1H34L45 12H-45Z',C.white,C.gray,2);
 return g(b,`translate(${x} ${y}) scale(${s})`);
}
function desk(x,y,s=1){return g(rect(-250,0,500,22,10,'#F7F5EB',C.ink,5)+path('M-208 22L-226 210M208 22L226 210','none',C.ink,7)+line(-208,88,208,88,C.light,4),`translate(${x} ${y}) scale(${s})`)}
function cup(x,y,s=1,t=0){let b=path('M-28 -36H28V8Q28 25 0 25Q-28 25 -28 8Z','#F4C64D',C.ink,4)+path('M29 -25Q63 -26 53 2Q47 13 29 10','none',C.ink,4);for(let k=0;k<2;k++)b+=path(`M${-12+k*22} -50Q${-23+k*22+wave(t,.5)*7} -67 ${-10+k*22} -85`,'none',C.gray,3);return g(b,`translate(${x} ${y}) scale(${s})`)}
function clockFace(x,y,r,t,h=3,ring=false){
 let b=ellipse(0,0,r,r,C.white,C.ink,6);
 for(let i=0;i<12;i++){let a=i*Math.PI/6;b+=line(Math.sin(a)*r*.79,-Math.cos(a)*r*.79,Math.sin(a)*r*.89,-Math.cos(a)*r*.89,C.ink,i%3===0?5:3)}
 let a=h*Math.PI/6;b+=line(0,0,Math.sin(a)*r*.49,-Math.cos(a)*r*.49,C.ink,7)+line(0,0,0,-r*.67,C.red,4)+ellipse(0,0,5,5,C.ink,'none',0);
 if(ring)b+=path(`M${-r*.9} ${-r*.8}Q${-r*1.4} ${-r*1.1} ${-r*.8} ${-r*1.32}M${r*.9} ${-r*.8}Q${r*1.4} ${-r*1.1} ${r*.8} ${-r*1.32}`,'none',C.red,6)+path(`M${-r*1.3} ${-r*.45}L${-r*1.5} ${-r*.6}M${r*1.3} ${-r*.45}L${r*1.5} ${-r*.6}`,'none',C.red,5);
 return g(b,`translate(${x} ${y}) rotate(${ring?wave(t,8)*7:0})`);
}
function rabbit(x,y,s=1,t=0,pose='idle',mood='happy',opts={}){
 const tired=['tired','sleep'].includes(mood),typing=pose==='type';
 const breathe=wave(t,.45)*2.5,blink=(t%4.8)>4.63;
 const tilt=opts.tilt??(mood==='shock'?-8:tired?7:wave(t,.35)*1.6);
 const nod=typing?Math.abs(wave(t,2))*2:breathe;
 let b=ellipse(-39,0,45,19,C.white,C.ink,5)+ellipse(43,0,45,19,C.white,C.ink,5);
 b+=path('M-52 -179C-94 -152 -78 -62 -55 -24Q0 9 58 -24C88 -65 84 -149 52 -179Z',C.white,C.ink,5);
 b+=ellipse(2,-83,38,45,'#F4F5EF','none',0);
 let ears='';
 for(let sign of [-1,1]){
  let ear=path('M-21 4C-38 -48 -27 -141 -1 -157C32 -164 31 -58 23 4Z',C.white,C.ink,5)+path('M-8 -12Q-18 -104 0 -125Q14 -87 10 -14','#F6E7DF','none',0);
  let a=sign*(tired?34:8)+wave(t,.7+sign*.1)*3;
  ears+=g(ear,`translate(${sign*42} -306) rotate(${a})`);
 }
 let head=ears+path('M-102 -242C-107 -305 -71 -342 0 -341C73 -342 110 -304 105 -246C101 -194 56 -173 0 -174C-57 -174 -99 -192 -102 -242Z',C.white,C.ink,5);
 head+=ellipse(-69,-236,20,10,'#FFDCD3','none',0)+ellipse(70,-236,20,10,'#FFDCD3','none',0);
 if(tired||blink){head+=path('M-56 -256Q-42 -249 -28 -256M28 -256Q42 -249 56 -256','none',C.ink,5);if(tired)head+=path('M-56 -242L-31 -238M30 -238L56 -242','none','#A8B2AC',3)}
 else {head+=ellipse(-43,-262,8,mood==='shock'?16:12,C.ink,'none',0)+ellipse(43,-262,8,mood==='shock'?16:12,C.ink,'none',0)+ellipse(-45,-266,2.5,3,C.white,'none',0)+ellipse(41,-266,2.5,3,C.white,'none',0);}
 head+=path('M-6 -238Q0 -232 6 -238L0 -231Z',C.ink,C.ink,2);
 if(mood==='shock')head+=ellipse(0,-211,12,16,C.white,C.ink,4)+path('M-59 -289L-27 -299M27 -299L59 -289','none',C.ink,4);
 else if(tired)head+=path('M-13 -211Q0 -218 13 -211','none',C.ink,4);
 else head+=path('M-19 -217Q-10 -203 0 -215Q10 -203 19 -217','none',C.ink,4);
 b+=g(head,`translate(0 ${nod}) rotate(${tilt} 0 -210)`);
 b+=path('M-63 -179Q0 -150 61 -179L53 -146Q0 -124 -57 -147Z',C.red,C.ink,4)+path(`M31 -145Q61 ${-126+wave(t)*6} 83 -102L58 -99L40 -79Q31 -110 16 -136Z`,C.red,C.ink,4);
 let l='M-64 -143Q-95 -111 -79 -77',r='M64 -143Q94 -110 77 -77';
 if(typing){l=`M-64 -143Q-104 -103 -33 ${-104+wave(t,4.5)*9}`;r=`M64 -143Q106 -102 36 ${-103-wave(t,4.5)*9}`;}
 if(pose==='pay'){r=`M64 -143Q100 -111 146 ${-169+wave(t,1.3)*8}`;l='M-64 -143Q-103 -105 -58 -79';}
 if(pose==='eat'){l='M-64 -143Q-107 -94 -34 -77';r=`M64 -143Q114 -166 38 ${-211+wave(t,.65)*22}`;}
 if(pose==='game'){l='M-64 -143Q-98 -96 -34 -96';r='M64 -143Q98 -96 34 -96';}
 if(pose==='phone'){r='M64 -143Q105 -130 104 -205';l='M-64 -143Q-103 -105 -65 -77';}
 if(pose==='wait'){r='M64 -143Q123 -184 77 -225';l='M-64 -143Q-100 -81 6 -80';}
 if(pose==='point'){r='M64 -143Q122 -91 145 -167';}
 b+=path(l,'none',C.ink,15)+path(l,'none',C.white,7)+path(r,'none',C.ink,15)+path(r,'none',C.white,7);
 if(pose==='pay')b+=rect(-100,-112,86,54,11,'#DDEADF',C.ink,4)+rect(-66,-93,52,22,6,'#ADCAAF',C.ink,3);
 if(pose==='phone')b+=g(rect(-28,-55,56,96,10,C.ink,C.ink,4)+rect(-20,-43,40,64,4,'#E8F5F0')+ellipse(0,31,3,3,C.white,'none',0),`translate(106 -225) rotate(10)`);
 if(pose==='eat')b+=g(path('M-14 0L-68 -20M-14 -8L-65 -29','none',C.ink,4),`translate(48 ${-211+wave(t,.65)*22})`);
 if(pose==='game')b+=g(path('M-46 -27Q0 -36 46 -27Q66 -5 59 19Q44 41 25 16H-25Q-47 42 -61 18Q-67 -6 -46 -27Z',C.white,C.ink,4)+path('M-38 -9H-16M-27 -20V2','none',C.ink,4)+ellipse(27,-13,5,5,C.red,'none',0)+ellipse(41,0,5,5,C.green,'none',0),`translate(0 -94) rotate(${wave(t,2)*3})`);
 return g(b,`translate(${x} ${y}) scale(${s})`);
}
function robot(x,y,s=1,t=0,work=true){
 let b=path('M-34 -40V-4H-68M34 -40V-4H68','none',C.ink,13)+rect(-76,-199,152,157,25,'#EDF3EF',C.ink,5)+rect(-39,-157,78,63,12,C.white,C.ink,3);
 b+=rect(-27,-144,work?54:4,12,6,work?C.green:C.red)+ellipse(0,-113,7,7,work?C.gold:C.red,'none',0);
 b+=path('M0 -342V-369','none',C.ink,5)+ellipse(0,-382,13,13,work?C.green:C.red,C.ink,4);
 b+=rect(-109,-343,218,147,32,C.white,C.ink,5)+rect(-86,-320,172,80,18,work?'#E5F5EE':'#F4EEE6');
 b+=txt(0,-283,'AI',37,800,C.ink,'middle');
 if(work)b+=path('M-48 -258L-37 -265L-26 -258M26 -258L37 -265L48 -258','none',C.ink,4);
 else b+=path('M-49 -263L-27 -258M27 -258L49 -263','none',C.ink,4);
 b+=path(work?'M-17 -221H17':'M-18 -215Q0 -232 18 -215','none',C.ink,4);
 let p=work?wave(t,6)*12:0;
 b+=path(`M-76 -167Q-117 -111 -40 ${-110+p}M76 -167Q120 -110 43 ${-110-p}`,'none',C.ink,14)+path(`M-76 -167Q-117 -111 -40 ${-110+p}M76 -167Q120 -110 43 ${-110-p}`,'none',C.white,6);
 if(!work)b+=g(path('M-75 -8Q-60 60 0 61Q60 60 75 -8Z',C.white,C.ink,4)+ellipse(0,-8,75,17,'#F1F3F0',C.ink,4)+txt(0,36,'额度',23,700,C.gray,'middle'),`translate(0 -100)`);
 return g(b,`translate(${x} ${y}) scale(${s})`);
}
function burst(x,y,t,color=C.red){let b='';for(let k=0;k<9;k++){let a=k*2.4,rr=20+clamp(t)*100;b+=line(x+Math.cos(a)*rr,y+Math.sin(a)*rr,x+Math.cos(a)*(rr+18),y+Math.sin(a)*(rr+18),color,4,`opacity="${1-clamp(t)}"`)}return b}
function bed(x,y,s=1,t=0){return g(rect(-230,-85,480,145,24,'#DFF0E7',C.ink,5)+path('M-230 -85V-172Q-230 -203 -197 -203H-100V-85',C.white,C.ink,5)+rect(-213,-158,130,73,28,C.white,C.ink,4)+path('M-245 62H268M-215 62V125M236 62V125','none',C.ink,8)+path(`M-80 -73Q20 ${-100+wave(t,.45)*4} 160 -66`,'none','#A7CBB7',4),`translate(${x} ${y}) scale(${s})`)}
function bowlArt(x,y,s=1,t=0,level=3){
 let b=shadow(0,176,205,20,.5)+path('M-224 0Q-196 151 -58 171H58Q194 149 224 0Z','#FAFBF8',C.ink,6)+path('M-166 64Q0 138 166 64','none','#D6E5DA',12)+rect(-68,167,136,17,8,C.white,C.ink,4)+ellipse(0,0,224,82,'#9D5635',C.ink,6)+ellipse(0,-8,205,65,'#C17B47','none',0);
 for(let k=0;k<15;k++){let yy=-46+k*6,xx=-153+Math.sin(k*4)*22;b+=path(`M${xx} ${yy}C${-45} ${yy-43} ${38} ${yy+52} ${160} ${yy-8}`,'none','#FFE5AA',6);}
 if(level>=1){for(let k=0;k<8;k++)b+=path(`M${-100+k*21} -41Q${-130+k*20} ${-5+k*2} ${-88+k*21} 25`,'none','#FFF2CE',7)}
 if(level>=2){for(let k=0;k<5;k++){b+=g(path('M-38 -22Q-6 -38 36 -16L47 13Q18 36 -28 23L-43 6Z','#7B3828','#56291F',3)+path('M-23 -8L23 7M-15 -20L31 -4','none','#DA9D79',4),`translate(${-129+k*60} ${-23+(k%2)*29}) rotate(${-24+k*11})`);}}
 if(level>=3)b+=g(path('M-73 4C-99 -43 -37 -75 -3 -53C29 -83 88 -34 73 2C103 39 35 65 0 50C-52 72 -90 42 -73 4Z','#FFF9E9','#E1B85B',3)+ellipse(0,-4,37,32,'#F4B633','#E5A22B',3)+path('M-19 -15Q-5 -30 13 -22','none','#FFDE75',6),`translate(84 -27) rotate(-16)`);
 for(let k=0;k<12;k++)b+=rect(-166+(k*47)%330,-49+(k*31)%77,13,7,2,k%2?C.green:'#296F46');
 for(let k=0;k<3;k++)b+=path(`M${-105+k*103} -104Q${-128+k*103+wave(t+k,.35)*20} -141 ${-104+k*103} -180Q${-83+k*103} -205 ${-109+k*103} -236`,'none','#B8C6BC',4,`opacity="${.45+.15*wave(t+k,.4)}"`);
 return g(b,`translate(${x} ${y}) scale(${s})`);
}
const defs=`<defs><linearGradient id="gold" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#FFE391"/><stop offset=".55" stop-color="#F8CA4B"/><stop offset="1" stop-color="#E3A72D"/></linearGradient><filter id="soft"><feDropShadow dx="0" dy="14" stdDeviation="18" flood-color="#182820" flood-opacity=".10"/></filter><clipPath id="screenClip"><rect x="60" y="600" width="960" height="610" rx="24"/></clipPath></defs>`;
