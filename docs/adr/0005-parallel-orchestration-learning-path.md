# 0005. Parallel orchestration learning path

- Status: accepted
- Date: 2026-10-03

User requested Dagster and Prefect versions in this repository, with Airflow a
possible later exercise. Keep the M1 pipeline as the single implementation and
put thin framework adapters outside `src/`, so neither can redefine ingestion or
the governed metric. Pin Dagster 1.13.25, dagster-webserver 1.13.25, and Prefect
3.8.7 as separate optional extras in the same uv lock. Use synthetic fixture
data by default, isolated local data directories, no automatic schedules, and
local UI/server only. Prefect rejects inherited API keys or remote API URLs; both
disable telemetry in the adapter's local invocation. This is an M2 learning slice,
not evidence that the dbt/recovery milestone is complete.

The framework comparison checks same-source published results rather than relying
on run-status messages alone. It produced matching fixture snapshot identity,
counts and 4/20 metric; these are harness results, not AI responses, production
reliability evidence, or a hosted orchestration benchmark. The first Prefect run
could not bind its ephemeral local API in the sandbox; a local-loopback-permitted
run succeeded. Preserve the failure in status instead of hiding it.

Airflow is deferred until after M2 dbt work supplies meaningful transformed assets
to orchestrate. Its extra server/database/install cost is not justified for the
current three-step tiny path. Reassess if learning a DAG/operator model still adds
value then. No Airflow installation or cloud infrastructure now.
