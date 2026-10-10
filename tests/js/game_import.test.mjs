import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {test} from 'node:test';
import {Chess} from '../../site/assets/vendor/chess-1.4.0.mjs';
import {LIMITS, framePgn, parseGame, importPgnFiles, analyzeGames, positionKey} from '../../site/assets/game-import-core.mjs';
const fixture = readFileSync(new URL('../fixtures/imports/authored-games.pgn', import.meta.url), 'utf8');
const duplicate = readFileSync(new URL('../fixtures/imports/annotated-duplicate.pgn', import.meta.url), 'utf8');
const files = [{name: 'authored-games.pgn', text: fixture}];
const aliases = {chesscom: 'examplewhite', lichess: 'ExampleWhite', pgn: 'EXAMPLEWHITE'};
const first = fixture.split('\n\n')[0] + '\n\n1.d4 Nf6 2.c4 e6 3.Nf3 d5 4.g3 Be7 1-0\n';
function reference(records) {
  const visits = records.slice(0, 2).map(record => record.visits[0]);
  assert.equal(visits[0].id, visits[1].id);
  return {ids: [visits[0].id], positions: {[visits[0].id]: {routes: visits.map(v => ({uci: v.route}))}}};
}

test('two providers and generic PGN replay fully; annotations do not duplicate games', async () => {
  const result = await importPgnFiles([...files, {name: 'duplicate.pgn', text: duplicate}]);
  assert.deepEqual(result.stats, {seen: 6, accepted: 5, duplicates: 1, conflicts: 0, rejected: 0, failed_files: 0});
  assert.deepEqual(result.records.map(r => r.provider), ['chesscom', 'lichess', 'chesscom', 'lichess', 'pgn']);
  assert.equal(result.records[0].id, 'live:90000001');
  assert.equal(result.records[1].id, 'fixture2');
  assert.equal(result.records[0].rated, null); // Do not guess rated status from Chess.com branding.
  assert.equal(result.records[1].rated, true);
  assert.equal(result.records[3].rated, false);
  assert.equal(result.records[2].visits.length, 0);
  assert.equal(result.records[4].visits[2].route_has_repeat, true);
});

test('personal denominators include short White games and coverage is a union', async () => {
  const {records} = await importPgnFiles(files);
  const ref = reference(records);
  const result = analyzeGames(records, aliases, ref);
  assert.equal(result.denominator_games, 4);
  assert.equal(result.excluded.black_games, 1);
  assert.equal(result.games_reaching_window, 3);
  assert.equal(result.covered_games, 2);
  assert.equal(result.coverage_share, 0.5);
  assert.equal(result.leaves_selected_routes_games, 1); // Reaching a six-ply route endpoint is not a departure.
  const narrower = structuredClone(ref);
  narrower.positions[narrower.ids[0]].routes = narrower.positions[narrower.ids[0]].routes.slice(0, 1);
  const otherOrder = analyzeGames(records, aliases, narrower);
  assert.equal(otherOrder.leaves_selected_routes_games, 3); // The short d4 d5 game also leaves the Nf6-only example.
  assert.equal(otherOrder.reenters_reference_games, 1);
  const overlapping = structuredClone(narrower);
  overlapping.ids.push('longer-example');
  overlapping.positions['longer-example'] = {routes: [{uci: narrower.positions[narrower.ids[0]].routes[0].uci + ' b1c3 f8b4'}]};
  assert.equal(analyzeGames(records, aliases, overlapping).leaves_selected_routes_games, 3); // A shorter endpoint still stops comparison when another example continues.

  assert.equal(result.coverage[0].additional_games, 2);
  const shared = result.positions.find(p => p.id === ref.ids[0]);
  assert.equal(shared.games, 2);
  assert.equal(shared.acyclic_routes, 2);
  assert.equal(shared.alternative_route_share, 0.5);
  assert.equal(shared.frequency, 0.5);
  const comparison = analyzeGames(records, aliases, ref, {minimum20: true});
  assert.equal(comparison.denominator_games, 3);
  assert.equal(comparison.excluded.short_comparison, 1);
  assert.equal(comparison.coverage_share, 2 / 3);
});

test('aliases stay provider scoped, empty denominators remain unavailable', async () => {
  const {records} = await importPgnFiles(files);
  const ref = reference(records);
  const result = analyzeGames(records, {lichess: 'ExampleWhite'}, ref);
  assert.equal(result.denominator_games, 1);
  assert.equal(result.excluded.unmatched_player, 3);
  assert.equal(result.excluded.black_games, 1);
  assert.equal(analyzeGames(records, {}, ref).coverage_share, null);
  assert.equal(analyzeGames(records, aliases, ref, {rated: 'true'}).denominator_games, 1);
  assert.equal(analyzeGames(records, aliases, ref, {time_control: '300'}).denominator_games, 2);
  assert.equal(analyzeGames(records, aliases, ref, {since: '2026-10-02', until: '2026-10-02'}).denominator_games, 1);
});

