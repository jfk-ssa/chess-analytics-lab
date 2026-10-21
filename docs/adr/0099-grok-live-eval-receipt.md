# 0099. grok-4.7 live-eval receipts and reasoning-effort sweep

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

## Reasoning-effort sweep

Two more artifacts are committed unchanged.

`reports/live-eval-receipt-grok-4.7-medium-r1-39583448999.json`, SHA-256
`539210c8ec139f48f3d8664ce8b827c61a6bbee8cabae2bb86c7358c1923b856`. Actions run
[39583448999](https://github.com/jfk-ssa/chess-analytics-lab/actions/runs/39583448999)
at `15aaeb364d8b066a742d3d2db5b7eb8219238b17`. Runner `run_id`
`10f0661cc4054f31a5eaaf76e60a1a31`. Effort `medium`, one repeat, cap 4,
`reserved_usd` 3.734254, `known_gross_cost_usd` 0.322454. Headline 45/48
(0.9375). Wilson 0.8316456194505365 to 0.9785167670916107. Bootstrap
0.8541666666666666 to 1.0. `hard_fail` false. Over-abstention 3. Reasoning
tokens 32,410. The failed rows are `coverage_1`, `coverage_2`, and
`indirect_opening_1`, each an `unsupported` over-abstention.

`reports/live-eval-receipt-grok-4.7-high-r1-39583461520.json`, SHA-256
`185d7dfcc4dcd9b92983420ed7798ac218788a65c2d2927d13bd024302ff724a`. Actions run
[39583461520](https://github.com/jfk-ssa/chess-analytics-lab/actions/runs/39583461520)
at the same commit. Runner `run_id` `471dacf9c8be41ab95b62d21978729ec`. Effort
`high`, one repeat, cap 6.5, `reserved_usd` 6.093358. The JSON number
`known_gross_cost_usd` is `0.40874600000000005`; six decimal places print
$0.408746. Headline 47/48 (0.9791666666666666). Wilson 0.8910078200474814 to
0.9963128890224893. Bootstrap 0.9375 to 1.0. `hard_fail` false.
Over-abstention 1. Reasoning tokens 46,763. The failed row is
`indirect_opening_1`, an `unsupported` over-abstention.

`frozen_file_sha256`, `case_set_sha256`, and `fixture_sha256` match the low
receipt and this checkout. `instructions_sha256` does not. Low is
`622007a3deb785c204e58ba68419af0adbb0c0929d29dd97241038514d17181f`. Medium and
high are both
`be294fd35f35327317ab64e58a202ef822347e9ac3451cda01bdc29ae15cc8d3`. That digest
is SHA-256 of the literal instructions text in `live_runner._quote`, the
`instructions` field of the quoted request body. Reasoning effort is not in
that string, so medium and high share it. Rebuilding the prompt at e396cf4 and
at 15aaeb3, with the analytical snapshot id each tree produces, matches those
two digests. Both prompts are 10,427 characters. The only difference is
`Dataset: 06bc03a3eabab5bbf3b958ec` versus
`Dataset: bea194558220eb669940d8f3`. The source snapshot ids are
`000af1d6788d6662b5ddbc5f` and `833e99dd7038ee87a28ae339`. `analytics_hash` is
unchanged (`d6b3209a334ab3ad`). The files inside `implementation_hash` that
differ are only `src/chess_analytics/eval_report.py` and
`src/chess_analytics/public_extract.py`. `uv.lock` and
`tests/fixtures/live_eval_100.pgn` are the same bytes. The model therefore
sees a different 24-character snapshot id. That is material. ADR 0096 treats
a dataset-id-only difference as comparable only for the known Luna/Sol hash
pair, or when both receipts record distinct `dataset_id` values. These grok
receipts have no `dataset_id`. `pair_explained_by_dataset_id` stays false for
this hash pair. The 5-repeat low run versus medium, and that low run versus
high, are not strictly comparable. The clean comparison is one repeat each of
low, medium, and high on the shared hash. The owner is running that low x1
from 15aaeb3. It is not in this tree yet. The page holds an empty slot,
`data-sweep-slot="low-1"`, and does not plot the 5-repeat run on the sweep
chart. Medium versus high share the prompt, the frozen inputs, the case ids,
and one repeat, so they are a matched pair. The sweep sign-tests only that
pair until the slot fills: high is better on 2 cases, medium on 0, exact
two-sided p = 0.5. It does not sign-test the 5-repeat low against either, and
it does not say whether that run's Wilson interval overlaps theirs. Medium and
high Wilson intervals do overlap. Medium and high clear the gate. That is a
gate fact, not a pass-rate ranking.

The 5-repeat low run stays the headline. Per repeat it costs $0.200661 (about
$0.20) and uses 13,955.2 reasoning tokens. That spend is not a quality result.
`usage_sicilian_3` is 3/5 on that headline run (one over-abstention, one wrong
answer) and passes the single medium draw and the single high draw, so it
stays on the headline grid and is not a 1-repeat sweep row. Medium costs
$0.322454 and uses 32,410 reasoning tokens. High costs $0.408746 and uses
46,763. On the 1-repeat arms, the other 45 cases pass. `coverage_1` and
`coverage_2` fail the one medium draw as over-abstention and pass the one high
draw. `indirect_opening_1` fails both as over-abstention.

The 1-repeat runs are not folded into the 5-repeat Wilson chart, the category
chart, the case grid, or the six headline cards. The gate card stays
`Luna, grok-4.7 low clear; Sol fail`. Full case and category rows for the
1-repeat runs would not fit the 262,144 byte budget. Those rows are omitted.
`live_eval_effort_case` stores the 6 grok rows for the three 1-repeat cases
above, medium and high only. A later low x1 on the same hash fills the low
rows. `(model, effort)` may repeat when the repeat counts differ and exactly
one receipt has 5 repeats. The non-headline twin's rate id is
`live_eval_pass_rate:grok-4.7 low r1`. A second 5-repeat low still fails the
uniqueness check. Run rows gain `instructions_sha256` and `reasoning_tokens`.
The committed extract is 257,899 bytes. The same tables without the `build`
key are 257,553 bytes. Both are under 262,144. The metric receipts
`live_eval_pass_rate:grok-4.7 medium` (45/48) and
`live_eval_pass_rate:grok-4.7 high` (47/48) are `committed_report`. The build
record and the non-live tables are unchanged.

## What this record leaves in place

This checkout makes no model call. The workflow still does not commit
receipts. The offline gate baseline is unchanged. The open question in
ADR 0093, whether an empty-action `needs_clarification` should count as
the refusal for the spending-cap sentence, is unchanged. Sol still
hard-fails on `boundary_budget`. The HTTP 400 run stays in ADR 0097
and is not a pass rate.
