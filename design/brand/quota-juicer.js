/* Quota Juicer identity v1.2.0 — framework-free, no network or application logic. */
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
    const staticOnly = options.static === true;
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
      .qj .arcs{stroke:var(--qj-gold)}.qj .energy-trace{stroke-dasharray:62 18 14 36}.qj .energy-glow{opacity:.12}.qj .energy-halo{opacity:.28}.qj .energy-filament{opacity:.92}.qj .energy-core{stroke:var(--qj-core);opacity:.95}.qj .branches{opacity:.65}.qj .branches .energy-trace{stroke-dasharray:18 10 5 22}
      .qj .pause-mark{stroke:var(--qj-gold)}
      .qj .disconnect-mark{stroke:var(--qj-gray)}.qj .error-mark{fill:var(--qj-red)}
      ${staticOnly ? '' : `
      .qj[data-state="working"] .symbol-motion{transform-origin:128px 122px;animation:qj-breathe 2.4s ease-in-out infinite}
      .qj[data-state="working"] .knob-rotor{transform-origin:127px 36px;animation:qj-turn 3.2s linear infinite}
      .qj[data-state="working"] .energy-trace{animation:qj-orbit 1.8s linear infinite}
      .qj[data-animated="false"] .motion{animation-play-state:paused!important}
      .qj[data-reduced="true"] .motion{animation:none!important}
      @media(prefers-reduced-motion:reduce){.qj .motion{animation:none!important}}
      @keyframes qj-breathe{0%,100%{opacity:.78;transform:scale(.985)}50%{opacity:1;transform:scale(1.015)}}
      @keyframes qj-turn{to{transform:rotate(360deg)}}
      @keyframes qj-orbit{to{stroke-dashoffset:-130}}`}`;
    const symbol = {
      waiting: '<path class="pause-mark" d="M115 94V135M139 94V135" stroke-width="10" stroke-linecap="round"/>',
      disconnected: '<path class="disconnect-mark" d="M119 98L115 94C110 89 102 91 100 98C99 102 100 106 104 109L113 118M136 111L145 120C150 125 150 132 145 136C140 140 134 138 130 134L126 130M111 135L143 94" fill="none" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/>',
      error: '<path class="error-mark" d="M122 89H134L132 122H124Z"/><circle class="error-mark" cx="128" cy="135" r="6"/>'
    }[state] || '<path class="bolt" d="M129 91H151L133 116H153L113 153L124 126H104Z"/>';
    const arcBack = 'M74 214L57 197L61 184L43 169L49 154L33 137L42 123L35 103L51 89L46 73L64 61';
    const arcFront = 'M153 38L177 46L174 55L203 66L213 83L205 96L229 113L220 127L230 143L216 157L221 175L199 187L202 199L178 208L153 215L137 207L109 221L90 214';
    const energy = (layer, path, branch = false, offset = 0) => state === 'working' ? `<g data-layer="${layer}" class="arcs ${branch ? 'branches' : ''}" fill="none" stroke-linecap="round" stroke-linejoin="round">${[[9,'glow'],[4.5,'halo'],[2.4,'filament'],[.85,'core']].map(([width,kind])=>`<path class="motion energy-trace energy-${kind}" d="${path}" stroke-width="${width}" style="animation-delay:${-offset*1.8}s"/>`).join('')}</g>` : '';
    return `<svg xmlns="http://www.w3.org/2000/svg" id="${id}" class="qj" data-state="${state}" data-animated="${animated}" data-reduced="${options.reducedMotion === true}" width="${size}" height="${size}" viewBox="0 0 256 256" focusable="false" ${rootA11y}>
      ${decorative ? '' : `<title id="${id}-title">${esc(label)}</title>`}
      <style>${css.replace(/\.qj(?=[\s.\[{])/g, '#'+id)}</style>
      ${energy('energy-back', arcBack, false, .35)}
      ${energy('branch-left', 'M49 154L62 144L58 131', true, .35)}
      <g data-layer="handle"><path class="handle" d="M180 78H199Q229 78 226 110L223 128Q220 156 176 153" fill="none" stroke-width="15" stroke-linejoin="round"/></g>
      <g data-layer="cup"><path class="blue" d="M62 63H193L181 158Q179 177 160 177H94Q75 177 73 158Z"/><path class="glass" d="M78 76H177L166 155Q165 163 155 163H99Q89 163 88 155Z"/></g>
      <g data-layer="lid"><rect class="blue" x="57" y="48" width="142" height="22" rx="11"/></g>
      <g data-layer="top-knob"><rect class="blue" x="110" y="29" width="35" height="14" rx="6"/><g class="motion knob-rotor"><circle class="glass" cx="127" cy="36" r="5"/><path class="blue" d="M127 32V36" stroke="var(--qj-blue)" stroke-width="2.5" stroke-linecap="round"/></g></g>
      <g data-layer="base"><path class="blue" d="M88 182H166Q183 182 187 199L190 212Q192 222 180 222H74Q62 222 64 212L67 199Q71 182 88 182Z"/></g>
      <g data-layer="control"><circle class="glass" cx="127" cy="202" r="10"/><path d="M127 196V201" stroke="var(--qj-blue)" stroke-width="3" stroke-linecap="round"/></g>
      <g data-layer="status-symbol" class="motion symbol-motion">${symbol}</g>
      ${energy('energy-front', arcFront)}
      ${energy('branch-top', 'M213 83L232 78L237 59', true)}
      ${energy('branch-base', 'M199 187L215 199L226 195', true, .6)}
    </svg>`.replace(/[ \t]+$/gm,'');
  }

  const api = {renderSVG, states, palettes, version:'1.2.0'};
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  root.QuotaJuicer = api;
  if (typeof HTMLElement === 'undefined' || !root.customElements || root.customElements.get('quota-juicer')) return;
  class QuotaJuicerElement extends HTMLElement {
    static get observedAttributes() { return ['state','theme','size','animated','reduced-motion','label','decorative']; }
    constructor() {super();this.attachShadow({mode:'open'});}
    connectedCallback() {this.render();}
    attributeChangedCallback(name) {
      const svg = this.shadowRoot.querySelector('svg');
      if (svg && name === 'animated') {svg.dataset.animated = String(this.animated);return;}
      if (svg && name === 'reduced-motion') {svg.dataset.reduced = String(this.getAttribute('reduced-motion') === 'true');return;}
      if (this.isConnected) this.render();
    }
    get state() {return this.getAttribute('state') || 'idle';}
    set state(v) {this.setAttribute('state',v);}
    get theme() {return this.getAttribute('theme') || 'auto';}
    set theme(v) {this.setAttribute('theme',v);}
    get animated() {return this.getAttribute('animated') !== 'false';}
    set animated(v) {this.setAttribute('animated', String(Boolean(v)));}
    render() {
      this.shadowRoot.innerHTML = `<style>:host{display:inline-block;line-height:0;vertical-align:middle}svg{max-width:100%;height:auto}</style>` + renderSVG({state:this.state,theme:this.theme,size:this.getAttribute('size'),animated:this.animated,reducedMotion:this.getAttribute('reduced-motion') === 'true',decorative:this.getAttribute('decorative') === 'true',label:this.getAttribute('label') ?? undefined});
    }
  }
  root.customElements.define('quota-juicer',QuotaJuicerElement);
})(typeof globalThis !== 'undefined' ? globalThis : this);
