import { Chess } from './vendor/chess-1.4.0.mjs';

export const LIMITS = Object.freeze({
  bytes: 10 * 1024 * 1024,
  games: 5000,
  plies: 1000,
  variationDepth: 32,
  files: 20,
});
export const CONTRACT_VERSION = '1.0.0';
export class ImportLimitError extends Error {}
const RESULTS = new Set(['1-0', '0-1', '1/2-1/2']);
const encoder = new TextEncoder();
const fold = (value) => value.normalize('NFC').toLowerCase();
export const positionKey = (board) => board.fen().split(' ').slice(0, 4).join(' ');
export async function sha256(value) {
  const bytes = typeof value === 'string' ? encoder.encode(value) : value;
  const hash = await globalThis.crypto.subtle.digest('SHA-256', bytes);
  return [...new Uint8Array(hash)].map((byte) => byte.toString(16).padStart(2, '0')).join('');
}

// Lex PGN structure before legal replay. Ignore comments and RAVs, never their delimiters.
// Result tokens and a fresh header block delimit games; quoted tags are not move text.
export function framePgn(text, limits = LIMITS) {
  const frames = [];
  let frame = { headers: Object.create(null), moves: [], result: null, errors: [] };
  let depth = 0;
  function emit() {
    if (Object.keys(frame.headers).length || frame.moves.length || frame.result) frames.push(frame);
    if (frames.length > limits.games)
      throw new ImportLimitError(
        `Game limit exceeded (${limits.games}). No partial file was imported.`,
      );
    frame = { headers: Object.create(null), moves: [], result: null, errors: [] };
  }
  for (let i = 0; i < text.length; ) {
    const char = text[i];
    if (/\s|\uFEFF/.test(char)) {
      i++;
      continue;
    }
    if (char === ';' || (char === '%' && (i === 0 || text[i - 1] === '\n'))) {
      const end = text.indexOf('\n', i);
      i = end < 0 ? text.length : end + 1;
      continue;
    }
    if (char === '{') {
      const end = text.indexOf('}', i + 1);
      if (end < 0) throw new Error('Unclosed PGN comment. No partial file was imported.');
      i = end + 1;
      continue;
    }
    if (char === '(') {
      if (++depth > limits.variationDepth)
        throw new ImportLimitError(
          'PGN variations are nested too deeply. No partial session was imported.',
        );
      i++;
      continue;
    }
    if (char === ')') {
      if (!depth) throw new Error('Unmatched PGN variation delimiter.');
      depth--;
      i++;
      continue;
    }
    if (char === '[') {
      const start = i++;
      let quoted = false;
      let escaped = false;
      for (; i < text.length; i++) {
        const c = text[i];
        if (escaped) {
          escaped = false;
          continue;
        }
        if (c === '\\' && quoted) {
          escaped = true;
          continue;
        }
        if (c === '"') quoted = !quoted;
        if (c === ']' && !quoted) break;
      }
      if (i >= text.length) throw new Error('Unclosed PGN header.');
      const tag = text.slice(start, ++i);
      if (depth) continue;
      if (frame.moves.length) emit(); // A truncated game stays visible as an unfinished rejection.
      const match = tag.match(/^\[([A-Za-z0-9_]+)\s+"((?:\\["\\]|[^"\\])*)"\]$/);
      if (!match || tag.length > 4096) {
        frame.errors.push('invalid_header');
        continue;
      }
      const value = match[2].replace(/\\(["\\])/g, '$1');
      if (Object.hasOwn(frame.headers, match[1])) frame.errors.push('duplicate_header');
      frame.headers[match[1]] = value;
      continue;
    }
    if (char === '}' || char === ']') throw new Error('Unmatched PGN delimiter.');
    const start = i;
    while (i < text.length && !/[\s(){}[\];]/.test(text[i])) i++;
    let token = text.slice(start, i);
    if (depth) continue;
    token = token
      .replace(/^\d+\.(?:\.\.)?/, '')
      .replace(/(?:\$\d+)+$/, '')
      .replace(/[!?]+$/, '');
    if (!token || token === '...' || token === 'e.p.' || /^\$\d+$/.test(token)) continue;
    if (RESULTS.has(token) || token === '*') {
      frame.result = token;
      emit();
      continue;
    }
    if (token.length > 32) {
      frame.errors.push('invalid_move_token');
      continue;
    }
    frame.moves.push(token);
    if (frame.moves.length > limits.plies)
      throw new ImportLimitError(
        `Per-game move limit exceeded (${limits.plies} plies). No partial session was imported.`,
      );
  }
  if (depth) throw new Error('Unclosed PGN variation. No partial file was imported.');
  emit();
  return frames;
}

function providerIdentity(headers) {
  const found = [];
  for (const value of [headers.Site, headers.Link]) {
    if (!value) continue;
    const brand = fold(value.trim());
    if (['chess.com', 'www.chess.com'].includes(brand))
      found.push({ provider: 'chesscom', nativeId: null });
    if (['lichess.org', 'www.lichess.org'].includes(brand))
      found.push({ provider: 'lichess', nativeId: null });
    try {
      const url = new URL(value);
      if (!['https:', 'http:'].includes(url.protocol)) continue;
      if (['chess.com', 'www.chess.com'].includes(url.hostname)) {
        const match = url.pathname.match(/^\/game\/(live|daily)\/(\d+)\/?$/);
        found.push({ provider: 'chesscom', nativeId: match ? `${match[1]}:${match[2]}` : null });
      }
      if (['lichess.org', 'www.lichess.org'].includes(url.hostname)) {
        const match = url.pathname.match(
          /^\/([A-Za-z0-9]{8})(?:[A-Za-z0-9]{4})?(?:\/(?:white|black))?\/?$/,
        );
        found.push({ provider: 'lichess', nativeId: match ? match[1] : null });
      }
    } catch {
      /* Brand-only Site tags are valid; never visit a PGN URL. */
    }
  }
  if (new Set(found.map((x) => x.provider)).size > 1)
    throw new Error('conflicting_provider_headers');
  const nativeIds = [...new Set(found.map((x) => x.nativeId).filter(Boolean))];
  if (nativeIds.length > 1) throw new Error('conflicting_game_id_headers');
  return { provider: found[0]?.provider || 'pgn', nativeId: nativeIds[0] || null };
}
function dateValue(headers) {
  const value = headers.UTCDate || headers.Date || '';
  if (!/^\d{4}\.\d{2}\.\d{2}$/.test(value) || value.startsWith('0000')) return null;
  const iso = value.replaceAll('.', '-');
  const parsed = new Date(`${iso}T00:00:00Z`);
  return Number.isFinite(parsed.valueOf()) && parsed.toISOString().slice(0, 10) === iso
    ? iso
    : null;
}
function ratedValue(headers) {
  if (['true', 'false'].includes(fold(headers.Rated || ''))) return fold(headers.Rated) === 'true';
  if (/^rated\b/i.test(headers.Event || '')) return true;
  if (/^(casual|unrated)\b/i.test(headers.Event || '')) return false;
  return null;
}
// Trim and NFC-normalize before the unknown-player and length checks.
function playerName(value) {
  const name = String(value ?? '')
    .trim()
    .normalize('NFC');
  if (!name || name === '?' || name.length > 200) throw new Error('missing_or_invalid_players');
  return name;
}
// chess.js strict mode rejects digit castling. 0-0 and 0-0-0 are the same moves as O-O and O-O-O.
export function canonicalSan(token) {
  return token.replace(/^0-0-0(?=$|[+#])/, 'O-O-O').replace(/^0-0(?=$|[+#])/, 'O-O');
}
export async function parseGame(frame, keyCache = new Map()) {
  const h = frame.headers;
  if (frame.errors.length) throw new Error(frame.errors[0]);
  if (h.Variant && fold(h.Variant) !== 'standard') throw new Error('unsupported_variant');
  if (h.FEN || (h.SetUp && h.SetUp !== '0')) throw new Error('unsupported_setup');
  if (!RESULTS.has(frame.result)) throw new Error('unfinished_or_missing_result');
  if (h.Result && h.Result !== frame.result) throw new Error('conflicting_result');
  const white = playerName(h.White);
  const black = playerName(h.Black);
  const board = new Chess();
  const seen = new Set([positionKey(board)]);
  let repeat = false;
  const moves = [];
  const sans = [];
  const visits = [];
  for (let i = 0; i < frame.moves.length; i++) {
    let move;
    try {
      move = board.move(canonicalSan(frame.moves[i]), { strict: true });
    } catch {
      throw new Error('illegal_or_invalid_mainline');
    }
    const uci = move.from + move.to + (move.promotion || '');
    moves.push(uci);
    sans.push(move.san);
    if (i < 20) {
      const key = positionKey(board);
      if (seen.has(key)) repeat = true;
      seen.add(key);
      const ply = i + 1;
      if (ply >= 6 && ply % 2 === 0) {
        if (!keyCache.has(key)) keyCache.set(key, (await sha256(key)).slice(0, 24));
        visits.push({
          ply,
          id: keyCache.get(key),
          position_key: key,
          full_fen: board.fen(),
          route: moves.join(' '),
          route_has_repeat: repeat,
          san_route: sans
            .map((san, j) => (j % 2 === 0 ? `${Math.floor(j / 2) + 1}.` : '') + san)
            .join(' '),
        });
      }
    }
  }
  visits.forEach((visit) => {
    visit.next_move = moves[visit.ply] || null;
  });
  const date = dateValue(h);
  const identity = providerIdentity(h);
  const semantic = JSON.stringify([fold(white), fold(black), date, moves]);
  const fingerprint = await sha256(JSON.stringify([fold(white), fold(black), moves, frame.result]));
  return {
    ...identity,
    id: identity.nativeId || `sha256:${await sha256(semantic)}`,
    fingerprint,
    white,
    black,
    date,
    result: frame.result,
    rated: ratedValue(h),
    time_control:
      h.TimeControl && h.TimeControl !== '*' && h.TimeControl !== '-' ? h.TimeControl : null,
    plies: moves.length,
    moves,
    visits,
  };
}

export async function importPgnFiles(files, progress = () => {}, limits = LIMITS) {
  if (files.length > limits.files) throw new Error(`Choose at most ${limits.files} files.`);
  if (files.reduce((sum, f) => sum + encoder.encode(f.text).byteLength, 0) > limits.bytes)
    throw new Error('Files exceed the 10 MiB session limit.');
  const parsedFiles = [];
  const failures = [];
  const sources = [];
  for (const file of files) {
    sources.push({ name: file.name, sha256: file.sha256 || (await sha256(file.text)) });
    try {
      parsedFiles.push({ name: file.name, frames: framePgn(file.text, limits) });
    } catch (error) {
      if (error instanceof ImportLimitError) throw error;
      failures.push({ file: file.name, reason: error.message });
    }
  }
  const total = parsedFiles.reduce((sum, file) => sum + file.frames.length, 0);
  if (total > limits.games)
    throw new Error(`Session exceeds ${limits.games} games. No partial session was imported.`);
  const groups = new Map();
  const rejected = [];
  const keyCache = new Map();
  let processed = 0;
  for (const file of parsedFiles) {
    for (let ordinal = 0; ordinal < file.frames.length; ordinal++) {
      const source = { file: file.name, ordinal: ordinal + 1 };
      try {
        const record = await parseGame(file.frames[ordinal], keyCache);
        const key = `${record.provider}:${record.id}`;
        const group = groups.get(key);
        if (!group) groups.set(key, { record, occurrences: [source], conflict: false });
        else {
          group.occurrences.push(source);
          if (group.record.fingerprint !== record.fingerprint) group.conflict = true;
        }
      } catch (error) {
        rejected.push({ ...source, reason: error.message });
      }
      processed++;
      if (processed % 20 === 0 || processed === total) {
        progress({ processed, total });
        await new Promise((resolve) => setTimeout(resolve, 0));
      }
    }
  }
  const records = [];
  let duplicates = 0;
  let conflicts = 0;
  for (const group of groups.values()) {
    if (group.conflict) {
      conflicts += group.occurrences.length;
      group.occurrences.forEach((source) => {
        rejected.push({ ...source, reason: 'conflicting_game_identity' });
      });
    } else {
      records.push(group.record);
      duplicates += group.occurrences.length - 1;
    }
  }
  const players = {};
  records.forEach((record) => {
    players[record.provider] ||= new Map();
    for (const color of ['white', 'black']) {
      const key = fold(record[color]);
      if (!players[record.provider].has(key))
        players[record.provider].set(key, { key, name: record[color], white: 0, black: 0 });
      players[record.provider].get(key)[color]++;
    }
  });
  return {
    records,
    players: Object.fromEntries(
      Object.entries(players).map(([provider, entries]) => [
        provider,
        [...entries.values()].sort((a, b) => a.key.localeCompare(b.key)),
      ]),
    ),
    stats: {
      seen: total,
      accepted: records.length,
      duplicates,
      conflicts,
      rejected: rejected.length - conflicts,
      failed_files: failures.length,
    },
    rejected,
    failures,
    sources,
  };
}

export function analyzeGames(records, aliases, reference, options = {}) {
  const included = [];
  const counts = {
    unmatched_player: 0,
    black_games: 0,
    date: 0,
    time_control: 0,
    rated: 0,
    short_comparison: 0,
  };
  for (const record of records) {
    const name = aliases[record.provider];
    if (!name || fold(record.white) !== fold(name)) {
      if (name && fold(record.black) === fold(name)) counts.black_games++;
      else counts.unmatched_player++;
      continue;
    }
    if (
      (options.since || options.until) &&
      (!record.date ||
        (options.since && record.date < options.since) ||
        (options.until && record.date > options.until))
    ) {
      counts.date++;
      continue;
    }
    if (
      options.time_control &&
      options.time_control !== 'all' &&
      (record.time_control || 'unknown') !== options.time_control
    ) {
      counts.time_control++;
      continue;
    }
    if (
      options.rated &&
      options.rated !== 'all' &&
      (record.rated === null ? 'unknown' : String(record.rated)) !== options.rated
    ) {
      counts.rated++;
      continue;
    }
    if (options.minimum20 && record.plies < 20) {
      counts.short_comparison++;
      continue;
    }
    included.push(record);
  }
  const denominator = included.length;
  const ids = reference.ids;
  const ranks = new Map(ids.map((id, i) => [id, i]));
  const prefixes = new Set();
  const continuingPrefixes = new Set();
  const endpoints = new Set();
  ids.forEach((id) => {
    (reference.positions[id]?.routes || []).forEach((route) => {
      const moves = route.uci.split(' ');
      endpoints.add(route.uci);
      for (let i = 1; i <= moves.length; i++) {
        prefixes.add(moves.slice(0, i).join(' '));
        continuingPrefixes.add(moves.slice(0, i - 1).join(' '));
      }
    });
  });
  const hits = Array(ids.length).fill(0);
  const positionMap = new Map();
  const departureCounts = new Map();
  let reachedWindow = 0;
  let leaves = 0;
  let reenters = 0;
  for (const record of included) {
    if (record.visits.length) reachedWindow++;
    let firstRank = Infinity;
    const seenPositions = new Set();
    for (const visit of record.visits) {
      firstRank = Math.min(firstRank, ranks.get(visit.id) ?? Infinity);
      if (seenPositions.has(visit.id)) continue;
      seenPositions.add(visit.id);
      if (!positionMap.has(visit.id))
        positionMap.set(visit.id, {
          id: visit.id,
          position_key: visit.position_key,
          games: 0,
          loops: 0,
          routes: new Map(),
          in_reference: ranks.has(visit.id),
        });
      const position = positionMap.get(visit.id);
      position.games++;
      if (visit.route_has_repeat) position.loops++;
      else {
        if (!position.routes.has(visit.route))
          position.routes.set(visit.route, { uci: visit.route, san: visit.san_route, games: 0 });
        position.routes.get(visit.route).games++;
      }
    }
    if (Number.isFinite(firstRank)) hits[firstRank]++;
    if (prefixes.size) {
      let departure = -1;
      for (let i = 0; i < Math.min(20, record.moves.length); i++) {
        // An example's endpoint does not prescribe its continuation.
        const previous = record.moves.slice(0, i).join(' ');
        if (endpoints.has(previous) || !continuingPrefixes.has(previous)) break;
        if (!prefixes.has(record.moves.slice(0, i + 1).join(' '))) {
          departure = i;
          break;
        }
      }
      if (departure >= 0) {
        leaves++;
        const ply = departure + 1;
        departureCounts.set(ply, (departureCounts.get(ply) || 0) + 1);
        if (record.visits.some((v) => v.ply > ply && ranks.has(v.id))) reenters++;
      }
    }
  }
  let covered = 0;
  const coverage = hits.map((added, i) => {
    covered += added;
    return {
      n: i + 1,
      games: covered,
      share: denominator ? covered / denominator : null,
      additional_games: added,
    };
  });
  const all = [...positionMap.values()];
  const positions = all
    .sort((a, b) => b.games - a.games || a.id.localeCompare(b.id))
    .slice(0, 20)
    .map((p) => {
      const routes = [...p.routes.values()].sort(
        (a, b) => b.games - a.games || a.uci.localeCompare(b.uci),
      );
      const acyclic = p.games - p.loops;
      return {
        ...p,
        frequency: denominator ? p.games / denominator : null,
        acyclic_routes: routes.length,
        alternative_route_share: acyclic ? 1 - routes[0].games / acyclic : null,
        routes: routes.slice(0, 3).map((r) => ({ ...r, share: r.games / p.games })),
      };
    });
  return {
    contract_version: CONTRACT_VERSION,
    denominator_games: denominator,
    games_reaching_window: reachedWindow,
    games_shorter_than_window: denominator - reachedWindow,
    excluded: counts,
    recurring_positions: all.filter((p) => p.games >= 2).length,
    distinct_positions: all.length,
    coverage,
    covered_games: covered,
    coverage_share: denominator ? covered / denominator : null,
    leaves_selected_routes_games: leaves,
    reenters_reference_games: reenters,
    first_departures: [...departureCounts]
      .sort((a, b) => a[0] - b[0])
      .map(([ply, games]) => ({ ply, games })),
    positions,
  };
}
