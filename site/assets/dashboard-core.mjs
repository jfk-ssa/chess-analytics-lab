// Browser and Node share this pure query layer. No warehouse or network runtime.
export const dimensions = ['time_control', 'color', 'rating_band', 'opening_family'];
export const bands = ['under_10', '10_to_29', '30_to_59', '60_plus'];
const labels = {
  time_control: 'time',
  color: 'color',
  rating_band: 'rating',
  opening_family: 'opening',
};
const sum = (rows, field) => rows.reduce((a, r) => a + (r[field] || 0), 0);
const number = (n) => n.toLocaleString('en-US');
const tenth = (n) =>
  (n < 0 ? '-' : '') + (Math.round((Math.abs(n) + Number.EPSILON) * 10) / 10).toFixed(1);
const signed = (n) => (n < 0 ? '' : '+') + tenth(n);
const countSigned = (n) => (n < 0 ? '' : '+') + number(n);
const percent = (n) => `${tenth(n * 100)}%`;
const mean = (rows, field) => {
  const valid = rows.filter((r) => r[field] != null && r.games);
  return sum(valid, 'games')
    ? valid.reduce((a, r) => a + r[field] * r.games, 0) / sum(valid, 'games')
    : null;
};
const ratingMatch = (r, value) => r === value || (value === '1200_1599' && r === '1400_1599');
const inside = (r, f) => r.period_start >= f.start && r.period_end <= f.end;
const join = (items) =>
  items.length < 2
    ? items.join('')
    : items.length === 2
      ? items.join(' or ')
      : `${items.slice(0, -1).join(', ')}, or ${items.at(-1)}`;
const labeled = (rows, field) =>
  rows
    .map((r) => ({ label: r[field], games: r.games, fen: r.fen ?? null }))
    .sort((a, b) => b.games - a.games);
export const breadcrumb = (d) =>
  ['Openings', d.family, d.line, d.fen ? 'Position' : null].filter(Boolean);
