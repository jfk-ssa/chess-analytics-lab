# 0085. Governed MetricFlow semantic layer

- Status: proposed, accepted on merge
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

Give each core metric one dbt 1.12 semantic definition. `dbt parse` and
`mf validate-configs` check it. `query_metric` reads it when the semantic
manifest and the built tables are present, and otherwise keeps the reviewed
SQL. The tool returns the same keys and values, so evidence IDs, existing
evals, and the pinned MCP example stay put. The MCP allowlist is unchanged.

[ADR 0006](0006-m2-dbt-and-mart-recovery.md) still says to pin
`dbt-duckdb==1.10.1`. That sentence is stale. The optional `dbt` extra pins
`dbt-duckdb==1.11.0`, and the lock resolves `dbt-core` 1.12.5. This record
does not edit ADR 0006. The same extra now also pins `dbt-metricflow==0.15.0`,
which brings `metricflow` 0.213.0. The CLI is `mf`, from `dbt-metricflow`,
not from `dbt-core`.

The semantic YAML uses the current spec only: `semantic_model` under the
model, entities and dimensions on columns, time granularity on the column,
simple metrics with `agg` and `expr`, and ratio metrics with `numerator` and
`denominator`.

### Models

`games` is one row per accepted game. `game_key` is `provider || ':' ||
game_id`, because a composite key cannot be the primary entity. Staging now
carries `rated` and `variant`. `opening_family` is
`nullif(trim(split_part(source_opening, ':', 1)), '')`. A null `utc_date`
stays null. Queries that do not group by time do not constrain it, and the
model does not invent a date.

`player_games` is one row per player in a game. MetricFlow requires a primary
entity, so `player_game_key` is that entity and `game_key` is a foreign
`game` entity. The build copies opening family, base seconds, and increment
onto the player row, so a score filter does not depend on a query-time join.
`rating_band` is a closed 200-point band (`1400-1599`). `rating` is also a
categorical dimension, because the contract's half-open range is not a band.

`metricflow_time_spine` is one row per day from 2012-01-01 through
2030-12-31. It exists so a later time query can compile. The analyst does not
group these metrics by date.

`mart_game_outcomes` and its reconciliation are unchanged. The semantic
eligible flag is separate from `metric_eligible`.

### Metrics

- `eligible_games`, `drawn_games`, `known_opening_games`, and
  `unknown_opening_games` are sums on `games`. The eligible flag is rated,
  Standard, completed, and not a source-marked bot.
- `game_draw_rate` is `drawn_games / eligible_games`.
- `opening_usage` is declared as `known_opening_games / known_opening_games`.
  A where filter applies to both inputs, so a filtered ratio is 1 whenever
  the family has any games. The analyst therefore queries
  `known_opening_games` twice, once with the family filter and once without,
  and divides in Python.
- `opening_player_score` is `opening_score_total / opening_score_games` on
  `player_games`. `win_rate` uses the same denominator. Wins, draws, and
  losses are supporting sums so the tool can return the contract's counts.
- `low_support` (fewer than 100 player-games) and a null value when the
  denominator is 0 stay in the analyst. MetricFlow has no native flag for
  either. The compiled draw-rate SQL uses `NULLIF`, and the tool applies the
  same empty-denominator rule.

### Out of scope

`clock_pressure_error_proxy` and `evaluation_coverage` read `fact_move`. dbt
does not build that table. `opening_adjusted_score` is a seeded cluster
bootstrap, which is not a MetricFlow metric.

### Analyst

`src/chess_analytics/analyst/semantic.py` resolves only
`game_draw_rate`, `opening_usage`, and `opening_player_score`. Anything else,
including a filter shape the semantic query cannot express, returns to the
existing SQL. A missing manifest, a missing `mf` binary, or a warehouse
without `games`, `player_games`, and `metricflow_time_spine` does the same.
Compiled SQL qualifies the catalog `"warehouse"`, which is the DuckDB file
stem, so the file has to be named `warehouse.duckdb`.

