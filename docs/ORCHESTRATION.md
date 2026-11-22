# Historical local orchestration comparison

The optional Dagster and Prefect adapters, extras, and comparison script
were retired by [ADR 0119](adr/0119-deduplicate-workflows-and-prune-stale-extras.md).
The Python CLI remains the pipeline runner; current commands are in the
[runbook](RUNBOOK.md). No scheduler or cloud service is required.

The [committed comparison receipt](../reports/orchestrator-comparison.json),
[ADR 0005](adr/0005-parallel-orchestration-learning-path.md), and
[ADR 0108](adr/0108-dagster-packages-update-together.md) preserve the learning
exercise. Reproducing those adapters requires their historical checkout;
the current lock does not provide `dagster` or `prefect` extras.
ADR 0005 also preserves the initial Prefect sandbox failure before the
successful local-loopback run.

The recorded run on 2026-10-03 materialized three Dagster assets and completed
three Prefect tasks. Both accepted 22 fixture games and independently read the
same 4/20 draw-rate metric from their own published snapshots. The compared
snapshot IDs, source hashes, counts, and metric objects matched. This is **offline
pipeline parity**, not a scheduler reliability benchmark or AI evaluation. The
foundation snapshot remains governed by the M1 checks.
