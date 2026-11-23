import { barDomain, breadcrumb, Cube, climb, selectFamily, selectLine } from './dashboard-core.mjs';

const root = document.querySelector('#dashboard');
const form = root.querySelector('form');
const status = root.querySelector('#dashboard-status');
const view = root.querySelector('#dashboard-view');
const names = {
  under_10: 'Under 10s',
  '10_to_29': '10–29s',
  '30_to_59': '30–59s',
  '60_plus': '60s+',
  under_1200: 'Under 1200',
  '1200_1599': '1200–1599',
  '1600_1999': '1600–1999',
  '2000_plus': '2000+',
};
const esc = (s) =>
  String(s ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
const num = (n) => n.toLocaleString('en-US');
// Each full move remains a single wrapping unit, as on the transpositions page.
function san(text) {
  const tokens = String(text)
    .replace(/\d+\.\s*/g, '')
    .split(/\s+/);
  const moves = [];
  for (let i = 0; i < tokens.length; i += 2)
    moves.push(
      `<span class="dash-move">${esc(`${Math.floor(i / 2) + 1}. ${tokens[i]} ${tokens[i + 1] || ''}`)}</span>`,
    );
  return moves.join(' ');
}
function board(fen) {
  const squares = [];
  for (const [rank, row] of fen.split(' ')[0].split('/').entries()) {
    let file = 0;
    for (const token of row) {
      const count = /[1-8]/.test(token) ? +token : 1;
      for (let n = 0; n < count; n++) {
        const piece = /[1-8]/.test(token)
          ? ''
          : `<img src="assets/pieces/${token === token.toUpperCase() ? 'w' : 'b'}${token.toUpperCase()}.svg" alt="${esc(token)}">`;
        squares.push(`<span class="${(rank + file++) % 2 ? 'dash-dark' : ''}">${piece}</span>`);
      }
    }
  }
  return `<div class="dash-board" role="img" aria-label="Published position ${esc(fen)}">${squares.join('')}</div>`;
}
function bars(rows, { action = '', sanLabels = false, field = 'games', count = true } = {}) {
  if (!rows.length) return '<p class="dash-empty">No cells for this cut.</p>';
  const [low, high] = barDomain(
    rows.map((r) => r[field]),
    count,
  );
  return `<div class="dash-bars"><p class="dash-axis">${count ? `Count axis: 0–${num(high)}` : `Rate axis: ${(low * 100).toFixed(1)}%–${(high * 100).toFixed(1)}%`}</p>${rows
    .map((r, i) => {
      const mark = `<span class="dash-bar-track"><span class="dash-bar" style="width:${Math.max(0, ((r[field] - low) / (high - low)) * 100)}%"></span></span><strong>${count ? num(r[field]) : `${(r[field] * 100).toFixed(1)}%`}</strong>`;
      const label =
        sanLabels && r.label !== 'Other orders' ? san(r.label) : esc(names[r.label] || r.label);
      return `<div class="dash-bar-row">${action ? `<button type="button" data-action="${action}" data-index="${i}">${label}</button>` : `<span>${label}</span>`}${mark}</div>`;
    })
    .join('')}</div>`;
}
let cube;
let drill = {};
let openingRows = [];
function filters() {
  const data = Object.fromEntries(new FormData(form));
  return Object.fromEntries(Object.entries(data).map(([key, value]) => [key, value || null]));
}
function render() {
  const f = filters();
  if (!f.start || !f.end || f.start > f.end) {
    status.textContent = 'Choose a valid date range: From must be on or before Through.';
    view.replaceChildren();
    return;
  }
  status.textContent = `Date ${f.start}–${f.end} · Time ${f.time_control || 'All'} · Color ${f.color || 'All'} · Rating ${names[f.rating_band] || f.rating_band || 'All'} · Opening ${f.opening_family || 'All'}`;
  const cards = cube.kpis(f);
  const opening = cube.openings(f, drill);
  openingRows = opening.rows.slice(0, 12);
  const trans = cube.transpositions(f, 8);
  const clock = cube.clock(f);
  const periods = cube.periods(f);
  const crumbs = breadcrumb(drill);
  const clockSample = drill.clock_band ? cube.clockGames(f, drill.clock_band) : null;
  view.innerHTML = `<div class="dash-grid dash-kpis">${cards.map((c) => `<article class="dash-card"><h2>${esc(c.label)}</h2><p class="dash-value">${esc(c.value)}</p><p>${esc(c.detail)}</p></article>`).join('')}</div>
<section><h2>Openings</h2><nav class="dash-crumb" aria-label="Opening breadcrumbs">${crumbs.map((c, i) => `<button type="button" data-action="crumb" data-index="${i}">${i === 2 ? san(c) : esc(c)}</button>`).join('<span aria-hidden="true"> / </span>')}</nav>
${drill.family ? '<button type="button" data-action="back">Back</button>' : ''}
${drill.fen ? board(drill.fen) : ''}
${bars(openingRows, { action: drill.fen ? '' : drill.line ? 'position' : drill.family ? 'line' : 'family', sanLabels: !!drill.family && !drill.line })}
<p class="source-note">${esc(opening.caption)} ${drill.fen ? 'Continuation moves from this published position.' : 'Select a bar label to drill into published lines and positions. Showing up to 12 rows.'}</p></section>
<section><h2>Most common transpositions</h2><div class="dash-grid">${trans.rows
    .map((r) => {
      const other = r.games - r.routes.reduce((s, route) => s + route[1], 0);
      const routes = r.routes.map(([label, games]) => ({ label, games }));
      if (other >= 10) routes.push({ label: 'Other orders', games: other });
      return `<article class="dash-card"><h3>After Black's move ${esc(r.title.split(' · ')[0].split('move ')[1])}</h3><p>${san(r.routes[0][0])}</p><p class="dash-value">${num(r.games)}</p><p>Games reaching this position · ${r.kept_games === r.games ? num(r.move_orders) : `top ${r.routes.length}`} move orders</p><details><summary>Board and move orders</summary>${board(r.fen)}${bars(routes, { sanLabels: true })}</details>${other > 0 && other < 10 ? '<p class="source-note">An unlisted remainder is below the ten-game floor.</p>' : ''}</article>`;
    })
    .join(
      '',
    )}</div>${!trans.rows.length ? '<p class="dash-empty">No cells for this cut.</p>' : ''}<p class="source-note">${esc(trans.caption)}</p></section>