export function selectFamily(d, family) {
  return { family, line: null, fen: null, clock_band: d.clock_band };
}
export function selectLine(d, row) {
  return { ...d, line: row.label, fen: row.fens.length === 1 ? row.fens[0] : null };
}
export function climb(d, fens = 1) {
  if (d.fen && fens > 1) return { ...d, fen: null };
  if (d.line) return { ...d, line: null, fen: null };
  return selectFamily(d, null);
}
export class Cube {
  constructor(payload) {
    if (payload.version !== 1 || !Object.keys(payload.grains).length)
      throw Error('Invalid dashboard JSON');
    this.rows = Object.entries(payload.grains).flatMap(([grain, table]) =>
      table.rows.map((row) => ({
        grain,
        ...Object.fromEntries(
          table.columns.map((key, i) => [
            key,
            row[i] == null
              ? null
              : table.dictionaries[key]
                ? table.dictionaries[key][row[i]]
                : row[i],
          ]),
        ),
      })),
    );
    this.carried = new Map();
    this.grains = new Map();
    for (const r of this.rows) {
      if (!this.grains.has(r.grain)) this.grains.set(r.grain, []);
      this.grains.get(r.grain).push(r);
    }
    this.ranks = payload.clock_ranks;
    this.provenance = payload.provenance;
  }
  grain(g) {
    return this.grains.get(g) || [];
  }
  carries(g, key) {
    const id = `${g}|${key}`;
    if (!this.carried.has(id))
      this.carried.set(
        id,
        this.grain(g).some((r) => r[key] != null),
      );
    return this.carried.get(id);
  }
  values(key) {
    return [
      ...new Set(
        this.rows.filter((r) => r.grain !== 'clock_game' && r[key] != null).map((r) => r[key]),
      ),
    ].sort();
  }
  bounds() {
    const rows = this.rows.filter((r) => r.cohort === 'rated_public');
    return [
      rows.map((r) => r.period_start).sort()[0],
      rows
        .map((r) => r.period_end)
        .sort()
        .at(-1),
    ];
  }
  ignored(g, f) {
    return ['color', 'opening_family', 'time_control', 'rating_band']
      .filter((key) => f[key] && !this.carries(g, key))
      .map((key) => labels[key]);
  }
  query(
    g,
    f,
    {
      dates = true,
      cohort = ['clock_slice', 'clock_game'].includes(g) ? 'm3_august_prefix' : 'rated_public',
      dimensional = true,
    } = {},
  ) {
    return this.grain(g).filter(
      (r) =>
        (!dates || inside(r, f)) &&
        r.cohort === cohort &&
        (!dimensional ||
          dimensions.every(
            (k) =>
              !f[k] ||
              !this.carries(g, k) ||
              (k === 'rating_band' ? ratingMatch(r[k], f[k]) : r[k] === f[k]),
          )),
    );
  }
  collect(g, f, force = null) {
    const active = { ...f, color: force || f.color };
    const notes = [...(force && !f.color ? ['White'] : []), ...this.ignored(g, active)];
    let rows = this.query(g, active);
    if (!rows.length) {
      rows = this.query(g, active, { dates: false });
      if (rows.length) notes.push('date');
      else if (dimensions.some((k) => active[k] && this.carries(g, k))) notes.push('cut');
    }
    return { rows, notes, active };
  }
  prior(g, current) {
    const { rows, notes, active } = current;
    if (!rows.length || notes.includes('date') || notes.includes('cut')) return null;
    const catalog = this.query(g, active, { dates: false });
    const selected = [...new Set(rows.map((r) => r.period))].sort();
    const ordered = [...new Set(catalog.map((r) => r.period))].sort();
    const i = ordered.indexOf(selected[0]);
    if (i < selected.length) return null;
    const previous = ordered.slice(i - selected.length, i);
    const index = (p) =>
      /^\d{4}-(0[1-9]|1[0-2])$/.test(p) ? +p.slice(0, 4) * 12 + +p.slice(5) : NaN;
    const sequence = [...previous, ...selected];
    if (
      sequence.some(
        (p, j) => !Number.isFinite(index(p)) || (j && index(p) !== index(sequence[j - 1]) + 1),
      )
    )
      return null;
    const signatures = new Set(
      catalog
        .filter((r) => sequence.includes(r.period))
        .map((r) => `${r.cohort}|${Date.parse(r.period_end) - Date.parse(r.period_start)}`),
    );
    if (signatures.size !== 1) return null;
    const found = catalog.filter((r) => previous.includes(r.period));
    return sum(found, 'games') > 0 ? found : null;
  }
  cohort(f) {
    return ['rated_public', !!this.query('opening_family', f, { dimensional: false }).length];
  }
  openings(f, d = {}) {
    const [cohort, covered] = this.cohort(f);
    const ignored = ['color', 'time_control', 'rating_band']
      .filter((k) => f[k] && !this.carries('opening_family', k))
      .map((k) => (k === 'time_control' ? 'time control' : labels[k]));
    const caption = `${covered ? `${cohort === 'rated_public' ? 'Rated public' : 'Elite month'}. Published positions only, not every game in the family.` : 'These positions use the full published window, which is wider than this date range.'}${ignored.length ? ` Positions are not split by ${join(ignored)}.` : ''}`;
    const options = { cohort, dates: covered };
    if (!cohort) return { rows: [], caption: 'No published positions in the cube.' };
    if (!d.family)
      return { rows: labeled(this.query('opening_family', f, options), 'opening_family'), caption };
    const active = { ...f, opening_family: d.family };
    if (d.fen)
      return {
        rows: labeled(
          this.query('opening_continuation', active, options).filter((r) => r.fen === d.fen),
          'continuation',
        ),
        caption,
      };
    const grouped = new Map();
    for (const r of this.query('opening_line', active, options)) {
      if (!grouped.has(r.opening_line))
        grouped.set(r.opening_line, { label: r.opening_line, games: 0, fens: [] });
      const slot = grouped.get(r.opening_line);
      slot.games += r.games;
      if (!slot.fens.includes(r.fen)) slot.fens.push(r.fen);
    }
    const rows = [...grouped.values()].sort((a, b) => b.games - a.games);
    return {
      rows: d.line
        ? (rows.find((r) => r.label === d.line)?.fens || []).map((fen) => ({
            label: fen,
            fen,
            games:
              this.query('opening_position', active, options).find((r) => r.fen === fen)?.games ||
              0,
          }))
        : rows,
      caption,
    };
  }
  transpositions(f, limit = 6) {
    const [cohort, covered] = this.cohort(f);
    const notes = [
      ...(!covered ? ['date'] : []),
      ...['color', 'time_control', 'rating_band']
        .filter((k) => f[k] && !this.carries('transposition', k))
        .map((k) => (k === 'time_control' ? 'time control' : labels[k])),
    ];
    const ignored = notes.filter((n) => n !== 'date');
    const caption = notes.includes('date')
      ? `Move orders use the full published window${ignored.length ? `. They are not split by ${join(ignored)}.` : ', which is wider than this date range.'}`
      : ignored.length
        ? `Move orders are not split by ${join(ignored)}.`
        : 'Distinct acyclic move orders. Routes under 10 games are omitted.';
    const rows = this.query('transposition', f, { cohort, dates: covered })
      .sort((a, b) => b.games - a.games)
      .slice(0, limit)
      .map((r) => {
        const routes = this.grain('transposition_route')
          .filter(
            (v) => v.cohort === cohort && v.fen === r.fen && v.opening_family === r.opening_family,
          )
          .sort((a, b) => b.games - a.games);
        return {
          fen: r.fen ?? null,
          family: r.opening_family,
          title: `After Black's move ${routes[0].ply / 2} · ${routes[0].opening_line.trim()}`,
          games: r.games,
          kept_games: sum(routes, 'games'),
          move_orders: r.ply,
          routes: routes.slice(0, 3).map((v) => [v.opening_line, v.games]),
          eco: r.eco,
        };
      });
    return { rows, caption };
  }
  clock(f) {
    const g = this.grain('clock_cell').length ? 'clock_cell' : 'clock_slice';
    const absent = ['time_control', 'rating_band']
      .filter(
        (k) => f[k] && this.carries(g, k) && !this.query(g, { [k]: f[k] }, { dates: false }).length,
      )
      .map((k) => labels[k]);
    let rows = absent.length ? [] : this.query(g, f);
    let fallback = false;
    let named = absent;
    if (!rows.length && !absent.length && this.grain(g).length) {
      const all = this.query(g, f, { dates: false, dimensional: false });
      const low = all.map((r) => r.period_start).sort()[0];
      const high = all
        .map((r) => r.period_end)
        .sort()
        .at(-1);
      if (!(f.start <= low && f.end >= high)) {
        // Preserve every carried dimension even in an explicitly labelled date fallback.
        rows = this.query(g, f, { dates: false });
        fallback = !!rows.length;
      }
      if (!rows.length)
        named = ['time_control', 'rating_band']
          .filter((k) => f[k] && this.carries(g, k))
          .map((k) => labels[k]);
    }
    const notes = [...new Set([...this.ignored(g, f), ...named, ...(fallback ? ['date'] : [])])];
    const ignored = notes.filter((n) => n !== 'date');
    const window = g === 'clock_cell' ? 'the warehouse window' : 'the August prefix';
    let caption = null;
    if (!rows.length && ignored.length) caption = `No clock slices for this ${join(ignored)}.`;
    else if (fallback)
      caption = ignored.length
        ? `Clock pressure is ${window} and is not split by ${join(ignored)}.`
        : `These slices are ${window}.`;
    else if (rows.length && ignored.length)
      caption = `Clock pressure is not split by ${join(ignored)}.`;
    const tag =
      notes.length === 1 && notes[0] === 'date'
        ? g === 'clock_cell'
          ? 'warehouse window'
          : 'August'
        : notes.length
          ? `not by ${notes.join(', ')}`
          : '';
    const grouped = bands
      .filter((b) => rows.some((r) => r.clock_band === b))
      .map((b) => {
        const matches = rows.filter((r) => r.clock_band === b);
        const evaluable = sum(matches, 'evaluable_moves');
        return {
          label: b,
          games: evaluable,
          moves: sum(matches, 'moves'),
          evaluable_moves: evaluable,
          proxy_errors: sum(matches, 'proxy_errors'),
          error_proxy_rate: evaluable ? sum(matches, 'proxy_errors') / evaluable : null,
        };
      });
    return { rows: grouped, caption, tag, fallback, named, source: rows };
  }
  clockGames(f, band, limit = 12) {
    if (!bands.includes(band) || !Number.isInteger(limit) || limit < 1)
      throw Error('Invalid clock sample request');
    const clock = this.clock(f);
    if (!clock.rows.some((r) => r.label === band))
      return {
        rows: [],
        total: 0,
        caption:
          'No clock games are published for this cut. The bar counts evaluable moves, not games.',
      };
    const rows = this.query('clock_game', f, { dates: !clock.fallback }).filter(
      (r) => r.clock_band === band,
    );
    const grouped = new Map();
    for (const r of rows) {
      if (!grouped.has(r.lichess_id))
        grouped.set(r.lichess_id, {
          lichess_id: r.lichess_id,
          played_on: r.period_start,
          time_control: r.time_control,
          result: r.result,
          white_rating: r.white_rating,
          black_rating: r.black_rating,
          opening_family: r.opening_family,
          opening_line: r.opening_line,
          colors: new Set(),
        });
      grouped.get(r.lichess_id).colors.add(r.color);
    }
    const found = [...grouped.values()].sort((a, b) =>
      this.ranks[a.lichess_id].localeCompare(this.ranks[b.lichess_id]),
    );
    for (const r of found) {
      r.side = r.colors.size === 2 ? 'Both' : r.colors.has('white') ? 'White' : 'Black';
      delete r.colors;
    }
    return {
      rows: found.slice(0, limit),
      total: found.length,
      caption: `Showing ${Math.min(limit, found.length)} of ${number(found.length)} published games with a move at this time remaining, in lowest-SHA-256 order of the Lichess id. ${rows.every((r) => r.cohort === 'm3_august_prefix') ? 'The sample is the August prefix.' : 'The sample is the published clock-game extract.'} Each time control, rating band, and color keeps one game from each of the six most common openings, the game with the lowest SHA-256 of its Lichess id. The bar counts evaluable moves, not games.`,
    };
  }
  periods(f) {
    const rows = this.query('corpus_month', f, { dimensional: false })
      .sort((a, b) => a.period.localeCompare(b.period))
      .map((r) => ({ label: r.period, games: r.games }));
    const ignored = ['color', 'time_control', 'rating_band', 'opening_family']
      .filter((k) => f[k])
      .map((k) => (k === 'time_control' ? 'time control' : labels[k]));
    return {
      rows,
      caption: `Rated public. ${rows.length ? '' : 'No published period sits fully inside this date range. '}${ignored.length ? `Period totals are not split by ${join(ignored)}.` : 'Each bar is one published period. The Games card counts warehouse cells of at least 10 games.'}`,
    };
  }
  kpis(f) {
    const force = f.color || 'white';
    const g =
      f.color || f.rating_band || !this.grain('game_cell').length ? 'result_cell' : 'game_cell';
    const games = this.collect(g, f, g === 'result_cell' ? force : null);
    const results = this.collect('result_cell', f, force);
    const cards = [];
    const card = (label, value, detail) => cards.push({ label, value, detail });
    const ignored = (notes) => notes.filter((n) => n !== 'White');
    const note = (notes) => (ignored(notes).length ? ` · not by ${ignored(notes).join(', ')}` : '');
    const pop = (notes) => (notes.includes('White') ? ' · White' : '');
    const total = sum(games.rows, 'games');
    const priorGames = this.prior(g, games);
    card(
      'Games',
      number(total),
      games.notes.includes('cut')
        ? 'no cells for this cut'
        : `rated public games in range${pop(games.notes)}${note(games.notes)}${priorGames ? ` · ${countSigned(total - sum(priorGames, 'games'))} vs prior` : ''}`,
    );
    const scored = sum(results.rows, 'games');
    const prior = this.prior('result_cell', results);
    for (const [label, field] of [
      ['Win rate', 'wins'],
      ['Loss rate', 'losses'],
      ['Draw rate', 'draws'],
    ]) {
      const count = sum(results.rows, field);
      const delta = prior
        ? ` · ${signed(+tenth((count / scored) * 100) - +tenth((sum(prior, field) / sum(prior, 'games')) * 100))} pp vs prior`
        : '';
      card(
        label,
        percent(scored ? count / scored : 0),
        !results.rows.length
          ? results.notes.includes('cut')
            ? 'no cells for this cut'
            : 'no scored cells'
          : `${number(count)} / ${number(scored)} · ${force === 'black' ? 'Black' : 'White'} perspective${note(results.notes)}${delta}`,
      );
    }
    const [cohort, covered] = this.cohort(f);
    const positions = new Set(
      this.query(
        'opening_position',
        { opening_family: f.opening_family, start: f.start, end: f.end },
        { cohort, dates: covered },
      ).map((r) => r.fen),
    );
    const posNotes = ['color', 'time_control', 'rating_band']
      .filter((k) => f[k])
      .map((k) => labels[k]);
    if (!covered) posNotes.push('date');
    card(
      'Positions',
      number(positions.size),
      `${cohort === 'rated_public' ? 'rated public' : 'elite month'}${note(posNotes)}`,
    );
    for (const [label, field] of [
      ['Rating diff', 'rating_diff'],
      ['Game length', 'mean_ply'],
    ]) {
      const useGames =
        label === 'Game length' && !f.color && !f.rating_band && this.grain('game_cell').length;
      const chosen = useGames ? this.collect('game_cell', f) : results;
      const earlier = useGames ? this.prior('game_cell', chosen) : prior;
      const value = mean(chosen.rows, field);
      const before = earlier ? mean(earlier, field) : null;
      const detail = chosen.notes.includes('cut')
        ? 'no cells for this cut'
        : `${chosen.notes.includes('White') ? 'White · ' : ''}${label === 'Game length' ? 'mean ply' : 'mean'}${note(chosen.notes)}${before != null && value != null ? ` · ${signed(+tenth(value) - +tenth(before))} vs prior` : ''}`;
      card(
        label,
        value == null ? '0.0' : label === 'Rating diff' ? signed(value) : tenth(value),
        detail,
      );
    }
    const clock = this.clock(f);
    const evaluable = sum(clock.source, 'evaluable_moves');
    const errors = sum(clock.source, 'proxy_errors');
    card(
      'Clock error',
      percent(evaluable ? errors / evaluable : 0),
      !evaluable
        ? clock.named.length
          ? `no cells for this cut · not by ${clock.named.join(', ')}`
          : `no evaluable moves${clock.tag ? ` · ${clock.tag}` : ''}`
        : `${number(errors)} / ${number(evaluable)}${clock.tag ? ` · ${clock.tag}` : ''}`,
    );
    return cards;
  }
}
// Rates start 10% below the displayed minimum; count bars always start at zero.
export function barDomain(values, count = true) {
  return [count ? 0 : Math.max(0, 0.9 * Math.min(...values)), count ? Math.max(1, ...values) : 1];
}
