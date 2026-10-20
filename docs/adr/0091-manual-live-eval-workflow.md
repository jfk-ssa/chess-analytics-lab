# 0091. Manual live-eval workflow

- Status: accepted
- Date: 2026-10-20

## Motivation

[ADR 0089](0089-llm-quality-evaluation.md) specified the manual job:
`workflow_dispatch` only, inputs `model`, `repeats`, `max_run_usd`, and
`acknowledge_personal_account`, the GitHub Environment `live-eval`, a
dedicated budget key, an uploaded receipt, concurrency that does not
cancel an in-progress run, and `contents: read`. It did not add the
workflow. [ADR 0090](0090-live-eval-scorer-runner-stats.md) added the
runner and left the workflow for this pull request.

The records are silent on Astra's place in the choice list, on how a
repeat count other than 5 meets the 5-repeat dollar caps, on how old a
recorded price may be, on artifact retention, and on whether a second
dispatch may run beside the first. This record is those choices. It
does not call a model.

## Decision

`.github/workflows/live-eval.yml` is the job. Its only trigger is
`workflow_dispatch`. The file has no `schedule`, no `push`, and no
`pull_request`. The push and pull-request workflows are unchanged, so
they do not run this file.

The model choice is `gpt-6-luna` or `gpt-6-sol`. Astra stays out. ADR
0089 allows one Astra repeat only with a separate cap, and that record
sets neither the id nor the cap.

`repeats` defaults to 5. The runner accepts an integer from 1 to 20, and
so does this job. `max_run_usd` is required and has no default. The job
refuses a cap above the ADR 0089 5-repeat ceiling: Luna $0.50, Sol $10.
The ceiling is not scaled when the repeat count changes. A smaller run
may use a cap inside that ceiling. A larger run may not raise it. The
runner still refuses, before any send, when the reservation is above the
cap the operator typed. `acknowledge_personal_account` must be true or
the job stops before the dry run.

The price-check date is `DEFAULT_PRICE_CHECKED_UTC_DATE` in
`preflight.py`. `pricing.py` does not store a date. The runner copies
the preflight constant and sets `prices_rechecked` to false. This job
does not probe the API and does not edit that constant. It reads the
date and stops when the age is greater than 14 days, unless the operator
sets `allow_stale_price_check`. Fourteen days is the window this record
adds: on 2026-10-20 the recorded date 2026-10-04 is 16 days old, so the
first dispatch has to set the override after the checklist. A check from
the same fortnight does not. The override does not mark
`prices_rechecked` and does not change the quoted model id. The checklist
is printed before that gate: recheck `gpt-6-sol` against `gpt-6.1-sol`,
confirm `reasoning.effort` of `none` on the chosen id, and recheck prices.

The key is the environment secret `CHESSLAB_OPENAI_API_KEY` on
`live-eval`. The job names that environment, so a required reviewer on
the environment holds the run. GitHub uses a repository secret of the
same name when the environment secret is absent, so this repository
must not also store that name as a repository secret. Checkout does not
persist credentials. Permissions are `contents: read` and no other
scope. In August 2025 a comment on `actions/upload-artifact` issue 197
reported that a private repository could upload with `contents: read`.
This pull request did not run the job, and that report is not a
guarantee for this public repository. If the upload is rejected for
permissions, the follow-up is `actions: write` and no contents write.

The concurrency group is `live-eval` with `cancel-in-progress: false`.
A second dispatch waits. The records required that an in-progress run
not be cancelled. They did not say two runs may spend the same key at
once. One group keeps a single spend.

The dry run prints the reservation and copies it to the job summary. The
live command is the existing runner. It drops `--offline` on that
command, matching the runbook, and it does not pass `--env-file`. The
receipt is `work/live-eval-receipt.json`. The job uploads it and retains
it for 90 days. Neither ADR set a retention; 90 days is the artifact
maximum this record uses. The job does not commit the receipt. John downloads the artifact and
commits that JSON under `reports/` in a separate pull request. The
workflow path `work/` is gitignored.

The job summary reads the receipt: model, repeats, headline raw pass
rate, the Wilson interval, repair counts beside that rate, hard fail,
known gross cost, and complete. `hard_fail` with `complete: true` leaves
the process exit at 0, as ADR 0090 requires. An incomplete receipt exits
1. The summary and the upload still run. There is no timeout: a timeout
would cancel a paid run.

