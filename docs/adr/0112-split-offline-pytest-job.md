# 0112. Split the no-dbt pytest step into its own job

- Status: accepted on merge
- Date: 2026-10-26

## Motivation

[ADR 0111](0111-parallel-offline-pytest.md) ran both full pytest steps with
`-n 4` and left them one after the other inside `offline`. On the pull
request that merged that change, Actions run
[40286416617](https://github.com/jfk-ssa/chess-analytics-lab/actions/runs/40286416617)
(`a76f45a`, 2026-10-26):

| Piece | Time |
|---|---|
| Pytest, dbt extra not installed | 91s (07:33:09Z–07:34:40Z) |
| Pytest with `CHESSLAB_REQUIRE_DBT=1` | 117s (07:34:45Z–07:36:42Z) |
| `offline` job | 4m 32s (07:32:44Z–07:37:16Z) |
| `portfolio` job | 44s (07:32:44Z–07:33:28Z) |

`portfolio` finished while `offline` was still in the first pytest step. The
pull-request wall clock was the sum of the two pytest steps plus the rest of
`offline`.

## Decision

The no-dbt full pytest step moves to a new job, `offline-core`. That job
runs in parallel with `offline` and `portfolio`. It sets no display name.
The check name is `Offline integrity / offline-core`. The job ids `offline`
and `portfolio` are unchanged, and the ruleset is not edited. `offline-core`
is not a required check until that name is added.

The new job checks out the repository, sets up uv 0.12.18 and Node 24, and
installs with `uv sync --locked --no-editable`. It then runs:

```text
uv run --locked --offline --no-editable pytest -q -n 4 --durations=15
```

It does not install the dbt extra. Node stays because the full pytest step
shells out to Node for the game-import test. uv, Node, and the install run
only when the pytest step is selected. The job itself always starts
(`needs: changes` and `if: !cancelled()`). A docs, site, or hosted diff
skips the pytest step and the job still succeeds, so the check can be
required without staying pending.

The `CHESSLAB_REQUIRE_DBT=1` pytest step stays in `offline`. Path selection
is the same as the step it replaces: python, analyst, and dbt diffs run it;
docs, site, and hosted diffs skip it. `scripts/ci_offline_changes.py` maps
the new job. The `offline` job no longer sets up Node solely because this
step used to live there.

`pytest --collect-only -q` stays 505. The executed totals stay 454 passed
and 53 skipped without the dbt extra, and 466 passed and 41 skipped with
`CHESSLAB_REQUIRE_DBT=1`.

## Consequences

After is Actions run
[40297571854](https://github.com/jfk-ssa/chess-analytics-lab/actions/runs/40297571854)
on `fe5f086` (pull request, 2026-10-26). Both pytest steps ran. The no-dbt
step reported 454 passed and 53 skipped in 99.65s. The dbt step reported
466 passed and 41 skipped in 163.30s.

| Piece | Before, run 40286416617 | After, run 40297571854 |
|---|---|---|
| Pytest, dbt extra not installed | 91s (07:33:09Z–07:34:40Z) | 100s (09:11:16Z–09:12:56Z); 454 passed, 53 skipped in 99.65s |
| Pytest with `CHESSLAB_REQUIRE_DBT=1` | 117s (07:34:45Z–07:36:42Z) | 164s (09:11:41Z–09:14:25Z); 466 passed, 41 skipped in 163.30s |
| `offline` job | 4m 32s (07:32:44Z–07:37:16Z) | 4m 4s (09:11:04Z–09:15:08Z) |
| `offline-core` job | inside `offline` | 1m 56s (09:11:04Z–09:13:00Z) |
| Wall clock, first job start to last job end | 4m 39s (07:32:37Z–07:37:16Z) | 4m 12s (09:10:56Z–09:15:08Z) |

`changes` started first, at 09:10:56Z. `offline` finished last, at 09:15:08Z.
`offline-core` finished at 09:13:00Z, while the dbt pytest step was still
running, so the no-dbt step did not add to the wall clock. On this runner
the dbt pytest step was slower than the 117s step in the before run, and
the `offline` job fell from 4m 32s to 4m 4s. The wall clock fell from
4m 39s to 4m 12s.

Rollback is reverting the pull request. After merge, add
`Offline integrity / offline-core` to the main-protection ruleset required
checks. This record does not authorize a live model call.
