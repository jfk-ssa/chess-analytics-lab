"""Prefect flow view of the existing pipeline. Requires the `prefect` extra."""

import argparse
import json
import os
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[3]

# Use isolated project-local state. A cloud profile or inherited API key must not
# quietly redirect this personal offline demo to an unrelated account.
os.environ["PREFECT_HOME"] = os.environ.get("CHESSLAB_PREFECT_HOME", str(PROJECT / "data/prefect"))
os.environ["PREFECT_SERVER_ANALYTICS_ENABLED"] = "false"
os.environ.pop("PREFECT_PROFILE", None)
if os.environ.get("PREFECT_API_KEY"):
    raise RuntimeError("Prefect adapter requires a local profile without an API key")
api_url = os.environ.get("PREFECT_API_URL", "")
if api_url and not api_url.startswith(("http://127.0.0.1:", "http://localhost:")):
    raise RuntimeError("Prefect adapter only permits a local API URL")

from prefect import flow, task  # noqa: E402  # pyright: ignore[reportMissingImports]

from chess_analytics.orchestration import core  # noqa: E402


@task(name="stage_source", retries=0)
def stage_source(project: str, data_dir: str, dataset: str) -> dict:
    return core.stage(Path(project), Path(data_dir), dataset)


@task(name="publish_snapshot", retries=0)
def publish_snapshot(project: str, data_dir: str, dataset: str) -> dict:
    return core.publish(Path(project), Path(data_dir), dataset)


@task(name="verify_metric", retries=0)
def verify_metric(project: str, data_dir: str, dataset: str) -> dict:
    return core.verify(Path(project), Path(data_dir), dataset)


@task(name="build_analytical_marts", retries=0)
def build_analytical_marts(project: str, data_dir: str, dataset: str) -> dict:
    return core.transform(Path(project), Path(data_dir), dataset)


@flow(name="chesslab-local-pipeline", persist_result=False, retries=0)
def run_pipeline(
    dataset: str = "tiny",
    data_dir: str | None = None,
    project: str | None = None,
    with_dbt: bool = False,
):
    project = str(Path(project or PROJECT).resolve())
    data_dir = str(Path(data_dir or Path(project) / "data").resolve())
    # Sequential task calls enforce publication only after successful staging.
    stage_source(project, data_dir, dataset)
    publish_snapshot(project, data_dir, dataset)
    result = verify_metric(project, data_dir, dataset)
    if with_dbt:
        result["mart"] = build_analytical_marts(project, data_dir, dataset)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="Prefect adapter for Chess Analytics Lab")
    parser.add_argument("--dataset", choices=("tiny", "foundation"), default="tiny")
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--serve", action="store_true", help="register a local UI deployment")
    parser.add_argument("--with-dbt", action="store_true", help="build checked M2 marts")
    args = parser.parse_args(argv)
    data_dir = str((args.data_dir or PROJECT / "data").resolve())
    if args.serve:
        run_pipeline.serve(
            name=f"{args.dataset}-manual",
            parameters={
                "dataset": args.dataset,
                "data_dir": data_dir,
                "project": str(PROJECT),
                "with_dbt": args.with_dbt,
            },
        )
    else:
        print(
            json.dumps(
                run_pipeline(args.dataset, data_dir, str(PROJECT), args.with_dbt), sort_keys=True
            )
        )


if __name__ == "__main__":
    main()
