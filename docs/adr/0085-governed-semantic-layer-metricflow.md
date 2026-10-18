# 0085. Governed MetricFlow semantic layer

- Status: accepted on merge
- Date: 2026-10-18

## Motivation

The same metric is written in three places: prose in
[docs/METRICS.md](../METRICS.md), a JSON contract, and SQL. The analyst's
draw-rate query in `CheckedTools.query_metric` omits the rated and variant
filter and the unknown-result and marked-bot counters that
`metrics/draw_rate.sql` reports. On a published snapshot those filters do not
change the count, because publication already keeps only rated Standard
games. The definitions still disagree, and an AI analyst can read only the
copy it is given.

## Decision

Give each core metric one dbt 1.12 semantic definition. MetricFlow compiles
the query in-process. The compiled statement runs on a read-only connection
to the published mart. `query_metric` uses that result only when the mart
matches this analytical snapshot. Any other case keeps the reviewed SQL and
returns the same keys, so evidence IDs, existing evals, and the pinned MCP
example stay put. The MCP allowlist is unchanged. The analytical snapshot is
never modified.

[ADR 0006](0006-m2-dbt-and-mart-recovery.md) still says to pin
`dbt-duckdb==1.10.1`. That sentence is stale. The optional `dbt` extra pins
`dbt-duckdb==1.11.0`, and the lock resolves `dbt-core` 1.12.5. This record
does not edit ADR 0006. `metricflow` 0.213.0 is already a dependency of
`dbt-core`. The `dbt` extra does not pin `dbt-metricflow`. There is no `mf`
CLI on this path.

The semantic YAML uses the current spec only: `semantic_model` under the
model, entities and dimensions on columns, time granularity on the column,
simple metrics with `agg` and `expr`, and ratio metrics with `numerator` and
`denominator`.

### Which warehouse

`CheckedTools` opens the analytical snapshot. That file has `fact_move` and
does not have the semantic views. `games` and `player_games` live on the mart
built from the analytical snapshot's source. `published_mart` reads
`data/<dataset>-mart-current.json` for the dataset named on that source
snapshot, calls `validate_mart`, and requires both of the following:

- the mart `snapshot_id` equals the analytical manifest's `source_snapshot_id`
- the mart `model_sha256` equals `model_hash(project)`

The mart also stores `semantic_manifest.json` and `model_hash.txt`.
`validate_mart` checks those digests against fields in the same mart
manifest. That sibling check is not enough: rewriting the semantic manifest
and `semantic_manifest_sha256` together still leaves `model_sha256` equal
to `model_hash(project)`. `published_mart` therefore parses the current
project and requires `digest(semantic_manifest.json)` to equal the digest
of that parse. The expected bytes come from the project models, which
`model_hash` already covers, not from a field stored beside the file.
The parsed digest is cached in process by `model_hash`. Embedding
`model_hash` inside the manifest and recomputing the outer checksum would
not stop an expression edit, so this record does not do that.

The transform command accepts `--dataset analytical`, which is the dataset
on a normal analytical source snapshot. A tiny or foundation mart is used
only when that source snapshot's dataset is tiny or foundation.

If no pointer exists, validation fails, the hashes differ, the stored
semantic manifest differs from the parse, MetricFlow cannot be imported, or
the query fails, `resolve_governed` returns none and the caller keeps the
reviewed SQL. A failed query includes `duckdb.Error` (`CatalogException`
inherits it, not `ValueError`). The log line is `semantic query failed;
using reviewed SQL`. It does not include the exception text, a path, or the
compiled statement. Tests that claim parity spy on `query_rows` and poison
a copy of the mart, so a silent fallback cannot pass.

### Models

`games` and `player_games` are views. `game_key` is `provider || ':' ||
game_id`, because a composite key cannot be the primary entity. Staging
carries `rated` and `variant`. `opening_family` is
`nullif(trim(split_part(source_opening, ':', 1)), '')`. A blank family is
null, so a source opening such as `: Foo` is unknown. A family whose text is
`None` is kept. The reviewed SQL uses the same expression. A null `utc_date`
stays null. Queries that do not group by time do not constrain it, and the
model does not invent a date.

`player_games` is one row per player in a game. MetricFlow requires a primary
entity, so `player_game_key` is that entity and `game_key` is a foreign
`game` entity. The view copies opening family, base seconds, and increment
onto the player row, so a score filter does not depend on a query-time join.
`rating` is a categorical dimension. There is no `rating_band`.

