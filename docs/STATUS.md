# Status — 2026-10-03

**M0–M2 accepted locally; M3 is next.** This is a new standalone local Git
repository; projects 1–3 remain together. No remote repository or hosting created.

## Completed acceptance

| Milestone | Implemented behavior | Verified evidence |
|---|---|---|
| M0 | Python 3.12.14, uv.lock, exact package/build pins, CLI, synthetic fixtures, table/metric contracts | Clean local clone + fresh environment installed offline from cache; all 21 tests and demo passed. Ruff check/format passed. |
| M1 | Bounded complete-source acquisition, legal PGN replay, provenance/quarantine, typed Parquet → DuckDB, checked snapshots, draw-rate metric | Publisher SHA256 verified; 121,332 accepted games and 242,664 participant rows; zero quarantine/conflicts; all quality checks passed. |
| M1 repeatability | Repeat full ingestion and repeat publication | Two full ingestions produced identical normalized-file hashes. An acquisition-only code change separates them; same-code repeat ingestion is also tested on tiny fixtures. Repeated foundation build preserves snapshot ID and metric. |
| M1 metric reference | Independent fixture arithmetic and real-source header tally | Tiny: 4/20 = 0.20. Foundation: 3,982/121,332 = 0.03281904196749415; DuckDB agrees exactly with the independent script. |
| Optional orchestrators | Thin Dagster asset graph and Prefect task flow over the existing pipeline; exact pins in separate optional extras | Same-input offline comparison: 3 assets and 3 tasks succeeded; both produced 22 accepted fixture games, 4/20 draws, and identical source/snapshot/metric records. [Machine-readable result](../reports/orchestrator-comparison.json). |
| M2 dbt | Five staging/intermediate/mart models over checked snapshots; isolated candidates, source-to-mart reconciliation, immutable published marts and lineage artifacts | Tiny and foundation each created 5 models and passed 19 dbt tests. Foundation mart: 121,332 games, 242,664 participant rows, 3,982 draws. [M2 evidence](M2.md). |
| M2 recovery | Failed dbt attempts and logs retained; pointer protected until checks pass; backfill by snapshot ID; validated rollback; operational ledger and source-version warnings | Injected failure preserved prior mart; retry matched clean run; failed dbt kept M1 snapshot usable; 23 offline tests passed in dbt-only environment. Dagster 4 assets and Prefect 4 tasks succeeded locally with dbt enabled. |

Acceptance details: [reports/M0-M1.md](../reports/M0-M1.md), machine-readable
[acceptance.json](../reports/acceptance.json), [foundation manifest](../reports/foundation-manifest.json).
CI workflow exists; equivalent commands ran locally. No hosted CI run is claimed.

## Current dataset versions

- Foundation source: complete `lichess_db_standard_rated_2013-01.pgn.zst`,
  17,761,302 compressed bytes; 92,811,021 decompressed bytes scanned.
- Source SHA256: `aa40b3671fa3cf1072eb182892cd90b0e1e003a4a5943492f64b77e7f3fd1635`.
- Foundation snapshot: `d81caa5b8d6e3122dcf8e917` in ignored `data/published/`.
- Tiny snapshot: `09759ec63554e3b47de939e6`; fabricated fixtures, never population data.
- M2 marts over those checked snapshots: foundation `04001031eb6ba61d2ccbfa13`,
  tiny `b2459d2fb4d0b3570051c6f6`. IDs also bind the dbt files and uv lock;
  a clean rebuild after a dependency change may use a new ID with the same counts.
- Observed foundation UTC dates: **2012-12-31 through 2013-01-31**, not inferred
  from the archive label. 218 participant ratings are missing and remain null.
- Metric/table contract version: 1.0.0. Source implementation commit:
  `a617582b7df05193485d07721c6f21cccda72df0`. Final documentation/evidence commits
  follow it without changing pipeline source. Full code/lock hashes are in reports.

## Limitations and blockers

No blocker for M3. Normal wheel installation (`--no-editable`) resolves the observed
macOS hidden editable `.pth` issue; see DECISIONS.md. Initial package/bootstrap
failures are recorded there. Archive and dependencies were downloaded once with
network access; offline reproduction assumes installed or cached dependencies.

M1/M2 target fixed complete Lichess exports and one local writer. They do not claim
general PGN import, power-loss durability, full multi-source reconciliation,
unattended scheduling, or scaling benchmarks. Failed/old local runs are retained.
The 2013 archive provides ingestion evidence, not contemporary player or clock analysis.
The optional orchestrators are local demonstrations, with no schedules or cloud
deployments. Prefect's local ephemeral API needs a localhost socket. The first
comparison attempt could not bind one inside the sandbox; a permitted local run
completed and its result was saved. See [run instructions](ORCHESTRATION.md).
Separate locked Dagster-only and Prefect-only environments installed from the local
uv cache and completed one-off tiny runs. A fresh base-only environment still passes
all 21 offline tests; Ruff check/format and `uv lock --check --offline` pass. The
foundation snapshot still reports 3,982/121,332 from the base environment.

## Next concrete work — M3

1. Select a newer, bounded source for opening and clock questions; record observed
   coverage, missingness, provenance, and limits before making claims.
2. Add versioned opening and clock metric contracts with independent references,
   and draft 12 development evaluation cases.
3. Consider an Airflow learning adapter only if comparing a third orchestration
   model still justifies its added local stack. No Airflow install or run is claimed.

Then M4 dashboard and memos; M5 analyst/replay/eval harness; M6 live experiment.
Jev remains M8; the personalized recommender remains backlog.

**No model responses, replay results or live benchmark exist.** Provider configuration
is disabled and inert; no provider SDK or credential discovery exists. Before M5/M6
live work, require personal account configuration, named model/prices and an explicit
run spending cap. No workplace credentials were read or used.
