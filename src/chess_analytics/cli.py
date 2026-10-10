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
    parser = argparse.ArgumentParser(description="Chess Analytics Lab — local checked data")
    parser.add_argument("--project", type=Path, default=Path.cwd(), help="repository root")
    parser.add_argument("--data-dir", type=Path, help="default: PROJECT/data")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor")
    demo = sub.add_parser("demo", help="offline foundation or complete portfolio fixture")
    demo.add_argument("--scope", choices=("tiny", "all"), default="tiny")
    demo.add_argument("--workspace", type=Path, help="isolated output for --scope all")
    for command in ("ingest", "build", "validate", "report"):
        item = sub.add_parser(command)
        item.add_argument("--dataset", choices=("tiny", "foundation"), default="tiny")
    m7 = sub.add_parser("m7", help="pinned M7 prefix, reference, cases, or live gate")
    m7.add_argument("--campaign", required=True, help="campaign id in config/m7_campaigns.json")
    m7_actions = m7.add_subparsers(dest="m7_action", required=True)
    for action in ("pin", "workspace", "reference", "cases"):
        m7_actions.add_parser(action)
    check = m7_actions.add_parser("check")
    check.add_argument("--preflight", type=Path, required=True)
    check.add_argument("--reports", type=Path, nargs=3, required=True)
    check.add_argument("--audits", type=Path, nargs=3, required=True)
    check.add_argument("--sandbox-attempt", type=Path)
    check.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    project = args.project.resolve()
    root = (args.data_dir or project / "data").resolve()
    dataset = getattr(args, "dataset", "tiny")
    try:
        if args.command == "m7":
            from chess_analytics.m7_campaign import execute

            result, code = execute(project, args)
            print(json.dumps(result, indent=2, sort_keys=True))
            return code
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
        elif args.command == "demo" and args.scope == "all":
            from chess_analytics.portfolio_demo import run

            result = run(project, args.workspace or project / "work/portfolio-demo")
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
