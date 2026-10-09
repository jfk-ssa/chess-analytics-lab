# Documentation guide

**HTML version:** [Read this guide on the documentation site](https://jfk-ssa.github.io/chess-analytics-lab/).

Start here if this is your first visit. Chess Analytics Lab is a local learning
and portfolio project combining a reliable data pipeline, opening/clock analytics,
and an evaluated analyst. You can explore all three without credentials or real
archive downloads. The default demo uses authored synthetic games; historical
live evaluations are recorded separately.

## Choose a path

| Your goal | Read / do next | What you will get |
|---|---|---|
| Run something immediately | [Offline demo](DEMO.md) | Install, build four unique fixture games, explore six dashboard views, replay checked answers |
| Understand the system | [Architecture](ARCHITECTURE.md) → [data dictionary](DATA_DICTIONARY.md) | Pipeline, code boundaries, table grain and provenance |
| Understand an analysis | [Metric contracts](METRICS.md) → [opening memo](M4-OPENINGS.md) / [clock memo](M4-CLOCK.md) | Denominators, cohort filters, missingness and limits |
| Assess the AI evidence | [Evaluation guide](EVALUATION.md) → [evidence index](EVIDENCE_INDEX.md) | Fixture tests versus actual responses; frozen references and retained failures |
| Compare rules, Jev and Decisions | [Classifier comparison](CLASSIFIER_COMPARISON.md) | Shared-case scores, cost and conclusions readable directly on GitHub |
| Reproduce optional classifier exercises | [Jev routing](JEV_ROUTING_RUNBOOK.md), [paired answers](JEV_END_TO_END.md), [Decisions](DECISIONS_ROUTING_RUNBOOK.md) | Offline harness/replay commands and separate live spending gates |
| Operate or extend the pipeline | [Runbook](RUNBOOK.md) → [sources](DATA_SOURCES.md) → [orchestration](ORCHESTRATION.md) | Bounded acquisition, recovery, optional dbt/Dagster/Prefect |
| Continue development | [Current status](STATUS.md) → [decision log](DECISIONS.md) | Completed phases, next gates and choices without needing the original chat |

## Repository map

| Location | Purpose |
|---|---|
| `src/chess_analytics/` | Foundation CLI, ingestion/warehouse, offline demo and optional classifier studies |
| `platform_m2/`, `dbt/` | Local marts and their validation/recovery path |
| `analytics_m3/`, `analytics_m4/` | Analytical source/moves, parameterized metrics, Streamlit dashboard |
| `analyst_m5/` | Checked read-only tools, typed plans, provider adapter and evaluation harness |
| `orchestration/` | Optional local Dagster/Prefect wrappers over the same pipeline |
| `contracts/`, `config/`, `evals/` | Definitions, bounded source plans, frozen questions and reference manifests |
| `tests/fixtures/`, `tests/` | Tracked synthetic inputs, independent expected values and offline regressions |
| `reports/` | Compact historical evidence and the original comparison report |
| `site/`, `scripts/build_docs_site.py` | Static website assets and generation from maintained guides |
| `work/`, `data/` | Ignored local outputs, raw attempts and bulk data; absent in a fresh clone |
| `auxiliary-examples/` | Separate business communication and observability examples, outside the chess application |

Paths with `m2`–`m5` identify where components were introduced; `M0`–`M8` files
record development milestones. They are not instructions to rerun all milestones
or a requirement to read everything in order. Historical names and frozen hashes
are retained deliberately; use the functional guides above as the public entry
points.

## Current guides versus historical records

This guide, the root README, demo, architecture, runbook, metric definitions and
evaluation guide describe how to use the current checkout. The milestone notes,
original [project brief](PROJECT_SPEC.md), [pre-fix review](REPOSITORY_REVIEW.md),
[hardening handoff](PORTFOLIO_HANDOFF.md) and old candidate audits preserve what
was planned or true at their recorded dates. Their “not uploaded” or “pending”
statements describe those historical candidates. Consult [STATUS](STATUS.md)
for current publication and verification, rather than inferring it from an old
report. The evidence index identifies which files require ignored real data.

## Viewing reports and reproducing results

GitHub renders Markdown guides, but displays `.html` reports as source. Read
[the published comparison](https://jfk-ssa.github.io/chess-analytics-lab/comparison.html)
for an interactive guide, or the
[full rendered report](https://jfk-ssa.github.io/chess-analytics-lab/reports/decisions-routing-comparison.html)
for tables, confusion matrices and threshold plots. You can also open the tracked
report locally. See [the website runbook](SITE.md) for source mapping and publication.

The demo and fixture tests can be reproduced from tracked files after dependency
installation. Real metrics need the exact bounded archive bytes; full rescoring
of historic live experiments needs retained ignored responses. A JSON checkpoint
is evidence of a recorded experiment, not a way to regenerate provider outputs.
Live commands need personal configuration and a new explicit spending cap; old
approvals and provider credits do not authorize another run.

For typography, shared dashboard styling and image maintenance, see
[the visual style guide](DESIGN.md).
