# 0119. Deduplicate offline CI and prune stale extras

- Status: Accepted for PRs 1–2; deployed page accepted 2026-11-23; PR 3 retires hosted Streamlit; PR 4 remains proposed
- Date: 2026-11-22

## Context

A 2026-11-22 read-only audit of `737a711` found repeated work in CI,
untested optional extras that still move in weekly Dependabot updates,
an unused public examples folder, and version drift in docs. The claims
below were checked against this checkout. This record does not change
code, workflows, or frozen files.

The `offline` job in `.github/workflows/offline.yml` runs `uv sync
--locked --no-editable` four times on a python pull request or full run:
the base install, then `--extra mcp`, `--extra ml`, and `--extra dbt`.
Each sync precedes the step that needs that extra. A pure dbt diff
selects two offline syncs: base and dbt. `offline-core` has a separate
base sync; `portfolio` already syncs once with `--extra dashboard`.

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
command or catalogued step edit needs a paired catalog change.
Coordinated full-SHA `setup-uv` bumps are accepted without a classifier
edit; new paths covered by existing rules need none either. Unmapped
tracked paths need a rule or an explicit fail-open entry. Required
check names stay `offline` and `portfolio`, so a workflow-level
`paths` filter is still not available: a skipped
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
- `tests/test_live_eval_100.py` still says "40-case set".
  `evals/cases/analyst_live_v1.json` has 48 cases, and
  `docs/RUNBOOK.md` already uses 48. Correct the unfrozen test
  docstring and current documentation only. `live_eval.py` has the
  same stale docstring but is in `live_runner.FROZEN_FILES`: leave it
  byte-for-byte unchanged, per [ADR 0117](0117-coach-agent-evals.md).
  Keep the Jev runbook's "40-case test": `jev_routing_v1_manifest.json`
  records 40 development and 40 test cases, a separate historical run.
- `docs/SITE.md` says "The nine current pages".
  `scripts/build_docs_site.py` writes ten top-level HTML pages:
  `index.html`, `architecture.html`, `metrics.html`, `demo.html`,
  `comparison.html`, `transpositions.html`, `import-games.html`,
  `opening-learning.html`, `live-eval.html`, and `portfolio.html`.
  [ADR 0118](0118-portfolio-page-presentation.md) already records the
  ten-page publication check. The header date on `docs/STATUS.md` is
  2026-10-10; this record does not treat that file as dated 2026-11-01.

## Decision

Use four implementation PRs in order: 1 CI cleanup and pruning (this
record), 2 static dashboard publish, 3 retire hosted Streamlit
([ADR 0120](0120-replace-hosted-streamlit-with-static-dashboard.md)),
4 scoped hash ([ADR 0121](0121-scoped-implementation-hash.md)). PRs 2
and 3 merge separately; PR 3 requires recorded acceptance of the
deployed page. Do not start implementation from this record alone.

1. In the `offline` job, replace the selected sequential `uv sync` steps
   with one locked sync that installs the union of extras required by
   the selected later steps (`mcp`, `ml`, and/or `dbt`). A docs-only
   pull request still skips extras it does not run. The `portfolio` job
   keeps its own `--extra dashboard` sync; `offline-core` keeps its
   separate base sync. Later commands must reuse the installed union
   rather than resyncing away another selected extra.
2. Keep the change-aware step selection from ADR 0100. Reduce
   classifier drift by making the step catalog the single source of
   truth: a stdlib-only `scripts/ci_offline_catalog.py` defines steps,
   commands, categories, required extras, and prerequisites. The
   classifier and install helper import it; a generator renders managed
   workflow step/output blocks, with a check mode in the map audit.
   Migrate `offline.yml`, the catalog, classifier, install helper,
   outputs, ordering checks, and tests in one atomic commit. Replace
   the old `sync_mcp`/`sync_ml`/`sync_dbt` outputs and ordering edges
   together. Catalog/helper/generator changes must select the full suite.
   New tracked paths need a category pattern or `FAIL_OPEN_PATHS` entry
   only when existing rules do not cover them.
   On detection errors, a failed changes job, or missing/invalid
   selection outputs, install all offline extras (`mcp`, `ml`, `dbt`)
   before running the full suite. Test the actual install arguments
   for each failure, not just emitted booleans. Keep ADR 0100 tests for
   docs-only skips, selective category unions, narrow-test suppression,
   unknown/empty diffs, full events, required job names, and no workflow
   path filters. Audit tests must reject command/output/order drift.
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
   rewrite dated measurements, frozen modules, or historical receipt
   hashes. Verify the DuckDB Jev-binary sentence against 2.0.0 before
   changing it from a packaging fact into a current claim.

`docs/review/`, font-trial ADRs, and the local Streamlit app are
outside this pull request. The hosted dashboard decision is
[ADR 0120](0120-replace-hosted-streamlit-with-static-dashboard.md).

## Consequences

Full offline runs install the needed extras once. Pages builds stop
linting the tree a second time, and still build dbt docs from a tiny
mart. Step changes update the shared catalog; its generated workflow
and classifier cannot disagree unnoticed by the audit.

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

All commits below belong to PR 1 of the four-PR sequence.

1. `ci: atomically migrate catalog, workflow, outputs, ordering, union sync, and tests`
2. `ci: drop the extra ruff check from the Pages workflow`
3. `build: remove untested Prefect and Dagster extras`
4. `chore: remove auxiliary-examples from the repository`
5. `docs: correct current pins and counts without editing frozen evidence`

## PR 1 implementation evidence — 2026-11-22

The offline step catalog now generates managed workflow blocks, output names,
and prerequisite ordering. One locked sync installs the selected union of
`mcp`, `ml`, and `dbt`; later offline commands use `--no-sync`. Validation
rejects missing, malformed, and inconsistent selection outputs before step
conditions run. Install-argument tests cover detection errors, failed changes
jobs, and invalid outputs, while valid full runs retain narrow-test suppression.
Pages retains its tiny dbt-docs fixture and drops the duplicate lint command.

The unused adapters/extras and auxiliary examples are removed. ADRs 0005,
0050, and 0108 and the comparison receipt remain historical evidence.
The current torch wheel name and size were checked against `uv.lock`.
The DuckDB community Jev compatibility matrix was read as HTML: the 2.0.0
column has unavailable markers on every listed platform. No extension was
installed or loaded. Historical 1.4.1/macOS and Linux torch measurements,
frozen analyst files, case sets, and receipts remain unchanged.

Local offline validation with `dbt`, `dashboard`, `mcp`, and `ml` installed:
679 passed, 18 skipped; the classifier suite separately passed 63 tests.
Ruff lint/format, basedpyright, the offline map audit (including generator
check mode), and all configured pre-commit file hooks passed before each
commit. These are fixture/offline checks, not live evaluations or hosted
CI timings. PRs 2–4 have not started.
