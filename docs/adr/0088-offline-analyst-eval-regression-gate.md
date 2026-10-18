# 0088. Offline analyst eval regression gate

- Status: accepted
- Date: 2026-10-18

## Motivation

The portfolio signal for this change is eval-driven CI for data and AI
engineering: a pull request should fail when the analyst stack stops
doing what the frozen cases say it does.

The thing that can run on every pull request is the deterministic stack:
checked tools, governed metrics, boundaries, caveats, and the scorer.
Replay of frozen plans is deterministic. The scorecard can therefore be
compared with exact equality.

This gate does not measure LLM quality. A live model eval needs a key,
is nondeterministic, and has a cost. It never runs in CI. That eval is
the follow-up in the last section of this record.

## What the gate checks

`python -m chess_analytics.analyst gate` builds a scorecard and exits
non-zero unless it equals `evals/baselines/analyst_gate_v1.json`.

Three suites are in that file.

| Suite | Rubric | What is scored |
|---|---|---|
| `gate_v1` | `portfolio-1.0` | 24 replay cases on the four-game portfolio fixture |
| `engine_v1` | `engine-1.0` | 9 boundary cases and 6 fake-engine structural cases |
| `m5_saved` | `m5-1.0` | 50 saved answers in `reports/M5-both-harness.json` |

`gate_v1` reads `tests/fixtures/portfolio_annotated.pgn`. Expected values
come from `tests/fixtures/portfolio_expected.json`. Pytest in
`tests/test_eval_gate.py` checks that file. The gate command does not read
it. The caveat check is protected because pytest calls the real scorer; the
baseline alone would not notice a scorer that stops checking caveats. The
cases cover
opening usage and the white score, the governed draw rate,
`compare_openings`, clock buckets including empty buckets whose rates
must be null, clarification, an unsupported claim, and five boundaries:
free-form SQL, network, a private file, a budget bypass, and a causal
claim. Scoring uses the existing `score_case_portfolio`.

The five boundary plans are copies of the M5 plans
`sql_attachment`, `network_fetch`, `read_private_file`, `budget_bypass`,
and `causal_clock`. Those plans have an empty action list, status
`unsupported`, and no dataset id, so they do not depend on a warehouse.
They are copies under `evals/replay_plans/gate_v1/`, not live references.
A later edit to an M5 plan does not move this gate. A test checks that
the copies still match.

`engine_v1` keeps the existing case-set hash. The gate runs the cases
whose group is `boundary`, and the cases that require an engine binary
and do not require the opening fixture. The structural cases use
`tests/fixtures/engines/fake_uci.py`. Boundary cases run with no engine
config. The three opening-fixture cases
(`engine_compare_with_frequency`, `engine_continuations_elite`,
`engine_continuations_rated`) stay out of this gate. CI does not
download Stockfish.

`m5_saved` rescores the committed M5 report with `score_case`. It does
not replay those plans and it does not claim a governed path. Re-running
those historical answers through `portfolio-1.0` would be a new analysis.
The rescore is included because it finishes well under five seconds and
reads only tracked files. The measured rescore time is in Results.

## What the gate does not check

It does not call a provider. It does not score a live model response.
The 50/50 M5 harness result remains a harness result, not model accuracy.
Node counts stay recorded and ungated inside the engine scorer; they are
not in the scorecard. Dataset ids and evidence ids are checked by the
scorer at run time and then dropped from the scorecard, because the
snapshot id includes the implementation hash and changes when `src/`
changes.

## Design

The module is `src/chess_analytics/analyst/gate.py`. The CLI is
`python -m chess_analytics.analyst gate`, with `--update` and
`--case <id>`. `evaluation.py`, `experiment.py`, `provider.py`, and
`preflight.py` are unchanged.

`stage()` publishes the four-game fixture in a temporary directory. It
does not call `portfolio_demo._stage_project`. That helper also writes
the demo's own replay plans and scores one opening. The fixture plan
fields match the demo, so the same four games are published. Ingest,
warehouse build, and analytical build run under one writer lock.
`build_mart` runs inside that lock only when a `dbt` executable sits
next to the current Python. The lock is not taken twice.

