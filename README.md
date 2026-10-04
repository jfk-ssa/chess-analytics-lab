# Chess Analytics Lab

A local portfolio connecting reliable chess data, defensible analytics, and an
evaluated AI analyst in one repository. Target recurring infrastructure cost: $0.

**Current scope: M0–M6 accepted locally; M7 in progress.** The CLI acquires the fixed January 2013 Lichess archive,
validates and normalizes games, publishes Parquet and DuckDB snapshots, and reports
one governed draw-rate metric. A tiny synthetic fixture runs entirely offline.
See [status](docs/STATUS.md) for measured acceptance evidence and remaining work.

M3 adds a bounded **partial** August 2026 source, source-tag opening metrics,
sampled move annotations and an exploratory clock/evaluation proxy. Its observed
games cover August 1 only. See the [M3 runbook and evidence](docs/M3.md).
M4 adds a local Streamlit dashboard and two checked analytical memos. M5 adds
typed metric tools, offline fixture replay and a 50-case harness; see
[M4–M5 evidence and commands](docs/M4-M5.md). The actual
[M6 measured release](docs/M6-RELEASE.md) reports model responses, failures,
cost, variability, and scope limits.

The same tiny offline pipeline can be run as [Dagster assets or a Prefect flow](docs/ORCHESTRATION.md).
Both adapters use the existing ingestion and metric code; an optional fourth step
builds the [M2 dbt marts](docs/M2.md). Neither starts a scheduler,
uses a cloud account, or makes a model call by default.

```text
Pinned archive → bounded acquisition + SHA256 → legal PGN replay
  → staged game/participant rows + quarantine → Parquet → DuckDB
  → quality checks → immutable snapshot → draw-rate evidence
```

## Quick start

From the repository root, with [uv](https://docs.astral.sh/uv/) installed:

```sh
uv sync --locked --no-editable
uv run --locked --no-editable chesslab doctor
uv run --locked --no-editable chesslab demo
uv run --locked --no-editable pytest -q
uv run --locked --no-editable ruff check .
```

Dependency installation requires network once. Demo/tests do not download archives
or call providers. Add `--offline` to uv commands to enforce cache-only operation.
The regular wheel installation avoids a hidden `.pth` issue observed on this Mac.
After editing source, run `uv sync --locked --no-editable --reinstall-package chess-analytics-lab`.
Developers can alternatively set `PYTHONPATH=src` while running tests.

For the real complete foundation corpus (manual, bounded download):

```sh
uv run --locked --no-editable chesslab ingest --dataset foundation
uv run --locked --no-editable chesslab build --dataset foundation
uv run --locked --no-editable chesslab validate --dataset foundation
uv run --locked --no-editable chesslab report --dataset foundation
uv run --locked --no-editable python scripts/reference_draw_rate.py data/raw/lichess_db_standard_rated_2013-01.pgn.zst
```

`ingest` reuses a checksum-verified local source, creates a fresh staging run, and
never appends to published tables. `build` publishes only after validation. Repeat
both commands to verify idempotence. A failure preserves the previous snapshot.
Use `chesslab --data-dir /path/to/data ...` to move bulk data outside the repository.

## Evidence and limits

- [Fixture tally](tests/fixtures/README.md): 4 draws / 20 eligible games = 20%.
- [Metric contract](contracts/game_draw_rate.json), [data dictionary](docs/DATA_DICTIONARY.md).
- [Runbook](docs/RUNBOOK.md), [decisions](docs/DECISIONS.md), [complete brief](docs/PROJECT_SPEC.md).
- [Milestone evidence](reports/M0-M1.md).

The foundation archive is historical ingestion evidence. It cannot establish
contemporary player behavior or clock-pressure findings. Source-marked bots and
unknown results are counted explicitly and excluded from the draw-rate denominator.

**Roadmap:** [M7 measured depth](docs/M7.md); use a new unseen holdout for future model claims;
M8 Jev. Recommendations stay backlog.

The M5 provider adapter remains disabled by default. An explicit run spending
cap and named personal key are prerequisites for any future live call; the
separate provider JSON is optional for the standard M6 pilot.

Data: [Lichess open database](https://database.lichess.org/), CC0. Dependency notices
and repository licensing status are in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
