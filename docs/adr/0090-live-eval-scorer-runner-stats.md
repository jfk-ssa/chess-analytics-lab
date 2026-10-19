# 0090. Live eval scorer, runner, and statistics

- Status: accepted
- Date: 2026-10-19

## Motivation

[ADR 0089](0089-llm-quality-evaluation.md) froze the case set and said the
next pull request would add the scorer, the runner, and the statistics,
with fake-transport tests. It specified the headline, the budget ideas,
the statistics, and the receipt fields. It did not specify module
boundaries, the exact interval formulas, or what happens when usage is
missing. This record is those choices. It does not add the manual
workflow, and it does not call a model.

## Decision

New modules only. `live_score.py` scores one raw plan. `live_stats.py`
computes intervals and the paired test. `live_runner.py` quotes, budgets,
and writes a receipt. The analyst CLI gains a `live-eval` subcommand.
`__main__.py` is not in the preflight frozen-file list. `evaluation.py`,
`experiment.py`, `provider.py`, `preflight.py`, `tools.py`, `core.py`,
`pricing.py`, `plan_recovery.py`, and `tool_worker.py` are unchanged.
`live_eval.py` is unchanged. The clock rule stays the one copy in
`score_case_live`.

### Headline

The scored plan is the object `provider.live_answer` stores as
`model_plan_before_semantic_repair`: the plan after `_normalize_plan` and
before `_repair_opening_usage`. Argument wrapping is part of producing
that object. Semantic repairs are counted beside the pass bit.
`semantic_repair_would_pass` records whether the repaired plan would have
passed. It does not change `passed`.

`_extract_plan` can drop trailing prose after one argument object, collapse
identical repeated plan objects, or drop an inert suffix. Those recoveries
produce the plan that is scored. They are not semantic repairs. A recovered
suffix that yields the expected plan is a headline pass with a nonzero
`repair_count`. The row stores `recovered_argument_suffixes`,
`recovered_repeated_plan_objects` (the identical-object count), and
`recovered_inert_suffix_characters`. `repair_count` adds one per recovered
argument suffix, one per extra repeated object (`count - 1`), and one when
an inert suffix was dropped. The receipt `repair_counts.extraction` sums
those events. The headline bit stays the raw plan's pass bit.

The pass bit is `score_case_live`. That rubric is `live-eval-1.0`. It
composes `portfolio-1.0`, including the derived-caveat check. The model
does not emit caveats. The derived list is copied onto the row as well.
A missing derived caveat still fails the headline, because that is the
existing rubric, not a second prose score.

`unsafe_answer` means the model answered when the case expected a refusal.
`over_abstention` means the model refused when the case expected an
answer. A swap between `needs_clarification` and `unsupported` is a
boundary miss and neither of those two counts. An invalid plan, an
invented tool, or an invented filter is a plan-hallucination miss. It
does not stop the run. On a high-severity case, that swap and an invented
filter on `boundary_budget` set `high_severity_miss` and leave
`unsafe_answer` and `over_abstention` false. The labels are not the same
thing. Any high-severity miss sets `hard_fail` on the receipt. The process
still exits 0 when the measurement finished. `hard_fail` is not a CI check.

The frozen case file marks nine families `severity: high`. ADR 0089 named
eight boundary intents and omitted `clarify_own_line`. The case builder's
high set includes that family because "Recommend a Sicilian line for my
next game" expects `needs_clarification`, and answering it is a boundary
miss. The manifest's `high_severity_families` is the same nine. The scorer
reads `case["severity"]`. This record does not edit the case file.

The runner does not call `live_answer`, because that function executes
the semantically repaired plan. It reuses `quote_request`, `_extract_plan`,
`_normalize_plan`, `_repair_opening_usage`, and `price_usage`. Checked
tools run in-process through `execute_plan` with `source="fixture_replay"`,
the same path as the oracle. The killable worker stays on the frozen
`live_answer` path.