Each `gate_v1` case records `path` as `governed` only when every governed
metric call returned a result and `semantic.query_rows` ran during that
call. `query_rows` compiles the MetricFlow query and executes it.
`resolve_governed` returning a dict is not enough: a resolver that returns
the reviewed-SQL payload, or returns `None` after a MetricFlow error, is
`reviewed_sql`. The baseline comparison then reports `PATH-CHANGED` for a
case whose committed path is `governed`. Cases that call no governed metric
are `reviewed_sql`. Clock metrics are not in `GOVERNED_METRICS`, so clock
cases stay `reviewed_sql` when dbt is installed. The eight governed cases
in the committed baseline
are `game_draw_rate`, `usage_sicilian`, `usage_french`, `usage_grouped`,
`white_sicilian_score`, `white_french_score`,
`compare_sicilian_minus_french`, and `compare_french_minus_sicilian`.
`engine_v1` and `m5_saved` are `reviewed_sql`. The baseline was written
with the dbt extra installed. A run that falls back to reviewed SQL
fails the equality check. That is the silent-fallback detection.

The case-set digest for `gate_v1` hashes the cases and every replay plan.
`load_gate_cases` raises `case set hash changed` when that digest does
not match `evals/cases/gate_v1_manifest.json`. `_load_m5` raises the same
`case set hash changed` when the M5 case digest or the saved-report hash
does not match. `load_engine_cases` raises `engine case set hash changed`
when the engine case digest does not match, and `engine case file hash
changed` when the case-file bytes do not match. A changed engine replay
plan raises `engine replay plan hash changed` from the gate loader. Each
of those raises before any case is scored, so the run aborts. A baseline
hash that differs from the hash on a completed scorecard is a separate
line, `case set hash changed: <suite>`, and does not abort the loader.

The scorecard is canonical JSON: sorted keys, two-space indent, a trailing
newline, and no timestamps. Per suite it stores the case-set hash, the
rubric version, the totals, and the per-category pass counts. Per case it
stores `passed`, `failures`, and `path`. Elapsed time is printed to stderr
and, when `GITHUB_STEP_SUMMARY` is set, appended under the step summary.
It is not stored in the baseline.

Any scorecard difference fails. Labels:

| Difference | Label |
|---|---|
| Pass becomes fail, or the failure list changes | `REGRESSION` |
| Fail becomes pass | `IMPROVEMENT` |
| Case present now and absent from the baseline | `ADDED` |
| Case absent now and present in the baseline | `REMOVED` |
| `path` differs | `PATH-CHANGED` |

A pass change and a path change on the same case are two blocks.
`REMOVED` means coverage cannot shrink without a diff. Numeric result
values keep the scorer's existing absolute tolerance of 1e-6. The
scorecard comparison itself is exact.

Compare cases store only the scalar difference fields. `_strict_subset`
does not walk lists, so an expected list has to equal the tool row
exactly. Full family and bucket rows include the analytical id and the
contract hash, and those change with the implementation hash. Grouped
opening usage still expects the two family rows, French Defense then
Sicilian Defense, each with numerator 2 and value 0.5, and those row
objects do not carry snapshot ids. Empty clock buckets expect null
`evaluation_coverage` and `error_proxy_rate`. A comparison that touches
an empty bucket expects null differences.

Failure text is one block per diff, then a totals line, a rerun hint,
and an update hint:

```text
REGRESSION gate_v1/game_draw_rate pass->fail [result_values] expected {...} got {...}
totals: baseline 89/89, now 88/89, diffs 1
rerun: python -m chess_analytics.analyst gate --case game_draw_rate
update: python -m chess_analytics.analyst gate --update
```

When `GITHUB_STEP_SUMMARY` is set, the check also appends a three-column
table with headers `category`, `baseline`, and `now`. A run of 60 seconds
or more prints a warning to stderr and to that summary. The warning does
not fail the check.

`--update` rewrites only the baseline. It refuses when `CI` is present in
the environment, including an empty value, and it refuses to combine with
`--case`. `--case` narrows both the baseline and the fresh scorecard to
that id, so the other cases are not reported as removed. A full check
fails when `gate_v1`, `engine_v1`, or `m5_saved` is missing or has zero
cases, or when the scorecard total is zero. The floor reads the fresh
scorecard only, so an empty scorecard does not pass by equaling an empty
baseline, and `--update` does not write that file. `--case` skips the
floor because that scorecard is one case.

The offline job runs the gate after the semantic-manifest step:

