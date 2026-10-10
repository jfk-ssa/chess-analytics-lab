"""Common adapter boundary. Business rules remain in chess_analytics."""

import sys
from pathlib import Path

from chess_analytics.cli import fixture_plan
from chess_analytics.common import read_json, writer_lock
from chess_analytics.ingest.acquire import acquire
from chess_analytics.ingest.pipeline import ingest
from chess_analytics.warehouse.snapshots import build, current, report


def stage(project: Path, data_dir: Path, dataset: str) -> dict:
    project, data_dir = project.resolve(), data_dir.resolve()
    if dataset not in {"tiny", "foundation"}:
        raise ValueError(f"unsupported dataset: {dataset}")
    plan = (
        fixture_plan(project)
        if dataset == "tiny"
        else read_json(project / "config/datasets.json")[dataset]
    )
    with writer_lock(data_dir):
        source = (
            project / "tests/fixtures/tiny.pgn" if dataset == "tiny" else acquire(data_dir, plan)
        )
        path = ingest(project, data_dir, dataset, source, plan)
    manifest = read_json(path / "manifest.json")
    return {
        "run_id": manifest["run_id"],
        "status": manifest["status"],
        "counts": manifest["counts"],
        "source_sha256": manifest["source_sha256"],
    }


def publish(project: Path, data_dir: Path, dataset: str) -> dict:
    project, data_dir = project.resolve(), data_dir.resolve()
    with writer_lock(data_dir):
        snapshot = build(project, data_dir, dataset)
        return report(project, snapshot)


def verify(project: Path, data_dir: Path, dataset: str) -> dict:
    return report(project.resolve(), current(data_dir.resolve(), dataset))


def transform(project: Path, data_dir: Path, dataset: str) -> dict:
    from chess_analytics.marts.pipeline import build_mart, validate_mart

    executable = Path(sys.executable).with_name("dbt")
    if not executable.exists():
        raise ValueError("dbt extra is required for M2 transformation")
    with writer_lock(data_dir.resolve()):
        path = build_mart(project.resolve(), data_dir.resolve(), dataset, executable)
    return validate_mart(path)
