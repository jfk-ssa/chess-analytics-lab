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
rewrite the published mart. `--target-path target` is relative to the dbt
project. dbt stores that relative path in the manifest. An absolute
`--target-path` is stored as that absolute path, which is how a runner
directory would be published. `--log-path` is relative to the current
directory, so `dbt/target/logs` keeps the log inside the gitignored
`dbt/target/` directory.

```sh
uv run --locked --offline --no-editable --extra dbt \
  dbt docs generate --project-dir dbt --profiles-dir dbt \
  --target-path target --log-path dbt/target/logs --no-use-colors
```

Open `dbt/target/index.html`. On the tiny fixture the catalog has column
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
uv run --locked --offline --no-editable --extra dbt \
  dbt build --select state:modified+ --state /tmp/dbt-state \
  --project-dir dbt --profiles-dir dbt \
  --target-path /tmp/dbt-current --log-path /tmp/dbt-current-logs --no-use-colors
uv run --locked --offline --no-editable --extra dbt \
  dbt test --select test_type:unit,state:modified --state /tmp/dbt-state \
  --project-dir dbt --profiles-dir dbt \
  --target-path /tmp/dbt-current --log-path /tmp/dbt-current-logs --no-use-colors
```

`dbt build` on dbt 1.12 counts modified unit tests but does not run them
when their parent model is unmodified. The `dbt test` selector runs those
unit tests. CI runs both. Point `CHESSLAB_DBT_PATH` at a copy named
`warehouse.duckdb` before the build and the test.

### Incremental player_games measurement

[ADR 0087](adr/0087-incremental-player-games.md) measured a scratch
incremental `player_games` and left the published model as a view. The
script writes synthetic `fact_game` and `fact_player_game` rows, copies
`dbt/` to a temp directory, and does not modify the published project or
download the corpus. The same command works on macOS and Linux. Scratch
files go to `tempfile.mkdtemp`.

```sh
uv run --locked --offline --no-editable --extra dbt \
  python scripts/measure_incremental_player_games.py \
  --games 100000,1000000 \
  --repeats 5 \
  --deltas 0.01,0.10 \
  --output reports/incremental-player-games.json