`metricflow_time_spine` is one row per day from 2012-01-01 through
2030-12-31. It is required by dbt parse. Deleting the model and parsing this
project produced `Parsing Error: The semantic layer requires a time spine
model with granularity DAY or smaller`. The analyst does not group these
metrics by date. With the spine present, an ungrouped draw-rate query still
does not mention `utc_date`. `utc_date` is the aggregation time dimension
because MetricFlow rejects a semantic model that has none.

`mart_game_outcomes` stays a table. A singular test checks that
`sum(games.eligible_game)` equals `sum(mart_game_outcomes.eligible_games)`.

### Metrics

- `eligible_games`, `drawn_games`, `known_opening_games`, and
  `unknown_opening_games` are sums on `games`. The eligible flag is rated,
  Standard, completed, and not a source-marked bot.
- `game_draw_rate` is `drawn_games / eligible_games`. The analyst returns
  that ratio as `value`. A zero denominator forces `value` to null.
- There is no `opening_usage` ratio. A where filter applies to both inputs,
  so a filtered ratio is 1 whenever the family has any games. The analyst
  queries `known_opening_games` twice, once with the family filter and once
  without, and divides in Python. A grouped query drops null families and
  zero `known_opening_games` rows before `LIMIT 501`, keeps a family
  literally named `None`, and sets `truncated` from the rows that remain.
- `opening_player_score` is `opening_score_total / opening_score_games` on
  `player_games`. `win_rate` uses the same denominator. Both ratios are the
  values the tool returns. Wins, draws, and losses are supporting sums.
- `low_support` (fewer than 100 player-games) stays in the analyst.
  MetricFlow has no native flag for it.

### Compile path

`MetricFlowEngine.explain` receives a client that only supplies the DuckDB
SQL renderer. `explain` does not open the mart. The compiled statement
qualifies the catalog `"warehouse"`, which is the DuckDB file stem, so the
mart file stays named `warehouse.duckdb`. DuckDB then runs that statement
with `read_only=True`. The engine is cached by the semantic-manifest digest
for the life of the process. A missing `metricflow` import is a fallback, so
the default install does not need the `dbt` extra to answer these metrics
from SQL.

### Mart identity

`mart_id` is the first 24 hex characters of the hash of `snapshot_id`,
`model_sha256`, and `lock_sha256`. `model_sha256` covers dbt SQL and YAML.
`lock_sha256` is `uv.lock`, so a lockfile change also changes the mart id.
`model_hash` skips `target`, `logs`, and `dbt_packages` only when that name
is the first path component under `dbt/`. A model directory named `target`
is part of the hash.

### What the manifest check stops

A same-directory edit of `semantic_manifest.json` plus
`semantic_manifest_sha256` cannot change a governed metric. The analyst
compares the stored file with a manifest parsed from the current project.
A local attacker who can rewrite the whole data directory and the project
models is out of scope: that person can change the reviewed SQL as well.
The check is not a signature over `data/`. It only refuses a rewrite that
leaves the project models, and therefore `model_hash`, unchanged.

### Out of scope

`clock_pressure_error_proxy` and `evaluation_coverage` read `fact_move`. dbt
does not build that table. `opening_adjusted_score` is a seeded cluster
bootstrap, which is not a MetricFlow metric.

## Impact

`query_metric` keeps its result shape. `compare_openings` calls
`query_metric("opening_player_score")` twice, so a matching mart puts that
comparison on the semantic path. The clock tools never do. Existing eval
manifests are not edited. One replay plan,
`evals/replay_plans/governed_draw_rate.json`, asks the draw-rate question and
is not part of the engine-v1 digest.

The offline workflow parses into a temporary target, validates that manifest
in-process, and runs `smoke-draw-rate` against the tiny mart. The dbt-extra
pytest job sets `CHESSLAB_REQUIRE_DBT=1`, so a skipped semantic test fails
that job. The default job still runs the pure-Python semantic tests and
skips the mart builds.

## Limits

The semantic path and the SQL path agree on published snapshots, where every
game is rated Standard. A warehouse that broke that publication check would
make the semantic eligible flag smaller than the analyst SQL. This lab does
not query such a warehouse. The reconcile test fails the mart build if the
two eligible counts diverge.

