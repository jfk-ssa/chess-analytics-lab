# 0119. Deduplicate offline CI and prune stale extras

- Status: Proposed
- Date: 2026-11-22

## Context

A 2026-11-22 read-only audit of `737a711` found repeated work in CI,
untested optional extras that still move in weekly Dependabot updates,
an unused public examples folder, and version drift in docs. The claims
below were checked against this checkout. This record does not change
code, workflows, or frozen files.

The `offline` job in `.github/workflows/offline.yml` runs `uv sync
--locked --no-editable` four times on a full python or dbt pull request:
the base install, then `--extra mcp`, `--extra ml`, and `--extra dbt`.
Each sync precedes the step that needs that extra. The `portfolio` job
syncs twice more, once base and once with `--extra dashboard`.

`.github/workflows/pages.yml` runs `ruff check .`, `chesslab demo`, and
`python -m chess_analytics.marts transform --dataset tiny`. Offline
integrity already has those three commands as selectable steps (`ruff`,
`demo`, and `transform`). The pages job still needs a tiny mart: the
same demo and transform feed `dbt docs generate`. The extra `ruff check
.` is only a second lint gate.

`scripts/ci_offline_changes.py` (1,040 lines) and
`tests/test_ci_offline_changes.py` (400 lines) are the filter config
from [ADR 0100](0100-change-aware-offline-integrity.md). The script
parses `.github/workflows/offline.yml` with a hand-rolled YAML subset
and requires an exact command match for catalogued steps. A workflow
edit, action SHA bump, or new tracked path needs a paired classifier
change. Required check names stay `offline` and `portfolio`, so a
workflow-level `paths` filter is still not available: a skipped
required check stays pending.

The `dagster` and `prefect` extras in `pyproject.toml` are the optional
learning adapters from [ADR 0005](0005-parallel-orchestration-learning-path.md).
[ADR 0108](0108-dagster-packages-update-together.md) grouped `dagster*`
in Dependabot because the pair must move together. At `737a711` those
extras are not used in CI and are not tested:

- No file under `tests/` mentions Prefect, Dagster, or
  `chess_analytics.orchestration`.
- No workflow installs `--extra prefect` or `--extra dagster`.
- The only runtime callers are
  `src/chess_analytics/orchestration/dagster_app.py`,
  `src/chess_analytics/orchestration/prefect_app.py`,
  `src/chess_analytics/orchestration/core.py`, and
  `scripts/compare_orchestrators.py`.
- `reports/orchestrator-comparison.json` is a historical manual receipt.

`auxiliary-examples/` holds the public business examples from
[ADR 0050](0050-separate-public-business-examples.md). It is excluded
from the project wheel, linked from `README.md` and `docs/README.md`,
and is not part of the chess evidence chain.

Documented pins and counts that no longer match this checkout:

- `docs/MAIA.md` cites `torch==2.14.1+cpu` and the macOS wheel
  `torch-2.14.1-cp312-cp312-macosx_14_0_arm64`. `pyproject.toml` pins
  `torch==2.15.0` in the `maia` extra. A measured Linux run that names
  `2.14.1+cpu` is historical evidence and stays as written.
- `docs/M8.md` says the repository currently pins DuckDB 1.4.1.
  `src/chess_analytics/routing_duckdb.py` comments that pinned DuckDB
  1.4.1 has no Jev binary. `pyproject.toml` pins `duckdb==2.0.0`
  ([ADR 0110](0110-duckdb-2.md)). The 1.4.1/macOS HTTP 404 note is a
  dated measurement and stays. The "currently pins" sentence and the
  Jev-binary comment need a current check against 2.0.0.
- `src/chess_analytics/analyst/live_eval.py` and
  `tests/test_live_eval_100.py` still say "40-case set".
  `evals/cases/analyst_live_v1.json` has 48 cases, and
  `docs/RUNBOOK.md` already uses 48. `docs/JEV_ROUTING_RUNBOOK.md`
  also says "40-case test".
