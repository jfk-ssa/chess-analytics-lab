# Hosted dashboard

`hosted/dashboard.py` queries `data/public/dashboard_cube.parquet` with
DuckDB and reads `data/public/dashboard_extract.json` for live eval.
It does not open a warehouse, take uploads, read secrets, or call the
network. [ADR 0094](adr/0094-hosted-read-only-dashboard.md) records the
deployment choice. [ADR 0098](adr/0098-hosted-dashboard-analysis.md)
records extract version 2. [ADR 0101](adr/0101-hosted-bi-cube.md)
records the cube. The local six-view dashboard is a different program
and still needs the analytical warehouse.

The sidebar filters are date range, time control, color, rating band,
and opening family, with the active line and a reset. Those filters
apply to the KPI strip, openings, transpositions, clock, and periods.
They do not change the live-eval numbers. The KPI strip is games, win
rate, draw rate, loss rate, clock error, published positions, rating
diff, and game length. Each card shows a value. Games is the
`game_cell` total, 1,009,445 on the full range, with detail
`warehouse`. With no color selected, win, draw, and loss are the White
`result_cell` rows: 49.2% (476,741 / 968,874), 5.1% (49,271 / 968,874),
and 45.7% (442,862 / 968,874). Rating diff is +0.1 and game length is
72.8 ply. A color or rating filter counts one side. Clock error stays
2,128 / 22,978, and positions stay 256. A filter the grain cannot
split is named on the card instead of leaving the value blank. A filter
on a column the grain stores, which matches nothing, says `no cells for
this cut` and does not widen the population. Clock error stays
2,128 / 22,978 when time and rating are All. A time control the August
slices do not contain, such as `180+2` or `-`, shows no slices and is
not labeled August. Period
bars stay the published months (1,042,346 training games).

Openings drill from a family bar to lines, then to one published FEN
and its continuations. The line chart uses the full SAN, does not stack
bars that share a prefix, and lists the same lines in a table. Most
common transpositions lists boards reached by at least two acyclic move
orders, with the route count, total games, the top three orders, and a
board from the Board control. Each card title is `After Black's move N`
plus the leading SAN, matching the transpositions page, and sibling
cards keep that form. The depth, the line, and the game count are
separate rows. The line reserves two lines so the counts line up across
a row. Each move order is a count column sized to the widest count, about six
tabular characters, and a SAN column, and a
thin bar shows that order's share of the position total. The
headline is that total. Games the card does not list are a muted
other-orders row when they add up to at least 10 games. A remainder
of 1–9 stays off the rows, and the card says rarer orders are not
shown, with no count. Each move
number stays with its reply, as in `4.Nxd4 Nf6` or `5.Nc3 a6`. A
trailing White move such as `3.Bc4` is its own unit. A line breaks only
between those units. The same grouping is on the line labels and the
Board control. Routes under 10 games are
omitted. Family
and date apply. Color, time control, and rating do not, and the caption
says so. Clock drills from a band to the largest slices in that band.
A slice is a rating, a time control, and a phase. Each section has one
short caption. Provenance stays in a collapsed expander.
Charts are Altair, with the `chesslab` theme (Inter and the page palette).

Card rows use an inline grid,
`repeat(auto-fill, minmax(min(100%, 256px), 1fr))`. The label and value
use `white-space: nowrap`. The detail nowraps the fraction and can
break at ` · `. 256px is 16rem at the CSS
reference pixel. With 256px, a 390px viewport is one column and a
1280px viewport holds several tracks. The eight KPI cards and the six
eval cards share that track. The grok sweep is three cards. Sweep detail breaks only at ` · `, so a
cost or a token count stays on one line. The three cards share one track
width.
The shared `.streamlit/config.toml` is unchanged.

