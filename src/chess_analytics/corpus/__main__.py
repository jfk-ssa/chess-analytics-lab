"""M3 local bounded corpus commands. Run from the repository root."""

import argparse
import json
import re
from pathlib import Path

from chess_analytics.common import read_json, writer_lock
from chess_analytics.corpus.publish import build_analytical, validate_analytical
from chess_analytics.corpus.source import acquire_prefix, extract_complete_games
from chess_analytics.ingest.pipeline import ingest
from chess_analytics.warehouse.snapshots import build, report


def main(argv=None):
    parser = argparse.ArgumentParser(description="Chess Analytics Lab M3 analytical corpus")
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--data-dir", type=Path)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("acquire", help="fetch or verify the fixed 40 MB range")
    sub.add_parser("extract", help="retain at most 100,000 complete PGNs")
    sub.add_parser("ingest", help="normalize and publish the bounded source")
    sub.add_parser("moves", help="publish a deterministic game sample of move annotations")
    sub.add_parser("report", help="validate and print the current move snapshot")
    args = parser.parse_args(argv)
    project = args.project.resolve()
    root = (args.data_dir or project / "data").resolve()
    plan = read_json(project / "config/datasets.json")["analytical"]
    try:
        if args.command == "report":
            pointer = read_json(root / "analytical-moves-current.json")
            identity = pointer["analytical_id"]
            if not re.fullmatch(r"[0-9a-f]{24}", identity):
                raise ValueError("invalid analytical snapshot ID")
            result = validate_analytical(root / "analytical/published" / identity)
        else:
            with writer_lock(root):
                if args.command == "acquire":
                    path = acquire_prefix(root, plan)
                    result = read_json(path.parent / "acquisition.json")
                elif args.command == "extract":
                    path = acquire_prefix(root, plan)
                    _, result = extract_complete_games(root, plan, path)
                elif args.command == "ingest":
                    path = acquire_prefix(root, plan)
                    source, receipt = extract_complete_games(root, plan, path)
                    candidate_plan = {**plan, "expected_records": receipt["complete_games"]}
                    ingest(project, root, "analytical", source, candidate_plan)
                    snapshot = build(project, root, "analytical")
                    result = report(project, snapshot)
                else:
                    path = build_analytical(project, root)
                    result = validate_analytical(path)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(1, f"m3: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
