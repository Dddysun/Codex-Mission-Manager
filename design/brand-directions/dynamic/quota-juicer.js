/* Quota Juicer identity v1.0.0 — framework-free, no network or application logic. */
(function (root) {
  'use strict';
  const states = ['idle', 'working', 'waiting', 'disconnected', 'error'];
  const labels = {idle:'空闲',working:'工作中',waiting:'等待额度',disconnected:'连接断开',error:'发生错误'};
  const palettes = {
    light: {blue:'#2168D5',glass:'#EAF3FF',gray:'#8795A8',gold:'#E7AA16',swirl:'#74A0D9',muted:'#758598',badge:'#F5F7FA',red:'#CD5058'},
    dark: {blue:'#4878AF',glass:'#172638',gray:'#7F8C9C',gold:'#E7B43C',swirl:'#537A9F',muted:'#637285',badge:'#1C2939',red:'#D67A80'}
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
    const label = options.label == null ? `额度榨汁机 · ${labels[state]}` : options.label;
    const decorative = options.decorative === true;
    const rootA11y = decorative ? 'aria-hidden="true"' : `role="img" aria-labelledby="${id}-title"`;
    const p = palettes[theme === 'dark' ? 'dark' : 'light'];
    const css = `.qj{${vars(p)};display:block;overflow:visible}
      ${theme === 'auto' ? `@media(prefers-color-scheme:dark){.qj{${vars(palettes.dark)}}}` : ''}
      .qj .blue{fill:var(--qj-blue)}.qj .glass{fill:var(--qj-glass)}
      .qj .handle{stroke:var(--qj-blue)}.qj .bolt{fill:var(--qj-gray)}
      .qj[data-state="working"] .bolt{fill:var(--qj-gold)}
      .qj[data-state="disconnected"]{--qj-blue:var(--qj-muted)}
      .qj .swirl{stroke:var(--qj-swirl)}.qj .arcs{stroke:var(--qj-gold);opacity:.65}
      .qj .badge-bg{fill:var(--qj-badge)}.qj .pause-mark{stroke:var(--qj-gold)}
      .qj .disconnect-mark{stroke:var(--qj-gray)}.qj .error-mark{fill:var(--qj-red)}
      ${staticOnly ? '' : `
      .qj[data-state="working"] .vortex-rotor{transform-origin:127px 121px;animation:qj-swirl 2.4s linear infinite}
      .qj[data-state="working"] .knob-rotor{transform-origin:127px 36px;animation:qj-turn 3.2s linear infinite}
      .qj[data-state="working"] .arcs{animation:qj-arc 2.8s ease-in-out infinite}
      .qj[data-animated="false"] .motion{animation-play-state:paused!important}
      .qj[data-reduced="true"] .motion{animation:none!important}
      @media(prefers-reduced-motion:reduce){.qj .motion{animation:none!important}}
      @keyframes qj-swirl{to{transform:rotate(360deg)}}
      @keyframes qj-turn{to{transform:rotate(360deg)}}
      @keyframes qj-arc{0%,100%{opacity:.35}50%{opacity:.8}}`}`;
    const badge = {
      waiting: '<path class="pause-mark" d="M199 196V208M208 196V208" stroke-width="4" stroke-linecap="round"/>',
      disconnected: '<path class="disconnect-mark" d="M194 207L201 200M206 199L213 192M198 192L210 208" fill="none" stroke-width="3.5" stroke-linecap="round"/>',
      error: '<path class="error-mark" d="M201 192H205V203H201ZM201 207H205V211H201Z"/>'
    }[state];
    return `<svg xmlns="http://www.w3.org/2000/svg" id="${id}" class="qj" data-state="${state}" data-animated="${animated}" data-reduced="${options.reducedMotion === true}" width="${size}" height="${size}" viewBox="0 0 256 256" focusable="false" ${rootA11y}>
      ${decorative ? '' : `<title id="${id}-title">${esc(label)}</title>`}
      <style>${css.replace(/\.qj(?=[\s.\[{])/g, '#'+id)}</style>
      <defs><clipPath id="${id}-cup"><path d="M78 76H177L166 155Q165 163 155 163H99Q89 163 88 155Z"/></clipPath></defs>
      <g data-layer="handle"><path class="handle" d="M180 78H199Q229 78 226 110L223 128Q220 156 176 153" fill="none" stroke-width="15" stroke-linejoin="round"/></g>
      <g data-layer="cup"><path class="blue" d="M62 63H193L181 158Q179 177 160 177H94Q75 177 73 158Z"/><path class="glass" d="M78 76H177L166 155Q165 163 155 163H99Q89 163 88 155Z"/></g>
      <g data-layer="vortex" clip-path="url(#${id}-cup)">
        ${state === 'working' ? '<g class="motion vortex-rotor" opacity=".55"><path class="swirl" d="M103 121C103 94 151 94 151 121C151 138 119 145 112 130M151 121C151 149 103 148 103 121C103 104 135 98 142 113" fill="none" stroke-width="4.5" stroke-linecap="round"/><circle cx="127" cy="121" r="37" fill="none" class="swirl" stroke-width="2" stroke-dasharray="48 68" opacity=".5"/></g>' : '<path class="swirl" d="M99 147Q125 158 153 145" fill="none" stroke-width="4" stroke-linecap="round" opacity=".4"/>'}
      </g>
      <g data-layer="lid"><rect class="blue" x="57" y="48" width="142" height="22" rx="11"/></g>
      <g data-layer="top-knob"><rect class="blue" x="110" y="29" width="35" height="14" rx="6"/><g class="motion knob-rotor"><circle class="glass" cx="127" cy="36" r="5"/><path class="blue" d="M127 32V36" stroke="var(--qj-blue)" stroke-width="2.5" stroke-linecap="round"/></g></g>
      <g data-layer="base"><path class="blue" d="M88 182H166Q183 182 187 199L190 212Q192 222 180 222H74Q62 222 64 212L67 199Q71 182 88 182Z"/></g>
      <g data-layer="control"><circle class="glass" cx="127" cy="202" r="10"/><path d="M127 196V201" stroke="var(--qj-blue)" stroke-width="3" stroke-linecap="round"/></g>
      <g data-layer="lightning"><path class="bolt" d="M129 83H151L133 108H153L113 145L124 118H104Z"/></g>
      <g data-layer="arcs" class="motion arcs" fill="none" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" ${state !== 'working' ? 'display="none"' : ''}><path d="M40 92L29 106H40L30 120"/><path d="M205 44L214 35"/><path d="M208 177L221 183"/></g>
      <g data-layer="status-badge">${badge ? `<circle class="badge-bg" cx="203" cy="202" r="20"/>${badge}` : ''}</g>
    </svg>`;
  }

  const api = {renderSVG, states, palettes, version:'1.0.0'};
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
