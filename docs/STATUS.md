# Status — 2026-10-03

## M0 — implemented; final fresh-environment check pending

New local Git repository, copied complete brief, Python 3.12.14, uv.lock, pinned
runtime/development/build dependencies, explicit table/metric contracts and CLI.
Tiny synthetic fixture: 26 inputs, 22 accepted games, 44 participant rows, 2 exclusions,
2 quarantined. Independently specified draw rate 4/20 = 0.20.
19 offline tests pass with socket connections forbidden; Ruff passes.
Regular wheel installation resolves this Mac's hidden editable .pth incompatibility.

## M1 — verification in progress

Bounded acquisition succeeded for the complete January 2013 standard archive.
Publisher SHA256 verified: aa40b3671fa3cf1072eb182892cd90b0e1e003a4a5943492f64b77e7f3fd1635.
Independent header reference: 121,332 games, 3,982 draws, fraction 0.03281904196749415.
Observed source UTC dates: 2012-12-31 through 2013-01-31.
Legal-move parsing, Parquet → DuckDB build, and full-corpus rerun remain to be checked.

## Scope and next milestone

M2–M8 remain unimplemented. Next after M1 acceptance: dbt models/tests/lineage,
expanded recovery/source-drift tests and operational report; only then Dagster.
M3 adds bounded newer data, clock/opening metric contracts and initial eval references.
M4 dashboard/memos; M5 analyst/replay/eval harness; M6 separately authorized live study.
Jev follows core release; personalized recommender remains backlog.

No provider SDK/calls, credential reads, model responses, replay results or model
benchmarks. No cloud infrastructure, remote repository, hosting or spend configured.
Failures and partial runs stay in ignored data/. See DECISIONS.md and RUNBOOK.md.
