# 0111. Parallel offline pytest

- Status: accepted on merge
- Date: 2026-10-26

## Motivation

The `offline` job sets the pull-request wall clock. `portfolio` finishes
while that job is still in pytest. On main `3b44f2a`, Actions run
[40271626929](https://github.com/jfk-ssa/chess-analytics-lab/actions/runs/40271626929)
(push, 2026-10-26):

| Piece | Time |
|---|---|
| Pytest, dbt extra not installed | 189.25s inside a 3m 10s step |
| Pytest with `CHESSLAB_REQUIRE_DBT=1` | 313.52s inside a 5m 13s step |
| `offline` job | 9m 31s (04:56:46Z–05:06:17Z) |
| `portfolio` job | 44s |

Those two pytest steps run one after the other. A local 4-CPU run of the
dbt suite on that checkout was 299.42s serial and 111.05s with
`pytest -n 4`. Both reported 466 passed and 41 skipped.

The slowest call in the serial log was
`test_incremental_matches_full_refresh_until_the_key_or_filter_breaks`
at 44.19s (36.79s on this machine). It runs eleven dbt builds or compiles.
Each subprocess spent about three seconds starting. Several analyst-gate
tests each replayed a clean scorecard and then a broken one. The clean
replay is the same card.

## Decision

`pytest-xdist==3.8.0` is a dev dependency. The two full pytest steps in
the `offline` job pass `-n 4 --durations=15`. The narrower pytest steps
and the `portfolio` job stay one process. The job ids stay `offline` and
`portfolio`. Nothing else in the workflows changes, and the ruleset is
untouched.

`-n 4` is the measured worker count. This machine has 4 CPUs, and a
standard `ubuntu-latest` runner has 4 vCPUs. `-n auto` would follow a
larger runner. DuckDB 2.0 already starts its own threads
([ADR 0110](0110-duckdb-2.md)), so the worker count stays fixed. The
scheduler stays the default `load`. Grouping a whole module onto one
worker would serialize `test_live_eval_runner.py`, which is longer than
rebuilding a module fixture on a second worker.

Pytest temp directories stay per worker. Two fixed paths were not:

- The extract-path tests changed directory to `/tmp/chesslab-extract-away`.
  They now use that test's `tmp_path`. The assertions are the missing-file
  error and the path `extract_path` returns.
- The semantic timing note is still `/tmp/semantic-timings.json`. Two
  workers merge it under an exclusive lock so a torn read cannot fail the
  portfolio parity test. The metrics those tests assert are unchanged.

The incremental equivalence proof accepts `in_process=True` and runs the
same dbt arguments, including `--no-partial-parse`, plus `--quiet`, in one
interpreter. It closes the adapter's DuckDB file before the next open or
content hash and restores the process environment afterwards.
The timing study in that script still shells out, so its wall-clock
samples still include process start. The test still asserts the same
report fields. On this machine that call went from 36.79s to 12.31s.

The analyst-gate module keeps one clean `collect` per worker. A test that
diffs a failure still collects that failure. Tests which skip unless dbt
is installed fill the cache only after that check, so the no-dbt job does
not pay a collect it used to skip. `test_two_gate_runs_are_byte_identical`
still compares the cached card with a second collect.

`pytest --collect-only -q` reported 505 tests before these edits and 505
after. The executed totals match run 40271626929: 454 passed and 53
skipped without the dbt extra, 466 passed and 41 skipped with
`CHESSLAB_REQUIRE_DBT=1`.

Local `-n 4` on this machine after the change: 82.58s with the dbt extra
(was 111.05s for xdist alone, and 299.42s serial) and 55.42s without the
dbt extra (the main step was 189.25s serial).

## Deferred

Run the no-dbt pytest step in its own job so the two pytest runs overlap.
The wall clock would then be the slower step rather than the sum. That
split is not in this change. The required check names stay `offline` and
`portfolio`, and a third job was deferred. Both pytest steps stay inside
`offline`.

## Consequences

Hosted after time, on the commit that changed the suite (`78fc7f2`,
Actions run
[40282291574](https://github.com/jfk-ssa/chess-analytics-lab/actions/runs/40282291574)):

| Piece | Main `3b44f2a` | This change |
|---|---|---|
| Pytest, dbt extra not installed | 189.25s | 72.33s |
| Pytest with `CHESSLAB_REQUIRE_DBT=1` | 313.52s | 100.73s |
| `offline` job | 9m 31s | 3m 50s (06:51:47Z–06:55:37Z) |

Executed totals were unchanged: 454 passed and 53 skipped, then 466
passed and 41 skipped. `portfolio` passed. The two pytest steps are still
sequential, so the deferred split would remove most of the remaining
pytest time from the wall clock.

Rollback is reverting the pull request. The lockfile drops `pytest-xdist`
and `execnet` with it. This record does not authorize a live model call.
