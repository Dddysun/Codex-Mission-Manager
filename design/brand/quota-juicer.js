/* Generated 1.3.0 bundle: static artwork + canonical motion + Web Component. */
/* TokenMax static vector artwork. Motion is provided by juicer-motion.js. */
(function (root) {
  'use strict';
  const states = ['idle', 'working', 'waiting', 'disconnected', 'error'];
  const labels = {idle:'空闲',working:'工作中',waiting:'等待额度',disconnected:'连接断开',error:'发生错误'};
  const palettes = {
    light: {blue:'#2168D5',glass:'#EAF3FF',gray:'#8795A8',gold:'#F5B82E',core:'#FFF2C9',swirl:'#74A0D9',muted:'#758598',badge:'#F5F7FA',red:'#CD5058'},
    dark: {blue:'#5386BF',glass:'#20344C',gray:'#7F8C9C',gold:'#F2BA42',core:'#FFE6A8',swirl:'#537A9F',muted:'#637285',badge:'#1C2939',red:'#D67A80'}
  };
  let serial = 0;
  const esc = value => String(value).replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const vars = p => Object.entries(p).map(([k,v])=>`--qj-${k}:${v}`).join(';');

  function renderSVG(options = {}) {
    const state = states.includes(options.state) ? options.state : 'idle';
    const theme = ['light','dark','auto'].includes(options.theme) ? options.theme : 'auto';
    const animated = options.animated !== false;
    const size = Math.min(2048, Math.max(16, Number(options.size) || 256));
    // Always generate a fresh namespace; multiple inline SVGs cannot share clip IDs.
    const id = `qj-${++serial}`;
    const label = options.label == null ? `TOKEN榨汁机 · ${labels[state]}` : options.label;
    const decorative = options.decorative === true;
    const rootA11y = decorative ? 'aria-hidden="true"' : `role="img" aria-labelledby="${id}-title"`;
    const p = palettes[theme === 'dark' ? 'dark' : 'light'];
    const css = `.qj{${vars(p)};display:block;overflow:visible}
      ${theme === 'auto' ? `@media(prefers-color-scheme:dark){.qj{${vars(palettes.dark)}}}` : ''}
      .qj .blue{fill:var(--qj-blue)}.qj .glass{fill:var(--qj-glass)}
      .qj .handle{stroke:var(--qj-blue)}.qj .bolt{fill:var(--qj-gray)}
      .qj[data-state="working"] .bolt{fill:var(--qj-gold)}
      .qj[data-state="disconnected"],.qj[data-state="idle"]{--qj-blue:var(--qj-muted)}

      .qj .pause-mark{stroke:var(--qj-gold)}
      .qj .disconnect-mark{stroke:var(--qj-gray)}.qj .error-mark{fill:var(--qj-red)}

    `;
    const symbol = {
      waiting: '<path class="pause-mark" d="M115 94V135M139 94V135" stroke-width="10" stroke-linecap="round"/>',
      disconnected: '<path class="disconnect-mark" d="M119 98L115 94C110 89 102 91 100 98C99 102 100 106 104 109L113 118M136 111L145 120C150 125 150 132 145 136C140 140 134 138 130 134L126 130M111 135L143 94" fill="none" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/>',
      error: '<path class="error-mark" d="M122 89H134L132 122H124Z"/><circle class="error-mark" cx="128" cy="135" r="6"/>'
    }[state] || '<path class="bolt" d="M129 91H151L133 116H153L113 153L124 126H104Z"/>';
    return `<svg xmlns="http://www.w3.org/2000/svg" id="${id}" class="qj" data-state="${state}" data-animated="${animated}" data-reduced="${options.reducedMotion === true}" width="${size}" height="${size}" viewBox="0 0 256 256" focusable="false" ${rootA11y}>
      ${decorative ? '' : `<title id="${id}-title">${esc(label)}</title>`}
      <style>${css.replace(/\.qj(?=[\s.\[{])/g, '#'+id)}</style>


      <g data-layer="handle"><path class="handle" d="M180 78H199Q229 78 226 110L223 128Q220 156 176 153" fill="none" stroke-width="15" stroke-linejoin="round"/></g>
      <g data-layer="cup"><path class="blue" d="M62 63H193L181 158Q179 177 160 177H94Q75 177 73 158Z"/><path class="glass" d="M78 76H177L166 155Q165 163 155 163H99Q89 163 88 155Z"/></g>
      <g data-layer="lid"><rect class="blue" x="57" y="48" width="142" height="22" rx="11"/></g>
      <g data-layer="top-knob"><rect class="blue" x="110" y="29" width="35" height="14" rx="6"/><g class="motion knob-rotor"><circle class="glass" cx="127" cy="36" r="5"/><path class="blue" d="M127 32V36" stroke="var(--qj-blue)" stroke-width="2.5" stroke-linecap="round"/></g></g>
      <g data-layer="base"><path class="blue" d="M88 182H166Q183 182 187 199L190 212Q192 222 180 222H74Q62 222 64 212L67 199Q71 182 88 182Z"/></g>
      <g data-layer="control"><circle class="glass" cx="127" cy="202" r="10"/><path d="M127 196V201" stroke="var(--qj-blue)" stroke-width="3" stroke-linecap="round"/></g>
      <g data-layer="status-symbol" class="motion symbol-motion">${symbol}</g>



    </svg>`.replace(/[ \t]+$/gm,'');
  }

  const api = {renderSVG:options=>renderSVG({...options,static:true}), states, palettes, version:'1.3.0'};
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  root.QuotaJuicerArtwork = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);

/* TokenMax motion 1.3.0. Canonical geometry and deterministic cosmetic RNG. */
(function (root) {
  'use strict';
  const base = typeof module !== 'undefined' && module.exports
    ? require('./juicer-artwork.js') : root.QuotaJuicerArtwork;
  const stroke = (points, parent = null) => ({points, parent});

  // Macro paths turn and fold before fine electrical fractures are added.
  // Branches may themselves branch. No shape is a rotation of another.
  const scenes = [
    {id:1, name:'短枝碎闪', gain:.83, strokes:[
      stroke([[112,121],[102,117],[104,108],[94,111],[89,104]]),
      stroke([[102,117],[98,125],[88,122],[85,132]],0),
      stroke([[104,108],[109,100],[100,95]],0),
      stroke([[88,122],[80,119],[76,125]],1),
      stroke([[94,111],[87,114],[83,108]],0)
    ]},
    {id:2, name:'折返分叉', gain:.95, strokes:[
      stroke([[147,121],[159,117],[165,127],[158,134],[170,141],[176,132],[174,148],[183,151]]),
      stroke([[165,127],[174,121],[171,111],[183,108]],0),
      stroke([[158,134],[150,140],[155,151],[145,157]],0),
      stroke([[176,132],[184,137],[191,130]],0),
      stroke([[171,111],[164,106],[169,99]],1)
    ]},
    {id:3, name:'长短错落', gain:.9, strokes:[
      stroke([[140,102],[150,97],[156,103],[153,89],[166,85],[164,75],[178,79],[185,71]]),
      stroke([[153,89],[143,84],[150,77]],0),
      stroke([[166,85],[176,93],[183,87]],0),
      stroke([[110,123],[102,128],[95,123],[89,129]]),
      stroke([[102,128],[105,136],[98,140]],3)
    ]},
    {id:4, name:'内核裂纹', gain:.69, strokes:[
      stroke([[122,104],[114,99],[117,90],[108,85]]),
      stroke([[114,99],[105,103],[100,96]],0),
      stroke([[146,121],[158,125],[162,117],[170,121]]),
      stroke([[158,125],[163,135],[156,141]],2),
      stroke([[120,143],[115,151],[123,159],[131,153]]),
      stroke([[115,151],[105,148],[102,156]],4),
      stroke([[163,135],[173,138],[178,131]],3),
      stroke([[117,90],[124,85],[119,79]],0)
    ]},
    {id:5, name:'侧向游走', gain:.85, strokes:[
      stroke([[116,113],[106,108],[109,98],[99,94],[102,84],[88,89],[85,101],[76,96],[69,106]]),
      stroke([[99,94],[92,103],[97,114],[87,119],[82,111]],0),
      stroke([[88,89],[83,80],[74,83],[70,75]],0),
      stroke([[76,96],[70,90],[61,95]],0),
      stroke([[97,114],[105,123],[98,131]],1),
      stroke([[92,103],[83,102],[80,96]],1)
    ]},
    {id:6, name:'下探裂枝', gain:.94, strokes:[
      stroke([[120,142],[114,150],[122,157],[111,164],[119,173],[106,177]]),
      stroke([[111,164],[100,158],[96,169],[85,166],[79,175]],0),
      stroke([[122,157],[132,160],[138,151],[150,160],[146,169]],0),
      stroke([[100,158],[94,151],[86,155]],1),
      stroke([[132,160],[129,171],[137,179]],2),
      stroke([[119,173],[123,180]],0)
    ]},
    {id:7, name:'弯折越壁', gain:1, strokes:[
      stroke([[148,119],[160,114],[170,121],[177,112],[173,101],[185,97],[182,85],[195,88],[202,99],[212,94]]),
      stroke([[177,112],[189,117],[194,109],[204,117]],0),
      stroke([[170,121],[170,134],[181,139],[175,149]],0),
      stroke([[185,97],[193,102],[187,109]],0),
      stroke([[195,88],[199,79],[209,83]],0),
      stroke([[181,139],[191,136],[195,145]],2)
    ]},
    {id:8, name:'一长两短', gain:.88, strokes:[
      stroke([[120,139],[110,145],[103,137],[96,147],[99,158],[86,153],[80,164],[70,159],[66,168]]),
      stroke([[96,147],[86,142],[82,150]],0),
      stroke([[99,158],[106,165],[98,171]],0),
      stroke([[141,104],[153,108],[159,99],[167,103]]),
      stroke([[153,108],[157,116]],3),
      stroke([[111,122],[104,116],[96,121]]),
      stroke([[80,164],[82,173],[74,179]],0)
    ]},
    {id:9, name:'偏侧树冠', gain:.86, strokes:[
      stroke([[125,103],[128,91],[116,86],[122,78],[109,74],[114,65]]),
      stroke([[116,86],[104,91],[101,80],[89,79],[83,86]],0),
      stroke([[104,91],[99,102],[89,97],[83,107]],1),
      stroke([[109,74],[99,68],[94,75]],0),
      stroke([[101,80],[109,78]],1),
      stroke([[89,97],[77,97],[73,89]],2),
      stroke([[147,120],[157,115],[164,124],[159,132]]),
      stroke([[157,115],[159,107]],6)
    ]},
    {id:10, name:'散簇微爆', gain:.74, strokes:[
      stroke([[146,122],[154,132],[165,128],[169,140]]),
      stroke([[154,132],[151,141],[161,147]],0),
      stroke([[165,128],[171,120],[179,124]],0),
      stroke([[121,107],[111,106],[108,96]]),
      stroke([[111,106],[105,114],[97,111]],3),
      stroke([[119,145],[111,154],[101,151]]),
      stroke([[111,154],[113,164]],5)
    ]}
  ];

  function random(seed) {
    let value = seed >>> 0;
    return () => {
      value += 0x6D2B79F5;
      let mixed = Math.imul(value ^ value >>> 15, 1 | value);
      mixed ^= mixed + Math.imul(mixed ^ mixed >>> 7, 61 | mixed);
      return ((mixed ^ mixed >>> 14) >>> 0) / 4294967296;
    };
  }
  const round = value => Math.round(value * 100) / 100;
  const key = point => point.join(',');
  const distance = (a,b) => Math.hypot(a[0]-b[0], a[1]-b[1]);
  const line = points => points.map((point,i) => `${i ? 'L' : 'M'}${point.join(' ')}`).join('');

  function instantiate(scene, seed) {
    const rng = random(seed), lengthScale = .76 + rng() * .33;
    const transformed = new Map();
    const paths = [];
    scene.strokes.forEach((item,index) => {
      const parent = item.parent;
      const tree = parent === null ? index : paths[parent].tree;
      const origin = scene.strokes[tree].points[0];
      transformed.set(`${tree}:${key(origin)}`, [...origin]);
      const points = item.points.map((point,i) => {
        if (parent === null && i === 0) return [...origin];
        const cacheKey = `${tree}:${key(point)}`;
        if (!transformed.has(cacheKey)) transformed.set(cacheKey, [
          round(Math.max(55, Math.min(216, origin[0] + (point[0]-origin[0])*lengthScale + (rng()-.5)*2.2))),
          round(Math.max(60, Math.min(181, origin[1] + (point[1]-origin[1])*lengthScale + (rng()-.5)*2.2)))
        ]);
        return transformed.get(cacheKey);
      });
      // Fine fractures follow a deliberately bent macro path, not a radial ray.
      const detailed = [points[0]];
      for (let i=1;i<points.length;i++) {
        const a=points[i-1], b=points[i], span=distance(a,b);
        const bend=(rng()-.5)*Math.min(3.3,span*.28);
        detailed.push([round((a[0]+b[0])/2-(b[1]-a[1])/span*bend),
                       round((a[1]+b[1])/2+(b[0]-a[0])/span*bend)], b);
      }
      paths.push({tree,parent,points,d:line(detailed),level:parent===null?0:paths[parent].level+1,
                  gain:round(.9+rng()*.1)});
    });
    return {id:scene.id,name:scene.name,gain:scene.gain,lengthScale,paths};
  }

  function buildSequence(seed=20261029, sceneId=null) {
    const rng=random(seed), order=sceneId===null ? scenes.map(scene=>scene.id) : [sceneId];
    for(let i=order.length-1;i>0;i--){const j=Math.floor(rng()*(i+1));[order[i],order[j]]=[order[j],order[i]];}
    let time=.17;
    const events=order.map(id=>{
      const scene=scenes.find(item=>item.id===id);
      if(!scene)throw Error('Unknown discharge scene');
      const duration=round(.29+rng()*.3), rise=round(.045+rng()*.055);
      const event={...instantiate(scene,Math.floor(rng()*4294967296)),start:round(time),duration,rise,
                   gain:round(scene.gain*(.88+rng()*.14))};
      time+=duration+.29+rng()*.65;
      return event;
    });
    // Export loops end on a full two-second breathing cycle as well.
    return {seed,events,cycleSeconds:sceneId===null?Math.ceil((time+.24)/2)*2:2};
  }

  function keyframes(name, stops, cycle) {
    const frames=stops.map(([time,value])=>`${round(time/cycle*100)}%{${value}}`).join('');
    return `@keyframes ${name}{${frames}}`;
  }

  function renderSVG(options={}) {
    let svg=base.renderSVG(options);
    svg=svg.replace(/<g data-layer="(?:energy-back|energy-front|branch-left|branch-top|branch-base)"[\s\S]*?<\/g>/g,'');
    if(options.state!=='working')return svg;
    const id=svg.match(/<svg[^>]+id="([^"]+)"/)[1], selector='#'+id;
    const sequence=buildSequence(options.seed,options.sceneId??null), cycle=sequence.cycleSeconds;
    const staticOnly=options.static===true;
    const events=staticOnly?[sequence.events[0]]:sequence.events;
    const hot=options.theme==='light'?'#FFF8E7':'#FFF5DD';
    let css=`
      ${selector} .symbol-motion,${selector} .knob-rotor{animation:none!important;transform:none!important}
      ${selector} .discharge-event{opacity:0}
      ${selector} .electric-path{fill:none;stroke-linecap:round;stroke-linejoin:round}
      ${selector} .electric-soft{stroke:var(--qj-gold);stroke-width:6.5;opacity:.17;filter:url(#${id}-arc-soft)}
      ${selector} .electric-edge{stroke:var(--qj-gold);stroke-width:2.4;opacity:.98}
      ${selector} .electric-hot{stroke:${hot};stroke-width:1.3;opacity:1}
      ${selector} .twig .electric-edge{stroke-width:1.6}${selector} .twig .electric-hot{stroke-width:.86}
      ${selector} .small-twig .electric-edge{stroke-width:1.2}${selector} .small-twig .electric-hot{stroke-width:.62}
      ${selector} .source-light{fill:url(#${id}-source-light);opacity:.38}
      ${selector} .bolt{filter:url(#${id}-bolt-light);opacity:1}
    `;
    const markup=events.map((event,index)=>{
      const burstName=`${id}-burst-${index}`, start=event.start, end=start+event.duration;
      if(staticOnly)css+=`${selector} .event-${index}{opacity:${event.gain}}`;
      else {
        css+=keyframes(burstName,[[0,'opacity:0'],[start,'opacity:0'],
          [start+event.rise*.48,`opacity:${round(event.gain*.7)}`],
          [start+event.rise,`opacity:${event.gain}`],
          [start+event.duration*.36,`opacity:${round(event.gain*.9)}`],
          [start+event.duration*.7,`opacity:${round(event.gain*.24)}`],
          [end,'opacity:0'],[cycle,'opacity:0']],cycle);
        css+=`${selector} .event-${index}{animation:${burstName} ${cycle}s linear infinite}`;
      }
      const paths=event.paths.map((item,pathIndex)=>{
        const onset=start+item.level*.014, growName=`${id}-grow-${index}-${pathIndex}`;
        if(!staticOnly){
          css+=keyframes(growName,[[0,'stroke-dashoffset:100'],[onset,'stroke-dashoffset:100'],
            [onset+event.rise*.85+item.level*.004,'stroke-dashoffset:0'],[cycle,'stroke-dashoffset:0']],cycle);
          css+=`${selector} .stroke-${index}-${pathIndex}{stroke-dasharray:100;animation:${growName} ${cycle}s linear infinite}`;
        }
        const layers=['soft','edge','hot'].map(layer=>`<path class="discharge-motion electric-path electric-${layer} stroke-${index}-${pathIndex}" pathLength="100" d="${item.d}"/>`).join('');
        return `<g class="${item.level===0?'trunk':item.level===1?'twig':'small-twig'}" data-parent="${item.parent??''}" data-points="${item.points.map(key).join(';')}" style="opacity:${round(item.gain*(item.level>1?.82:1))}">${layers}</g>`;
      }).join('');
      const roots=event.paths.filter(item=>item.parent===null).map(item=>
        `<ellipse class="source-light" cx="${item.points[0][0]}" cy="${item.points[0][1]}" rx="23" ry="24"/>`).join('');
      return `<g data-layer="discharge-${event.id}" data-scene-id="${event.id}" class="discharge-motion discharge-event event-${index}">${roots}${paths}</g>`;
    }).join('');
    if(!staticOnly){
      css+=`@keyframes ${id}-bolt-breathe{0%,100%{opacity:.58}50%{opacity:1}}
        ${selector} .bolt-breathe{animation:${id}-bolt-breathe 2s ease-in-out infinite}
        ${selector}[data-animated="false"] .discharge-motion{animation-play-state:paused!important}
        ${selector}[data-reduced="true"] .discharge-motion{animation:none!important}
        ${selector}[data-reduced="true"] .discharge-event{opacity:0}
        @media(prefers-reduced-motion:reduce){${selector} .discharge-motion{animation:none!important}${selector} .discharge-event{opacity:0}}
      `;
    }
    const defs=`<defs>
      <radialGradient id="${id}-source-light"><stop stop-color="${hot}" stop-opacity=".64"/><stop offset=".42" stop-color="var(--qj-gold)" stop-opacity=".2"/><stop offset="1" stop-color="var(--qj-gold)" stop-opacity="0"/></radialGradient>
      <filter id="${id}-arc-soft" x="-80%" y="-80%" width="260%" height="260%"><feGaussianBlur stdDeviation="1.1"/></filter>
      <filter id="${id}-bolt-light" x="-50%" y="-40%" width="200%" height="180%"><feDropShadow dx="0" dy="0" stdDeviation="1.7" flood-color="var(--qj-gold)" flood-opacity=".23"/></filter>
    </defs>`;
    svg=svg.replace('</style>','</style>'+defs+'<style>'+css+'</style>');
    svg=svg.replace('<g data-layer="status-symbol"',markup+'<g data-layer="status-symbol"');
    svg=svg.replace('class="bolt"','class="bolt discharge-motion bolt-breathe"');
    return svg.replace('class="qj"',`class="qj" data-cycle="${cycle}" data-seed="${sequence.seed}"`);
  }

  const api={renderSVG,buildSequence,instantiate,scenes,version:'1.3.0',breathSeconds:2};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
  root.QuotaJuicerMotion=api;
})(typeof globalThis!=='undefined'?globalThis:this);


