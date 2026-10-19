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
does not stop the run. Any high-severity miss sets `hard_fail` on the
receipt. The process still exits 0 when the measurement finished.
`hard_fail` is not a CI check.

The runner does not call `live_answer`, because that function executes
the semantically repaired plan. It reuses `quote_request`, `_extract_plan`,
`_normalize_plan`, `_repair_opening_usage`, and `price_usage`. Checked
tools run in-process through `execute_plan` with `source="fixture_replay"`,
the same path as the oracle. The killable worker stays on the frozen
`live_answer` path.

### Budget

Before any send, and before the key is read, the runner sums
`quote_request` reservations across the cases and multiplies by the
repeats. If that total exceeds `max_run_usd`, it raises and the
transport is not called. Recommended caps are printed. They are not a
second limit. Luna's recorded cap for this envelope is $0.50. Sol's is
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
`passes_by_case` aligns rows by sorted case id. A case is discordant when
the pass counts differ. Ties are dropped. The p-value is
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
receipt fields, and a repeated bootstrap seed. The full offline bar is
recorded on the pull request after it is run.
