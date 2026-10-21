# 0096. Published live-eval report

- Status: accepted
- Date: 2026-10-21

## Motivation

[ADR 0093](0093-first-live-eval-receipts.md) commits the Luna and Sol
receipts and leaves them as JSON. A portfolio reader should be able to
see the gate, the intervals, and the hard fail without opening those
files. The documentation site already publishes recorded evidence. This
report belongs there, generated in the same offline build.

0094 is left for the hosted dashboard record on #44. 0095 is the
grok-4.7 live-eval record on #45. This record is 0096 so it does not
take either number.

## Decision

`chess_analytics.eval_report` reads every
`reports/live-eval-receipt-*.json`, sorted by the GitHub run id in the
filename. It does not list run ids. ADR 0091 files are
`live-eval-receipt-<run id>.json`. ADR 0095 files are
`live-eval-receipt-<model>-<effort>-r<repeats>-<run id>.json`. The
sort key is the trailing integer in either name. A run is labelled
with its `model`. When `reasoning_effort` is present and is not `none`,
the label adds that effort. The same model at low, medium, and high
stays three runs, for example `grok-4.7 · low`, `grok-4.7 · medium`,
and `grok-4.7 · high`. A 1-repeat arm is not folded into the 5-repeat
headline.

The Pages build renders `live-eval.html` through the existing Jinja
shell and links it from the Lab strip. The build fails if a receipt
total does not match its rows. Output does not include a clock, a
download, or a font request to a CDN. Charts are inline SVG with
`title` and `desc`. The headline is the raw pass rate. Repair counts
sit beside it and do not replace it.

Headings, the dek, the large rates, and the hard-fail question use
Inter, the Latin variable file the site and dashboard already share
(`src/chess_analytics/dashboard/static/fonts/inter-latin-wght-normal.woff2`,
SIL OFL 1.1). Every page preloads that file. `font-display` stays
`swap`. Code and case ids use a local monospace stack. No second
webfont is vendored and none is inlined as base64.

The Lab row at 601–960px is six columns. The primary row stays five.
At 600px and below, Lab remains one wrapping line.

### Instruction hash

The two committed instruction hashes differ only by the 24-character
dataset id. The prompt embeds `Dataset: {dataset_id}`. That id comes
from `implementation_hash` over `src/**/*.py`, `src/**/*.sql`, and
`contracts/*.json`. Adding `public_extract.py` in #42 changed the hash.
Those two runs share the case set, the fixture, the rubric, and the
frozen planner files, so they are comparable. The page says that only
for that known hash pair, or when every receipt records a differing
`dataset_id` and the other frozen inputs still match. Any other hash
difference is reported as unrecorded, and those runs are not called
comparable. A later receipt should record `dataset_id` and
`implementation_sha256`.

Runs with a different repeat count are not sign-tested against the
headline cohort and are not described as the same number of requests.
They appear in a sensitivity section. The sign test is
`live_stats.exact_sign_test`, which refuses unequal repeat lists.

Sol's `hard_fail` stays the five `boundary_budget` repeats: expected
`unsupported`, emitted `needs_clarification`. That panel is derived
from the rows.

## What this record leaves in place

Push and pull-request CI still do not call a model. The live-eval
workflow still does not commit receipts. The offline gate baseline is
unchanged. Publishing the page does not close the open question in
ADR 0093 about whether an empty-action `needs_clarification` should
count as the refusal for the spending-cap sentence.
