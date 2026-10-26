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
The ruleset contexts are the short names `offline` and `portfolio`. The
context to add is `offline-core`. The ruleset is not edited here.
`offline-core` is not required until that context is added.

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
the new job. The dbt pytest step also runs `tests/test_game_import.py`,
which shells out to Node, so `offline` sets up Node 24 whenever that step
runs. The runner's Node 22 is not the one that step uses.

`pytest --collect-only -q` stays 505. The executed totals stay 454 passed
and 53 skipped without the dbt extra, and 466 passed and 41 skipped with
`CHESSLAB_REQUIRE_DBT=1`.

## Consequences

These are two noisy samples of the same split. They are not a single-run
gain. The structural effect is that the ~91s no-dbt pytest step leaves the
`offline` critical path and runs in `offline-core` at the same time.
Runner noise on the dbt pytest step is larger than that move: 163.30s in
one sample and 110.81s in the next.

Attempt 1 is Actions run
[40297571854](https://github.com/jfk-ssa/chess-analytics-lab/actions/runs/40297571854)
on `fe5f086`. The no-dbt step reported 454 passed and 53 skipped in 99.65s.
The dbt step reported 466 passed and 41 skipped in 163.30s. `offline` was
4m 4s (09:11:04Z–09:15:08Z). `offline-core` was 1m 56s (09:11:04Z–09:13:00Z).
Wall clock from the first job start to the last job end was 4m 12s
(09:10:56Z–09:15:08Z).

The second sample is Actions run
[40298450874](https://github.com/jfk-ssa/chess-analytics-lab/actions/runs/40298450874)
on `51e49bf`. `offline` was 3m 1s (09:18:21Z–09:21:22Z). `offline-core` was
2m 31s (09:18:21Z–09:20:52Z). The dbt pytest step was 110.81s and the
no-dbt pytest step was 137.55s. Wall clock was 3m 9s (09:18:13Z–09:21:22Z).

Before, on run 40286416617, the two steps were sequential inside `offline`
(91s, then 117s). That job was 4m 32s. Wall clock was 4m 39s
(07:32:37Z–07:37:16Z).

| Piece | Before 40286416617 | Attempt 1, 40297571854 on `fe5f086` | 40298450874 on `51e49bf` |
|---|---|---|---|
| Pytest, dbt extra not installed | 91s | 99.65s; 454 passed, 53 skipped | 137.55s |
| Pytest with `CHESSLAB_REQUIRE_DBT=1` | 117s | 163.30s; 466 passed, 41 skipped | 110.81s |
| `offline` job | 4m 32s | 4m 4s | 3m 1s |
| `offline-core` job | inside `offline` | 1m 56s | 2m 31s |
| Wall clock, first job start to last job end | 4m 39s | 4m 12s | 3m 9s |

Rollback is reverting the pull request. After merge, add `offline-core` to
the main-protection ruleset required checks. This record does not authorize
a live model call.
