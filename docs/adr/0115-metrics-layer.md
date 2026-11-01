# 0115. Metrics layer for Streamlit KPIs and Pages cards

- Status: accepted
- Date: 2026-10-31

## Motivation

Win rate already appears in three shapes: MetricFlow `win_rate` on
`player_games` ([dbt/models/marts/_semantic.yml](../../dbt/models/marts/_semantic.yml)),
cube `result_cell` tallies in
[hosted/dashboard.py](../../hosted/dashboard.py) /
[src/chess_analytics/dashboard_cube.py](../../src/chess_analytics/dashboard_cube.py),
and opening-score receipts in the public extract. Draw rate is governed for
the analyst ([ADR 0085](0085-governed-semantic-layer-metricflow.md)) but the
hosted KPI strip still computes rates from Parquet cells. Clock pressure and
evaluation coverage read `fact_move`, which dbt does not build, so they stay
on reviewed SQL ([docs/METRICS.md](../METRICS.md)). Accuracy as a first-class
KPI is not defined. Job-search value is one definition consumed by Streamlit
and Pages, with a parity test.

## Decision

Extend the existing MetricFlow path. Do not replace it.

**MetricFlow on dbt-duckdb works at the pinned versions.** Evidence:

- `pyproject.toml` pins `dbt-duckdb==1.11.1`; `uv.lock` resolves `dbt-core`
  1.12.5 and `metricflow` 0.213.0 (also noted in ADR 0085).
- DuckDB is pinned at `duckdb==2.0.0` ([ADR 0110](0110-duckdb-2.md)).
- Semantic models and metrics already parse and query on published marts:
  `games`, `player_games`, `metricflow_time_spine`; ratios include
  `game_draw_rate`, `opening_player_score`, and `win_rate`.
- `CheckedTools.query_metric` / `resolve_governed` in
  `src/chess_analytics/analyst/` compile via MetricFlow and fall back to
  reviewed SQL. Offline smoke: `smoke-draw-rate`,
  `tests/test_semantic_layer.py`.

Because MetricFlow works, the path is **extend ADR 0085**. Add a thin dbt
model so move-level KPIs join that path instead of staying reviewed-SQL-only.

### Thin dbt `move_evals`

Add **proposed** `dbt/models/marts/move_evals.sql` (name fixed here) that
reads published `fact_move` as a dbt source (the analytical
`warehouse.duckdb` table and/or sibling `fact_move.parquet` from
`src/chess_analytics/corpus/publish.py`). Declare the source in
`dbt/models/staging/_sources.yml` (or a sibling sources file). The model
is a view or table of one row per provider/game_id/ply with the columns
needed for MetricFlow: keys, `utc_date` (from the game), `opening_family`,
`clock_bucket`, `phase_proxy`, `centipawn_deterioration`, evaluable flag,
and the existing error-proxy flag. MetricFlow semantic metrics on this
model own **mean centipawn loss** and **clock pressure / time trouble**.
Until the model merges, those ids may keep reviewed SQL behind
`query_metric`; after merge, `GOVERNED_METRICS` expands and exposures in
`dbt/models/exposures.yml` list the new metrics.

### Accuracy KPI: mean centipawn loss

| Field | Rule |
|---|---|
| Id (proposed) | `mean_centipawn_loss` |
| Grain | One evaluable move in `move_evals` (same sample as M3 `fact_move`) |
| Numerator input | `centipawn_deterioration` from `fact_move` / `moves.py`: `max(0, mover-perspective cp_before − cp_after)` |
| Clamp | Per-move contribution is `least(centipawn_deterioration, 1000)` before averaging. The 1000 cp cap stops a single annotated swing from dominating the mean; it is a contract constant, not a Lichess official. |
| Denominator | Count of **evaluable** moves: both before and after **centipawn** scores present (`eval_before_cp_white` and `eval_after_cp_white` not null). |
| Mate scores | `fact_move` stores `eval_*_mate_white` separately. `moves.py` only sets `centipawn_deterioration` when both cp fields are non-null, so mate-only or mate-transition plies already have null deterioration. Those plies are **excluded** from the mean (not zero). Mate transitions are counted separately for coverage reporting, matching `contracts/clock_pressure_error_proxy.json` and `contracts/evaluation_coverage.json`. |
| Missing evals | Null deterioration; excluded from denominator; never coerced to zero. |
| Aggregation | `sum(clamped_deterioration) / nullif(evaluable_moves, 0)`; zero denominator → null. |
| Units | Centipawns per evaluable move. |

### Scope and surfaces

| KPI | Today | Decision |
|---|---|---|
| Win rate | Semantic `win_rate` on `player_games`; cube `result_cell` wins/games | One contract + MetricFlow (or documented cube grain that matches the contract). Streamlit and Pages call the same id. |
| Draw rate | Already governed `game_draw_rate` | Wire hosted / Pages cards to the same receipt path used by the extract when the cut is global; filtered cube cuts stay grain-documented. |
| Accuracy | No contract | `mean_centipawn_loss` as above, MetricFlow on `move_evals`. |
| Time trouble | `clock_pressure_error_proxy` on analytical `fact_move` | Keep definition in `contracts/clock_pressure_error_proxy.json`. MetricFlow metric on `move_evals` after the thin model lands. |

