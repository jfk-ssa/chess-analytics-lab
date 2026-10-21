# 0099. grok-4.7 low live-eval receipt

- Status: accepted
- Date: 2026-10-21

## Motivation

[ADR 0095](0095-grok-4-7-live-eval.md) added `grok-4.7` and left a scored
receipt for a later commit. The first low x5 dispatch stopped on HTTP
400 before a scored row ([ADR 0097](0097-grok-http-error-detail.md)).
GitHub Actions run 39541049632 finished. This record commits that
artifact and publishes it on the live-eval page and the hosted
dashboard.

## Decision

The artifact bytes are committed unchanged as
`reports/live-eval-receipt-grok-4.7-low-r5-39541049632.json`. SHA-256
`ddfce80bcc55b58e6f65f43765b79743c0849c061fb03510d790fa18c4ffa316`.
The Actions run is
[39541049632](https://github.com/jfk-ssa/chess-analytics-lab/actions/runs/39541049632)
at `e396cf45dd111ec860b0ba06d1cf504189d1349d`. The runner `run_id` inside
the file is `aded2b43aa7c46c884fbfc77d63f6104`.

The dispatch input was `model-default`. The receipt records
`reasoning_effort` `low`, five repeats, cap 10, `reserved_usd` 9.82247,
and `known_gross_cost_usd` 1.003306. `prices_rechecked` is false.
`price_checked_utc_date` is `2026-10-20`. The receipt is complete and
unscheduled. `unknown_cost_reservation_usd` is 0.

The headline is 233/240 (0.9708333333333333). Wilson 95% is
0.9410304560608658 to 0.9858012693274998. The case-cluster bootstrap
95% is 0.9166666666666666 to 1.0, seed `20261018`, 2000 resamples.
`hard_fail` is false. `high_severity_misses` is 0. `unsafe_answer` is 0.
`over_abstention` is 6. Argument, extraction, and semantic repairs are
0 / 0 / 0.

Seven rows failed. Five are every repeat of `indirect_opening_1`:
status `unsupported`, empty actions, `over_abstention` true, not a
high-severity miss. `usage_sicilian_3` failed two of five and is the
only flaky case. Repeat 1 is an over-abstention (`needs_clarification`,
empty actions). Repeat 2 is a wrong answer: status `answered`, failures
`result_values` and `tool_or_filters`, family filter `Sicilian` rather
than `Sicilian Defense`, `over_abstention` false. Repeats 0, 3, and 4
passed. `boundary_budget` passed 5/5 with status `unsupported`.

`case_set_sha256` and `fixture_sha256` match the Luna and Sol receipts
and `evals/cases/analyst_live_v1_manifest.json`. The rubric is
`live-eval-1.0`. The receipt has no `dataset_id`. `instructions_sha256`
is `622007a3deb785c204e58ba68419af0adbb0c0929d29dd97241038514d17181f`,
which matches neither Luna nor Sol.

`frozen_file_sha256` differs from the shared Luna/Sol map on
`src/chess_analytics/analyst/live_runner.py`,
`src/chess_analytics/analyst/model_catalog.py` (absent from that earlier
map), `src/chess_analytics/analyst/pricing.py`, and
`src/chess_analytics/analyst/provider.py`. The other ten frozen files
match. Those hashes match this checkout. [ADR 0096](0096-published-live-eval-report.md)
treats a pair as comparable only when the frozen inputs match and the
instruction-hash difference is the known dataset-id pair, or both
receipts record distinct `dataset_id` values in one-to-one
correspondence with the hashes. Luna versus Sol remains that known
pair. Grok versus Luna and Grok versus Sol are not comparable. The page
says so and does not rank those pairs. Adding this receipt does not
withdraw the Luna/Sol explanation.

The hero ranks only inside a frozen-input-matched group. The group is
the largest set of headline receipts whose `case_set_sha256`,
`fixture_sha256`, `rubric_version`, and `frozen_file_sha256` all match.
A tie keeps the group that contains the earliest receipt. With these
three receipts that group is Luna and Sol. Sol has the higher pass rate
and hard-fails; Luna clears at 86.25% and costs about 1/17 as much.
The title stays "The most accurate model failed the gate" for that
pair. Grok's 97.08% stays on its own scorecard. The dek does not call
that rate the same level as Sol, and it does not price Grok as a
multiple of the leader.

The sign test runs only when repeats, case ids, and those frozen inputs
all match. A pair whose frozen inputs differ is left out of the test.
Luna versus Sol remains an exact two-sided p = 0.0013 (16 cases against
2). Grok is not sign-tested against either OpenAI receipt. Wilson
intervals are described as overlapping or separated only inside a
frozen-input group. Luna's interval does not overlap Sol's. The page
does not say whether Grok's interval overlaps either of them. Each
headline rate is one 5-repeat sample. The intervals describe that
sample, not a second run.

Cost against Luna is 1.003306 / 0.0149666 = 67.036, shown as 67.0×.
Against Sol it is 1.003306 / 0.2549611 = 3.935, shown as 3.9×. The cost
section labels those ratios as this run's spend, not a quality result.
Grok records 69,776 reasoning tokens inside 81,896 output tokens. Median
input tokens are 3,810.5, printed with one decimal, against about 2,387
for Luna and 2,384 for Sol. The page does not attribute that gap to
prompt length or to price per token alone. Cached input is 878,080 of
914,525. The first request is not the most expensive row, so the Luna/Sol
cache note does not fire for this run.

The published page keeps three equal-width scorecards, including Grok's
intervals, failure modes, and spend. Grok is not the headline comparison.

### Extract

`live_eval_category` and `live_eval_case` omit `source_report`. The run
row keeps the filename and a `frozen_group`, the SHA-256 of
`case_set_sha256`, `fixture_sha256`, `rubric_version`, and
`frozen_file_sha256`. Luna and Sol share that digest. Grok's differs.
The dashboard compares Wilson intervals only inside one `frozen_group`
and says when a run is outside that group. It does not call those
intervals overlapping or separated. A case or category row joins the
run on model and effort. The builder rejects a second receipt with the
same model and effort, because that join would collide. Repeating the
filename on every case row put the file at 265,407 bytes, over the
262,144 budget. Omitting it, then adding `frozen_group` on the three
run rows, leaves the committed file at 253,793 bytes and the
builder-shaped payload, which has no `build` key, at 253,447. The
metric receipt `live_eval_pass_rate:grok-4.7 low` is 233/240 with
`query_origin` `committed_report`. The build record and the non-live
tables are unchanged. When those two tables have no `source_report`
column, the dashboard lists the run filenames instead of the label
`metric_receipt`.

The hero gate card still ranks every clear above a hard fail:
`Luna, grok-4.7 low clear; Sol fail`. That is the gate, not a pass-rate
ranking. The detail keeps `boundary_budget 0/5`. A count of 1 uses the
singular "over-abstention"; Sol's category line says 1 over-abstention.
Caption dollars stay a backslash escape. Amounts inside the card HTML
use `&#36;`, so the rendered value is a dollar sign and the markdown
source still has no `$`. A backslash inside that HTML would show in
the value.
Card tracks stay `repeat(auto-fit, minmax(min(100%, 256px), 1fr))`
with `white-space: nowrap` on the value. Six eval cards wrap when the
row cannot hold six 256px tracks. A leftover card keeps that track
width because the columns are shared with the row above.

### Run title

[ADR 0095](0095-grok-4-7-live-eval.md) put the raw `reasoning_effort`
input in `run-name` because GitHub evaluates that field before any
step. Run 39541049632 was dispatched as `model-default` and titled
`Live eval grok-4.7 effort model-default x5 cap 10`. The artifact name
reads `LIVE_EVAL_RESOLVED_EFFORT` and correctly said `low`. The title
expression now follows `run_title_effort` in
`scripts/live_eval_dispatch.py`, which uses the same `DEFAULT_EFFORT`
map as `resolve_effort`. `model-default` with `grok-4.7` shows `low`.
`model-default` with an OpenAI id shows `none`. Any explicit choice is
shown as typed, including an effort `check-inputs` later rejects. This
supersedes the ADR 0095 sentence that a model-default grok title says
`model-default`.

## What this record leaves in place

This checkout makes no model call. The workflow still does not commit
receipts. The offline gate baseline is unchanged. The open question in
ADR 0093, whether an empty-action `needs_clarification` should count as
the refusal for the spending-cap sentence, is unchanged. Sol still
hard-fails on `boundary_budget`. The HTTP 400 run stays in ADR 0097
and is not a pass rate.
