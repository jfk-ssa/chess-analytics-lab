# Data and dependency notices

Inspected installed distribution metadata on 2026-10-03. The Streamlit row
below is the current lock, 1.66.1, also pinned in `hosted/requirements.txt`.
The 2026-10-03 inspection recorded Streamlit 1.50.0; [ADR 0008](docs/adr/0008-m4-local-product-and-uncertainty.md)
is that earlier pin and is unchanged. Dependencies are installed
by uv, not vendored in Git; their original license files remain in distributions.
This is an inventory, not a grant to relicense third-party code.

| Component | Version | License reported by distribution |
|---|---|---|
| chess (python-chess) | 1.11.2 | GPL-3.0-or-later |
| DuckDB | 2.0.0 | MIT |
| zstandard | 0.25.0 | BSD-3-Clause (also inspect bundled native-library notices) |
| pytest (development) | 8.4.2 | MIT |
| Ruff (development) | 0.14.0 | MIT |
| Dagster (optional) | 1.13.x | Apache-2.0 |
| dagster-webserver (optional) | 1.13.x | Apache-2.0 |
| Prefect (optional) | 3.8.7 | Apache-2.0 |
| dbt-duckdb (optional) | 1.11.0 | Apache-2 (distribution metadata) |
| dbt-core (transitive optional) | 1.12.5 | Apache-2.0 |
| Streamlit (optional dashboard; current lock) | 1.66.1 | Apache-2.0 (license expression) |
| PyArrow (transitive dashboard) | 25.0.1 | Apache-2.0 (license expression) |

Build uses pinned Hatchling and its pinned dependencies; uv.lock records runtime and
development and optional-orchestrator resolution with hashes. Source PGN data comes from the standard rated
Lichess open database, released under CC0: https://database.lichess.org/.
The exact source URL/checksum/listing date are in config/datasets.json. No broadcast
data or engine binary is included. Tiny fixture games were authored for tests.

Inspected distribution metadata again on 2026-10-18. The semantic path
imports `metricflow`, which `dbt-core` already depends on. The optional
`dbt` extra depends on `dbt-duckdb` and does not depend on
`dbt-metricflow`. The lock does not include `halo`, `log-symbols`,
`spinners`, `termcolor`, or `update-checker`.

| Component | Version | License reported by distribution |
|---|---|---|
| metricflow (transitive, dbt extra) | 0.213.0 | Apache-2.0 |

Original project code is licensed under [GPL-3.0-or-later](LICENSE). The
python-chess dependency is GPL-3.0-or-later; other dependencies retain the
licenses listed above. CC0 source data does not set the software license.

## Bundled typography

Inter is bundled as a Latin normal-style variable WOFF2 font
from Fontsource packages **5.3.0**, under **SIL Open Font License 1.1**.
It retains its own license; the project's GPL does not replace it.
See [pinned URLs and SHA-256 hashes](site/assets/fonts/provenance.json),
[Inter license](src/chess_analytics/dashboard/static/fonts/LICENSE.inter.txt).
The live-eval page uses this same file. Every documentation page preloads
it, `font-display` is `swap`, and the build does not inline a second face
or request a font CDN. The OFL text is the file linked above.


## Bundled browser chess engine

chess.js **1.4.0** is bundled unchanged from the npm registry distribution under
**BSD-2-Clause**, for legal Standard mainline replay in a local worker. There is
no runtime CDN or npm installation. Preserve [its license](site/assets/vendor/LICENSE.chess-js.txt)
and [registry URL, integrity and SHA256 provenance](site/assets/vendor/chess-js-provenance.json)
when updating it. Browser board pieces are generated with the existing
GPL-3.0-or-later python-chess dependency; project licensing remains unchanged.
