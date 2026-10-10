# Local orchestration comparison

Dagster and Prefect are optional views over one Chess Analytics Lab pipeline. The
Dagster graph has `staged_games → published_snapshot → verified_metric` assets;
the Prefect flow has the corresponding `stage_source → publish_snapshot →
verify_metric` tasks. With dbt enabled, each adds a fourth analytical-mart step.
Both call `src/chess_analytics/orchestration/core.py`, which delegates parsing,
validation, publication, and metric calculation to the existing `chess_analytics`
package. The default dataset is the committed tiny synthetic fixture. There is no
schedule, cloud account, model call, or paid service in these demos.

Run from the repository root. Install each extra in its own environment to compare
them independently (a first install needs package-network access; later runs can
use uv's cache):

```sh
UV_PROJECT_ENVIRONMENT=work/dagster-venv uv sync --locked --no-editable --extra dagster
UV_PROJECT_ENVIRONMENT=work/prefect-venv uv sync --locked --no-editable --extra prefect
```

The separate `work/` environments are Git-ignored. Dagster discovery and a one-off
tiny run:

```sh
mkdir -p data/dagster-home
cp config/dagster.yaml data/dagster-home/dagster.yaml
DAGSTER_DISABLE_TELEMETRY=1 work/dagster-venv/bin/dagster asset list -m chess_analytics.orchestration.dagster_app
DAGSTER_HOME="$PWD/data/dagster-home" DAGSTER_DISABLE_TELEMETRY=1 \
  CHESSLAB_DATA_DIR="$PWD/data/dagster-demo" \
  work/dagster-venv/bin/dagster asset materialize -m chess_analytics.orchestration.dagster_app --select '*'
```

For the local Dagster UI, run:

```sh
DAGSTER_HOME="$PWD/data/dagster-home" DAGSTER_DISABLE_TELEMETRY=1 \
  CHESSLAB_DATA_DIR="$PWD/data/dagster-demo" \
  work/dagster-venv/bin/dagster dev -m chess_analytics.orchestration.dagster_app
```

Open the localhost address printed by Dagster. Materialize the three assets from
the UI. `CHESSLAB_DATASET=foundation` selects the already-configured, bounded
historical archive and may download it; leave it unset for a quick offline run.

Prefect one-off execution starts only an ephemeral local API:

```sh
env -u PREFECT_API_KEY -u PREFECT_API_URL -u PREFECT_PROFILE \
  work/prefect-venv/bin/python -m chess_analytics.orchestration.prefect_app \
  --data-dir data/prefect-demo
```

For the Prefect UI, start its local server in one terminal, then serve the flow in
another. Open `http://127.0.0.1:4200` and trigger the `tiny-manual` deployment.
The application rejects inherited API keys and nonlocal API URLs, and isolates its
Prefect home under `data/`.

```sh
env -u PREFECT_API_KEY -u PREFECT_API_URL -u PREFECT_PROFILE \
  PREFECT_HOME="$PWD/data/prefect" PREFECT_SERVER_ANALYTICS_ENABLED=false \
  work/prefect-venv/bin/prefect server start
```

```sh
env -u PREFECT_API_KEY -u PREFECT_PROFILE \
  PREFECT_API_URL=http://127.0.0.1:4200/api \
  work/prefect-venv/bin/python -m chess_analytics.orchestration.prefect_app \
  --data-dir data/prefect-demo --serve
```

For a same-input acceptance comparison, install both extras in one third
environment and run the script. It writes separate local data directories and
`reports/orchestrator-comparison.json`. This command needs permission to bind a
localhost port for Prefect's ephemeral API; it does not need Internet access after
installation.

```sh
UV_PROJECT_ENVIRONMENT=work/both-venv uv sync --locked --no-editable --extra dagster --extra prefect
work/both-venv/bin/python -m scripts.compare_orchestrators
```

To compare the M2 step, install the dbt extra alongside either framework. For
Dagster, set `CHESSLAB_WITH_DBT=1` in the materialize or UI command; for Prefect,
add `--with-dbt` to its one-off or `--serve` command. The dbt build is local and
publishes only after its tests and reconciliation pass. The separate M2 evidence
and recovery commands are in [M2.md](M2.md).

```sh
UV_PROJECT_ENVIRONMENT=work/dagster-dbt-venv uv sync --locked --no-editable --extra dagster --extra dbt
UV_PROJECT_ENVIRONMENT=work/prefect-dbt-venv uv sync --locked --no-editable --extra prefect --extra dbt
```

The recorded run on 2026-10-03 materialized three Dagster assets and completed
three Prefect tasks. Both accepted 22 fixture games and independently read the
same 4/20 draw-rate metric from their own published snapshots. The compared
snapshot IDs, source hashes, counts, and metric objects matched. This is **offline
pipeline parity**, not a scheduler reliability benchmark or AI evaluation. The
foundation snapshot remains governed by the M1 checks.

These optional packages increase local install size and dependency count but add
no recurring project charge when self-hosted locally. Do not enable Dagster+ or
Prefect Cloud for this exercise. The Python/CLI path remains the smallest runtime
and source of truth. A third Airflow adapter can now be considered against a
working dbt pipeline, but only if its operator/DAG ergonomics justify another
large local stack.
No Airflow dependency or infrastructure is present now.
