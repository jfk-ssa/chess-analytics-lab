'use strict';

// Small self-hosted SVG charts. Tables and the ranking controls remain the text equivalents.
window.PositionCharts = (() => {
  const NS = 'http://www.w3.org/2000/svg';
  const colors = ['#17664d', '#8a5425'];
  function element(tag, attributes = {}, text) {
    const node = document.createElementNS(NS, tag);
    Object.entries(attributes).forEach(([key, value]) => node.setAttribute(key, value));
    if (text !== undefined) node.textContent = text;
    return node;
  }
  function canvas(title, xTitle, yTitle) {
    const svg = element('svg', {viewBox: '0 0 660 310', class: 'position-chart', role: 'img', 'aria-label': title});
    svg.append(element('title', {}, title), element('path', {d: 'M65 25V255H630', fill: 'none', stroke: '#879a91'}));
    svg.append(element('text', {x: 345, y: 302, 'text-anchor': 'middle'}, xTitle));
    svg.append(element('text', {x: 8, y: 15}, yTitle));
    return svg;
  }
  function tick(svg, x, y, text, anchor = 'middle') {
    svg.append(element('text', {x, y, 'text-anchor': anchor, class: 'chart-tick'}, text));
  }
  function line(series, title, xTitle) {
    const svg = canvas(title, xTitle, 'Share');
    const points = series.flatMap(s => s.points);
    if (!points.length) return svg;
    const minX = Math.min(...points.map(p => p.x));
    const maxX = Math.max(...points.map(p => p.x));
    const maxY = Math.min(1, Math.max(0.1, Math.ceil(Math.max(...points.map(p => p.y)) * 10) / 10));
    const x = n => 65 + (n - minX) / Math.max(1, maxX - minX) * 565;
    const y = n => 255 - n / maxY * 230;
    for (let i = 0; i <= 4; i++) {
      const n = i * maxY / 4;
      svg.append(element('path', {d: `M65 ${y(n)}H630`, stroke: '#dce5df', fill: 'none'}));
      tick(svg, 55, y(n) + 4, `${(n * 100).toFixed(1).replace(/\.0$/, '')}%`, 'end');
    }
    [...new Set(points.map(p => p.x))].forEach(n => {
      if (points.length <= 16 || n === minX || n === maxX || n % 5 === 0) tick(svg, x(n), 275, n);
    });
    series.forEach((s, index) => {
      const color = colors[index % colors.length];
      svg.append(element('path', {d: s.points.map((p, i) => `${i ? 'L' : 'M'}${x(p.x)} ${y(p.y)}`).join(' '), fill: 'none', stroke: color, 'stroke-width': 3}));
      s.points.forEach(p => {
        const dot = element('circle', {cx: x(p.x), cy: y(p.y), r: 4, fill: color});
        dot.append(element('title', {}, `${s.name}: ${p.x}, ${(p.y * 100).toFixed(2)}%`));
        svg.append(dot);
      });
    });
    return svg;
  }
  function scatter(positions, onSelect) {
    const svg = canvas('Published ranked positions: games and distinct acyclic routes, logarithmic axes', 'Games (log scale)', 'Acyclic routes (log scale)');
    svg.setAttribute('role', 'group');
    if (!positions.length) return svg;
    const maxX = Math.max(1, Math.ceil(Math.log10(Math.max(...positions.map(p => p.games)))));
    const maxY = Math.max(1, Math.ceil(Math.log10(Math.max(...positions.map(p => Math.max(1, p.acyclic_routes))))));
    const x = n => 65 + Math.log10(Math.max(1, n)) / maxX * 565;
    const y = n => 255 - Math.log10(Math.max(1, n)) / maxY * 230;
    for (let i = 0; i <= maxX; i++) tick(svg, x(10 ** i), 275, (10 ** i).toLocaleString('en-US'));
    for (let i = 0; i <= maxY; i++) tick(svg, 55, y(10 ** i) + 4, (10 ** i).toLocaleString('en-US'), 'end');
    positions.forEach((p, index) => {
      const share = p.alternative_route_share;
      const label = `Inspect position ${index + 1}: ${p.games.toLocaleString('en-US')} games, ${p.acyclic_routes} routes, ${share === null ? 'no acyclic arrivals' : (share * 100).toFixed(2) + '% alternative-route share'}`;
      const dot = element('circle', {cx: x(p.games), cy: y(Math.max(1, p.acyclic_routes)), r: 8, tabindex: 0, role: 'button', 'aria-label': label, fill: share === null ? '#66756e' : `hsl(155 45% ${65 - share * 42}%)`, stroke: '#174e3b', 'stroke-width': 1.5, class: 'chart-point'});
      dot.append(element('title', {}, label));
      dot.addEventListener('click', () => onSelect(p.id));
      dot.addEventListener('keydown', event => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          onSelect(p.id);
        }
      });
      svg.append(dot);
    });
    return svg;
  }
  return {line, scatter};
})();
