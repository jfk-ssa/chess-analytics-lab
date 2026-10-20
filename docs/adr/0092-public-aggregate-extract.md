# 0092. Public aggregate extract for a hosted read-only dashboard

- Status: accepted on merge
- Date: 2026-10-20

## Motivation

The local dashboard opens the August analytical warehouse. Bulk DuckDB
snapshots stay gitignored. The opening-corpus index is recorded at 141.8
MB, above GitHub's 100 MiB file limit, and those warehouses contain game
and player grain. A hosted read-only app cannot ship them, and it cannot
run dbt or MetricFlow. The homepage pipeline count and the August prefix
counts are different lineage stages. Putting them in one total would
describe a population this repository has not measured.

## Decision

Commit identifier-free aggregates in
`data/public/dashboard_extract.json`. `scripts/build_public_extract.py`
builds that file. `chess_analytics.public_extract` reads it with the
standard library and can register the tables in an in-memory DuckDB
connection. This record does not add the hosted app. The local dashboard
is unchanged.

The file is JSON with sorted keys, stable row order, and no build
timestamp. The reader loads it with the standard library. DuckDB is used
only when a caller wants SQL. A two-write check of DuckDB 1.5.6 Parquet
was byte-stable on a one-row table, so Parquet was not rejected for
timestamps. JSON is the committed form because a reviewer can see the
aggregates in the diff and the hosted app does not depend on a Parquet
writer. The size budget is 256 KiB. `data/` stays gitignored except
`data/README.md` and `data/public/dashboard_extract.json`.

### Lineage

Two lineages are stored and are not added together.

- `opening_corpus` is the training index in
  `reports/opening-corpus.json`. Its total is 1,042,346 games. The
  2026-08 slice inside that index is a training-filter count, not the
  August prefix.
- `m3_august_prefix` is the ordered 2026-08-01 prefix: 100,000 seen,
  99,467 accepted, 99,117 eligible, and 99,117 known-opening games.
  Within this lineage, seen partitions into accepted and excluded, and
  accepted partitions into marked bots, unknown results, and eligible
  games. That partition is not a bridge to the opening corpus.

### Where each number comes from

The committed aggregates are copied from reviewed reports:
`opening-corpus.json`, `M3-source-manifest.json`,
`M3-analytical-manifest.json`, `M3-independent-reference.json`, and
`M4-figures.json`.

On 2026-10-20 the extract was rebuilt with MetricFlow from mart
`9d3ca923a6f1cd06d82a8645`. Live counts matched the committed reference.
`game_draw_rate`, `opening_usage`, and both `opening_player_score`
receipts (French Defense and Sicilian Defense) are `metricflow` and
carry that mart's `mart_id`, `model_sha256`, and
`semantic_manifest_sha256`. The four `clock_pressure_error_proxy`
buckets are `reviewed_sql`. Adjusted score, its bootstrap, and the
lineage counts stay `committed_report` with null identity fields.

A checkout without the warehouse reprints the skipped steps. It writes
the same aggregate rows with `committed_report` and null identity. It
does not reproduce the raised labels. The builder relabels a receipt
only when the live count matches the committed reference, and it does
not replace aggregate rows.

- `game_draw_rate`, `opening_usage`, and `opening_player_score` may
  become `metricflow` when `resolve_governed` returns a matching mart,
  or `reviewed_sql` when the reviewed SQL matches and MetricFlow does
  not. The player-score receipt numerator is wins plus half the draws.
  The cell table keeps wins, draws, and losses separate.
- `clock_pressure_error_proxy` may become `reviewed_sql`. It has no
  governed source: `fact_move` is not a dbt model.
- `opening_adjusted_score` and `opening_adjusted_score_bootstrap` stay
  `committed_report`. The adjustment and the seeded cluster bootstrap
  are outside MetricFlow ([ADR 0085](0085-governed-semantic-layer-metricflow.md)).

A clock, adjusted-score, or bootstrap receipt labeled `metricflow` is
a build error.

### Privacy

The extract is aggregates only. Column names and string values must not
carry `player_key`, `game_id`, `headers_json`, fingerprints, usernames,
absolute paths, or PGN paths. Opening names, rating bands, and time
controls stay because they are the published categories.

Lichess game data is CC0. The elite month inside the opening corpus is
the curated subset published by nikonoel. The elite lineage note names
nikonoel so a hosted app can credit that curator from the extract alone.
The extract does not copy the publisher URL or a local path.

## Consequences

The hosted app can depend on Streamlit and DuckDB and read this file.
It does not need the `dbt` extra. Rebuilding without `data/` reprints
the skipped warehouse steps and writes the same aggregate rows.
Receipt labels and mart identity match the committed file only when
that rebuild finds the same matching mart. The local six-view
dashboard still reads the warehouse.
