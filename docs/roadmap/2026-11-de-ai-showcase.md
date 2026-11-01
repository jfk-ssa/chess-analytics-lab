# Roadmap: DE / AI showcase (2026-11)


- Status: accepted
- Date: 2026-10-31
- Base: `main` at `b45076c`

## Motivation

Showcase practical data engineering and AI/ML on a real warehouse, not a toy
demo. The lab already has dbt-duckdb marts, a MetricFlow semantic path
([ADR 0085](../adr/0085-governed-semantic-layer-metricflow.md)), a Parquet
hosted cube (`data/public/dashboard_cube.parquet`), Streamlit at
https://chess-analytics-lab.streamlit.app/, Pages at
https://jfk-ssa.github.io/chess-analytics-lab/, and a manual `live-eval`
environment with budget caps, receipts, and frozen-file hashes. Three
features turn that stack into resume evidence: one source of truth for KPIs,
a supervised mistake model with calibration, and a tool-calling coach graded
under the same live-eval discipline.

Audience: John's job search. Scope: PR-sized slices (~400 lines of real code
each, [CONTRIBUTING.md](../../CONTRIBUTING.md)).

## Features (build order)

| Order | Feature | ADR | Depends on |
|---|---|---|---|
| 1 | Metrics / semantic layer for Streamlit + Pages | [0115](../adr/0115-metrics-layer.md) | none (extends ADR 0085; adds thin `move_evals`) |
| 2 | Mistake classifier + risky-positions view | [0116](../adr/0116-mistake-classifier.md) | none for labels if `fact_move` sample is present; independent of 0115 |
| 3 | Coach agent + live-eval | [0117](../adr/0117-coach-agent-evals.md) | **0115** (typed SQL / metric tools) |

Feature (3) the classifier is independent of (6) the metrics layer unless a
later PR wants metric-backed slice cards. Feature (5) the coach must not ship
before (6): answers have to come from the same governed metrics the surfaces
use.

## What each demonstrates

| Feature | Resume skills |
|---|---|
| 0115 metrics layer | Semantic modeling, MetricFlow on DuckDB, single source of truth, surface parity tests, data quality |
| 0116 mistake classifier | Supervised ML, feature design from warehouse columns, HistGradientBoosting, calibration, model card, product view |
| 0117 coach agent | Tool-calling LLM agents, warehouse tools, eval design (exact + LLM judge), cost governance, instructions-hash discipline |

## Out of scope

- Rewriting historical live-eval receipts or `live_runner.FROZEN_FILES`
- New provider keys outside Doppler / `live-eval` (`CHESSLAB_OPENAI_API_KEY`,
  `CHESSLAB_XAI_API_KEY` per [ADR 0114](../adr/0114-doppler-secrets-source-of-truth.md))
- Causal claims, engine strength rankings, or population accuracy for all
  Lichess games
- Replacing the typed analyst planner (`PLAN_SCHEMA`) with free-form SQL
- Committing trained classifier weights or scored samples

## Success criteria

1. Streamlit KPI strip and Pages metric cards read the same governed metric
   ids for win rate, mean centipawn loss (accuracy), and time-trouble / clock
   pressure, with an offline parity test that fails on drift.
2. Mistake classifier trains on labeled `fact_move` rows, publishes a model
   card with calibration, and exposes a risky-positions view in the Streamlit
   app without live model spend. CI uses a small fixture only; no trained
   model or scored sample is committed.
3. Coach agent answers frozen questions (e.g. opening loss patterns) via
   typed metric tools only; live-eval compares Grok 4.7 and `gpt-6-sol`
   like-for-like under budget caps, with a new frozen set and receipts that
   do not mutate existing ones. First live run is Grok 4.7 under a $5 cap.
   Judge is fixed `gpt-6-luna` and scores explanation only.
4. Each theme lands in stacked PRs under ~400 lines of real code.

## Decided 2026-10-31

1. Accuracy KPI = mean centipawn loss from `fact_move.centipawn_deterioration`
   (clamping and mate rules in [ADR 0115](../adr/0115-metrics-layer.md)).
2. Thin dbt `move_evals` model so MetricFlow governs clock and accuracy;
   source is published `fact_move`.
3. Coach LLM judge = `gpt-6-luna` (fixed); exact checks carry most of the
   score; judge scores explanation only.
4. First live coach run = Grok 4.7, $5 USD cap, manual `live-eval` environment.
5. Classifier artifacts = small CI fixture only; rebuild locally; no trained
   model or scored sample in git.
