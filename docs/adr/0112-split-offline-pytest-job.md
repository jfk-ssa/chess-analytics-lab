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

Before is run 40286416617 above. After is the full-suite run of the commit
that adds this job. The table below is filled from that run.

| Piece | Before | After |
|---|---|---|
| Pytest, dbt extra not installed | 91s | pending |
| Pytest with `CHESSLAB_REQUIRE_DBT=1` | 117s | pending |
| `offline` job | 4m 32s | pending |
| `offline-core` job | inside `offline` | pending |
| Slower of `offline` and `offline-core` | 4m 32s | pending |

Rollback is reverting the pull request. After merge, add
`Offline integrity / offline-core` to the main-protection ruleset required
checks. This record does not authorize a live model call.
