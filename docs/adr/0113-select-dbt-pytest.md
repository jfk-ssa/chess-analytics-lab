# 0113. Select dbt tests in the dbt-extra pytest step

- Status: accepted on merge
- Date: 2026-10-31

## Motivation

[ADR 0112](0112-split-offline-pytest-job.md) moved the full no-dbt suite
into `offline-core`. The dbt-extra step still repeated the full suite.
On PR #79 head `b5fd6b9`, Actions run
[41175985496](https://github.com/jfk-ssa/chess-analytics-lab/actions/runs/41175985496),
job `124463558911`:

| Piece | Time / result |
|---|---|
| `offline` job | 4m 25s |
| Pytest with dbt required | 3m 05s; 491 passed, 41 skipped |
| Full no-dbt pytest in parallel `offline-core` | 2m 19s |

Slow calls included `test_grok_live_eval.py` (~40s),
`test_live_eval_runner.py` (13–24s), M2 recovery/backfill/drift (~40s),
and incremental player-games equivalence (~35s). The first two exercise
offline evaluation machinery and already run in `offline-core`.

## Decision

Register `dbt` and enable `--strict-markers`. Mark 13 tests in six files:

| File under `tests/` | Marked tests |
|---|---:|
| `test_m2.py` (module marker) | 2 |
| `test_dbt_contract.py` | 1 |
| `test_eval_gate.py` | 4 |
| `test_incremental_player_games.py` | 1 |
| `test_semantic_layer.py` | 4 |
| `test_live_eval_100.py` | 1 |

Twelve tests skip without dbt, directly or through the semantic product
fixtures. The oracle test runs in both environments and explicitly checks
the governed mart path when dbt is installed. Pure lineage, SQL-shape,
and mocked tests stay in the core suite.

The `offline` dbt pytest step now runs:

```text
CHESSLAB_REQUIRE_DBT=1 uv run --locked --offline --no-editable --extra dbt pytest -m dbt -q -n 4 --durations=15
```

`offline-core` still runs the full collection without the extra. Job ids,
path selection, the `pytest_dbt` output, Node setup, and rulesets stay as
before. The step catalog audits the new exact command. Python, analyst,
and dbt diffs select it. Docs-only changes outside the existing analyst/dbt
exceptions (`docs/METRICS.md` / `docs/DBT_LINEAGE.md`), site, and hosted diffs
skip it.

`tests/test_dbt_marker.py` starts a fresh full `--collect-only` process.
For every unmarked item it inspects skip markers, test/helper source, and
the resolved transitive fixture closure. Unexplained skip sites and direct
dbt-executable branches require `dbt`. Module-level optional imports are
checked even when they prevent collection. Explicit exceptions cover
other optional extras, ignored datasets, local runtimes/configuration,
and the Maia scorer's dynamic skip reason. Collection executes no test
bodies or fixture setup and needs no dbt installation. The guard rejects
unexplained module-level skip/importorskip Call sites it can see, including
assignments and nested `if` statements; it does not seal every possible skip shape.

## Consequences

Skip/importorskip and dbt-executable checks cover only `tests/`, including
helpers reachable from unmarked items' fixture closures that live under `tests/`.
Silent dual-path staging in `src/` (such as `_maybe_mart` or `with_name("dbt")`)
is invisible to the guard. Governed-path preservation there is covered only by
the marked baseline byte-match (`test_live_scorecard_matches_the_committed_baseline`),
path-changed / poisoned-mart cases, and oracle path check
(`test_tools_match_the_independent_oracle`).

The expensive dbt builds and mart parity assertions remain in `offline`;
the unrelated evaluation machinery runs once in `offline-core`. The oracle
test intentionally overlaps so both SQL and governed paths remain checked.
This is fixture/replay validation, not a live model result.

Local validation on Linux, Python 3.12.14, pytest 9.2.0, four workers:

| Check | Before | After |
|---|---|---|
| Full local collection, no dbt extra | 530 | 531; only the guard was added |
| dbt-step selection | Full suite | 13 selected, 518 deselected |
| dbt-required execution | Hosted: 491 passed, 41 skipped; 185s | Blocked locally by dependency installation |
| Selection smoke test without dbt | Not run | 1 passed, 14 skipped; 1.65s |

The 14 skips in the selection smoke test are the 12 gated tests plus two
collection skips for the docs and MCP extras. This is not a successful
dbt-required run. The locked `dbt-duckdb==1.11.1` is absent from the
available caches (which contain 1.11.0), and a normal locked install also
failed on DNS resolution. The lockfile and dependency versions were not
changed to work around that failure. Hosted after timings require a
subsequent Actions run; no hosted speedup is claimed here.

The guard and existing path-selection tests passed, 41 tests in 2.33s.
Four in-memory collection mutations removing markers were rejected: a
direct dbt skip, the M2 module marker, a semantic fixture consumer, and
the oracle's dbt branch. Restoring the markers passed the full collection
guard. Comparing collected node ids before and after found no removed
tests. Ruff check, Ruff format, basedpyright, the step-map audit, and the
offline tiny demo passed (22 accepted games, draw rate 4/20 = 0.2).

The full no-dbt run stopped progressing. A verbose diagnostic rerun with
60-second traceback capture located waits in `chess.engine.id` from
`test_fake_engine_agrees_between_the_direct_process_and_the_tool` and
`test_ranking_report_answers_only_published_positions`. Both attempts
were interrupted; neither is counted as passing. A third attempt with
those two tests explicitly deselected also stopped progressing and was
interrupted. Its progress log recorded 436 passed and 29 skipped before
interruption; these partial counts are not a complete suite result.

Option 2, session-scoped fixture caching, is explicitly deferred and out
of scope. This change does not alter fixture scopes, add caches, or
authorize live model calls. Rollback is reverting this change.
