# Local runbook

Run from the repository root. Use `uv sync --locked --no-editable --extra dbt
--extra dashboard` for the full local toolset, then `uv run --locked --offline
--no-editable --extra dbt --extra dashboard pytest -q`. Installation may need a
one-time dependency download; the demo and tests make no network request after
installation. `UV_CACHE_DIR=.uv-cache` is useful when the default cache is
inaccessible. Reinstall the wheel after source edits with `uv sync --locked
--offline --no-editable --extra dbt --extra dashboard --reinstall-package
chess-analytics-lab`. Install local checks with `pre-commit install` and
`pre-commit install --hook-type commit-msg` so commit messages follow
[Conventional Commits](../CONTRIBUTING.md#commits).

For the complete credential-free path, run `chesslab demo --scope all`, then
`CHESSLAB_PROJECT="$PWD/work/portfolio-demo/project" streamlit run
src/chess_analytics/dashboard/dashboard.py`. [DEMO.md](DEMO.md) contains the full checked
commands and expected values. The original `chesslab demo` is the smaller
foundation-only fixture. Both are synthetic and local. The complete demo
writes only to ignored `work/portfolio-demo`, separate from real data.

For the real complete foundation corpus, first check the exact pin and free
disk allowance in [datasets.json](../config/datasets.json), then run:

```sh
uv run --locked --no-editable chesslab ingest --dataset foundation
uv run --locked --offline --no-editable chesslab build --dataset foundation
uv run --locked --offline --no-editable chesslab validate --dataset foundation
uv run --locked --offline --no-editable chesslab report --dataset foundation
uv run --locked --offline --no-editable python \
  scripts/reference_draw_rate.py data/raw/lichess_db_standard_rated_2013-01.pgn.zst
```

The analytical August prefix is deliberately bounded and must be acquired
manually. `python -m chess_analytics.corpus` supports `acquire`, `extract`, `ingest`,
`moves`, and `report` in that order. `--data-dir` moves bulk output outside
the repository. [DATA_SOURCES.md](DATA_SOURCES.md) explains the source and
observed coverage. The real dashboard uses the repository's `data/` by
default. The demo dashboard uses the explicit `CHESSLAB_PROJECT` directory.

For optional dbt, run `python -m chess_analytics.marts transform --dataset tiny` after
tiny ingest/build and use `report-mart`, `ops-report`, or `rollback-mart` as
needed. Backfill accepts `--snapshot-id`; validate a known mart before
rollback. [M2.md](M2.md) contains exact examples. [ORCHESTRATION.md](ORCHESTRATION.md)
shows the thin Dagster and Prefect alternatives, neither of which schedules
unattended runs here.

### dbt unit tests, lineage, and docs

Unit tests run inside `dbt build`, including the tiny `transform` above. To run
only those tests, copy the published tiny warehouse first. The copy must be
named `warehouse.duckdb`: dbt-duckdb uses the file stem as the catalog, and
the published views qualify `warehouse`.

```sh
mart=$(uv run --locked --offline --no-editable --extra dbt python -c 'import json; print(json.load(open("data/tiny-mart-current.json"))["mart_id"])')
mkdir -p /tmp/chesslab-dbt
cp "data/marts/published/${mart}/warehouse.duckdb" /tmp/chesslab-dbt/warehouse.duckdb
export CHESSLAB_DBT_PATH=/tmp/chesslab-dbt/warehouse.duckdb
export DBT_PROFILES_DIR=dbt DBT_SEND_ANONYMOUS_USAGE_STATS=false DO_NOT_TRACK=1
uv run --locked --offline --no-editable --extra dbt \
  dbt test --select test_type:unit \
  --project-dir dbt --profiles-dir dbt \
  --target-path /tmp/dbt-target --log-path /tmp/dbt-logs --no-use-colors
```

The copy already has `fact_game` and `fact_player_game`, which the unit-test
fixtures introspect. The same commands work on macOS and Linux. `/tmp` is the
temporary directory on both.

Regenerate the committed diagram after `dbt parse` writes a manifest:

```sh
uv run --locked --offline --no-editable --extra dbt \
  python scripts/render_dbt_dag.py \
  --manifest /tmp/dbt-target/manifest.json \
  --output docs/DBT_LINEAGE.md
```

`--check` exits 1 when the committed file is stale. CI does that. The script
uses only the Python standard library.

Generate the catalog locally from that same copy so the command does not
rewrite the published mart:

```sh
uv run --locked --offline --no-editable --extra dbt \
  dbt docs generate --project-dir dbt --profiles-dir dbt \
  --target-path /tmp/dbt-docs --log-path /tmp/dbt-docs-logs --no-use-colors
```

Open `/tmp/dbt-docs/index.html`. On the tiny fixture the catalog has column
names and types. DuckDB reported `has_stats` false, so that catalog has no
row counts. It is not the 2013 corpus. The Pages workflow publishes the same
command's `index.html`, `manifest.json`, and `catalog.json` at `/dbt-docs/`
and does not commit them.

To see what a branch would rebuild, check out or archive the base revision's
`dbt/` directory, parse it, and select downstream of the difference. CI checks
out the pull request's base SHA (or the previous commit on a main push) for
that parse. Locally, when the base commit is already available:

```sh
mkdir -p /tmp/dbt-base
git archive BASE_SHA dbt | tar -x -C /tmp/dbt-base
uv run --locked --offline --no-editable --extra dbt \
  dbt parse --project-dir /tmp/dbt-base/dbt --profiles-dir /tmp/dbt-base/dbt \
  --target-path /tmp/dbt-state --log-path /tmp/dbt-state-logs --no-use-colors
uv run --locked --offline --no-editable --extra dbt \
  dbt ls --select state:modified+ --state /tmp/dbt-state \
  --project-dir dbt --profiles-dir dbt \
  --target-path /tmp/dbt-current --log-path /tmp/dbt-current-logs --no-use-colors
```

## Recovery

1. **Download failure:** inspect `data/raw/acquisition-failures.json` and
   `data/raw/acquisition/JOB/attempt-N.part`. Retry the same pinned acquisition.
   Incomplete bytes remain for diagnosis and are never published. Cached complete
   sources are reused only after checksum verification.
2. **Parser/data failure:** inspect `data/staging/RUN/manifest.json` and
   `quarantine.jsonl`. Conflicting duplicate IDs block publication. Resolve the
   source or contract deliberately and reingest; do not select a silent winner.
3. **Limit reached:** byte, record, game and generated-disk caps fail explicitly.
   Failed attempts count against the configured allowance. Check retained files
   before deleting anything or changing a cap. DuckDB memory/threads/spill are
   bounded settings, not whole-process RAM guarantees.
4. **Interrupted build:** the previous pointer remains usable. Verify the writer
   is gone and rerun from the staged source. Candidate/attempt records remain.
   `kill -9` may leave the attempt status marked running.
5. **Rollback or backfill:** select a verified immutable snapshot/mart. The M2
   `rollback-mart` command validates the target and moves the mart pointer under
   the writer lock. Backfill of an older snapshot does not move the current
   pointer. For foundation snapshot pointer repair, validate the chosen snapshot
   and change its pointer only under `writer_lock`; there is no convenience CLI.
6. **Schema/code drift:** report/build may reject a snapshot whose implementation
   hash differs from current source. Reingest with the locked code; never relabel
   historical output. The portfolio demo creates a fresh isolated snapshot after
   each code revision.

All data-changing CLI commands take the advisory writer lock. Direct Python
pipeline calls require the caller to take `writer_lock`. A local filesystem is
assumed; power-loss durability is not claimed.

## M7 campaigns

`chesslab m7 --campaign july pin` downloads one pinned 40 MB prefix when it is
missing and checks it against `config/m7_campaigns.json`. `workspace`,
`reference`, and `cases` rebuild an isolated month view, the raw-PGN reference,
and the 50-case file. `check` scores a retained three-run gate; December also
needs `--sandbox-attempt`. Frozen case files and live reports stay the evidence.

## Analyst and provider incidents

`python -m chess_analytics.analyst` exposes `typed`, `replay`, `eval`, and `live`. Use the
first two for offline questions; [EVALUATION.md](EVALUATION.md) explains the
case splits and evidence. `eval` needs its matching analytical snapshot.
The default demo does not read a credential. The live adapter is disabled
without a personal config or explicitly capped experiment, and reads only
`CHESSLAB_OPENAI_API_KEY` when invoked. An ignored `work/.env` may hold that
variable; no workplace credential is discovered or used. Never commit the
key, paste it into a report, or infer spending authorization from credits.

For a future authorized frozen experiment, `python -m chess_analytics.analyst.experiment
prepare --max-run-usd CAP --preflight work/new-preflight.json` makes a quote
without loading a key; `run` requires that exact preflight, a separate explicit
cap and `--env-file work/.env`. [M6.md](M6.md) documents historical usage.
Do not reuse an old approved cap. The runner records actual usage, reserves
unknown-cost attempts at their bound, stops when a full next request cannot
fit and retains failures. Inspect the attempt ledger, raw ignored response,
compact report and evidence audit before interpreting a score. `--config`
accepts a separate disabled-by-default JSON example when exact model/rates
are supplied; the key stays out of JSON. No live call is part of CI or the
portfolio demo.