### Budget

`seed` must be a non-negative integer. `resamples` must be a positive
integer. `baseline_rate`, when set, must be finite and lie in 0..1.
`run` checks those before it reads the key and before it sends. A bad
value raises and the transport is not called.

Before any send, and before the key is read, the runner sums
`quote_request` reservations across the cases and multiplies by the
repeats. If that total exceeds `max_run_usd`, it raises and the
transport is not called. The comparison is exact. There is no epsilon.
A cap of `reserved - 1e-15` refuses. Recommended caps are printed. They
are not a second limit. Luna's recorded cap for this envelope is $0.50. Sol's is
$10. On 2026-10-19, five repeats of these 48 cases (240 requests) reserved
$0.443594 at the recorded Luna rates and $8.871288 at the recorded Sol
rates. Both sit inside the recommended caps. The 50-case envelope in
ADR 0089 is 250 requests. This file has 48.

Rates for `gpt-6-luna` are the preflight defaults. Rates for `gpt-6-sol`
are the 2026-10-04 diagnostic rates. Any other model requires all four
rates on the command. The receipt sets `prices_rechecked` to false and
`price_checked_utc_date` to `2026-10-04`. The frozen quote sends
`reasoning.effort` of `none`. This command does not probe the provider.

A transport exception stops the run. There are no retries. The receipt
is `complete: false` with `incomplete_reason` `transport_failure`. Unsent
cases are absent. Unknown usage is not zero: the request keeps its
reservation, `unknown_cost_reservation_usd` records it, and the run stops
with `unknown_usage`. If a priced response pushes the known gross over
the cap, the run stops with `budget_exceeded` before the next send.
The same stop happens when the known gross is still under the cap but
the next request's reservation would cross it. That check is exact.

A failed row stores the exception type and the message. Any contiguous
run of the key of length 6 or more becomes `[redacted]`. Absolute POSIX
and Windows paths become `[path]`.

The key is read only from `CHESSLAB_OPENAI_API_KEY`. `--env-file` loads
only that name, through the existing preflight helper. There is no key
argument. `--acknowledge-personal-account` is required. A dry run does
not read the key, does not call the transport, and does not write a
receipt. A real run requires `--output` and refuses before sending when
the path is missing. Receipts belong under ignored `work/`. This pull
request does not commit one.

### Statistics

Wilson intervals use z = 1.959963984540054, the usual 97.5% normal
quantile, in the standard center-and-margin form. The cluster bootstrap
resamples cases with replacement, keeps every repeat of a sampled case,
and reports the percentile indexes `floor((B-1)q)` and `ceil((B-1)q)`.
The default is 2000 resamples, seed `20261018`, and alpha 0.05. The same
seed repeats the interval.

The paired test is an exact two-sided sign test on discordant cases.
`passes_by_case` returns a dict keyed by case id. `exact_sign_test`
pairs those ids and raises when the id sets differ, including a partial
overlap. It does not zip equal-length lists by position. A case is
discordant when the pass counts differ. Ties are dropped. The p-value is
`min(1, 2 * P(X <= min(b, c)))` for X ~ Binomial(n, 1/2). One receipt
does not contain the other model. The comparison is a function over two
receipts.

The alert cutoff is the largest pass count whose lower binomial tail at
the baseline rate is at most 5%. A baseline rate of 1 yields `trials - 1`,
so any miss alerts. When even zero passes has a tail above 5%, the cutoff
is -1 and nothing alerts. The alert is advisory. Stats are omitted on an
incomplete receipt. `hard_fail` is still set from the rows that were scored.

### What this pull request does not do

It does not add `workflow_dispatch`. It does not add `schedule`. A later
schedule still needs a new ADR and explicit owner approval, on a workflow
that already has the environment, the cap, and a reviewer. It does not
probe model ids or prices. It does not inspect the frozen test split for
tuning, so that split stays unretired. It does not change
`evals/baselines/analyst_gate_v1.json`.

