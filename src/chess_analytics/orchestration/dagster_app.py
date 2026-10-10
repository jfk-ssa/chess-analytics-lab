"""Dagster asset view of the existing pipeline. Requires the `dagster` extra."""

import os
from pathlib import Path

os.environ["DAGSTER_DISABLE_TELEMETRY"] = "1"

import dagster as dg  # pyright: ignore[reportMissingImports]

from chess_analytics.orchestration import core

PROJECT = Path(__file__).resolve().parents[3]


def make_assets(project: Path, data_dir: Path, dataset: str = "tiny", with_dbt: bool = False):
    """Bind one fixed dataset and directory to three inspectable data assets."""
    project, data_dir = project.resolve(), data_dir.resolve()

    @dg.asset(group_name="chesslab", description="Bounded source and normalized staging manifest")
    def staged_games() -> dg.MaterializeResult:
        result = core.stage(project, data_dir, dataset)
        return dg.MaterializeResult(
            metadata={
                "dataset": dataset,
                "run_id": result["run_id"],
                "source_sha256": result["source_sha256"],
                "accepted_games": result["counts"]["accepted"],
            }
        )

    @dg.asset(
        deps=[staged_games],
        group_name="chesslab",
        description="Checked immutable Parquet/DuckDB snapshot",
    )
    def published_snapshot() -> dg.MaterializeResult:
        result = core.publish(project, data_dir, dataset)
        return dg.MaterializeResult(
            metadata={
                "dataset": dataset,
                "snapshot_id": result["snapshot_id"],
                "accepted_games": result["counts"]["accepted"],
            }
        )

    @dg.asset(
        deps=[published_snapshot],
        group_name="chesslab",
        description="Read-only validation and governed game draw rate",
    )
    def verified_metric() -> dg.MaterializeResult:
        result = core.verify(project, data_dir, dataset)
        return dg.MaterializeResult(
            metadata={
                "dataset": dataset,
                "snapshot_id": result["snapshot_id"],
                "draws": result["metric"]["numerator"],
                "eligible_games": result["metric"]["denominator"],
            }
        )

    assets = [staged_games, published_snapshot, verified_metric]
    if with_dbt:

        @dg.asset(
            deps=[verified_metric],
            group_name="chesslab",
            description="Checked dbt staging, intermediate, and mart models",
        )
        def analytical_marts() -> dg.MaterializeResult:
            result = core.transform(project, data_dir, dataset)
            return dg.MaterializeResult(
                metadata={
                    "dataset": dataset,
                    "mart_id": result["mart_id"],
                    "dbt_tests_passed": result["dbt_results"]["passed"],
                }
            )

        assets.append(analytical_marts)
    return assets


def make_definitions(project: Path, data_dir: Path, dataset: str = "tiny", with_dbt: bool = False):
    return dg.Definitions(assets=make_assets(project, data_dir, dataset, with_dbt))


defs = make_definitions(
    PROJECT,
    Path(os.environ.get("CHESSLAB_DATA_DIR", PROJECT / "data")),
    os.environ.get("CHESSLAB_DATASET", "tiny"),
    os.environ.get("CHESSLAB_WITH_DBT") == "1",
)