`mf` calls `UpdateChecker` on every invocation. That checker GETs
`https://pypi.org/pypi/dbt-metricflow/json` with a one-second timeout. A
`RequestException` comes back as `{"success": false}`, `check` returns
`None`, and the command continues. There is no environment switch to skip
the request. The subprocess sets `https_proxy` and `http_proxy` to
`http://127.0.0.1:9`, and clears `no_proxy`, so the request fails closed.
`DBT_SEND_ANONYMOUS_USAGE_STATS=false` and `DO_NOT_TRACK=1` are set as well.
In this install, MetricFlow telemetry is a Python log handler. The
`metricflow` and `dbt_metricflow` trees contain no Snowplow client.

Mart identity already hashes every `dbt/**/*.sql` and `*.yml` file. Semantic
YAML changes the mart id. That is the existing rule.

## Impact

`query_metric` keeps its result shape. Compare-openings and the clock tools
are untouched, and the clock tools never take the semantic path. Existing
eval manifests are not edited. One new replay plan,
`evals/replay_plans/governed_draw_rate.json`, asks the draw-rate question and
is not part of the engine-v1 digest. The offline workflow parses the project,
validates the manifest, and queries the tiny mart with the proxy set.

## Implementation steps

1. Pass `rated`, `variant`, `game_key`, and `opening_family` through staging.
   Add `rating_band` and `player_game_key` on player games.
2. Add `games`, `player_games`, and `metricflow_time_spine`, with singular
   tests that the family and the band match the source expressions.
3. Add the semantic models and metrics in `dbt/models/marts/_semantic.yml`.
4. Resolve the three governed metrics in `semantic.py` and call it from
   `query_metric` before the SQL branches.
5. Pin `dbt-metricflow==0.15.0`, refresh `uv.lock`, and record the new
   licenses in `THIRD_PARTY_NOTICES.md`.

## Limits

The semantic path and the SQL path agree on published snapshots, where every
game is rated Standard. A warehouse that broke that publication check would
make the semantic eligible flag smaller than the analyst SQL. This lab does
not query such a warehouse.

The filtered `opening_usage` ratio metric is not the contract. The contract
value is the two-query division. Time-grouped queries are not part of the
tool. `fact_move` metrics and the cluster bootstrap stay outside MetricFlow.
`low_support` and the zero-denominator null stay in Python.

## Results

Measured on 2026-10-18 against the current models. `dbt parse` succeeded.
`mf validate-configs --skip-dw`, with the closed proxy set, reported
`ERRORS: 0, FUTURE_ERRORS: 0, WARNINGS: 0`.

Tiny fixture, `mf query --metrics drawn_games,eligible_games,game_draw_rate`:

- `4,20,0.2`

`mf query --explain --metrics game_draw_rate` compiled:

```sql
SELECT
  CAST(SUM(drawn_game) AS DOUBLE) / CAST(NULLIF(SUM(eligible_game), 0) AS DOUBLE) AS game_draw_rate
FROM "warehouse"."main"."games" games_src_10000
```

The statement does not mention `utc_date`. The source alias is generated.
After one eligible game's `utc_date` was set to null, the same query still
returned `4,20,0.2`.

Portfolio fixture (`tests/fixtures/portfolio_annotated.pgn`):

- Draw rate: 1 drawn, 4 eligible
- Known openings: 4. Unknown openings: 0
- Sicilian Defense and French Defense: 2 games each
- Sicilian, white, rating `[1400, 1600)`, 60+0: 1 win, 0 draws, 1 loss,
  score sum 1.0, score rate 0.5, win rate 0.5
- French, same cohort: 1 win, 1 draw, 0 losses, score sum 1.5, score rate
  0.75, win rate 0.5

A filtered ratio query, `opening_usage` where the family is Sicilian Defense,
returned `opening_usage=1.0` and `known_opening_games=2`. The contract usage
is 2/4. That is why the analyst does not use the filtered ratio.

Update check, bypassing the one-hour cache:

- Direct `query_pypi("dbt-metricflow")` returned version 0.15.0 in 0.025 s.
  `UpdateChecker.check` then returned `None`.
- The same call through `https_proxy=http://127.0.0.1:9` returned
  `{"success": false}` in 0.001 s.
- With that proxy set, `mf query` of the tiny draw rate still exited 0 and
  returned `4,20,0.2`.
