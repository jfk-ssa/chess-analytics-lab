# Data and dependency notices

Inspected installed distribution metadata on 2026-10-03. Dependencies are installed
by uv, not vendored in Git; their original license files remain in distributions.
This is an inventory, not a grant to relicense third-party code.

| Component | Version | License reported by distribution |
|---|---|---|
| chess (python-chess) | 1.11.2 | GPL-3.0-or-later |
| DuckDB | 1.4.1 | MIT |
| zstandard | 0.25.0 | BSD-3-Clause (also inspect bundled native-library notices) |
| pytest (development) | 8.4.2 | MIT |
| Ruff (development) | 0.14.0 | MIT |
| Dagster (optional) | 1.13.25 | Apache-2.0 |
| dagster-webserver (optional) | 1.13.25 | Apache-2.0 |
| Prefect (optional) | 3.8.7 | Apache-2.0 |
| dbt-duckdb (optional) | 1.10.1 | Apache-2 (distribution metadata) |
| dbt-core (transitive optional) | 1.12.5 | Apache-2.0 |
| Streamlit (optional dashboard) | 1.50.0 | Apache License 2.0 (distribution metadata) |
| PyArrow (transitive dashboard) | 25.0.1 | Apache-2.0 (license expression) |

Build uses pinned Hatchling and its pinned dependencies; uv.lock records runtime and
development and optional-orchestrator resolution with hashes. Source PGN data comes from the standard rated
Lichess open database, released under CC0: https://database.lichess.org/.
The exact source URL/checksum/listing date are in config/datasets.json. No broadcast
data or engine binary is included. Tiny fixture games were authored for tests.

The repository's distribution license has not been selected. Review compatibility
with GPL python-chess before public distribution; CC0 data does not make the software
or all dependencies CC0. Do not describe this repository as permissively licensed.
