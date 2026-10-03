"""Typed analyst and replay CLI, with live calls disabled by default."""

import argparse
import json
from pathlib import Path

from analyst_m5.core import execute_plan, replay
from analyst_m5.evaluation import save
from analyst_m5.provider import recorded_live_answer


def main(argv=None):
    parser = argparse.ArgumentParser(description="Checked chess-data analyst")
    parser.add_argument("--project", type=Path, default=Path.cwd())
    sub = parser.add_subparsers(dest="mode", required=True)
    typed = sub.add_parser("typed")
    typed.add_argument("question")
    typed.add_argument("--plan", type=Path, required=True)
    fixture = sub.add_parser("replay")
    fixture.add_argument("question")
    fixture.add_argument("--fixture", type=Path, required=True)
    evaluation = sub.add_parser("eval")
    evaluation.add_argument("--split", choices=["dev", "test", "both"], default="both")
    live = sub.add_parser("live")
    live.add_argument("question")
    live.add_argument("--config", type=Path, required=True)
    args = parser.parse_args(argv)
    project = args.project.resolve()
    try:
        if args.mode == "typed":
            answer = execute_plan(project, args.question, json.loads(args.plan.read_text()))
        elif args.mode == "replay":
            answer = replay(project, args.question, args.fixture)
        elif args.mode == "eval":
            answer = save(project, args.split)
        else:
            answer = recorded_live_answer(project, args.question, args.config)
        print(json.dumps(answer, indent=2, sort_keys=True))
    except (OSError, ValueError, TimeoutError) as exc:
        parser.exit(1, f"analyst: {exc}\n")


if __name__ == "__main__":
    main()
