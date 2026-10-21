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

The measured file is 580,528 bytes and 34,798 rows, under the 10 MB
budget. Every row uses one column set. The grain column is one of
`corpus_month` (10), `opening_family` (275), `opening_line` (1,416),
`opening_position` (508), `opening_continuation` (2,410),
`august_family` (138), `color_score` (4), `august_draw` (1),
`clock_slice` (275), `transposition` (422), `transposition_route`
(1,164), `game_cell` (5,867), and `result_cell` (22,308).
`game_cell` sums to 1,009,445 games after the 10-game floor, from the
1,042,346-game `opening_game` selection. `result_cell` sums to
1,937,960 because each game is stored once per color. `rating_diff`
and `mean_ply` are filled on the warehouse rows and stay null on the
published rows.

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
  inside November 2025. Color, time control, and rating are not on
  those rows. The section stays visible and says so. The same rule
  covers clock and periods: a filter that the grain cannot apply does
  not hide the section.
- A transposing board has at least two distinct acyclic arrival
  prefixes, the definition in
  [TRANSPOSITIONS.md](../TRANSPOSITIONS.md). The published `routes`
  list is that set. Routes under 10 games are omitted. Each surviving
  board is one `transposition` row (games, and `ply` as the route
  count) plus one `transposition_route` row per move order. The page
  shows the top boards, the route count, total games, the top three
  orders, and a board from the Board control. Each card is titled the
  way the transpositions page names that row: `After Black's move N`
  from the leading arrival, then that arrival's SAN. Sibling cards use
  that same form. Family and date apply. Color, time control, and
  rating do not, unless a later warehouse build fills those columns.
- With no color selected, win rate, draw rate, and loss rate use the
  White `result_cell` rows so the two sides are not added. On the full
  range that is 476,741 / 968,874 wins (49.2%), 49,271 / 968,874 draws
  (5.1%), and 442,862 / 968,874 losses (45.7%). The White denominator
  is under the `game_cell` total because a color cell under 10 games
  is dropped. The Games card counts `game_cell` (1,009,445, detail
  `warehouse`) unless a color or rating filter is set, in which case
  it counts one side. Rating diff and game length are the
  games-weighted means on those cells (+0.1 and 72.8 ply on the full
  range). The published `color_score` rows stay in the file. The page
  uses `result_cell` when that grain is present.
- Clock error stays the August published figure, 2,132 / 22,994.
  Published positions stay 256 for the rated-public span. August draw
  rate and clock slices remain the August prefix. When the date range
  does not contain that day, the clock card still shows the figure and
  says so. They are not split by opening family or color. Period bars
  stay `corpus_month` (1,042,346 training games). The Games card does
  not repeat a prior-period delta once `game_cell` is present.

`scripts/build_warehouse_cube.py` aggregates a local `warehouse.duckdb`.
An analytical warehouse (`fact_game` and `fact_player_game`) still
writes `game_cell`, `result_cell`, `result_line`, and, when `fact_move`
has the clock columns, `clock_cell`. The openings warehouse at
`data/openings/published/00e7a73fbf67c401e23b4b4b/warehouse.duckdb`
is detected from `opening_game` (1,042,346 training games).
`retained_game` is not read. That file has no move or clock table, so
the builder writes `game_cell` and `result_cell` only. Color is one row
per side, from `white_rating`, `black_rating`, and `result`. Opening
family is the text before the first colon, the same split as
`opening_family_expr`. Cohort is `source_cohort` and period is
`source_period`. The row window is the min and max `utc_date` of that
source, so it lines up with `corpus_month` (a rated-public prefix stays
one day; the elite month stays 2025-11-01 through 2025-11-30). Cells
under 10 games are dropped, so the summed games sit under
1,042,346. The script does not download and does not select
identifiers. The committed file was rebuilt from that warehouse on
the machine that holds the snapshot. The hosted page uses those
grains, so month, time control, rating band, color, and opening
family change the same cards. With no color selected, a rating
filter counts the White cells so the two sides are not added. The
write fails closed above 10 MB.

Sidebar filters are the date range, time control, color, rating band,
and opening family. A row is included when its period is fully inside
the date range. The same filters apply to the KPI strip, openings,
clock, periods, and transpositions. Live-eval numbers are not
filtered. A reset restores the full published range and clears the drill.

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

On the machine that has the openings warehouse, from the repository
root, without `--offline`:

```sh
uv run --locked --no-editable --extra dashboard \
  python scripts/build_warehouse_cube.py \
  --warehouse data/openings/published/00e7a73fbf67c401e23b4b4b/warehouse.duckdb
```

The command writes `data/public/dashboard_cube.parquet`, keeps the
published rows, and replaces any previous warehouse grains. It prints
the byte size, the row count, and the `game_cell` game total after the
10-game floor. It exits 2 when the file is missing and refuses a file
over 10 MB. Report that printed size and game total before committing
the Parquet. The population is the `opening_game` selection in that
snapshot. An analytical `fact_game` warehouse uses the same script and
the same `--warehouse` flag.
