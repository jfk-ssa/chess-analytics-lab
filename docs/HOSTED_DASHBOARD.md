# Hosted read-only dashboard

`hosted/dashboard.py` reads `data/public/dashboard_extract.json` through
`chess_analytics.public_extract`. It does not open a warehouse, take
uploads, read secrets, or call the network. Figures and lineage come
from that file. [ADR 0093](adr/0093-hosted-read-only-dashboard.md)
records the deployment choice. The local six-view dashboard is a
different program and still needs the analytical warehouse.

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