- `docs/SITE.md` says "The nine current pages".
  `scripts/build_docs_site.py` writes ten top-level HTML pages:
  `index.html`, `architecture.html`, `metrics.html`, `demo.html`,
  `comparison.html`, `transpositions.html`, `import-games.html`,
  `opening-learning.html`, `live-eval.html`, and `portfolio.html`.
  [ADR 0118](0118-portfolio-page-presentation.md) already records the
  ten-page publication check. The header date on `docs/STATUS.md` is
  2026-10-10; this record does not treat that file as dated 2026-11-01.

## Decision

Land the cleanup as one later implementation pull request, with one
Conventional Commit per change below. Do not start that work from this
record alone.

1. In the `offline` job, replace the four sequential `uv sync` steps
   with one locked sync that installs the union of extras required by
   the selected later steps (`mcp`, `ml`, and/or `dbt`). A docs-only
   pull request still skips extras it does not run. The `portfolio` job
   keeps its own `--extra dashboard` sync.
2. Keep the change-aware step selection from ADR 0100. Reduce
   classifier drift by making the step catalog the single source of
   truth for `offline.yml` and `scripts/ci_offline_changes.py`, so a
   workflow edit cannot silently diverge from the audit. New tracked
   paths still need a category pattern or a `FAIL_OPEN_PATHS` entry.
3. Remove `ruff check .` from `pages.yml`. Keep `chesslab demo` and
   the tiny mart transform there only as the fixture for
   `dbt docs generate`, not as a second integrity gate. A later change
   may reuse an offline artifact instead of rebuilding that fixture.
4. Remove the `prefect` and `dagster` extras, the
   `src/chess_analytics/orchestration/` package, and
   `scripts/compare_orchestrators.py`. Drop the Dependabot `dagster`
   group and its catch-all exclude. Leave ADR 0005, ADR 0108, and
   `reports/orchestrator-comparison.json` as historical records.
   Update `docs/ORCHESTRATION.md`, `README.md`, and other live docs
   that still present the adapters as current optional extras.
5. Remove `auxiliary-examples/`. Leave ADR 0050 as the historical
   decision. Drop the README links. Public URLs into that folder will
   404 after the deletion; that is accepted.
6. Correct the current pin and count sentences listed above. Do not
   rewrite dated measurements. Verify the DuckDB Jev-binary sentence
   against 2.0.0 before changing it from a packaging fact into a
   current claim.

`docs/review/`, font-trial ADRs, and the local Streamlit app are
outside this pull request. The local dashboard decision is
[ADR 0120](0120-replace-hosted-streamlit-with-static-dashboard.md).

## Consequences

Full offline runs install the needed extras once. Pages builds stop
linting the tree a second time, and still build dbt docs from a tiny
mart. Classifier edits stay required, but the catalog and workflow
cannot disagree by accident.

Dependabot no longer opens Prefect or Dagster bumps for unused
adapters. Local `UV_PROJECT_ENVIRONMENT` recipes in the orchestration
guide go away. Anyone reproducing the 2026-10 learning comparison uses
the committed receipt and the historical ADRs, not the deleted
adapters.

Doc drift fixes are editorial. They do not change eval cases, frozen
receipts, or `live_runner.FROZEN_FILES`.

## Alternatives considered

Keep the extras as unmaintained learning examples. Rejected: they are
untested, unused in CI, and still generate lockfile and Dependabot
work, including the special Dagster grouping in ADR 0108.

Delete `scripts/ci_offline_changes.py` and run every step on every
pull request. Rejected: ADR 0100 measured about 8 minutes saved on
docs-only diffs, and required checks still cannot use `paths`.

Move `auxiliary-examples/` to a separate repository in this change.
Rejected as extra scope; the folder is not part of the lab evidence
chain, and this record only removes it from this repository.

## Planned commits

1. `ci: install the union of selected extras in one offline sync`
2. `ci: share one offline step catalog with the change classifier`
3. `ci: drop the extra ruff check from the Pages workflow`
4. `build: remove untested Prefect and Dagster extras`
5. `chore: remove auxiliary-examples from the repository`
6. `docs: correct torch, DuckDB, live-eval case, and Pages counts`
