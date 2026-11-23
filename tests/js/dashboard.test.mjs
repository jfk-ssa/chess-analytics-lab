import assert from 'node:assert/strict';
import { test } from 'node:test';
import { barDomain, breadcrumb, climb, Cube, selectFamily, selectLine } from '../../site/assets/dashboard-core.mjs';

function payload(rows) {
  const grains = {};
  for (const row of rows) {
    const { grain, ...values } = row;
    grains[grain] ||= { columns: Object.keys(values), dictionaries: {}, rows: [] };
    grains[grain].rows.push(grains[grain].columns.map((key) => values[key]));
  }
  return { version: 1, grains, clock_ranks: {} };
}
const fixture = (rows) => new Cube(payload(rows));
const f = { start: '2026-08-01', end: '2026-08-31' };
const cell = { grain: 'result_cell', cohort: 'warehouse', period: '2026-08', period_start: '2026-08-01', period_end: '2026-08-31', time_control: '180+0', color: 'white', rating_band: '1400_1599', opening_family: 'Sicilian', games: 100, wins: 40, draws: 10, losses: 50, rating_diff: 5, mean_ply: 60 };

test('carried cuts stay empty; unsupported dimensions are captioned', () => {
  const cube = fixture([{ ...cell, grain: 'game_cell', color: null, rating_band: null }]);
  assert.equal(cube.query('game_cell', { ...f, time_control: 'never' }).length, 0);
  assert.equal(cube.collect('game_cell', { ...f, time_control: 'never' }).rows.length, 0);
  assert.deepEqual(cube.ignored('game_cell', { ...f, color: 'black', rating_band: '2000_plus' }), ['color', 'rating']);
});
test('rating subset and multiple filters intersect', () => {
  const cube = fixture([cell]);
  assert.equal(cube.query('result_cell', { ...f, rating_band: '1200_1599', color: 'white' }).length, 1);
  assert.equal(cube.query('result_cell', { ...f, rating_band: '1200_1599', color: 'black' }).length, 0);
});
test('prior periods require equal blocks, contiguous months, cohort and span', () => {
  const cube = fixture([{ ...cell, period: '2026-07', period_start: '2026-07-01', period_end: '2026-07-31', wins: 30 }, cell]);
  const cards = cube.kpis(f);
  assert.match(cards[1].detail, /\+10.0 pp vs prior/);
  assert.equal(cards[1].value, '40.0%');
  for (const change of [{ period: '2026-06' }, { cohort: 'other' }, { period_end: '2026-07-30' }]) {
    const other = fixture([{ ...cell, period: '2026-07', period_start: '2026-07-01', period_end: '2026-07-31', ...change }, cell]);
    assert.doesNotMatch(other.kpis(f)[1].detail, /vs prior/);
  }
});
test('drills retain clock state and breadcrumbs; single-position back skips position', () => {
  const family = selectFamily({ clock_band: 'under_10' }, 'Sicilian');
  const line = selectLine(family, { label: 'e4 c5', fens: ['fen'] });
  assert.deepEqual(breadcrumb(line), ['Openings', 'Sicilian', 'e4 c5', 'Position']);
  assert.equal(climb(line).line, null);
  assert.equal(climb(line, 2).line, 'e4 c5');
  assert.equal(selectFamily(line, null).clock_band, 'under_10');
});
test('period empty date cut never widens and unsupported filters have captions', () => {
  const cube = fixture([{ ...cell, grain: 'corpus_month' }]);
  assert.equal(cube.periods({ start: '2000-01-01', end: '2000-01-02', color: 'black' }).rows.length, 0);
  assert.match(cube.periods({ ...f, color: 'black' }).caption, /not split by color/);
});
test('August clock fallback is explicit and absent controls never reuse it', () => {
  const cube = fixture([{ ...cell, grain: 'clock_slice', color: null, opening_family: null, clock_band: 'under_10', moves: 200, evaluable_moves: 100, proxy_errors: 20 }]);
  assert.match(cube.clock({ start: '2025-01-01', end: '2025-01-31' }).caption, /August prefix/);
  assert.equal(cube.clock({ ...f, time_control: 'never' }).rows.length, 0);
  assert.equal(cube.clockGames({ ...f, time_control: 'never' }, 'under_10').total, 0);
  assert.throws(() => cube.clockGames(f, 'invalid'));
  assert.throws(() => cube.clockGames(f, 'under_10', 0));
});
test('count axes use zero and clustered rate axes retain ten points of context', () => {
  assert.deepEqual(barDomain([30, 40]), [0, 40]);
  assert.deepEqual(barDomain([0.8, 0.9], false), [0.7000000000000001, 1]);
});
test('invalid exported JSON fails visibly', () => {
  assert.throws(() => new Cube({ version: 2, grains: {} }));
});