Version 2 adds `opening_color_score` (French and Sicilian, both colors,
1400–1599, 60+0, with Black bootstrap intervals), `clock_pressure_band`,
the transposition reduction (`transposition_view`,
`transposition_compression`, `transposition_coverage`,
`transposition_scope`, `transposition_limitation`), and the live-eval
summary (`live_eval_run`, `live_eval_category`, `live_eval_case`,
`live_eval_effort_case`).
Those receipts are `committed_report`. Category and case rows omit
`source_report`; the run row keeps the filename, and model plus effort
joins a row to that run. Each run row also carries `frozen_group`,
`instructions_sha256`, and `reasoning_tokens`. Headline cards stay on the 5-repeat runs and name grok as
`grok-4.7 · low ×5`. The pass-rate chart, the category chart, and the
case grid also draw the three 1-repeat grok runs, labelled
`grok-4.7 · low ×1`, `grok-4.7 · medium ×1`, and `grok-4.7 · high ×1`.
Those 1-repeat case rows are not stored in full: the page fills them from
`live_eval_effort_case` and treats a missing case as passed, then checks
the pass total against the run row. A 1-repeat Wilson bar is that
receipt's interval on 48 trials. The page does not recompute it.
Pass-rate axes start 10 percentage points below the lowest plotted value
or interval bound, clamped at 0, and end at 100%. The margin is 10
percentage points, not 10 percent of the minimum. The case grid colors
the pass fraction and prints `passed/repeats`. Column labels are
horizontal, and the grid scrolls inside its block on a narrow viewport.
The category legend is one column. Tied category rates are stacked on
the row label, and the six run colors stay apart (Luna teal, Sol orange, then
blue, violet, pink, and yellow-green). Sweep cards print the per-repeat
cost at three decimals. Low ×5 is not strictly comparable with
Luna and Sol, because the frozen runner files changed. The 1-repeat runs
are like-for-like with each other. Low ×5 differs from them in the dataset snapshot id
embedded in the instructions. Wilson intervals are compared only inside
those two groups. The file is 259,711 bytes.

## Run locally

Python 3.12, from the repository root. The dashboard extra supplies the
same Streamlit pin as `hosted/requirements.txt`.

```sh
uv sync --locked --no-editable --extra dashboard
uv run --locked --offline --no-editable --extra dashboard \
  streamlit run hosted/dashboard.py
```

The script adds `src/` to the import path for the extract reader and
the cube module. You do not install the project package to run this
page. The page queries the cube with DuckDB, which Community Cloud
installs from `hosted/requirements.txt`. Rebuild the cube, when a
committed source changes, with:

```sh
uv run --locked --offline --no-editable --extra dashboard \
  python scripts/build_dashboard_cube.py --positions /path/to/opening-positions.json
```

The positions report is not on the tip. The script does not download it.
The committed cube is 569,634 bytes and 34,084 rows. `game_cell` covers
1,009,445 games.

The openings warehouse was appended with this command, from the
repository root on the machine that has the file, without `--offline`:

```sh
uv run --locked --no-editable --extra dashboard \
  python scripts/build_warehouse_cube.py \
  --warehouse data/openings/published/00e7a73fbf67c401e23b4b4b/warehouse.duckdb
```

The command exits 2 when the file is missing. It reads `opening_game`
and does not read `retained_game`. It writes `game_cell` and
`result_cell` (color, rating band, time control, the corpus period, and
the opening family before the first colon). It does not write clock
cells from that file. Cells under 10 games are dropped. The printed
line includes the byte size and the `game_cell` game total. The write
refuses a file over 10 MB. A `fact_game` warehouse uses the same script
and can still add `result_line` and `clock_cell`. The committed cube
is the result of that openings command. The page reads those grains.

Check the page without a browser:

```sh
uv run --locked --offline --no-editable --extra dashboard \
  pytest -q tests/test_hosted_dashboard.py
```

Without the dashboard extra, the AppTests skip. The Streamlit pin check
in that file still runs.

## Deploy on Streamlit Community Cloud

Use these settings. Community Cloud installs `hosted/requirements.txt`
with pip and starts the entrypoint. The repository root is the working
directory, which is where the reader finds the committed extract and cube.

| Setting | Value |
|---|---|
| Main file path | `hosted/dashboard.py` |
| Python version | 3.12 |
| Requirements file | `hosted/requirements.txt` |

Set the requirements path in the app's advanced settings. There is no
`requirements.txt` at the repository root. Do not add secrets. The
extract is already in the repository.

Community Cloud installs only the packages named in
`hosted/requirements.txt` with pip. Streamlit does not install those
pins itself. The file pins `streamlit==1.65.0`. Pandas, protobuf,
Altair, narwhals, and jsonschema are dependencies of that pin or of
Altair. If they stay unpinned, pip can install versions that differ
from `uv.lock`. The requirements file therefore also pins the locked
versions, `altair==5.5.0`, `narwhals==2.26.0`, `jsonschema==4.26.0`,
`pandas==2.3.3`, `protobuf==6.33.6`, and `duckdb==1.5.6`. Streamlit
1.65.0 accepts `pandas<4,>=1.4.0` and `protobuf<8,>=5.26.1`, so those
pins install. Narwhals 2.26.0 has no dependencies of its own. Altair
5.5.0 depends on jsonschema and narwhals. DuckDB 1.5.6 has no
dependencies. The cp312 manylinux x86_64 wheel recorded in `uv.lock`
is 21,568,087 bytes.