Pages cards means the documentation-site metric / extract cards built via
`scripts/build_public_extract.py` and the site under `site/`. Streamlit KPIs
means the hosted strip in `hosted/dashboard.py` over
`data/public/dashboard_cube.parquet`.

### Data inputs (existing)

- dbt marts: `games`, `player_games`, `mart_game_outcomes`,
  `mart_player_outcomes`, `metricflow_time_spine`
  (`dbt/models/marts/`).
- Staging / intermediate: `stg_games`, `stg_player_games`,
  `int_game_eligibility`.
- Analytical warehouse (not yet dbt): `fact_game`, `fact_player_game`,
  `fact_move` (`contracts/tables.json`, `contracts/m3_tables.json`).
- Hosted cube grains: `game_cell`, `result_cell`, `clock_cell`, …
  (`scripts/build_dashboard_cube.py`, ADR 0101).
- Contracts: `contracts/game_draw_rate.json`,
  `opening_player_score.json`, `clock_pressure_error_proxy.json`,
  `evaluation_coverage.json`.
- Semantic allowlist today: `GOVERNED_METRICS` in
  `src/chess_analytics/analyst/semantic.py`
  (`game_draw_rate`, `opening_usage`, `opening_player_score`).

### Proposed additions

- Contract `contracts/mean_centipawn_loss.json` and MetricFlow metric
  `mean_centipawn_loss` on `move_evals`.
- dbt source pointing at published `fact_move` / `fact_move.parquet`, plus
  model `move_evals`.
- Shared Python facade used by `hosted/dashboard.py` and the Pages extract
  builder so both resolve ids through one module (MetricFlow when the mart
  matches; reviewed SQL otherwise)—same pattern as `resolve_governed`.
- Expand `GOVERNED_METRICS` / exposures for the new ids.

### PR slicing (~400 lines real code each)

1. **dbt source + `move_evals` model** + unit / singular tests; no semantic
   metrics yet beyond parse.
2. **Contracts + semantic YAML** for `mean_centipawn_loss` and clock-pressure
   on `move_evals`; win/draw alignment docs; tiny-mart reconcile vs reviewed
   SQL.
3. **Streamlit KPI strip** reads shared facade for the global (unfiltered)
   cards; filtered cube grains keep their captions.
4. **Pages / public extract** rebuild path uses the same facade; parity
   pytest compares Streamlit global numbers to extract receipts on the
   tiny or portfolio fixture.

Stacked drafts; one theme per PR ([CONTRIBUTING.md](../../CONTRIBUTING.md)).

## Consequences

### Evaluation and acceptance

- Offline parity test: for each governed KPI id in the showcase set, the
  Streamlit global value and the Pages / extract receipt agree within the
  contract's exact fraction or documented rounding. Drift fails CI.
- Clamp and mate exclusion for `mean_centipawn_loss` are asserted on a
  fixture that includes a >1000 cp swing and a mate-transition ply.
- Existing semantic tests keep passing; `CHESSLAB_REQUIRE_DBT=1` job still
  fails on skipped semantic coverage ([ADR 0113](0113-select-dbt-pytest.md)).
- `dbt parse` and `validate-configs` succeed with the expanded semantic
  manifest. Mart `model_sha256` / semantic digest rules from ADR 0085 stay.
- No live model calls. No rewrite of live-eval receipts.

### Risks

- Cube grains (`result_cell` per color / rating / opening) will not always
  match an unfiltered MetricFlow total. Acceptance is parity on documented
  cuts, not every sidebar filter.
- Adding `fact_move` into the mart increases build time and mart identity
  churn (`model_sha256`, `mart_id`).
- Source `%eval` quality varies; the accuracy contract must repeat the
  evaluation-coverage caveats.

### Out of scope

- Changing `live_runner.FROZEN_FILES` or historical receipts.
- Free-form SQL from the coach or dashboard.
- Replacing the Parquet cube with a live warehouse open on Streamlit Cloud.
- Causal time-pressure claims.
- Independent Stockfish re-annotation of the corpus.

## Rejected alternatives

- **Python-only metrics registry without MetricFlow:** rejects the working
  ADR 0085 path. Not chosen; `move_evals` keeps move metrics on MetricFlow.
- **dbt-metricflow CLI / remote Semantic Layer service:** ADR 0085 already
  chose in-process `MetricFlowEngine.explain` + read-only DuckDB.
- **Forcing every filtered cube cell through MetricFlow:** cube grains are
  coarser and floor-filtered (10-game); document the cut instead.
- **Leaving clock/accuracy on reviewed SQL permanently:** rejected in favor
  of `move_evals` so both surfaces and the coach share one governed path.

## References

- [ADR 0085](0085-governed-semantic-layer-metricflow.md),
  [ADR 0086](0086-dbt-engineering-depth.md),
  [ADR 0101](0101-hosted-bi-cube.md),
  [ADR 0105](0105-kpi-period-deltas.md),
  [docs/METRICS.md](../METRICS.md),
  [docs/DBT_LINEAGE.md](../DBT_LINEAGE.md),
  `contracts/m3_tables.json`,
  `src/chess_analytics/corpus/moves.py`

## Decided 2026-10-31

1. Accuracy = mean centipawn loss with a 1000 cp per-move clamp; mate
   transitions excluded (null deterioration, not zero).
2. Thin dbt `move_evals` from published `fact_move` is in scope so MetricFlow
   governs clock and accuracy.
