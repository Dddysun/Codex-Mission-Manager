const SHOTS=[
 {id:'01_price',name:'官网20美元_真实截图与数字',duration:7,poster:5},
 {id:'02_exchange',name:'实时查询截图_美元换人民币',duration:6,poster:4.8},
 {id:'02b_members',name:'六项会员_真实Logo逐个入场',duration:6,poster:4.8},
 {id:'03_balance',name:'六会员天秤_金币连续转场',duration:12,poster:7.8},
 {id:'04_map',name:'中国贵州贵阳_地图推进街头',duration:10,poster:4.5},
 {id:'05_noodles',name:'贵阳牛肉粉_加粉加肉加煎蛋',duration:9,poster:7.2},
 {id:'06_quota',name:'五小时与周额度_同时消耗',duration:10,poster:7.7},
 {id:'07_week',name:'十次机会_七天日历',duration:6,poster:4.5},
 {id:'08_life',name:'兔子上班吃饭睡觉娱乐',duration:12,poster:1.8},
 {id:'09_alarm',name:'晚上十点_凌晨三点惊醒',duration:10,poster:7.8},
 {id:'10_office',name:'人在公司_惦记家中额度',duration:8,poster:5.4},
 {id:'11_pay',name:'我花钱_AI敲键盘',duration:8,poster:4.5},
 {id:'12_wait',name:'AI等额度_人等AI_时间流失',duration:8,poster:4.5},
 {id:'13_install',name:'简介箭头_截图给Agent安装',duration:22,poster:11}
];
function cropImage(file,x,y,w,h,vb){return `<svg x="${x}" y="${y}" width="${w}" height="${h}" viewBox="${vb.join(' ')}" preserveAspectRatio="xMidYMid slice" overflow="hidden">${img(file,0,0,1280,720)}</svg>`}
function scenePrice(t){
 let b=header('CHATGPT PLUS / 每月订阅',['这个会员，','每个月多少钱？'],t);
 let p=out((t-1.6)/1.1),z=mix(1,1.15,p);
 b+=g(rect(64,598,952,555,26,C.white,C.light,2,'filter="url(#soft)"')+rect(64,598,952,66,26,'#F3F6F3')+txt(105,641,'help.openai.com',25,500,C.gray)+ellipse(941,630,5,5,C.green,'none',0),`translate(0 ${60*(1-out(t/.8))})`);
 if(t<1.7)b+=cropImage('openai_00_官方说明.png',88,680,904,430,[85,10,850,404]);
 else{
  b+=cropImage('openai_01_月费20美元.png',95,697,895,330,[108,0,mix(830,600,p),mix(306,222,p)]);
  b+=line(180,838,180+472*out((t-2.4)/.6),838,C.red,8);
 }
 let pop=spring(t-3.1,7,12);b+=g(num(540,1450,'$20',206,C.ink,'middle'),`translate(540 1375) scale(${Math.max(0,pop)}) translate(-540 -1375)`);
 if(t>3.1)b+=txt(540,1541,'美元 / 月',40,600,C.gray,'middle')+spark(820,1290,.85)+spark(236,1454,.5);
 return b+footer('OpenAI 官方说明实拍截图 · 查询于 2026.10.29');
}
function sceneExchange(t){
 let b=header('USD → CNY / 真实查询',['换成人民币，','一百三十多。'],t);
 let p=out((t-1.2)/.8);
 b+=rect(62,590,956,695,24,C.white,C.light,2,'filter="url(#soft)"');
 let file=t<.65?'google_00_搜索前.png':t<1.25?'google_01_输入查询.png':'google_02_汇率结果.png';
 b+=cropImage(file,84,610,912,640,[mix(0,78,p),0,mix(1280,720,p),mix(898,505,p)]);
 let q=out((t-2.4)/.8);b+=g(num(540,1507,'¥133.22',145,C.ink,'middle'),`translate(0 ${30*(1-q)})`,`opacity="${q}"`);
 if(t>3)b+=txt(540,1594,'20 美元 ≈ 133.22 元',35,500,C.gray,'middle');
 return b+footer('2026.10.29 查询结果 · 实际支付以账单为准');
}
const APPS=['qqmusic','tencentvideo','bilibili','iqiyi','neteasemusic','youku'];
const APP_NAMES=['QQ音乐','腾讯视频','B站大会员','爱奇艺','网易云','优酷'];
function sceneMembers(t){
 let b=header('同一笔钱 / 换一种花法',['音乐、追剧，','还能再加几个。'],t);
 for(let i=0;i<6;i++){
  const dt=t-.25-i*.5;if(dt<0)continue;const p=spring(dt,8,12),x=230+(i%3)*310,y=815+Math.floor(i/3)*440;
  b+=g(shadow(0,105,92,12,.45)+logo(APPS[i],0,0,181)+txt(0,183,APP_NAMES[i],36,700,C.ink,'middle'),`translate(${x} ${y-115*(1-p)}) scale(${1+.08*Math.exp(-dt*5)*Math.sin(dt*12)})`,`opacity="${clamp(dt/.18)}"`);
  if(dt<.45)b+=burst(x,y+96,dt/.45,C.green);
 }
 if(t>3.7)b+=g(txt(540,1618,'一个、两个……六个。',48,750,C.ink,'middle'),' ',`opacity="${out((t-3.7)/.5)}"`);
 return b+footer('各品牌真实标识 · 套餐与价格需以平台为准');
}
function sceneBalance(t){
 const extract=out((t-9.3)/1.7),cx=mix(791,540,extract),cy=mix(865,980,extract),cr=mix(62,193,extract);
 let b=header('同一笔预算 / 买什么',['一个 Plus，','还是这一大堆？'],t);
 let theta=-10;
 for(let i=0;i<6;i++){let dt=t-(.9+i*.55);if(dt>0)theta+=1.37*spring(dt,3.5,9)}
 if(t>5.3)theta+=1.78*spring(t-5.3,2.8,10);
 let a=theta*Math.PI/180;const ax=540-333*Math.cos(a),ay=766-333*Math.sin(a),bx=540+333*Math.cos(a),by=766+333*Math.sin(a);
 let s=shadow(540,1445,260,25)+path('M463 1405H617L590 1365H490Z',C.ink,C.ink,4)+path('M540 786V1365','none',C.ink,17)+path(`M${ax} ${ay}L${bx} ${by}`,'none',C.ink,12)+ellipse(540,766,23,23,C.gold,C.ink,5);
 for(const [x,y] of [[ax,ay],[bx,by]])s+=path(`M${x} ${y+6}L${x-176} ${y+447}M${x} ${y+6}L${x+176} ${y+447}`,'none',C.ink,3)+path(`M${x-183} ${y+447}Q${x} ${y+540} ${x+183} ${y+447}Z`,'#F1F6F2',C.ink,5);
 s+=rect(ax-118,ay+213,236,220,23,C.white,C.light,2,'filter="url(#soft)"')+logo('chatgpt',ax,ay+288,100)+txt(ax,ay+388,'Plus',46,750,C.ink,'middle');
 for(let i=0;i<6;i++){
  const start=.9+i*.55,p=spring(t-start,6,12);if(t<start)continue;
  const x=bx-94+(i%3)*94,y=by+286+Math.floor(i/3)*98,dy=-260*(1-p);
  s+=g(logo(APPS[i],x,y,77),`translate(0 ${dy}) rotate(${(1-p)*(i%2?16:-16)} ${x} ${y})`,`opacity="${clamp(p)}"`);
  if(t-start<.55)s+=burst(x,y+45,(t-start)/.55,C.green);
 }
 b+=g(s,'',`opacity="${1-extract}"`);
 if(t<9.3){b+=txt(208,1537,'ChatGPT Plus',34,700,C.ink,'middle')+txt(856,1537,'六项会员 + ¥20',31,700,C.ink,'middle');
  if(t>4.3)b+=pill(327,1612,426,'预算分配示意',C.white,C.gray);
 }
 if(t>5.3){let q=spring(t-5.3,7,11);b+=coin(cx,cy-370*(1-q),cr,t,'20',extract>0?(1-extract)*Math.PI*2:0);}
 if(extract>.2){b+=g(txt(540,1305,'还有这 20 块。',72,800,C.ink,'middle'),' ',`opacity="${extract}"`)+g(txt(540,1411,'带你回我的家乡。',39,500,C.gray,'middle'),'',`opacity="${extract}"`);}
 return b+footer('会员套餐合计待核价 · 天秤为预算示意');
}
function mapCamera(t){
 const keys=[[0,104,32,65],[.7,104,32,65],[3,106.65,26.85,8],[3.5,106.65,26.85,8],[5.5,106.68,26.74,1.7],[6,106.68,26.74,1.7],[8.7,106.71,26.58,.032],[10,106.71,26.58,.032]];
 for(let i=0;i<keys.length-1;i++){const a=keys[i],b=keys[i+1];if(t>=a[0]&&t<=b[0]){let p=ease((t-a[0])/(b[0]-a[0]));return [mix(a[1],b[1],p),mix(a[2],b[2],p),Math.exp(mix(Math.log(a[3]),Math.log(b[3]),p))]}}
 return keys.at(-1).slice(1);
}
function sceneMap(t){
 const stage=t<2?'中国':t<4.5?'贵州':t<7.3?'贵阳':'贵阳街头';let b=header('这 20 块 / 带你回家乡',[stage,'一碗牛肉粉。'],t);
 const [lon,lat,span]=mapCamera(t),sx=980/span,sy=sx/Math.cos(lat*Math.PI/180);const project=p=>[540+(p[0]-lon)*sx,1025-(p[1]-lat)*sy];
 const visible=r=>r.some(p=>Math.abs(p[0]-lon)<span*.85&&Math.abs(p[1]-lat)<span*1.1);
 let m='';
 function region(r,isCity=false){
  for(let pts of r.rings){if(span<.3||!visible(pts))continue;let p=pts.map(project),d='M'+p.map(v=>v.map(z=>z.toFixed(1)).join(' ')).join('L')+'Z';let hi=r.id===(isCity?520100:520000);m+=path(d,hi?C.mint:'#F1F4F1',hi?C.green:'#C5D0C8',hi?3:1.2);}
 }
 for(let r of GEO.provinces)region(r);
 if(span<12)for(let r of GEO.cities)region(r,true);
 if(span<.4){
  for(let r of GEO.roads){let pts=r.pts.map(project);if(!pts.some(p=>p[0]>-100&&p[0]<1180&&p[1]>450&&p[1]<1620))continue;const d='M'+pts.map(p=>p.map(z=>z.toFixed(1)).join(' ')).join('L');m+=path(d,'none',['primary','secondary'].includes(r.kind)?'#BCCEC1':'#D9E4DC',['primary','secondary'].includes(r.kind)?9:4);}
 }
 let pin=project([106.71,26.58]);m+=ellipse(pin[0],pin[1],35+wave(t,.6)*4,35+wave(t,.6)*4,C.mint,'none',0)+ellipse(pin[0],pin[1],12,12,C.green,C.white,4);
 if(span>2)m+=txt(pin[0]+30,pin[1]-20,'贵阳',34,700,C.ink);
 b+=`<svg x="55" y="520" width="970" height="1060" viewBox="55 520 970 1060" overflow="hidden">${m}</svg>`;
 if(t<1.25){let p=out(t/1.25);b+=coin(mix(540,pin[0],p),mix(980,pin[1],p),mix(193,18,p),t,'20',p*Math.PI*2)}
 if(t>8){let p=out((t-8)/.65),a=170*p;let shop=rect(-130,-63,260,197,10,C.white,C.ink,5)+rect(-141,-117,282,63,7,C.red,C.ink,4)+txt(0,-74,'牛肉粉',35,800,C.white,'middle')+rect(-98,-20,91,151,4,'#DFF1E8',C.ink,4)+rect(22,-20,80,74,4,'#FBF0CF',C.ink,4)+path('M-142 -45H142','none',C.ink,5)+line(0,134,0,180,C.ink,4);
 b+=g(shop,`translate(540 1000) scale(${p*1.4})`);}
 b+=pill(84,1600,196,'中国',C.white,t<2?C.green:C.gray)+txt(305,1640,'→',38,600,C.gray)+pill(358,1600,196,'贵州',C.white,t>=2&&t<4.5?C.green:C.gray)+txt(580,1640,'→',38,600,C.gray)+pill(639,1600,196,'贵阳',C.mint,C.green);
 return b+footer('位置与店铺示意 · 地图：China-GeoData / © OSM');
}
function sceneNoodles(t){
 const phase=t<1.5?0:t<3.5?1:t<5.5?2:3;
 const title=['全家福牛肉粉。','再加一份粉。','再加一份肉。','最后，加煎蛋。'][phase];
 let b=header('贵州 · 贵阳 / 街头一碗',['20 块的快乐，',t>7?'吃！到！饱！':title],t);
 const dropStart=[0,1.5,3.5,5.5][phase],dt=t-dropStart;
 b+=bowlArt(540,1110,1.72,t,phase>0&&dt<.85?phase-1:phase);
 if(phase>0&&dt<.85){let p=out(dt/.85),yy=mix(570,1050,p);if(phase===1){for(let i=0;i<8;i++)b+=path(`M${410+i*28} ${yy-160}Q${380+i*30} ${yy-70} ${450+i*24} ${yy+20}`,'none','#E2B66C',8)}
 else if(phase===2){for(let i=0;i<3;i++)b+=g(path('M-45 -18Q0 -45 48 -12L39 28Q0 43 -49 15Z','#7B3828','#56291F',3)+line(-25,-8,22,15,'#DEA57D',4),`translate(${425+i*118} ${yy+(i-1)*40}) rotate(${(1-p)*80+i*20})`)}
 else b+=g(path('M-73 4C-99 -43 -37 -75 -3 -53C29 -83 88 -34 73 2C103 39 35 65 0 50C-52 72 -90 42 -73 4Z','#FFF9E9','#E1B85B',3)+ellipse(0,-4,37,32,C.gold,'none',0),`translate(680 ${yy}) rotate(${(1-p)*140}) scale(1.5)`);
 }
 for(let i=0;i<3;i++){let p=spring(t-(1.5+i*2),7,13);if(p<=0)continue;b+=g(pill(112+i*292,1506,260,['＋粉','＋肉','＋煎蛋'][i],i===2?'#FFF2CB':C.mint,C.ink),`translate(${242+i*292} 1534) scale(${p}) translate(${-242-i*292} -1534)`)}
 if(t>7)b+=spark(187,821,1.2)+spark(882,792,1.6)+spark(918,1316,.7);
 return b+footer('代码绘制的食物动画 · 金额为口播情境示例');
}
function sceneQuota(t){
 const p=ease((t-1.4)/5.0),short=Math.round(100*(1-p)),week=Math.round(100-10*p),done=t>6.4;
 let b=header('额度 / 两个窗口同时消耗',['五小时，','先撑不住了。'],t);
 const rows=[{y:720,title:'五小时额度',v:short,fill:short<20?C.red:C.ink},{y:1180,title:'周额度',v:week,fill:C.green}];
 for(let j=0;j<2;j++){let r=rows[j];b+=txt(84,r.y-90,r.title,47,700)+num(994,r.y-82,`${r.v}%`,92,r.fill,'end');b+=rect(84,r.y,912,91,45,C.light)+rect(84,r.y,Math.max(0,912*r.v/100),91,45,r.fill);
  for(let k=1;k<10;k++)b+=line(84+k*91.2,r.y+17,84+k*91.2,r.y+74,C.white,3,`opacity=".4"`);
  if(j===0&&done)b+=g(pill(84,r.y+131,218,'已耗尽','#FFEBE5',C.red),`translate(${wave(t,7)*Math.exp(-(t-6.4)*4)*9} 0)`);
  if(j===1&&done)b+=pill(84,r.y+131,300,'才用掉约 10%',C.mint,C.green);
 }
 if(done){let q=out((t-6.4)/.6);b+=g(txt(540,1630,'这边停工，那边还剩一大截。',40,700,C.ink,'middle'),`translate(0 ${20*(1-q)})`,`opacity="${q}"`);}
 return b+footer('剩余额度示意 · 10% 为口播假设，并非固定比例');
}
function sceneWeek(t){
 let b=header('按上述假设 / 算第二笔账',['约十次机会，','一周只有七天。'],t);
 for(let i=0;i<10;i++){let p=spring(t-.5-i*.13,8,14);if(p<=0)continue;let x=142+(i%5)*199,y=675+Math.floor(i/5)*182;b+=g(rect(-58,-58,116,116,30,i<7?C.mint:'#FFF0E8',i<7?C.green:C.red,3)+num(0,18,String(i+1),50,i<7?C.green:C.red,'middle'),`translate(${x} ${y}) scale(${p})`);}
 let q=out((t-2.4)/.7);b+=g(rect(85,1110,910,405,28,C.white,C.ink,4)+rect(85,1110,910,74,28,C.ink)+txt(125,1160,'一周日历',32,700,C.white)+txt(951,1160,'7 DAYS',26,600,C.white,'end'),`translate(0 ${50*(1-q)})`,`opacity="${q}"`);
 for(let i=0;i<7;i++){b+=g(txt(149+i*130,1264,['一','二','三','四','五','六','日'][i],31,500,C.gray,'middle')+num(149+i*130,1390,String(i+1),61,C.ink,'middle'),'',`opacity="${q}"`)}
 return b+footer('十次使用机会为举例 · 具体取决于任务与实际额度');
}
function paws(x,y,s,t){let b='';for(let sign of [-1,1]){let yy=y+wave(t+sign*.06,4.5)*9;b+=ellipse(x+sign*48*s,yy,19*s,12*s,C.white,C.ink,4);if(wave(t+sign*.06,4.5)<-.4)b+=line(x+sign*48*s,yy-24,x+sign*61*s,yy-42,C.gray,3)}return b}
function plant(x,y,s=1,t=0){return g(path('M-28 0H28L20 62H-20Z','#F5EDDA',C.ink,4)+path('M0 0V-100M0 -62Q-58 -120 -57 -76Q-47 -41 0 -45M0 -43Q47 -95 50 -56Q43 -24 0 -24',C.mint,C.ink,3),`translate(${x} ${y}) scale(${s}) rotate(${wave(t,.4)*1.2})`)}
function sceneLife(t){
 const i=Math.min(3,Math.floor(t/3)),u=t-i*3,names=['要上班。','要吃饭。','要睡觉。','还要有自己的娱乐。'];
 let b=header('一周七天 / 也得过自己的生活',[names[i]],Math.min(1,u+.1));
 let local='';
 if(i===0){local+=clockFace(838,674,83,u,10)+plant(182,1095,.85,u)+shadow(540,1490,210,23)+rabbit(540,1350,1.85,u,'type');local+=desk(540,1140,1.65)+laptop(540,1123,1.23,u)+cup(862,1113,1.05,u)+paws(540,1135,1.3,u);}
 if(i===1){local+=shadow(540,1490,210,23)+rabbit(540,1350,1.85,u,'eat')+desk(540,1150,1.65)+bowlArt(525,988,.88,u,3)+cup(855,1118,.8,u);let yy=950+wave(u,.65)*22;for(let k=0;k<4;k++)local+=path(`M${520+k*9} ${yy}Q${535+k*8} 980 ${500+k*8} 985`,'none','#D6AE67',4);}
 if(i===2){local+=path('M811 664A71 71 0 1 1 744 555A58 58 0 0 0 811 664',C.mint,C.ink,4)+spark(890,573,.45)+rabbit(402,1339,1.4,u,'idle','sleep',{tilt:-28})+bed(540,1285,1.65,u);for(let j=0;j<3;j++){let p=(u*.4+j*.28)%1;local+=txt(547+85*p,1066-175*p,'z',33+24*p,650,C.gray,'middle',`opacity="${1-p}"`);}}
 if(i===3){let hop=Math.max(0,wave(u,1.2))*22;local+=shadow(540,1450,182-hop,20)+rabbit(540,1420-hop,1.95,u,'game','happy',{tilt:wave(u,1.2)*4});for(let j=0;j<7;j++){let x=200+j*113,y=674+wave(u+j,.4)*25;local+=g(rect(-5,-13,10,26,4,[C.green,C.gold,C.red][j%3]),`translate(${x} ${y}) rotate(${j*33+u*25})`)}local+=txt(840,1066,'＋1',43,700,C.green,'middle');}
 const enter=out(u/.35);b+=g(local,`translate(${(1-enter)*140} 0)`,`opacity="${enter}"`);
 for(let j=0;j<4;j++){let active=j===i;b+=rect(84+j*232,1618,211,8,4,active?C.red:C.light)+txt(189+j*232,1683,['工作','吃饭','睡觉','娱乐'][j],32,active?750:450,active?C.ink:C.gray,'middle');}
 return b+footer('AI 应该帮你工作，也该留出你的生活。');
}
function sceneAlarm(t){
 let late=t>6.1,phase=t<2.2?0:t<6.1?1:2;
 let b=header('额度刷新 / 不会配合你的作息',[late?'额度恢复了。':'晚上十点，用完了。',late?'人，也被叫醒了。':'你该睡觉了。'],t);
 let hh=22;if(t>4.1&&t<6.1)hh=(22+Math.floor(ease((t-4.1)/2)*5))%24;if(late)hh=3;
 b+=num(540,650,String(hh).padStart(2,'0')+':00',153,late?C.red:C.ink,'middle');
 if(phase===0){b+=shadow(540,1500,250,22)+rabbit(524,1410,1.6,t,'type','tired')+desk(540,1225,1.4)+laptop(540,1210,1.1,t,true)+paws(540,1227,1.2,t);}
 if(phase===1){let p=out((t-2.2)/.45);b+=g(rabbit(376,1344,1.3,t,'idle','sleep',{tilt:-29})+bed(540,1270,1.6,t),`translate(${70*(1-p)} 0)`,`opacity="${p}"`)+txt(659,1026,'z',45,650,C.gray)+txt(703,961,'z',33,650,C.gray);}
 if(phase===2){let dt=t-6.1,p=spring(dt,6,12);b+=shadow(434,1505,200,20)+rabbit(432,1485-24*Math.exp(-dt*2),1.65,t,'phone',dt<.65?'shock':'tired',{tilt:mix(-17,6,clamp(dt))})+clockFace(832,1152,106,t,3,true);if(dt<.8)b+=burst(453,961,dt/.8);b+=txt(540,1613,'人醒了，脑子还没醒。',49,750,C.ink,'middle');}
 return b+footer('22:00 → 03:00 为情境举例 · 恢复时间以账户为准');
}
function sceneOffice(t){
 let b=header('人在公司 / 心在家里的电脑',['上着班，','还得惦记额度。'],t);
 let h=path('M-173 -85L0 -239L173 -85','none',C.ink,6)+path('M-139 -112V138H139V-112',C.white,C.ink,5)+laptop(0,75,.65,t,t>2.2)+txt(0,201,'家里的电脑',29,600,C.gray,'middle');
 b+=g(h,'translate(796 810) scale(.92)');
 const d='M406 1074C460 974 520 1006 620 919';b+=path(d,'none',C.gray,3,'stroke-dasharray="10 14"');let p=(t*.6)%1;b+=ellipse(mix(410,620,p),mix(1070,920,p)-Math.sin(p*Math.PI)*25,8,8,C.green,'none',0);
 b+=shadow(311,1470,180,20)+rabbit(330,1400,1.38,t,t>3?'phone':'type',t>3?'tired':'happy')+desk(330,1217,1.09)+laptop(330,1203,.92,t)+paws(330,1218,.9,t);
 if(t>2.4){let p=spring(t-2.4,7,14);b+=g(pill(630,1060,320,'额度又用完了','#FFF0E8',C.red),`translate(790 1088) scale(${p}) translate(-790 -1088)`)}
 if(t>4){let p=out((t-4)/.5);b+=g(clockFace(820,1348,91,t,15,t<5.4)+txt(820,1510,'再定一个闹钟',31,700,C.ink,'middle'),' ',`opacity="${p}"`);}
 return b+footer('生活场景演绎 · 原创兔子角色');
}
function scenePay(t){
 let b=header('本来 / 花钱买效率',['我付钱，','AI 替我干活。'],t);
 b+=shadow(270,1462,151,20)+shadow(815,1462,166,20)+rabbit(245,1417,1.48,t,'pay')+robot(811,1417,1.53,t,true)+desk(813,1261,.82)+laptop(813,1250,.72,t)+paws(813,1267,.8,t);
 for(let i=0;i<3;i++){let p=(t*.48+i/3)%1,x=mix(438,787,p),y=mix(1150,1010,p)-Math.sin(p*Math.PI)*240;b+=coin(x,y,36,t,'',p*Math.PI*3);}
 b+=path('M417 774Q610 655 802 788','none',C.gray,3,'stroke-dasharray="8 12"')+path('M778 770L803 790L802 757','none',C.gray,3);
 b+=txt(247,1550,'我',41,750,C.ink,'middle')+txt(811,1550,'AI',41,750,C.ink,'middle');
 if(t>2)b+=g(pill(650,703,270,'正在干活',C.mint,C.green),`translate(0 ${wave(t,.8)*4})`);
 return b+footer('买会员，是为了让工具替我们节省时间。');
}
function sceneWait(t){
 let b=header('结果 / 现在反过来了',['AI 在等额度，','我在等 AI。'],t);
 let settle=out(t/.65);b+=shadow(249,1460,151,20)+shadow(816,1460,166,20)+rabbit(244,1417,1.5,t,'wait','tired')+robot(816,1417,1.53,t,false);
 b+=pill(676,702,272,'剩余额度 0%','#FFF0E8',C.red)+txt(210,725,'还要多久…',36,600,C.gray);
 for(let i=0;i<3;i++){b+=ellipse(446+i*80,895,8,8,C.gray,'none',0,`opacity="${.2+.8*clamp(wave(t-i*.15,1))}"`);}
 const p=(t*.4)%1;b+=coin(539,1100+p*420,42,t,'',p*Math.PI*4);
 b+=txt(246,1545,'等 AI',36,750,C.ink,'middle')+txt(814,1545,'等额度',36,750,C.ink,'middle');
 b+=rect(86,1620,908,8,4,C.light)+rect(86,1620,908*clamp(t/8),8,4,C.red)+txt(540,1695,'订阅时间，还在一秒一秒地走。',36,650,C.red,'middle');
 return b+footer('时间流逝的视觉比喻 · 并非按秒扣费');
}
function sceneInstall(t){
 if(t<6){
  let b=header('TOKENMAX / 获取方式',['打开视频简介，','复制给你的 Agent。'],t);
  const p=spring(t-.5,7,12);let copy=rect(-155,-177,267,331,24,C.white,C.ink,7)+rect(-112,-134,267,331,24,C.white,C.ink,7)+rect(-72,-78,188,18,9,C.mint)+line(-72,-14,104,-14,C.ink,8)+line(-72,43,71,43,C.ink,8)+line(-72,100,99,100,C.ink,8);
  b+=g(copy,`translate(540 865) scale(${Math.max(0,p)}) rotate(${wave(t,.55)*2})`);
  let yy=1230+Math.max(0,wave(t,.8))*33;b+=path(`M540 ${yy}V${yy+250}M450 ${yy+168}L540 ${yy+260}L630 ${yy+168}`,'none',C.red,22)+txt(540,1634,'就在视频下方 ↓',42,750,C.ink,'middle');
  return b+footer('也可以暂停下一屏，直接截图给 Agent。');
 }
 let b=header('TOKENMAX / 暂停这一屏即可',['截图，发给 Agent。'],6);
 b+=txt(84,435,'让它查询并安装最新发布版本。',39,500,C.gray);
 b+=rect(65,522,950,949,30,C.white,'#BCC9C0',3,'filter="url(#soft)"');
 b+=pill(104,563,230,'给 Agent 的指令',C.mint,C.green);
 b+=txt(105,692,'请读取这个仓库的安装说明：',39,650);
 b+=txt(105,795,'https://github.com/Dddysun/TokenMax-Zhazhiji',40,500,C.ink,'start','font-family="Helvetica, Arial, sans-serif"');
 b+=txt(105,857,'公开仓库 / Windows 与 macOS 原生应用',30,500,C.gray);
 b+=line(105,901,965,901,C.light,2);
 const lines=['查询执行时最新已发布的 Release','（含预览版），按我的系统和芯片','架构下载匹配安装包，校验后安装。','保留已有数据；需要授权或登录时，','请提示我。'];
 lines.forEach((s,i)=>b+=txt(105,995+i*78,s,39,500));
 b+=pill(84,1546,410,'Windows x64',C.white,C.ink)+pill(527,1546,467,'macOS · Apple Silicon',C.white,C.ink);
 b+=txt(540,1688,'安装包按执行时的 Release 选择',31,500,C.gray,'middle');
 return b+footer('不写死版本号 · 当前发布包的原生平台如上');
}
const FUNCS=[scenePrice,sceneExchange,sceneMembers,sceneBalance,sceneMap,sceneNoodles,sceneQuota,sceneWeek,sceneLife,sceneAlarm,sceneOffice,scenePay,sceneWait,sceneInstall];
window.SHOTS=SHOTS;
window.renderFrame=(index,time)=>{
 const content=FUNCS[index](clamp(time,0,SHOTS[index].duration-1/30));
 document.getElementById('frame').innerHTML=defs+rect(0,0,1080,1920,0,C.white)+content;
 return {index,time};
};
