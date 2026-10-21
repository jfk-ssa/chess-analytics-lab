# Hosted read-only dashboard

`hosted/dashboard.py` reads `data/public/dashboard_extract.json` through
`chess_analytics.public_extract`. It does not open a warehouse, take
uploads, read secrets, or call the network. Figures and lineage come
from that file. [ADR 0094](adr/0094-hosted-read-only-dashboard.md)
records the deployment choice, and
[ADR 0098](adr/0098-hosted-dashboard-analysis.md) records extract
version 2 and the page that sits on it. The local six-view dashboard
is a different program and still needs the analytical warehouse.

The page opens with three equal-width cards: opening-corpus training
games, the August draw rate, and the analyst gate (Luna and grok-4.7
low clear; Sol fails). Tabs are Overview, Openings, Clock pressure, AI analyst eval,
and About the data. Filters cover opening family, color, rating band,
time control, phase, transposition cohort, and eval category. Charts
are Altair, with the `chesslab` theme (Inter and the page palette).
Provenance hashes are on About the data.

Card rows use an inline grid,
`repeat(auto-fit, minmax(min(100%, 256px), 1fr))`. The value is
`white-space: nowrap`. 256px is 16rem at the CSS reference pixel.
Streamlit's 14px root would make a literal 16rem 224px, and three of
those tracks fit at 768px. With 256px, a 390px viewport is one column
and a 768px viewport holds two tracks. The three-card hero is one row
at 1280px. The eval tab has six cards, so that row is four plus two at
1280px and three rows of two at 768px. A leftover card stays as wide as
the cards in the row above.
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
`instructions_sha256`, and `reasoning_tokens`. Headline charts and the
six eval cards stay on the 5-repeat runs. The eval tab adds a grok
reasoning-effort sweep for one repeat each of low, medium, and high on
the same instructions. Low x1 is 47/48 at $0.22253 and fails `coverage_2`.
Medium x1 is 45/48 and high x1 is 47/48. All three clear the gate. The
5-repeat low stays on the headline cards and is not strictly comparable
with that trio. The file is 259,711 bytes.

## Run locally

Python 3.12, from the repository root. The dashboard extra supplies the
same Streamlit pin as `hosted/requirements.txt`.

```sh
uv sync --locked --no-editable --extra dashboard
uv run --locked --offline --no-editable --extra dashboard \
  streamlit run hosted/dashboard.py
```

The script adds `src/` to the import path for the extract reader. You
do not install the project package to run this page, and the page does
not import DuckDB.

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
directory, which is where the reader finds the committed extract.

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
`pandas==2.3.3`, and `protobuf==6.33.6`. Streamlit 1.65.0 accepts
`pandas<4,>=1.4.0` and `protobuf<8,>=5.26.1`, so those pins install.
Narwhals 2.26.0 has no dependencies of its own. Altair 5.5.0 depends
on jsonschema and narwhals.
