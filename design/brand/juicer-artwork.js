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
