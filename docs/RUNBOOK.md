# Local runbook

Run from the repository root. Use `uv sync --locked --no-editable --extra dbt
--extra dashboard` for the full local toolset, then `uv run --locked --offline
--no-editable --extra dbt --extra dashboard pytest -q`. Installation may need a
one-time dependency download; the demo and tests make no network request after
installation. `UV_CACHE_DIR=.uv-cache` is useful when the default cache is
inaccessible. Reinstall the wheel after source edits with `uv sync --locked
--offline --no-editable --extra dbt --extra dashboard --reinstall-package
chess-analytics-lab`.

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

`python -m analyst_m5` exposes `typed`, `replay`, `eval`, and `live`. Use the
first two for offline questions; [EVALUATION.md](EVALUATION.md) explains the
case splits and evidence. `eval` needs its matching analytical snapshot.
The default demo does not read a credential. The live adapter is disabled
without a personal config or explicitly capped experiment, and reads only
`CHESSLAB_OPENAI_API_KEY` when invoked. An ignored `work/.env` may hold that
variable; no workplace credential is discovered or used. Never commit the
key, paste it into a report, or infer spending authorization from credits.

For a future authorized frozen experiment, `python -m analyst_m5.experiment
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
