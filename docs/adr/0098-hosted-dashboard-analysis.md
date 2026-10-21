# 0098. Hosted dashboard analysis

- Status: accepted on merge
- Date: 2026-10-21

## Motivation

[ADR 0094](0094-hosted-read-only-dashboard.md) shipped a read-only page
that opened on provenance hashes, then one draw rate, one bar chart,
and raw tables. Extract version 1 held the August family shares, two
Black opening-score cells, four clock buckets, and the 275 clock
strata. It had no rating-by-control rollup, no transposition aggregates,
and no live-eval summary. The full opening-position report stays off
the tip ([ADR 0072](0072-opening-rankings-stay-outside-the-tip.md)).

## Decision

`extract_version` is `"2"`. The reader rejects any other version. New
tables are `committed_report`. A warehouse-less rebuild fills them from
committed files and leaves their receipts unlabeled. The three governed
metrics stay `metricflow`, and the four clock buckets stay
`reviewed_sql`, only on a rebuild that has the analytical warehouse.
The committed file keeps the 2026-10-20 MetricFlow labels and build
record.

`opening_color_score` has four cells: French Defense and Sicilian
Defense, White and Black, ratings 1400–1599, 60+0. Counts come from
`reports/M3-independent-reference.json`. The adjusted cluster-bootstrap
interval from `reports/M4-figures.json` is attached only where that
publication's family, color, rating window, time control, and counts
match, which is the two Black cells. `low_support` is `games < 100`,
the same rule as `src/chess_analytics/corpus/metrics.py`. All four
cells are above that line. White adjusted fields are null. No other
rating band is invented, and the score interval is the published
bootstrap interval.

`clock_pressure_band` pools `clock_stratum` by rating band and time
control: sum the counts, then divide. A cell with zero evaluable moves
stores a null error proxy. M4's caveat stands: moves inside a game are
dependent, so this table has no interval.

Transposition rows come from `reports/opening-positions-dashboard.json`.
That file is the aggregate reduction of pinned
`reports/opening-positions.json`
(`31a395044203532224cbb387475ef0bb790c8e88faac98bc9b2a12f5d500c46e`,
commit `c1e3040a3c9542626a3b8cb78e1e7475ea8bcdab`). The builder reads
the reduction. It does not need the blob, which a fetch-depth-1
checkout often lacks. The reduction copies compression, the all-view
coverage curves, per-opening view counts, and the seven limitation
strings. It has no position ids, moves, or ECO labels.
`transposition_scope` copies games, visits, ply bounds, and the
positions hash from `reports/opening-positions-checkpoint.json`.

`live_eval_run`, `live_eval_category`, and `live_eval_case` come from
complete receipts under `reports/live-eval-receipt-*.json`, checked
with `eval_report.verify` against `evals/cases/analyst_live_v1.json`.
Wilson bounds are the receipt's `stats.wilson`. A headline row has
`repeats == 5` ([ADR 0096](0096-published-live-eval-report.md)). This
checkout has two such receipts, gpt-6-luna and gpt-6-sol, both effort
`none`. The model allowlist includes `grok-4.7` so a future receipt can
validate. This extract does not invent a grok row.

The hosted page leads with three cards: opening-corpus training games
(1,042,346), the August draw rate (3.7%, 3,669 / 99,117), and the
highest 5-repeat pass rate. That rate is gpt-6-sol at 97.5%, and the
card says hard fail. Tabs are Overview, Openings, Clock pressure, AI
analyst eval, and About the data. Provenance hashes are on About the
data. Each chart has a one-line takeaway, and a separate caption names
one query origin.

Charts use an Altair theme named `chesslab`: Inter, a transparent
background, and the page palette. `st.altair_chart` is called with
`theme=None` so Streamlit does not replace it. `.streamlit/config.toml`
is unchanged, and the local six-view dashboard is unchanged. The font
file is still the copy recorded in ADR 0094.

Card rows are an inline grid,
`grid-template-columns: repeat(N, minmax(0, 1fr))`, with `min-width: 0`
on each card. `N` is the number of cards in that row. The hero uses 3.
The eval tab uses 4. The contract is the same at every viewport,
including 390px, so the row stays one row of equal tracks.

`hosted/requirements.txt` adds `altair==5.5.0` and `narwhals==2.26.0`,
the lock versions that Streamlit 1.65.0 installs. Narwhals has no
dependencies. The extract is 246,655 bytes, under the 256 KiB budget.

## Consequences

Community Cloud settings stay main file `hosted/dashboard.py`, Python
3.12, and `hosted/requirements.txt`. No secrets, no warehouse, and no
network at runtime. `tests/test_public_extract.py` copies the reduction,
the checkpoint, the live-eval receipts, and the case file into the
warehouse-less builder fixture. `tests/test_hosted_dashboard.py` checks
the chart list and the equal-width markup. A browser check measures
card widths at 1280px and 390px.

The page states these limits in the captions: one published rating
window; adjusted intervals for Black only; no clock interval; the
all-view recurring and transposing coverage curves match, so the chart
draws the recurring curve; 1800+0 is not a steady fall across rating
bands; the higher pass rate still hard-fails on `boundary_budget`.
There is still no homepage link.
