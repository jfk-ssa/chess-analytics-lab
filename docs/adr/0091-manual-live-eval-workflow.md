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
`action.yml` is the upload action. Ruff check and ruff format check
passed on the new Python files. The new workflow tests and the runner
source check passed 10. The whole-repository offline bar is recorded
with the pull request once that run finishes.
