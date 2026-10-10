# 0006. M2 dbt and mart recovery

- Status: accepted
- Date: 2026-10-03

Pin `dbt-duckdb==1.10.1` as a separate optional extra. The resolved local
combination includes dbt-core 1.12.5 and existing DuckDB 1.4.1; it actually built
the tiny and foundation models. Keep five SQL models and generic/singular data
tests in `dbt/`, with one local DuckDB profile and one thread. No hosted dbt
service or remote connection is required. dbt usage telemetry is disabled for
the wrapper's subprocess.

Retain M1 snapshots as immutable sources. M2 copies the checked DuckDB file to
an attempt directory, executes dbt there, reconciles mart counts with the M1
metric contract, and publishes a separate immutable mart only after success.
The mart identity includes M1 snapshot, dbt model files, and uv lock hashes.
Store dbt lineage/result artifacts with the published mart and keep failure logs
with attempts. A historical backfill does not switch the current mart pointer;
rollback selects only a validated prior mart. The one-writer lock covers mart
publication. This adds local disk cost (the foundation mart database was 30 MB)
but no recurring service charge.

Source drift severity remains simple and explicit: a configured publisher
checksum mismatch fails ingestion; multiple observed hashes for an unpinned
local dataset produce an operational warning. This is not a full schema-evolution
system. The process-level injected failures and recovery tests passed; power-loss
durability, general multi-source reconciliation, process peak-memory measurement,
and unattended scheduling remain outside the claim. Both existing orchestrators
gain an opt-in fourth dbt step, preserving their small default demonstrations.
