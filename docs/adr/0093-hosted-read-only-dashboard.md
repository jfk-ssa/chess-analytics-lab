# 0093. Hosted read-only dashboard

- Status: accepted on merge
- Date: 2026-10-21

## Motivation

[ADR 0092](0092-public-aggregate-extract.md) commits the aggregate extract
and leaves the hosted app for a later change. Streamlit Community Cloud
will run that app from this repository. It cannot ship the analytical
warehouse, and it must not run dbt, MetricFlow, or DuckDB. ADR 0092
allowed the hosted app to depend on Streamlit and DuckDB. This record
does not take the DuckDB option.

The dashboard extra in `pyproject.toml` and `uv.lock` pins Streamlit
1.65.0. [ADR 0008](0008-m4-local-product-and-uncertainty.md) recorded
1.50.0, and `THIRD_PARTY_NOTICES.md` still repeated that older
inspection. The hosted requirements file has to follow the lock.

## Decision

`hosted/dashboard.py` is the Community Cloud entrypoint. It calls
`chess_analytics.public_extract.load_extract` and does not call
`connect`. The reader validates the schema, query origins, and build
record. The page fails closed, with a short message and no figures,
when the extract is missing, not valid JSON, or rejected by that
reader. A missing build record also stops the page: the published
extract carries mart identity, and a warehouse-less reprint without
`build` is not a substitute.

`hosted/requirements.txt` pins `streamlit==1.65.0` and nothing else.
Community Cloud installs that file with pip. It does not install
`chess-analytics-lab`. That package depends on DuckDB, python-chess,
and zstandard, and the hosted page does not query SQL. The script
inserts `src/` on `sys.path` only for the import, then removes it.
`public_extract` imports `hash_json` from `chess_analytics.common`.
Both modules use the standard library. DuckDB stays inside `connect`,
which this page does not call.

The page shows the committed figures and labels each one with the
receipt query origin (`metricflow`, `reviewed_sql`, or
`committed_report`). Build provenance is on the page: mart id, source
snapshot, model hash, lock hash, semantic manifest hash, extract
sha256, and analytical id. Tables have at most three columns. The page
has no uploader and no control that calls another service. The two
lineages stay in separate tables.

The shared `.streamlit/config.toml` still turns usage stats off and
sets the palette. Its font URL is served from the entrypoint's
`static/` directory. Streamlit rejects a static file whose real path
leaves that directory, so `hosted/static/fonts/inter-latin-wght-normal.woff2`
is a copy of the dashboard font, with the same license file beside it.
A test checks that the font bytes match. The local six-view dashboard
is unchanged. This record does not add a homepage link.

## Consequences

Deploy on Community Cloud with main file `hosted/dashboard.py`, Python
3.12, and requirements file `hosted/requirements.txt`. No secrets.
Run locally from the repository root with the dashboard extra, whose
Streamlit pin is the same version. `tests/test_hosted_dashboard.py`
renders the committed extract and the two failure paths. Those AppTests
need the dashboard extra and skip without it. The portfolio CI job
installs that extra and runs the file. The pin check itself does not
import Streamlit.

`THIRD_PARTY_NOTICES.md` now names Streamlit 1.65.0. ADR 0008 keeps
the earlier pin as the decision it was.