```text
uv run --locked --offline --no-editable --extra dbt python -m chess_analytics.analyst gate
```

The gate does not reuse the tiny mart from the previous step. `stage()`
publishes the portfolio fixture in a temp directory and builds a mart
there because the dbt extra is installed. Plain pytest, which syncs
without that extra, still passes: the tests that need a mart skip unless
`CHESSLAB_REQUIRE_DBT=1`, and that variable turns the skip into a failure.
The hash, diff, render, and baseline-file tests run either way.

Exception text replaces absolute paths with `<path>` so a temp directory
cannot change the scorecard. One case that raises `Exception` (not
`BaseException`) is recorded as `exception:<Type>: <message>` and the
other cases still score. The engine loop, the saved-M5 loop, and
`execute_cli` use that same recording, so a traceback does not leak a
temp path. A test runs `collect` twice on one staged project and requires
byte-identical scorecards.

## Alternatives considered

Exact equality, not a ratchet. An improvement is still a reviewed diff.
A ratchet that only fails on a lower pass count would hide a case that
flips from fail to pass for the wrong reason, and it would hide a path
change that keeps the pass bit.

Live LLM eval in CI. Rejected for this pull request. It needs a key, the
result moves between calls, and it spends money. The follow-up below is
the place for that measurement.

A statistical tolerance on this scorecard. Rejected. Replay of these
plans is deterministic. The 1e-6 tolerance stays inside the existing
scorer for rates. The committed scorecard has no second tolerance.

## Results

Measured on this Linux agent on 2026-10-18, CPython 3.12.14, uv 0.12.18.
Node on this agent is v22.14.0. CI installs Node 24 for the JavaScript
checks; those checks passed here on v22.14.0.

| Run | Seconds |
|---|---|
| Full gate, no dbt extra | 2.213 |
| Full gate, dbt extra installed | 16.168 |
| Same check again after `--update` | 14.029 |
| `gate --update` with the dbt extra | 18.673 |
| M5 saved-answer rescore alone | 0.001294 |

With the dbt extra the check printed `ok 89/89`: `gate_v1` 24/24,
`engine_v1` 15/15, `m5_saved` 50/50. Eight `gate_v1` cases take
`governed`. The other sixteen stay `reviewed_sql`. Both full-gate times
are under the 60 second warning. The no-dbt run exited 1 in 2.213 seconds.
The pass bits stayed 89/89, and the report was eight `PATH-CHANGED` lines,
`governed` to `reviewed_sql`, for the eight MetricFlow cases. That is the
intended failure when the mart is absent. Local and CI checks of the
baseline use the dbt extra. `--update` was run after that passing check
and rewrote only the baseline file.

The same machine, still without the dbt extra, reported `248 passed, 30
skipped` from `pytest -q` in 51.76 seconds. The gate file in that run was
`14 passed, 3 skipped`: the path, poison, and live-baseline tests skip
until the dbt extra is installed. With `CHESSLAB_REQUIRE_DBT=1` after
`uv sync --extra dbt`, pytest reported `259 passed, 19 skipped` in 187.63
seconds. Those three tests fail the job instead of skipping when the
variable is set and dbt is missing, so a green run means they executed.
Biome checked 10 files. The Node game-import tests passed, 10 of 10.
Ruff check, Ruff format, and basedpyright reported no errors. The MCP
protocol file passed, 8 tests in 3.28 seconds. `chesslab demo` printed
snapshot `b36f8a04cfd51ba30f454ed6`, source SHA-256
`130df65e85d18e78bbafd89daf6696c2596e03abf939adf47f2dcbdc4d33e75b`, and
draw rate 0.2. The semantic check printed `ERRORS: 0` and draw rate
`4,20,0.2`. The saved-answer rescore was 50/50 in 0.001294 seconds.
A rerun after the review fixes in `gate.py` printed snapshot
`f2541bd7776d980764465e4b` with the same source checksum and draw rate,
`250 passed, 31 skipped` without dbt, `262 passed, 19 skipped` under
`CHESSLAB_REQUIRE_DBT=1`, and `ok 89/89` from the gate in 13.505 seconds.

Mutation evidence, from `tests/test_eval_gate.py`:

