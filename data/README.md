# Local data (ignored by Git)

raw/: verified archive, acquisition plan, partial attempts and failures.
staging/: immutable ingestion candidates, quarantine, failed build artifacts.
published/: checked Parquet/DuckDB snapshots and manifests.
DATASET-current.json: atomically replaced pointer to the checked snapshot.
DATASET-staged.json: pointer to the latest successfully parsed candidate.

Default data-directory allowance is 5 GB including retained failures and snapshots.
No automatic cleanup removes evidence. Choose `--data-dir` to relocate this tree.

`public/` holds two committed aggregates. It is not a warehouse. `dashboard_extract.json` is extract version 2 (ADR 0092 and ADR 0098): opening color scores, the clock-pressure rollup, the transposition reduction, and the live-eval summary. Those receipts are `committed_report`. `dashboard_cube.parquet` is the pre-aggregated cube the hosted page queries (ADR 0101). `hosted/dashboard.py` reads both files and does not open a warehouse. See [the hosted dashboard note](../docs/HOSTED_DASHBOARD.md).

The committed extract was rebuilt with MetricFlow on 2026-10-20 from mart `9d3ca923a6f1cd06d82a8645`. `game_draw_rate`, `opening_usage`, and `opening_player_score` are `metricflow`. The four clock buckets are `reviewed_sql`. Adjusted score, bootstrap, and lineage counts stay `committed_report`. The old M3 snapshot `6cf51473f8da6ae6b12ea5c2` failed the implementation-hash check, so the pinned August prefix was re-ingested as snapshot `7764247e6bdb0b6e73420253`. Its source hash matches `reports/M3-source-manifest.json`, and the live counts matched that committed reference exactly. `build` in the extract records that snapshot and the lock hash. Snapshot `7764247e6bdb0b6e73420253` comes from the implementation hash of `src/**/*.py` at a1c7690 (`0a3bdb34c4c2e9b7388bcdba483154d7cfa4c60eabe758ecda4a5a4f8d11c694`). A later re-ingest after source changes gets a new snapshot id, which is expected.

Mac rebuild from `~/Developer/chess-analytics-lab`, using the venv override below. The `dbt` extra is required for MetricFlow. The dashboard extra is not. The builder prints which receipts were relabeled and why the others were not.

```
UV_PROJECT_ENVIRONMENT=$HOME/.venvs/chess-analytics-lab uv run --directory $HOME/Developer/chess-analytics-lab --locked --no-editable --extra dbt python scripts/build_public_extract.py
```
