"""Local M2 commands. Run as python -m chess_analytics.marts from the repository root."""

import argparse
import json
import sys
from pathlib import Path

from chess_analytics.common import read_json, writer_lock
from chess_analytics.marts.pipeline import (
    build_mart,
    checked_id,
    operational_report,
    rollback_mart,
    validate_mart,
)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Chess Analytics Lab M2 local operations")
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--data-dir", type=Path)
    sub = parser.add_subparsers(dest="command", required=True)
    transform = sub.add_parser("transform", help="run dbt on a checked snapshot")
    transform.add_argument("--dataset", choices=("tiny", "foundation"), default="tiny")
    transform.add_argument("--snapshot-id", help="backfill an older checked snapshot")
    rollback = sub.add_parser("rollback-mart", help="select a validated prior mart")
    rollback.add_argument("--dataset", choices=("tiny", "foundation"), default="tiny")
    rollback.add_argument("mart_id")
    for command in ("report-mart", "ops-report"):
        item = sub.add_parser(command)
        item.add_argument("--dataset", choices=("tiny", "foundation"), default="tiny")
    args = parser.parse_args(argv)
    project = args.project.resolve()
    root = (args.data_dir or project / "data").resolve()
    try:
        if args.command == "transform":
            executable = Path(sys.executable).with_name("dbt")
            if not executable.exists():
                raise ValueError("dbt extra is not installed in this environment")
            with writer_lock(root):
                result = build_mart(
                    project, root, args.dataset, executable, source_id=args.snapshot_id
                )
            output = validate_mart(result)
        elif args.command == "rollback-mart":
            with writer_lock(root):
                result = rollback_mart(root, args.dataset, args.mart_id)
            output = validate_mart(result)
        elif args.command == "report-mart":
            pointer = read_json(root / f"{args.dataset}-mart-current.json")
            output = validate_mart(root / "marts/published" / checked_id(pointer["mart_id"]))
        else:
            output = operational_report(root, args.dataset)
        print(json.dumps(output, indent=2, sort_keys=True))
        return 0
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(1, f"m2: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