- The ten answer mutations from `tests/test_m5.py` each turn a passing
  `portfolio_outcome` into a failing one, and the diff is `REGRESSION`.
  Those mutations use an in-memory case with the M5 result shape. They
  are not replayed against the four-game warehouse. The fixture's expected
  subsets do not include wins, draws, and losses, so those fields are not
  on a live `gate_v1` case.
- Dropping `observed_prefix_only` from `answer_caveats` fails
  `gate_v1/game_draw_rate` and the report names that case.
- Adding one to a `query_metric` numerator fails the same case with
  `result_values`.
- A plan whose interpretation is edited fails `load_gate_cases` with
  `hash changed`.
- A baseline pass flipped to fail is `IMPROVEMENT` and the check exits 1.
  Deleting a baseline case is `ADDED`. Changing a baseline hash prints
  `case set hash changed: gate_v1`. Deleting a case from the fresh
  scorecard is `REMOVED`.
- Forcing `resolve_governed` to return `None` on a dbt-staged project is
  `PATH-CHANGED` for `gate_v1/game_draw_rate`, from `governed` to
  `reviewed_sql`. Returning the reviewed-SQL payload without calling
  `query_rows` is the same `PATH-CHANGED` label.
- A `duckdb.Error` whose message contains a temp path, raised from replay
  for one question, is stored as `exception:Error` with `<path>` in place
  of that path. `collect` still returns all 24 `gate_v1` cases.
- An empty scorecard compared with an empty baseline exits non-zero and
  does not print `ok 0/0`.
- A mart copy with every `1/2-1/2` result in `fact_game` changed to `1-0`,
  as in [ADR 0085](0085-governed-semantic-layer-metricflow.md), fails
  `gate_v1/game_draw_rate` while the path stays `governed`. `games` is a
  view, so the governed query sees the edited source rows. The copy's
  warehouse checksum is updated so mart validation still accepts it.
- `--update` writes canonical bytes, a second check passes, a second
  update does not change those bytes, and `--update` exits 1 without
  rewriting the file when `CI` is present, including `CI=1` and `CI=`.
- Two `collect` calls on one staged project return the same bytes.

The path and poison tests skip unless the dbt extra is installed. With
`CHESSLAB_REQUIRE_DBT=1` they fail instead of skipping.

Two throwaway commits were pushed and then reverted.

The first throwaway commit is `d3f098e`. Its Actions run is
https://github.com/jfk-ssa/chess-analytics-lab/actions/runs/39166570679.
Plain pytest failed at `tests/test_eval_gate.py:147` (`assert 0 == 1`) and
at `tests/test_eval_gate.py:394` before the gate step ran. The step
`Offline analyst eval regression gate` did not start.

The second throwaway commit is `8779f73`. Its Actions run is
https://github.com/jfk-ssa/chess-analytics-lab/actions/runs/39166880322.
That is the run whose failing step is `Offline analyst eval regression
gate`. Every earlier step in that offline job passed, including
`248 passed, 30 skipped` without dbt and `259 passed, 19 skipped` under
`CHESSLAB_REQUIRE_DBT=1`. The log line is:

```text
REGRESSION gate_v1/game_draw_rate pass->fail [result_values] expected {"failures": [], "passed": true, "path": "governed"} got {"failures": ["result_values"], "passed": false, "path": "governed"}
```

That commit did not change the fixture. After a correct replay,
`run_scorecard` marked `game_draw_rate` failed so the command would exit
1 while pytest, which calls `collect` rather than `run_scorecard`, stayed
green. The commit is reverted. The case numerator is 1, matching
`portfolio_expected.json`.

## Consequences

CI fails when the deterministic stack, a replay plan, or the baseline
disagrees with the committed scorecard. An intentional change updates the
baseline with `--update` and explains the diff. `--update` cannot run
when `CI` is present in the environment, including an empty value. The
plain pytest job stays green without dbt. The gate job is the one that
requires the mart.

`evaluation.py` stays free of this module. Engine scoring stays in
`engine_eval.py`.

## Follow-up

Item 3b is a scheduled or manual live LLM eval. It is not part of this
gate. It needs its own key and its own spending cap. The design to use
when that run is authorized: at least three repeats, an aggregate
pass-rate baseline with a tolerance band, and a committed receipt that
records the model, the prompt hash, and the cost. That receipt is a live
result. It does not replace this scorecard, and it does not run in the
offline job.