(function(root){
 'use strict';
 const api=Object.assign({},root.QuotaJuicerMotion,{states:root.QuotaJuicerArtwork.states,palettes:root.QuotaJuicerArtwork.palettes});
 root.QuotaJuicer=api;if(typeof module!=='undefined'&&module.exports)module.exports=api;
 if(typeof HTMLElement==='undefined'||!root.customElements||customElements.get('quota-juicer'))return;
 class QuotaJuicerElement extends HTMLElement {
  static get observedAttributes(){return ['state','theme','size','animated','reduced-motion','label','decorative'];}
  constructor(){super();this.attachShadow({mode:'open'});this.seed=Math.floor(Math.random()*4294967296);this.breathTime=0;}
  connectedCallback(){this.render();this.tick();}
  disconnectedCallback(){cancelAnimationFrame(this.frame);}
  attributeChangedCallback(name){const svg=this.shadowRoot.querySelector('svg');if(svg&&name==='animated'){svg.dataset.animated=String(this.animated);return;}if(svg&&name==='reduced-motion'){svg.dataset.reduced=String(this.getAttribute(name)==='true');return;}if(this.isConnected)this.render();}
  get state(){return this.getAttribute('state')||'idle';}set state(v){this.setAttribute('state',v);}
  get theme(){return this.getAttribute('theme')||'auto';}set theme(v){this.setAttribute('theme',v);}
  get animated(){return this.getAttribute('animated')!=='false';}set animated(v){this.setAttribute('animated',String(Boolean(v)));}
  tick(){if(!this.isConnected)return;const svg=this.shadowRoot.querySelector('svg');const clock=svg?.querySelector('.discharge-event')?.getAnimations()[0];if(clock&&clock.playState==='running'&&Number(clock.currentTime)>=Number(svg.dataset.cycle)*1000){this.seed=Math.floor(Math.random()*4294967296);this.render();}this.frame=requestAnimationFrame(()=>this.tick());}
  render(){const previous=this.shadowRoot.querySelector('.bolt-breathe')?.getAnimations()[0]?.currentTime;if(previous!=null)this.breathTime=Number(previous);this.shadowRoot.innerHTML='<style>:host{display:inline-block;line-height:0;vertical-align:middle}svg{max-width:100%;height:auto}</style>'+api.renderSVG({state:this.state,theme:this.theme,size:this.getAttribute('size'),animated:this.animated,reducedMotion:this.getAttribute('reduced-motion')==='true',decorative:this.getAttribute('decorative')==='true',label:this.getAttribute('label')??undefined,seed:this.seed});const next=this.shadowRoot.querySelector('.bolt-breathe')?.getAnimations()[0];if(next)next.currentTime=this.breathTime;}
 }
 customElements.define('quota-juicer',QuotaJuicerElement);
})(typeof globalThis!=='undefined'?globalThis:this);
