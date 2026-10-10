// Bounded, authored-fixture performance evidence. No files from an account or network.
import assert from 'node:assert/strict';
import {readFileSync, writeFileSync} from 'node:fs';
import {performance} from 'node:perf_hooks';
import {LIMITS, framePgn, importPgnFiles, analyzeGames} from '../site/assets/game-import-core.mjs';
const fixture = readFileSync(new URL('../tests/fixtures/imports/authored-games.pgn', import.meta.url), 'utf8');
const first = fixture.slice(0, fixture.indexOf('[Event', 1));
const results = [];
for (const games of [100, 1000, LIMITS.games]) {
  const text = Array.from({length: games}, (_, index) => first.replace('90000001', String(91000000 + index))).join('\n');
  assert(Buffer.byteLength(text) <= LIMITS.bytes);
  const start = performance.now();
  const imported = await importPgnFiles([{name: `authored-${games}.pgn`, text}]);
  const importedAt = performance.now();
  assert.equal(imported.stats.accepted, games);
  const visits = imported.records[0].visits;
  const reference = {ids: visits.map(v => v.id), positions: Object.fromEntries(visits.map(v => [v.id, {routes: [{uci: v.route}]}]))};
  const analysis = analyzeGames(imported.records, {chesscom: 'ExampleWhite'}, reference);
  assert.equal(analysis.covered_games, games);
  results.push({games, bytes: Buffer.byteLength(text), import_seconds: +( (importedAt - start) / 1000).toFixed(3),
    analysis_seconds: +((performance.now() - importedAt) / 1000).toFixed(3), accepted: imported.stats.accepted,
    covered_games: analysis.covered_games, process_rss_bytes: process.memoryUsage().rss});
}
assert.throws(() => framePgn(first.repeat(LIMITS.games + 1)), /Game limit/);
const evidence = {kind: 'authored_fixture_import_performance', runtime: process.version, platform: process.platform,
  architecture: process.arch, limits: LIMITS, results,
  scope: 'Node core replay on repeated authored 20-ply games with unique native IDs. Browser worker limits remain enforced; long-game/device performance is not inferred.'};
if (process.argv[2]) writeFileSync(process.argv[2], JSON.stringify(evidence, null, 2) + '\n');
console.log(JSON.stringify(evidence));
