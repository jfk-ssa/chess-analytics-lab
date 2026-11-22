# 0120. Replace the hosted Streamlit app with a static Pages dashboard

- Status: Proposed
- Date: 2026-11-22

## Context

The repository now ships three overlapping presentation layers:

- The Community Cloud app under `hosted/`, which queries
  `data/public/dashboard_cube.parquet` and still reads extract version 2
  for live eval ([ADR 0094](0094-hosted-read-only-dashboard.md),
  [ADR 0101](0101-hosted-bi-cube.md),
  [ADR 0107](0107-hosted-repository-source-reload.md)). The live URL is
  https://chess-analytics-lab.streamlit.app/.
- The local Streamlit app at
  `src/chess_analytics/dashboard/dashboard.py`, which opens the local
  analytical warehouse and has six views: Overview and coverage,
  Opening comparisons, Clock pressure, Data quality, AI analyst, and
  Evaluation results.
- The GitHub Pages site built by `scripts/build_docs_site.py`, including
  the live-eval report and the transposition explorer.

The hosted app is the expensive surface. `hosted/requirements.txt` pins
nine packages. `tests/test_hosted_dashboard.py` includes
`test_hosted_streamlit_pin_matches_the_lock`, which breaks when a
Dependabot bump moves Streamlit, pandas, narwhals, or the other hosted
pins until the test, the requirements file, and often the docs are
updated together. Community Cloud reload quirks also produced
`hosted/repo_import.py` and the hand-bumped
`src/chess_analytics/build_info.py`, which only the hosted page and its
tests use.

`chesslab demo` does not launch Streamlit. It imports
`clock_analysis` and `opening_catalog` from
`src/chess_analytics/dashboard/analysis.py`. Checked analyst tools also
import coverage helpers from that module. The local six-view app is
exercised by
`tests/test_portfolio_demo.py::test_six_dashboard_views_and_empty_buckets`
and by `scripts/check_m4_dashboard.py`.

The committed cube is already a warehouse-less, identifier-free extract
suitable for a static page: 593,637 bytes and 35,100 rows at this
checkout, under the 10 MB budget from ADR 0101. Pages already serves
interactive charts with Inter, paper, teal, and the shared site tokens
in `site/assets/site.css` ([ADR 0060](0060-inter-medium-selected-for-current-guides-and-dashboard.md),
[ADR 0065](0065-shared-outer-canvas-and-semantic-table-columns.md),
[ADR 0118](0118-portfolio-page-presentation.md)).

## Decision

Build a static, interactive `dashboard.html` on GitHub Pages from
`data/public/dashboard_cube.parquet`, then retire the Community Cloud
app once that page is live and reviewed. Keep the local Streamlit
dashboard as an optional warehouse tool. This record is the plan; the
implementation is a later pull request.

The Pages dashboard is a CI artifact of the documentation workflow. The
build reads the committed cube, or a JSON view produced from it at
build time, and emits `dashboard.html` plus any small assets it needs.
It does not open a warehouse, call MetricFlow, or download. Filters and
charts follow the existing hosted cuts where the cube already supports
them: date, time control, color, rating band, and opening family on the
KPI strip, openings, transpositions, clock, and periods, with the same
fail-closed captions when a grain cannot carry a filter. Live-eval
figures stay on `live-eval.html` and keep ignoring those dashboard
filters, as they do today. Provenance (mart id, source snapshot, hashes)
stays visible.

Charts and layout reuse the Pages visual system: Inter, `--paper`,
`--ink`, `--teal`, `--accent`, `--line`, the 1120px canvas, and the
existing chart patterns in `site/assets/`. Do not add a new font, a
new palette, or a Streamlit-like chrome. Prefer the client-side
patterns already used on the transpositions and live-eval pages over a
new Python charting dependency in the Pages job.

Keep `src/chess_analytics/dashboard/analysis.py`. Keep
`src/chess_analytics/dashboard/dashboard.py` and the dashboard extra
for local use. `chesslab demo` continues to call the analysis
functions and does not start Streamlit. The local app stays useful
because it queries the local warehouse, including fixture replay on the
AI analyst view, which a public cube page cannot do. After the hosted
app is retired, the dashboard extra no longer has to satisfy the
Community Cloud pin contract; leftover hosted-only pins can shrink in
the retirement commit.

Rollout:

1. Add `dashboard.html` to the Pages build and navigation. Link it from
   the homepage, `PORTFOLIO.md`, and `docs/HOSTED_DASHBOARD.md`. Ship
   this first and review it on the deployed Pages site.
2. After that page is accepted, retire the Community Cloud deployment.
   https://chess-analytics-lab.streamlit.app/ goes away. Streamlit
   Community Cloud does not offer a durable HTTP redirect off that
   host, so the retirement commit takes the app down and, if the
   platform still serves a page, leaves a short notice that points to
   `https://jfk-ssa.github.io/chess-analytics-lab/dashboard.html`.
   Every in-repo link to the Streamlit URL is updated or removed in
   the same commit.
3. Delete `hosted/`, `hosted/requirements.txt`,
   `hosted/repo_import.py`, `src/chess_analytics/build_info.py`, and
   `tests/test_hosted_dashboard.py` (including the pin contract). Keep
   `data/public/dashboard_cube.parquet`, the cube builder, and the
   public extract that live eval still reads. Update
   `docs/HOSTED_DASHBOARD.md` to describe the Pages dashboard, or
   replace that guide with a short current page and leave the ADR
   trail in place.

Rollback: revert the retirement commit and restore the Community Cloud
settings (main file `hosted/dashboard.py`, Python 3.12,
`hosted/requirements.txt`) from git. The cube and extract will still be
on the tip. Reverting only the Pages dashboard commit leaves the
Streamlit app in place if retirement has not landed. No warehouse and
no secrets are involved.

## Consequences

Dependabot bumps of Streamlit, pandas, and narwhals stop breaking a
hosted pin test. Community Cloud reload workarounds go away. The public
dashboard becomes a static Pages artifact next to the rest of the lab
site, reviewed with the existing documentation suite.

The Streamlit URL stops resolving as a dashboard. Anyone with an old
link depends on the notice, if any page is still served, or on the
updated repository links. The local six-view app remains, so the
dashboard extra and some Streamlit tests stay until a later decision
retires that optional tool.

This change will likely exceed the 400-line guideline, mostly in the
new page, tests, and the later hosted deletion. Generated site output
stays outside that count.

## Alternatives considered

Retire both Streamlit apps and keep only Pages. Rejected: the local
app is the warehouse-backed six-view product, it is already tested, and
`chesslab demo` plus the analyst tools still need
`dashboard/analysis.py`. A public cube page is not a substitute for
local replay.

Rebuild the hosted app as a Streamlit page on Pages, or as a "Claude
dashboard" that calls a model. Rejected: the cube is already static,
Pages already has a visual system, and a live model is out of scope
for this product surface.

Keep Community Cloud and add the Pages dashboard beside it. Rejected:
that leaves the pin contract and the three-way overlap this record
exists to end. The hosted app stays only until the static page is
reviewed.

## Planned commits

1. `feat(pages): add a CI-built static dashboard from the public cube`
2. `docs: link the Pages dashboard and describe Streamlit retirement`
3. `chore(hosted): retire the Community Cloud app and pin contract`