test('UI renders the shared query results, drills, reset, empty cut and invalid dates offline', async () => {
  const fen = 'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq -';
  const data = payload([
    cell, { ...cell, grain: 'game_cell' },
    { ...cell, grain: 'opening_family', cohort: 'rated_public', color: null, rating_band: null, time_control: null },
    { ...cell, grain: 'opening_line', cohort: 'rated_public', opening_line: '1.e4 c5 2.Nf3', fen, color: null, rating_band: null, time_control: null },
    { ...cell, grain: 'opening_position', cohort: 'rated_public', fen },
    { ...cell, grain: 'opening_continuation', cohort: 'rated_public', fen, continuation: 'Nf3' },
    { ...cell, grain: 'clock_slice', clock_band: 'under_10', moves: 200, evaluable_moves: 100, proxy_errors: 10 },
    { ...cell, grain: 'clock_game', lichess_id: 'abcdefgh', clock_band: 'under_10', white_rating: 1500, black_rating: 1550, opening_line: 'Sicilian' },
    { ...cell, grain: 'corpus_month' },
  ]);
  data.clock_ranks = { abcdefgh: '1' };
  const handlers = {};
  const viewHandlers = {};
  const elements = Object.fromEntries(['start', 'end', 'time_control', 'color', 'rating_band', 'opening_family'].map((name) => [name, { value: '', set defaultValue(value) { this.value = value; } }]));
  const form = { elements, addEventListener: (name, handler) => { handlers[name] = handler; } };
  const status = {};
  const view = { addEventListener: (name, handler) => { viewHandlers[name] = handler; }, replaceChildren() { this.innerHTML = ''; } };
  const root = { querySelector: (selector) => ({ form, '#dashboard-status': status, '#dashboard-view': view })[selector] };
  const saved = { document: globalThis.document, fetch: globalThis.fetch, FormData: globalThis.FormData };
  globalThis.document = { querySelector: () => root };
  globalThis.fetch = async () => ({ ok: true, json: async () => data });
  globalThis.FormData = class { constructor() { return Object.entries(elements).map(([key, e]) => [key, e.value]); } };
  const click = (action, index = 0) => viewHandlers.click({ target: { closest: () => ({ dataset: { action, index } }) } });
  try {
    await import('../../site/assets/dashboard-ui.mjs?ui-test');
    assert.match(view.innerHTML, /dash-kpis/);
    assert.match(view.innerHTML, /200 eligible moves/);
    assert.match(view.innerHTML, /100 evaluable moves/);
    assert.match(view.innerHTML, /<h2>Games<\/h2>/);
    click('family');
    assert.equal(elements.opening_family.value, 'Sicilian');
    assert.match(view.innerHTML, /dash-move">1. e4 c5<\/span>/);
    assert.doesNotMatch(view.innerHTML, /1. 1.e4/);
    click('line');
    assert.match(view.innerHTML, /dash-board/);
    assert.match(view.innerHTML, /Continuation moves/);
    click('crumb', 0);
    assert.equal(elements.opening_family.value, '');
    click('clock');
    assert.match(view.innerHTML, /game sample/);
    assert.match(view.innerHTML, /lichess.org\/abcdefgh/);
    assert.match(view.innerHTML, /six most common openings/);
    elements.time_control.value = 'absent'; handlers.change();
    assert.match(view.innerHTML, /No cells for this cut/);
    assert.doesNotMatch(view.innerHTML, /lichess.org\/abcdefgh/);
    elements.start.value = '2100-01-01'; handlers.change();
    assert.match(status.textContent, /valid date range/);
    elements.start.value = '2026-08-01'; elements.time_control.value = '';
    handlers.reset(); await Promise.resolve();
    assert.match(view.innerHTML, /dash-kpis/);
  } finally { Object.assign(globalThis, saved); }
});