The semantic path runs only for a published mart whose source snapshot and
model hash match, and whose semantic manifest matches a parse of those
models. A missing mart, a stale manifest, a rewritten semantic manifest, or
a failed query falls back to SQL. That fallback is the product behavior.
Parity tests are not allowed to treat it as success. `metricflow_time_spine`
stays. Deleting it breaks dbt parse.

The filtered opening-usage value is the two-query division, not a semantic
ratio. Time-grouped queries are not part of the tool. `fact_move` metrics
and the cluster bootstrap stay outside MetricFlow. `low_support` and the
zero-denominator null stay in Python.

`compare_openings` is on this path. An earlier draft of this record said it
was untouched. That was wrong.

## Results

Measured on 2026-10-18 after the in-process resolver, on this checkout.

`dbt parse` of the project succeeded. `validate-configs` on the mart
manifest returned no blocking errors (`ERRORS: 0` from the module command
when the message list is empty). The same check is what the semantic tests
call.

Tiny product path, `CheckedTools` on an analytical snapshot whose source is
the tiny fixture, with one sampled game id so move publication can finish
and with openings `: Foo` and `None: Example` added:

- Draw rate `4, 20, 0.2`, equal to the SQL path, with at least one
  `query_rows` call.
- Family `None`: numerator 1, unknown openings 19. The grouped rows are
  `None` only. `: Foo` is not a family.
- After one eligible `utc_date` was set to null on a mart copy, the draw
  rate stayed `4, 20, 0.2`.
- A mart copy with every `1/2-1/2` result changed to `1-0` returned a
  different numerator from the SQL result's 4. The analytical warehouse
  digest did not change.
- The unpoisoned mart warehouse digest was identical before and after the
  queries.
- A mart manifest whose `model_sha256` does not match the sidecar falls
  back to the SQL result, and the spy sees no `query_rows` call for that
  fallback.
- Dropping the `games` view on a mart copy, then updating
  `warehouse_sha256` so `validate_mart` still passes, falls back to the
  SQL draw rate. The semantic log line is only `semantic query failed;
  using reviewed SQL`.
- Replacing the stored manifest expression `"drawn_game"` with
  `"eligible_game"` and rewriting `semantic_manifest_sha256` to match
  falls back to the SQL draw rate `4, 20, 0.2`. The spy sees no
  `query_rows` call. Before that parse check, the same test called
  `query_rows` on the rewritten manifest.

Portfolio fixture, same product path (`portfolio_demo` plus
`transform --dataset analytical`):

- Draw rate: 1 drawn, 4 eligible
- Sicilian Defense and French Defense: 2 games each, denominator 4
- Sicilian, white, rating `[1400, 1600)`, 60+0: score rate 0.5, `low_support`
  true
- French, same cohort: score rate 0.75, `low_support` true
- `compare_openings` for those two families called `query_rows` and returned
  the Sicilian score rate 0.5
- The portfolio mart warehouse digest was identical before and after

Wall time around `query_metric` in that test process:

| Call | Seconds |
|---|---|
| First tiny draw rate | 3.441 |
| Portfolio draw rate | 0.046 |
| Sicilian usage | 0.058 |
| French usage | 0.059 |
| Sicilian score | 0.080 |
| French score | 0.070 |
| `compare_openings` | 0.150 |

The first call in the process parses the project models and checks that
digest against the stored semantic manifest, then builds the semantic
lookup. Later calls with the same `model_hash` reuse that digest. These
are single-process measurements, not a benchmark suite.

The previous revision's `mf` CLI took about 2.4 seconds per query and opened
the warehouse read-write. That CLI is gone, so those timings and the PyPI
update-check timings in the earlier draft are one-off measurements of a
removed path. They are not reproduced here.

`tests/test_semantic_layer.py` passed 13 tests in 14.17 seconds, including
both product builds. With the `dbt` extra installed, `pytest -q` passed 232
tests and skipped 19 in 57.40 seconds. The skips are the existing optional
snapshots, not the semantic tests. Without the extra, the same command
passed 226 and skipped 25 in 26.76 seconds. `basedpyright` reported 0
errors in both environments.

`chesslab demo` on the tiny fixture reported accepted 22, eligible 20, drawn
4, value 0.2. `python -m chess_analytics.marts transform --dataset tiny` then
published mart `b7a77b24a77ae29ca5d7aef8` with dbt `created` 8 and `passed`
39. `games` and `player_games` are views in that warehouse.
`validate-configs` printed `ERRORS: 0`. `smoke-draw-rate` printed `4,20,0.2`.