```

The receipt from the measurement VM is
[reports/incremental-player-games.json](../reports/incremental-player-games.json).
That run's script wall clock was 771.8 s. CI does not run this command.
`tests/test_incremental_player_games.py` checks the seeder and a 40-game
equivalence proof, including a broken `unique_key` and a broken filter.

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
without a personal config or explicitly capped experiment, and reads the
key named by that config. OpenAI configs name `CHESSLAB_OPENAI_API_KEY`.
A `grok-4.7` config names `CHESSLAB_XAI_API_KEY`. Keys come only from the
process environment.
Run `doppler setup` once from the repository root in workplace `personal`; it
reads `doppler.yaml` (project `chess-analytics-lab`, config `dev`). Then use
`doppler run -- uv run ...` to inject named keys into the process environment.
Env vars take precedence over the dormant `--env-file` fallback still
present in frozen eval modules (`live_runner.FROZEN_FILES`); that fallback
is not the recommended path and will be removed at the next intentional
frozen-set change. Never commit the key, paste it into a report, or infer
spending authorization from credits.

For a future authorized frozen experiment, `python -m chess_analytics.analyst.experiment
prepare --max-run-usd CAP --preflight work/new-preflight.json` makes a quote
without loading a key; `run` requires that exact preflight, a separate explicit
cap and the named process environment key. [M6.md](M6.md) documents
historical usage.
Do not reuse an old approved cap. The runner records actual usage, reserves
unknown-cost attempts at their bound, stops when a full next request cannot
fit and retains failures. Inspect the attempt ledger, raw ignored response,
compact report and evidence audit before interpreting a score. `--config`
accepts a separate disabled-by-default JSON example when exact model/rates
are supplied; the key stays out of JSON. No live call is part of CI or the
portfolio demo.

## Live analyst eval

The offline runner scores the frozen 48-case set. Tests and the push and
pull-request workflows use a fake transport. They do not call a model.
`.github/workflows/live-eval.yml` is `workflow_dispatch` only. It has no
`schedule`. A schedule later needs a new ADR and explicit owner approval,
added to this same workflow after the `live-eval` environment, the cap,
and the required reviewer are already in place.
[ADR 0089](adr/0089-llm-quality-evaluation.md) is the plan.
[ADR 0090](adr/0090-live-eval-scorer-runner-stats.md) is the runner.
[ADR 0091](adr/0091-manual-live-eval-workflow.md) is the manual job.
[ADR 0095](adr/0095-grok-4-7-live-eval.md) adds `grok-4.7`. The headline
run is low at 5 repeats. The effort comparison is one repeat each of
low, medium, and high on the same instructions. Medium and high are not
5-repeat rates.

The same commands work on macOS and Linux. They use the repository Python
and do not depend on a Linux-only flag.

### Pre-run checklist

Do this before any live call. The dry run does not do it for you, and it
does not probe the API.

1. Recheck the provider model page. Past Sol runs in this repository use
   `gpt-6-sol`. The approved plan records that OpenAI's page has listed
   `gpt-6.1-sol`. On 2026-10-20 both `gpt-6-luna` and `gpt-6-sol` were
   valid ids. `gpt-6.1-sol` does not accept `reasoning.effort` of `none`,
   so the frozen id stays `gpt-6-sol`.
2. Confirm the reasoning effort on the chosen id. On 2026-10-20 both
   OpenAI ids accepted `reasoning.effort` of `none`, and the OpenAI quote
   sends that value. `grok-4.7` cannot disable reasoning. Its allowed
   efforts are `low`, `medium`, `high`, and `xhigh`. The headline run is
   `low` at 5 repeats. The effort comparison is one repeat each of low,
   medium, and high on the same instructions. Medium and high are not
   5-repeat rates. This command does not probe the API.
3. Recheck prices. On 2026-10-20 the official OpenAI pages matched the
   recorded rates exactly: Luna $0.10 input, $0.01 cached, $0.125 cache
   write, and $0.50 output; Sol $2, $0.20, $2.50, and $10. On 2026-10-21
   the grok-4.7 model page matched $2 input, $0.50 cached input, and $6
   output per million tokens below 200,000 prompt tokens, and $4, $1, and
   $12 for the whole request at or above that threshold. Reasoning tokens
   bill as output. The date is `DEFAULT_PRICE_CHECKED_UTC_DATE` in
   `preflight.py`, set to `2026-10-20`. `pricing.py` does not store that
   date. A receipt sets `prices_rechecked` to false. The manual workflow
   stops when the date is older than 14 days unless
   `allow_stale_price_check` is set after this recheck. A dispatch on
   2026-10-21 does not need that override. Credits are not a budget.
4. Choose `max_run_usd` yourself. The recommended gross caps are Luna
   $0.50, Sol $10, and grok-4.7 $10. They are not an approval to spend.
   On 2026-10-19 the conservative reservation for these 48 cases, five
   repeats, 240 requests, was $0.443594 for Luna and $8.871288 for Sol.
   On 2026-10-21 the same envelope for grok-4.7 reserved $9.822470 at
   low, $18.671270 at medium, and $30.466790 at high. Low at 5 repeats
   fits under $10. Medium and high fit at 1 repeat ($3.734254 and
   $6.093358) and stop at 5 repeats. The expected cost of the three
   planned runs is about $4–5. The assumptions are in
   [ADR 0095](adr/0095-grok-4-7-live-eval.md). A reservation over the cap
   refuses before any request is sent.
5. Acknowledge the personal account on the command line. OpenAI runs
   read `CHESSLAB_OPENAI_API_KEY`. grok-4.7 runs read
   `CHESSLAB_XAI_API_KEY`. Inject the selected variable using Doppler.
   For an authorized xAI run, select `prd` with
   `doppler run --config prd -- uv run ...`; local `dev` holds only the
   OpenAI key. Do not commit the key or the receipt.

### Dry run

Publish the 100-game fixture into ignored `work/`, then quote. Neither
step downloads or calls a model.

```sh
uv run --locked --offline --no-editable python -c '
from pathlib import Path
from chess_analytics.analyst.live_eval import stage_live_fixture
stage_live_fixture(Path("."), Path("work/live-eval"))
'
uv run --locked --offline --no-editable python -m chess_analytics.analyst live-eval \
  --staged work/live-eval/project \
  --model gpt-6-luna \
  --max-run-usd 0.50 \
  --repeats 5 \
  --acknowledge-personal-account \
  --dry-run
```

The dry run prints the model, the reasoning effort, the repeat count,
the case count, the reserved dollars, and the cap. It does not read the
API key. A grok-4.7 headline quote adds `--reasoning-effort low`,
`--max-run-usd 10`, and `--repeats 5`. A sensitivity quote uses
`--reasoning-effort medium` or `high`, `--repeats 1`, and the same cap.
Medium or high at five repeats exits 1 because the reservation is above
$10. The dry run still does not call xAI.

### Real run

Drop `--offline` on the real command. The frozen transport calls the
Responses API. CI does not run this command. Write the receipt under
`work/` and leave it uncommitted. John commits a receipt from a later
artifact in a separate pull request.

```sh
doppler run -- uv run --locked --no-editable python -m chess_analytics.analyst live-eval \
  --staged work/live-eval/project \
  --model gpt-6-luna \
  --max-run-usd 0.50 \
  --repeats 5 \
  --acknowledge-personal-account \
  --output work/live-eval-receipt.json
