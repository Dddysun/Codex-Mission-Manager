/* TokenMax brand motion proposal 1 — reuses the current vector artwork. */
(function (root) {
  'use strict';
  const base = typeof module !== 'undefined' && module.exports
    ? require('../../quota-juicer.js') : root.QuotaJuicer;

  // Each trunk starts inside the existing bolt. Every branch begins at an
  // actual trunk vertex. The paths never connect around the cup perimeter.
  const channels = [
    { name: 'upper-left', delay: 0, points: [[124,109],[116,105],[109,107],[103,96],[96,99],[90,88],[82,91],[76,81],[69,83],[60,74]],
      branches: [[[103,96],[105,88],[100,82]], [[82,91],[80,100],[72,97]]] },
    { name: 'lower-right', delay: 0, points: [[139,126],[146,132],[153,130],[156,141],[163,140],[166,150],[175,151],[178,162],[187,161],[194,170]],
      branches: [[[156,141],[163,134],[170,138]], [[178,162],[172,169],[178,176]]] },
    { name: 'upper-right', delay: 1.26, points: [[140,103],[148,99],[152,102],[158,91],[165,95],[172,84],[180,87],[187,76],[194,79],[201,70]],
      branches: [[[158,91],[157,83],[165,77]], [[180,87],[184,96],[193,92]]] },
    { name: 'lower-left', delay: 1.26, points: [[122,137],[114,140],[111,136],[106,147],[99,145],[96,155],[88,154],[84,165],[76,162],[68,170]],
      branches: [[[106,147],[103,138],[96,136]], [[88,154],[85,147],[78,150]]] },
    { name: 'right-short', delay: 2.38, points: [[145,119],[154,115],[159,119],[165,112],[173,116],[179,109],[187,113]],
      branches: [[[165,112],[166,104],[172,101]]] },
    { name: 'left-short', delay: 2.38, points: [[119,121],[112,117],[108,121],[101,115],[96,119],[90,114],[83,119]],
      branches: [[[101,115],[100,108],[94,105]]] }
  ];
  const pathData = points => points.map((point, index) => `${index ? 'L' : 'M'}${point.join(' ')}`).join('');

  function renderSVG(options = {}) {
    let svg = base.renderSVG(options);
    const id = svg.match(/<svg[^>]+id="([^"]+)"/)[1];
    const selector = '#' + id;
    // Keep the cup, handle, lid, base and state symbols exactly as version 1.2.
    svg = svg.replace(/<g data-layer="(?:energy-back|energy-front|branch-left|branch-top|branch-base)"[\s\S]*?<\/g>/g, '');
    if (options.state !== 'working') return svg;

    const staticOnly = options.static === true;
    const dark = options.theme === 'dark';
    const hot = dark ? '#FFF5DD' : '#FFF9E9';
    const glow = dark ? '#F4B747' : '#ECAE29';
    const cycle = 3.6;
    const css = `
      ${selector} .knob-rotor,${selector} .symbol-motion{animation:none!important;transform:none!important}
      ${selector} .core-bloom{fill:url(#${id}-source-light);opacity:.2}
      ${selector} .discharge{opacity:0}
      ${selector} .discharge path{fill:none;stroke-linecap:round;stroke-linejoin:round}
      ${selector} .electric-soft{stroke:${glow};stroke-width:7;opacity:.13;filter:url(#${id}-electric-soft)}
      ${selector} .electric-edge{stroke:var(--qj-gold);stroke-width:2.25;opacity:.96}
      ${selector} .electric-hot{stroke:${hot};stroke-width:.8;opacity:.98}
      ${selector} .twig{stroke-width:1.05;opacity:.76}
      ${selector} .twig-hot{stroke-width:.38;opacity:.9}
      ${selector} .bolt{filter:url(#${id}-bolt-soft)}
      ${staticOnly ? `${selector} .discharge.major-static{opacity:.86}` : `
      ${selector} .discharge{animation:tm-discharge ${cycle}s linear infinite;animation-delay:var(--fire-delay)}
      ${selector} .trunk{stroke-dasharray:100;animation:tm-grow ${cycle}s linear infinite;animation-delay:var(--fire-delay)}
      ${selector} .twig,${selector} .twig-hot{stroke-dasharray:100;animation:tm-twig ${cycle}s linear infinite;animation-delay:var(--fire-delay)}
      ${selector} .core-bloom{animation:tm-source ${cycle}s ease-in-out infinite}
      ${selector} .bolt{animation:tm-bolt ${cycle}s ease-in-out infinite}
      ${selector}[data-animated="false"] .discharge-motion{animation-play-state:paused!important}
      ${selector}[data-reduced="true"] .discharge-motion{animation:none!important}
      ${selector}[data-reduced="true"] .discharge{opacity:0}
      ${selector}[data-reduced="true"] .core-bloom{opacity:.14}
      @media(prefers-reduced-motion:reduce){
        ${selector} .discharge-motion{animation:none!important}
        ${selector} .discharge{opacity:0}
        ${selector} .core-bloom{opacity:.14}
      }
      @keyframes tm-discharge{0%,8%{opacity:0}9%{opacity:.55}11%,16%{opacity:1}20%{opacity:.62}26%{opacity:.18}32%,100%{opacity:0}}
      @keyframes tm-grow{0%,8%{stroke-dashoffset:100}11%,100%{stroke-dashoffset:0}}
      @keyframes tm-twig{0%,11%{stroke-dashoffset:100}17%,100%{stroke-dashoffset:0}}
      @keyframes tm-source{0%,8%{opacity:.12}11%,16%{opacity:.5}32%{opacity:.12}46%,51%{opacity:.45}67%{opacity:.13}77%,82%{opacity:.34}95%,100%{opacity:.12}}
      @keyframes tm-bolt{0%,8%{opacity:.88}11%,17%{opacity:1}32%{opacity:.91}46%,52%{opacity:1}67%{opacity:.9}77%,83%{opacity:1}100%{opacity:.88}}`}
    `;
    const defs = `<defs>
      <radialGradient id="${id}-source-light"><stop stop-color="${hot}" stop-opacity=".8"/><stop offset=".36" stop-color="${glow}" stop-opacity=".25"/><stop offset="1" stop-color="${glow}" stop-opacity="0"/></radialGradient>
      <filter id="${id}-electric-soft" x="-80%" y="-80%" width="260%" height="260%"><feGaussianBlur stdDeviation="1.25"/></filter>
      <filter id="${id}-bolt-soft" x="-50%" y="-40%" width="200%" height="180%"><feDropShadow dx="0" dy="0" stdDeviation="2.1" flood-color="${glow}" flood-opacity=".25"/></filter>
    </defs>`;
    const energy = channels.map((channel, index) => {
      const path = pathData(channel.points);
      const trunk = ['soft','edge','hot'].map(layer => `<path class="discharge-motion trunk electric-${layer}" pathLength="100" d="${path}"/>`).join('');
      const twigs = channel.branches.map(points => ['edge','hot'].map(layer => `<path class="discharge-motion ${layer === 'hot' ? 'twig-hot' : 'twig'} electric-${layer}" pathLength="100" d="${pathData(points)}"/>`).join('')).join('');
      return `<g data-layer="discharge-${channel.name}" data-origin="${channel.points[0]}" class="discharge-motion discharge ${index < 2 ? 'major-static' : ''}" style="--fire-delay:${channel.delay}s">${trunk}${twigs}</g>`;
    }).join('');
    const source = `<g data-layer="core-source"><ellipse class="discharge-motion core-bloom" cx="130" cy="122" rx="49" ry="52"/></g>`;
    svg = svg.replace('</style>', '</style>' + defs + '<style>' + css + '</style>');
    // Electricity is in front of the glass but behind the solid bolt, so the
    // roots appear to emerge from its edges instead of floating beside it.
    svg = svg.replace('<g data-layer="status-symbol"', source + energy + '<g data-layer="status-symbol"');
    svg = svg.replace('class="bolt"', 'class="bolt discharge-motion"');
    return svg;
  }

  const api = {renderSVG, channels, version:'1.3.0-proposal.1', cycleSeconds:3.6};
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  root.TokenMaxDischargePreview = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
