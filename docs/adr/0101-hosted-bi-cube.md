# 0101. Hosted dashboard cube

- Status: accepted on merge
- Date: 2026-10-21

## Motivation

The hosted page was a read-only view of extract version 2
([ADR 0094](0094-hosted-read-only-dashboard.md),
[ADR 0098](0098-hosted-dashboard-analysis.md)). Filters on that page
did not change a shared result, and a chart could not open the next
grain. A read-only extract view is not the dashboard to keep.

The warehouse stays off the tip, and the public extract forbids player
and game identifiers. A game-level table would also miss the 10 MB
budget and would republish rows the extract already refuses. The
opening-position report stays off the tip
([ADR 0072](0072-opening-rankings-stay-outside-the-tip.md)).

## Decision

`scripts/build_dashboard_cube.py` builds one Parquet file,
`data/public/dashboard_cube.parquet`, from the committed corpus,
the opening-position report when it is on disk, the M3 reference, the
M4 figures, and the M3 analytical manifest. The script does not
download. The hosted page queries that file with DuckDB 1.5.6 and does
not open a warehouse. The JSON extract stays. Live eval still reads it.
`src/chess_analytics/analyst/` is unchanged.

The measured file is 87,861 bytes and 5,037 rows, under the 10 MB
budget. Every row uses one column set. The grain column is one of
`corpus_month` (10), `opening_family` (275), `opening_line` (1,416),
`opening_position` (508), `opening_continuation` (2,410),
`august_family` (138), `color_score` (4), `august_draw` (1), and
`clock_slice` (275).

The natural grain is coarser than a game, a day, or a full cross of
opening, clock, rating, and color:

- There is no game list. A clock band opens the largest slices in that
  band. A slice is a rating band, a time control, and a phase.
- Corpus months are the published periods. The games delta compares the
  selected months with the previous N published months. The full range
  has no prior window. There is no invented daily series inside a
  prefix.
- Opening positions are the published top positions, not every game in
  a family. The explorer uses `rated_public` when that span sits inside
  the date range, and otherwise `elite_reference` when the range is
  inside November 2025. A color, time-control, or rating filter hides
  the explorer, because those positions are not split that way.
- White and black color cells are not added. Win rate and loss rate
  appear only when a color is selected. The 1,400–1,599 cell is the
  published subset of the 1,200–1,599 band.
- August draw rate and clock slices appear only when 2026-08-01 sits
  inside the date range. They are not split by opening family.

Sidebar filters are the date range, time control, color, rating band,
and opening family. A row is included when its period is fully inside
the date range. The same filters apply to the KPI strip, openings,
clock, and periods. Live-eval numbers are not filtered. A reset
restores the full published range and clears the drill.

Drill state is family, line, position, and clock band. A family bar
sets the opening filter and lists lines. A line with one position opens
that FEN. A line with more than one position asks which FEN. The board
is an SVG of the published FEN plus continuation counts. A clock bar
lists slices. A breadcrumb and a Back control climb one level.

DuckDB 1.5.6 is pinned in `hosted/requirements.txt`. The manylinux
CPython 3.12 x86_64 wheel is 21,568,087 bytes and has no dependencies.
That supersedes the ADR 0094 statement that the hosted page does not
install DuckDB. Altair selections stay on the Streamlit pin. Plotly is
not added.

## Consequences

Rebuild the cube with `scripts/build_dashboard_cube.py` when a
committed source changes. The positions file is an explicit `--positions`
path because that report is not on the tip. A missing cube fails closed
with "Dashboard cube unavailable". The JSON extract remains the
live-eval source and keeps its 256 KiB budget.