```

Swap the model and the cap together. A Sol run uses `--model gpt-6-sol`
and a cap you have actually approved. The recommendation for the
5-repeat envelope is $10. Pass `--baseline-rate` only when you already
have a baseline pass rate to compare. The alert it prints is advisory.
`hard_fail` on the receipt means some high-severity case missed. That
flag does not by itself fail the process. An incomplete receipt does.
The push and pull-request workflows do not run this command.

### GitHub Actions dispatch

John runs the paid job from the Actions tab. Create the environment
before the first dispatch. The job does not probe the provider.

1. In the repository settings, create the environment `live-eval` and
   add John as a required reviewer. Do that before the first dispatch.
   A dispatch against a missing environment can create an empty one, and
   a run then starts without a review. Set Deployment branches to
   Selected branches and allow only `main`. `workflow_dispatch` runs the
   workflow file from the chosen ref, so a same-repo branch could print
   the key after approval. Before approving, compare the run SHA with
   `main`. The job exits 1 before the secret step unless `github.ref` is
   `refs/heads/main`, when the file on that ref still contains the guard.
   The branch rule is what stops a file that removed the guard.
2. Create a dedicated key for the provider you will call and set a
   provider-side spend limit on that key. Add an OpenAI key as the
   environment secret `CHESSLAB_OPENAI_API_KEY`. Add an xAI key as
   `CHESSLAB_XAI_API_KEY`. John is setting a $10 monthly limit on the
   xAI key. This repository does not enforce that monthly limit. Keep
   both names off the repository secrets. The live step receives only
   the secret for the selected model.
3. Open Actions, choose **Live analyst eval**, and run the workflow.
   `model` is `gpt-6-luna`, `gpt-6-sol`, or `grok-4.7`. Astra is not a
   choice: ADR 0089 leaves its id and its cap unset. `repeats` defaults
   to 5 and accepts an integer from 1 to 20. `max_run_usd` has no
   default. Type a cap at or under the ceiling: Luna $0.50, Sol $10, or
   grok-4.7 $10. The ceiling is not scaled when the repeat count
   changes. `reasoning_effort` defaults to `model-default`, which is
   `none` on the OpenAI ids and `low` on grok-4.7. The run title shows
   that resolved effort. The grok headline is
   low at 5 repeats with cap $10. The comparable effort check is one
   repeat each of low, medium, and high on the same instructions.
   Dispatch those three with `repeats` 1. Run low first and compare its
   receipt `known_gross_cost_usd`
   and `token_usage` with the quote before medium and high. The token usage
   sums input, output, reasoning, and billed output. Medium or high at
   5 repeats stops in the dry run. The dry-run step sets `pipefail`, so
   that failure does not continue into the secret step.
   The job timeout is 150 minutes. Check
   `acknowledge_personal_account`. The recorded price-check date is
   `2026-10-20` in `preflight.py`. When that date is older than 14 days,
   check `allow_stale_price_check` only after the rechecks above. A
   dispatch on 2026-10-21 does not need the override. The override does
   not call the API and does not mark `prices_rechecked` on the receipt.
4. Approve the `live-eval` environment review when GitHub asks. Compare
   the run SHA with `main` before you approve. The job prints the
   checklist, refuses a ref other than `refs/heads/main`, refuses a stale
   price date and an over-cap input, prints the dry-run reservation, then
   runs the live command. A second dispatch waits. A third dispatch
   replaces the one that is waiting. The run already in progress is not
   cancelled. This workflow does not set `queue`.
5. Download the artifact named
   `live-eval-receipt-<model>-<resolved effort>-r<repeats>-<run_id>`.
   `<run_id>` is the Actions run id. Retention is 90 days. The run title includes
   the model, the resolved reasoning effort, the repeats, and the cap.
   `model-default` is shown as `none` for the OpenAI ids and `low` for
   grok-4.7. An explicit choice is shown as typed. Select `low` with 5
   repeats, or `medium` or `high` with 1 repeat, so the title matches
   the receipt. The job summary shows the model, the
   reasoning effort, the repeats, the pass rate labelled with that
   repeat count, its Wilson interval, the repair counts, hard fail, the
   known gross cost, and complete true or false. A 1-repeat summary
   says the rate is not a 5-repeat headline comparison.
6. Read the receipt and commit the artifact bytes unchanged in a separate
   pull request. Keep the artifact name:
   `reports/live-eval-receipt-<model>-<resolved effort>-r<repeats>-<run_id>.json`.
   `<run_id>` is the Actions run id at the end of that name. The published
   report sorts `reports/live-eval-receipt-*.json` by that trailing integer.
   The Luna and Sol receipts stay `reports/live-eval-receipt-<run_id>.json`.
   The workflow does not commit the file. `work/` is ignored.

### Adding a schedule later

Do not add `schedule` to `live-eval.yml` in place. A later change needs
a new ADR and explicit owner approval. It belongs on this workflow,
which already names the `live-eval` environment, checks the cap, and
waits for the required reviewer. That change is not in this file.