test('conflicting native IDs withhold both versions, including annotated copies', async () => {
  const conflict = duplicate.replace('[Result "1-0"]', '[Result "0-1"]').replace(/1-0\s*$/, '0-1');
  const result = await importPgnFiles([...files, {name: 'duplicate.pgn', text: duplicate}, {name: 'conflict.pgn', text: conflict}]);
  assert.deepEqual(result.stats, {seen: 7, accepted: 4, duplicates: 0, conflicts: 3, rejected: 0, failed_files: 0});
  assert.equal(result.records.some(r => r.id === 'live:90000001'), false);
  assert.equal(result.rejected.filter(r => r.reason === 'conflicting_game_identity').length, 3);
});

test('PGN framing handles comments, escaped tags, variations and results inside annotations', () => {
  const text = '[Event "A \\"quoted\\" event"]\n[White "W"]\n[Black "B"]\n[Result "1-0"]\n\n1.e4 {0-1 [Event "false"]} e5 (1...c5 (1...e6))\n; 1/2-1/2\n2.Nf3 $1 Nc6 1-0\n';
  const [game] = framePgn(text);
  assert.equal(game.headers.Event, 'A "quoted" event');
  assert.deepEqual(game.moves, ['e4', 'e5', 'Nf3', 'Nc6']);
  assert.equal(game.result, '1-0');
  assert.throws(() => framePgn(text + '{bad'), /Unclosed/);
  assert.throws(() => framePgn(text + '('), /Unclosed/);
  assert.throws(() => framePgn(') ' + text), /Unmatched/);
});

test('unsupported setups, variants, incomplete games and illegal tails are visible rejections', async () => {
  const samples = [
    ['unsupported_variant', '[Variant "Chess960"]\n' + first],
    ['unsupported_setup', '[SetUp "1"]\n' + first],
    ['unfinished_or_missing_result', first.replace('[Result "1-0"]', '[Result "*"]').replace(/1-0\s*$/, '*')],
    ['conflicting_result', first.replace('[Result "1-0"]', '[Result "0-1"]')],
    ['illegal_or_invalid_mainline', first.replace('4.g3 Be7', '4.Ke4 Be7')],
    ['duplicate_header', '[White "Other"]\n' + first],
    ['conflicting_provider_headers', first.replace('[Site "Chess.com"]', '[Site "https://lichess.org/fixture1"]')],
  ];
  for (const [reason, text] of samples) {
    const result = await importPgnFiles([{name: 'rejection.pgn', text}]);
    assert.equal(result.stats.accepted, 0, reason);
    assert.equal(result.rejected[0].reason, reason);
  }
  const tail = first.replace(/1-0\s*$/, '5.Bg2 O-O 6.O-O c5 7.dxc5 Bxc5 8.Nc3 Nc6 9.Bg5 h6 10.Bxf6 Qxf6 11.Ke4 1-0');
  const result = await importPgnFiles([{name: 'illegal-tail.pgn', text: tail}]);
  assert.equal(result.rejected[0].reason, 'illegal_or_invalid_mainline'); // Full game, not just the study window.
});

test('failed framing imports no partial file, caps reject rather than truncate', async () => {
  const result = await importPgnFiles([...files, {name: 'bad.pgn', text: fixture + '\n{unclosed'}]);
  assert.equal(result.stats.accepted, 5);
  assert.equal(result.stats.failed_files, 1);
  await assert.rejects(() => importPgnFiles([{name: 'a', text: first}, {name: 'b', text: first}], () => {}, {...LIMITS, games: 1}), /No partial/);
  await assert.rejects(() => importPgnFiles(files, () => {}, {...LIMITS, games: 1}), /No partial/);
  await assert.rejects(() => importPgnFiles(files, () => {}, {...LIMITS, bytes: 1}), /10 MiB/);
  assert.throws(() => framePgn(first, {...LIMITS, plies: 2}), /move limit/);
  assert.throws(() => framePgn('('.repeat(33)), /nested too deeply/);
});

test('canonical keys preserve castling and legal EP, exclude draw counters and pinned EP', () => {
  const board = new Chess('4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 1');
  assert.equal(positionKey(board).split(' ').at(-1), 'd6');
  const pinned = new Chess('k3r3/8/8/3pP3/8/8/8/4K3 w - d6 0 1');
  assert.equal(positionKey(pinned).split(' ').at(-1), '-');
  assert.equal(positionKey(board), positionKey(new Chess(board.fen().split(' ').slice(0, 4).join(' ') + ' 12 8')));
  assert.notEqual(positionKey(new Chess()), positionKey(new Chess(new Chess().fen().replace('KQkq', '-'))));
});

test('Unicode header content remains data, generic IDs ignore annotations and promotion is legal', async () => {
  const text = first.replace('[Site "Chess.com"]', '[Site "Local"]')
    .replace(/^\[Link .+\]\n/m, '').replace('[White "ExampleWhite"]', '[White "<img src=x onerror=alert(1)>"]');
  const record = await parseGame(framePgn(text)[0]);
  assert.equal(record.white, '<img src=x onerror=alert(1)>');
  assert.equal(record.provider, 'pgn');
  const annotated = await parseGame(framePgn(text.replace('1.d4', '1.d4 {comment}'))[0]);
  assert.equal(record.id, annotated.id);
  assert.equal(record.fingerprint, annotated.fingerprint);
  const game = new Chess();
  const moves = 'a4 h5 a5 h4 a6 h3 axb7 hxg2 bxa8=Q'.split(' ');
  moves.forEach(move => game.move(move, {strict: true}));
  assert.equal(game.get('a8').type, 'q');
});