The checks live in `scripts/live_eval_dispatch.py`. That script is
outside `src/`, so the implementation hash and the 0088 gate baseline
stay put. `--today` on the price check is a test clock. The workflow
does not pass it.

A later `schedule` still needs a new ADR and explicit owner approval,
on this workflow, after the environment, the cap, and the reviewer exist.
This record does not add it.

## Results

Checked on this Linux agent on 2026-10-20. No model was called.
`CHESSLAB_OPENAI_API_KEY` was unset.

The price check for today 2026-10-20 exited 1: the recorded date
2026-10-04 was 16 days old, above the 14-day limit. The same date with
`allow_stale_price_check` true exited 0. Today 2026-10-18 is 14 days and
exited 0 without the override. `check-inputs` accepted Luna at $0.50 and
refused Sol at $10.01 and a false acknowledgement.

The workflow's dry-run command, after staging the fixture under ignored
`work/live-eval`, printed Luna reserved $0.443594 under a $0.50 cap and
Sol reserved $8.871288 under a $10 cap. Both were 240 requests,
`prices_rechecked: false`, and neither wrote a receipt. The runner alone
accepted a Luna cap of $0.51, because $0.443594 still fits. The workflow
check refuses that cap before the runner.

actionlint 1.7.12 reported no findings on `live-eval.yml`. `bash -n` on
the seven `run` scripts passed. The pinned `actions/upload-artifact`
commit `cf430e030ddbb5b0abf93d22962f4752f3646cd9` is tag v7.0.2 and its
`action.yml` is the upload action. The new workflow tests and the
runner source check passed 10 when those two files were run alone.
Each listed assertion failed when the workflow text was mutated:
trigger, schedule, environment, permissions (`contents: write` and an
added `actions: write`), concurrency (`cancel-in-progress: true` and a
missing flag), secret (a renamed key and a second secret), pin, receipt
upload (including retention 30), and a `git commit` of the receipt.
Astra as a model choice, a default on `max_run_usd`, and `--today` on
the price check failed the same way. The source was left unchanged.

The whole-repository offline bar on the same machine:

- `ruff check .` passed. `ruff format --check .` reported 314 files
  already formatted.
- basedpyright reported 0 errors, 0 warnings, and 0 notes.
- `pytest -q` without the dbt extra: 311 passed, 31 skipped, 102.57s.
  That is 9 more passes than the ADR 0090 review count of 302. The
  added tests are the workflow file.
- Node v22.23.3: `node --test tests/js/game_import.test.mjs` passed 10.
  `scripts/check_game_import.mjs` and both `import_parity.mjs` fixtures
  exited 0. Biome 2.5.15 checked 10 files and applied no fixes. The CI
  workflow uses Node 24. This agent did not rerun the JavaScript tests
  on Node 24.
- MCP extra: `pytest -q tests/test_mcp_protocol.py` passed 8 in 2.98s.
- `chesslab demo` published tiny snapshot `3efeca2acc08a0764414edbc`.
- After `uv sync --locked --no-editable --extra dbt`,
  `CHESSLAB_REQUIRE_DBT=1 pytest -q`: 323 passed, 19 skipped, 207.46s.
- `transform --dataset tiny` published mart `686508be9bd2a1967f7ee140`:
  dbt created 8, no-op 2, passed 42.
- Semantic validation: dbt 1.12.5 and duckdb adapter 1.11.0,
  `validate-configs` reported `ERRORS: 0`, `smoke-draw-rate` printed
  `4,20,0.2`, and `scripts/render_dbt_dag.py --check` exited 0.
- `python -m chess_analytics.analyst gate` printed `ok 89/89` in 9.403s.
  `evals/baselines/analyst_gate_v1.json` is unchanged.
- The docs-site step in that bar failed while the gitignored
  `reports/opening-positions.json` was absent. After
  `scripts/materialize_opening_positions.py` wrote 2,308,456 bytes, the
  same pytest command passed 17 in 6.60s.

The workflow was not dispatched. There is no `live-eval` environment
and no key on this agent, so the upload under `contents: read` was not
executed. Slim `state:modified+` was not run locally. `dbt/` is
unchanged.