<section><h2>Clock</h2><p>Time remaining before the move. Bar length counts evaluable moves; eligible moves include moves without an evaluable error proxy.</p>${bars(clock.rows, { action: 'clock' })}
<p class="source-note">${esc(clock.caption || '')}</p><div class="dash-grid">${clock.rows.map((r) => `<article class="dash-card"><h3>${esc(names[r.label])}</h3><p>${num(r.moves)} eligible moves<br>${num(r.evaluable_moves)} evaluable moves<br>${num(r.proxy_errors)} proxy errors</p></article>`).join('')}</div>
${bars(
  clock.rows.filter((r) => r.error_proxy_rate != null),
  { field: 'error_proxy_rate', count: false },
)}
${clockSample ? `<h3>${esc(names[drill.clock_band])}: game sample</h3><button type="button" data-action="all-bands">All bands</button><div class="dash-grid">${clockSample.rows.map((r) => `<article class="dash-card"><h4><a href="https://lichess.org/${r.lichess_id}" target="_blank" rel="noopener noreferrer">${esc(r.lichess_id)}</a></h4><p>${esc(r.opening_line)}<br>${esc(r.played_on)} · ${esc(r.time_control)} · ${esc(r.result)}<br>White ${num(r.white_rating)} · Black ${num(r.black_rating)}<br>Clock mover: ${esc(r.side)}</p></article>`).join('')}</div><p class="source-note">${esc(clockSample.caption)}</p>` : ''}</section>
<section><h2>Periods</h2>${bars(periods.rows)}<p class="source-note">${esc(periods.caption)}</p></section>`;
}
form.addEventListener('submit', (event) => event.preventDefault());
form.addEventListener('change', () => {
  drill = selectFamily(drill, filters().opening_family);
  render();
});
form.addEventListener('reset', () => {
  queueMicrotask(() => {
    drill = {};
    render();
  });
});
view.addEventListener('click', (event) => {
  const button = event.target.closest('button[data-action]');
  if (!button) return;
  const i = +button.dataset.index;
  const row = openingRows[i];
  switch (button.dataset.action) {
    case 'family':
      drill = selectFamily(drill, row.label);
      form.elements.opening_family.value = row.label;
      break;
    case 'line':
      drill = selectLine(drill, row);
      break;
    case 'position':
      drill = { ...drill, fen: row.fen };
      break;
    case 'back':
      drill = climb(
        drill,
        cube.openings(filters(), { family: drill.family }).rows.find((r) => r.label === drill.line)
          ?.fens.length || 1,
      );
      form.elements.opening_family.value = drill.family || '';
      break;
    case 'crumb':
      if (i === 0) {
        drill = selectFamily(drill, null);
        form.elements.opening_family.value = '';
      } else if (i === 1) drill = { ...drill, line: null, fen: null };
      else if (i === 2) drill = { ...drill, fen: null };
      break;
    case 'clock':
      drill.clock_band = cube.clock(filters()).rows[i].label;
      break;
    case 'all-bands':
      drill.clock_band = null;
      break;
  }
  render();
});
try {
  const response = await fetch('assets/dashboard.json');
  if (!response.ok) throw Error(`HTTP ${response.status}`);
  cube = new Cube(await response.json());
  const [start, end] = cube.bounds();
  for (const [name, value] of [
    ['start', start],
    ['end', end],
  ]) {
    const input = form.elements[name];
    input.min = start;
    input.max = end;
    input.defaultValue = value;
  }
  for (const [name, values] of [
    ['time_control', cube.values('time_control')],
    ['color', ['white', 'black']],
    ['rating_band', ['under_1200', '1200_1599', '1600_1999', '2000_plus']],
    ['opening_family', cube.values('opening_family')],
  ]) {
    form.elements[name].innerHTML =
      `<option value="">All</option>${values.map((v) => `<option value="${esc(v)}">${esc(names[v] || v)}</option>`).join('')}`;
  }
  render();
} catch (error) {
  status.textContent = `Dashboard unavailable: ${error.message}. Serve the preview over local HTTP; see the build runbook.`;
}
