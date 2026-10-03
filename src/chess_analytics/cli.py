import argparse
import json
import platform
import shutil
from pathlib import Path

from chess_analytics.common import read_json, writer_lock
from chess_analytics.ingest.acquire import acquire
from chess_analytics.ingest.pipeline import ingest
from chess_analytics.warehouse.snapshots import build, current, report, validate_snapshot


def fixture_plan(project):
    return {
        "url": "local:tests/fixtures/tiny.pgn",
        "period": "synthetic",
        "complete_archive": False,
        "source_kind": "synthetic_test_fixture",
        "max_source_bytes": 1_000_000,
        "max_decompressed_bytes": 1_000_000,
        "max_generated_bytes": 5_000_000_000,
        "max_games": 100,
        "max_record_bytes": 100_000,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Chess Analytics Lab — local M0/M1 pipeline")
    parser.add_argument("--project", type=Path, default=Path.cwd(), help="repository root")
    parser.add_argument("--data-dir", type=Path, help="default: PROJECT/data")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor")
    sub.add_parser(
        "demo", help="synthetic fixture pipeline, offline; analyst replay is planned for M5"
    )
    for command in ("ingest", "build", "validate", "report"):
        item = sub.add_parser(command)
        item.add_argument("--dataset", choices=("tiny", "foundation"), default="tiny")
    args = parser.parse_args(argv)
    project = args.project.resolve()
    root = (args.data_dir or project / "data").resolve()
    dataset = getattr(args, "dataset", "tiny")
    try:
        if args.command == "doctor":
            provider = read_json(project / "config/provider.json")
            result = {
                "python": platform.python_version(),
                "platform": platform.platform(),
                "free_disk_bytes": shutil.disk_usage(project).free,
                "lock_present": (project / "uv.lock").exists(),
                "provider_configuration": provider,
                "live_calls_supported": False,
                "credentials_read": False,
            }
        elif args.command in {"ingest", "build", "demo"}:
            with writer_lock(root):
                if args.command in {"ingest", "demo"}:
                    plan = (
                        fixture_plan(project)
                        if dataset == "tiny"
                        else read_json(project / "config/datasets.json")[dataset]
                    )
                    source = (
                        project / "tests/fixtures/tiny.pgn"
                        if dataset == "tiny"
                        else acquire(root, plan)
                    )
                    stage = ingest(project, root, dataset, source, plan)
                    result = read_json(stage / "manifest.json")
                if args.command in {"build", "demo"}:
                    snapshot = build(project, root, dataset)
                    result = report(project, snapshot)
        elif args.command == "validate":
            result = {"quality_checks": validate_snapshot(current(root, dataset))}
        else:
            result = report(project, current(root, dataset))
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (OSError, ValueError, RuntimeError) as e:
        parser.exit(1, f"chesslab: {e}\n")


if __name__ == "__main__":
    raise SystemExit(main())