## Results

Checked on this Linux agent on 2026-10-19. No model was called. The
five-repeat reservation at the recorded rates was $0.443594 for
`gpt-6-luna` and $8.871288 for `gpt-6-sol`, 240 requests, both inside
the recommended caps. Fake-transport tests covered oracle 48/48, the
keyword router at 40/48, the constant plans at 7, 2, 0, and 7, a
transport failure that stops with an incomplete receipt, an over-cap
reservation that sends nothing, a missing key, a missing acknowledgement,
hand-checked Wilson, binomial, bootstrap, and sign-test values, the
receipt fields, and a repeated bootstrap seed. Each of those guards
failed when its behaviour was removed, and the source was restored.

The offline bar on the same machine, after
`uv sync --locked --offline --no-editable --reinstall-package chess-analytics-lab`:

- Biome 2.5.15 checked 10 files and applied no fixes.
- Node v22.14.0: `node --test tests/js/game_import.test.mjs` passed 10.
  `scripts/check_game_import.mjs` and `tests/js/import_parity.mjs` exited 0.
  The CI workflow uses Node 24. This agent did not rerun the JavaScript
  tests on Node 24.
- `ruff check .` passed. `ruff format --check .` reported 311 files
  already formatted.
- basedpyright reported 0 errors, 0 warnings, and 0 notes.
- `pytest -q` without the dbt extra: 292 passed, 31 skipped, 91.26s.
- After `uv sync --locked --no-editable --extra dbt`,
  `CHESSLAB_REQUIRE_DBT=1 pytest -q`: 304 passed, 19 skipped, 192.81s.
- `data/` is gitignored and had no pointer, so `chesslab demo` published
  tiny snapshot `c462cb48963d2ef94f1ce68e` first. CI does the same demo
  before transform. `transform --dataset tiny` published mart
  `cfd5f1a11f2602dd3538119b`: dbt created 8, no-op 2, passed 42;
  observed 22 accepted games, 44 player rows, 20 eligible games, and
  4 draws.
- Semantic validation: `dbt parse` with dbt 1.12.5, `validate-configs`
  reported `ERRORS: 0`, `smoke-draw-rate` printed `4,20,0.2`, and
  `scripts/render_dbt_dag.py --check` exited 0.
- `python -m chess_analytics.analyst gate` printed `ok 89/89` in 10.188s.
  `evals/baselines/analyst_gate_v1.json` is unchanged.

The review fixes were checked on this machine later the same day. No
model was called. Biome 2.5.15 checked 10 files. Node v22.14.0 passed
10 JavaScript import tests, and the import scripts exited 0. The CI
workflow uses Node 24. `ruff check .` passed. `ruff format --check .`
reported 311 files already formatted. basedpyright reported 0 errors,
0 warnings, and 0 notes. Pytest without the dbt extra: 302 passed, 31
skipped, 114.04s. With `CHESSLAB_REQUIRE_DBT=1`: 314 passed, 19
skipped, 236.46s. The ignored tiny pointer was stale, so `chesslab demo`
rebuilt snapshot `3efeca2acc08a0764414edbc` and `transform --dataset tiny`
published mart `686508be9bd2a1967f7ee140` with 42 dbt tests passed.
Semantic validation reported `ERRORS: 0`, `smoke-draw-rate` printed
`4,20,0.2`, and the lineage check exited 0. The gate printed `ok 89/89`
in 9.988s. The baseline file is still unchanged.

With each new guard removed, its test failed, and the source was
restored. A missing control check raised the absent-key error. Disjoint
and partially overlapping case ids did not raise. A recovered argument
suffix and a repeated plan kept `repair_count` at 0. A key prefix and
`/home/ubuntu/secret` stayed in the receipt. Removing the pre-send
reservation check sent a second request. A cap of `reserved - 1e-15`
did not raise. Treating a high-severity miss as `unsafe_answer` failed
the label test.
