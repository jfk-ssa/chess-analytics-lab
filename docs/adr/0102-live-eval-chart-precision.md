# 0102. Live-eval chart precision on the hosted page

- Status: accepted on merge
- Date: 2026-10-21

## Motivation

The hosted live-eval charts drew the three 5-repeat receipts and kept the
1-repeat grok runs on a separate sweep. Pass-rate axes ran from 0% to 100%,
so the intervals sat in a narrow band at the right. The case grid rotated
model labels and colored a 0–5 count, which cannot sit next to a 1-repeat
column. The sweep cards clipped the reasoning-token line and overlapped the
chart under them.

## Decision

This is display only. The runner, catalog, pricing, provider, cases, rubric,
and scoring stay as they are. The extract stays 259,711 bytes. The page does
not recompute a Wilson interval.

The pass-rate chart, the category chart, and the reasoning-effort chart use
one axis rule. The lower limit is the smallest plotted value, including
Wilson lower bounds where the chart has them, minus 10 percentage points,
clamped at 0. The upper limit is 100%. The margin is 0.10 on the unit
interval, not 10 percent of the minimum. Ticks are whole percents: 5-point
steps when the window is 40 points or narrower, otherwise 10-point steps.

A 1-repeat bar is that receipt's Wilson interval on 48 trials (one repeat of
the 48 cases). It is not drawn as a 5-repeat rate. Those bounds are already
on the run row.

The case grid adds `grok-4.7 · low ×1`, `grok-4.7 · medium ×1`, and
`grok-4.7 · high ×1` after `gpt-6-luna`, `grok-4.7 · low ×5`, and
`gpt-6-sol`. Labels are horizontal, on two lines for an effort run, at 10px,
with no character limit. The column width is 112px per run so the label fits.
The chart block scrolls on its own: at a 390px viewport the page scroll width
stays 390 and the grid's container is 362px wide around an 821px chart.
Color is the pass fraction from 0 to 1. The cell prints `passed/repeats`.
The category legend is one column so a label such as `grok-4.7 · medium ×1`
stays inside a 362px chart. Tied rates share an x position. Each run is
offset symmetrically around the category label, on a faint row band. The
min-to-max line is not drawn. Luna stays `#116559` and Sol stays `#a84a1f`.
The other runs are blue `#1d4ed8`, violet `#7c3aed`, pink `#db2777`, and
yellow-green `#4d7c0f`.

Pass-rate, category, and case-grid charts keep padding around the axes. A
label such as `grok-4.7 · medium ×1` or `clock_compare_under_10_2`, and the
`Gate clear` legend, sit inside the frame.

Sweep cards print the per-repeat cost at three decimals (`$0.223`, `$0.322`,
`$0.409`). The caption under the chart still quotes the receipt figures.

The 1-repeat case and category rows are not in the extract. The page rebuilds
them from `live_eval_effort_case`: a case missing from that table passed.
The summed passes must equal the run row, which the extract already checked
against the receipt. That is how `coverage_2` is 0/1 on low ×1 and the other
47 cases are 1/1.

Labels are `grok-4.7 · low ×5` and `grok-4.7 · medium ×1`. Luna and Sol stay
`gpt-6-luna` and `gpt-6-sol`. No run hash. Cards in one row use that same
title helper. Sweep detail breaks only at ` · `, so `$0.22253 per repeat`
and `14,768 reasoning tokens` each stay intact.

The hard-fail line names every shown run. Sol still hard-fails. The four
grok runs clear. Wilson overlap is stated for Luna versus Sol, and among the
1-repeat trio. Low ×5 is not compared with Luna or Sol, because the frozen
runner files changed. It is not compared with the 1-repeat runs either: those
are like-for-like with each other, and low ×5 differs from them in the
dataset snapshot id embedded in the instructions.

Cost and reasoning tokens for all six runs are one table. Headline cost cards
also show the token count. The sweep table of imperfect 1-repeat cases stays.

## Consequences

The extract budget is unchanged. A later 1-repeat receipt still has to match
the effort-case convention or the page fails closed when the pass total does
not. The static live-eval page is unchanged.
