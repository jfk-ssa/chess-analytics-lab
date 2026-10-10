# 0062. Functional package names

- Status: accepted
- Date: 2026-10-10

The milestone packages move under `src/chess_analytics/` with names that describe
the work: `marts` for the dbt publication and recovery path, `corpus` for the
bounded analytical source and metrics, `dashboard` for the Streamlit views and
parameterized analysis, `analyst` for the checked tools and evaluation harness,
and `orchestration` for the optional Dagster and Prefect adapters. The wheel
lists only `src/chess_analytics`. Entry points are `python -m chess_analytics.marts`,
`python -m chess_analytics.corpus`, and `python -m chess_analytics.analyst`.
The dashboard command is `streamlit run src/chess_analytics/dashboard/dashboard.py`.
Published preflight JSON keeps the old relative paths. New snapshots hash the
current paths. On the tiny fixture the source SHA-256 stayed
`130df65e85d18e78bbafd89daf6696c2596e03abf939adf47f2dcbdc4d33e75b` and the draw
rate stayed 0.2; the snapshot id changed to `97d637ad66e2a11bc065900c`.
Historical hashes stay as recorded.
