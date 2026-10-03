"""Offline, same-input Dagster/Prefect acceptance run. Requires both extras."""

import json
import os
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
os.environ["CHESSLAB_PREFECT_HOME"] = str(PROJECT / "data/prefect")
os.environ["PREFECT_SERVER_ANALYTICS_ENABLED"] = "false"
os.environ["DAGSTER_DISABLE_TELEMETRY"] = "1"

import dagster as dg  # noqa: E402

from chess_analytics.common import write_json  # noqa: E402
from orchestration.core import verify  # noqa: E402
from orchestration.dagster_app import make_assets  # noqa: E402
from orchestration.prefect_app import run_pipeline  # noqa: E402


def compare(base: Path | None = None):
    base = (base or PROJECT / "data/orchestration-comparison").resolve()
    dagster_data = base / "dagster"
    prefect_data = base / "prefect"
    dagster_data.mkdir(parents=True, exist_ok=True)
    prefect_data.mkdir(parents=True, exist_ok=True)
    with dg.DagsterInstance.ephemeral() as instance:
        run = dg.materialize(make_assets(PROJECT, dagster_data), instance=instance)
        if not run.success:
            raise RuntimeError("Dagster materialization failed; local run artifacts retained")
    dagster_report = verify(PROJECT, dagster_data, "tiny")
    prefect_report = run_pipeline("tiny", str(prefect_data), str(PROJECT))
    keys = ("snapshot_id", "source_sha256", "counts", "metric")
    if any(dagster_report[k] != prefect_report[k] for k in keys):
        raise AssertionError("orchestrator results differ; local artifacts retained")
    result = {
        "kind": "offline fixture adapter comparison; no model responses",
        "dataset": "tiny synthetic fixture",
        "dagster_version": dg.__version__,
        "prefect_version": __import__("prefect").__version__,
        "dagster_assets_materialized": 3,
        "prefect_tasks_completed": 3,
        "snapshot_id": dagster_report["snapshot_id"],
        "source_sha256": dagster_report["source_sha256"],
        "counts": dagster_report["counts"],
        "metric": dagster_report["metric"],
        "results_equal": True,
    }
    return result


if __name__ == "__main__":
    output = compare()
    write_json(PROJECT / "reports/orchestrator-comparison.json", output)
    print(json.dumps(output, indent=2, sort_keys=True))
