"""Run frozen M7 repetitions under one cumulative gross cap; retain each attempt."""

import argparse
import hashlib
import json
from pathlib import Path

from analyst_m5.experiment import run
from chess_analytics.common import write_json


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--config", type=Path, help="explicit personal provider configuration")
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument(
        "--holdout-version", type=int, choices=(3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14), default=3
    )
    parser.add_argument(
        "--prior-gross-usd",
        type=float,
        default=0.0,
        help="known previous gross plus full reservation for unknown-cost attempts",
    )
    args = parser.parse_args()
    if args.ledger.exists():
        raise ValueError("existing ledger requires manual audit before another run")
    preflight_bytes = args.preflight.read_bytes()
    preflight = json.loads(preflight_bytes)
    if preflight["kind"] != "m7_typed_planner_holdout_preflight_no_model_calls":
        raise ValueError("M7 frozen preflight required")
    expected_case_file = (
        "evals/cases/m7_holdout.json"
        if args.holdout_version == 3
        else f"evals/cases/m7_holdout_v{args.holdout_version - 2}.json"
    )
    if preflight["case_file"] != expected_case_file:
        raise ValueError("M7 holdout version differs from frozen preflight")
    if not 1 <= args.repeats <= 3:
        raise ValueError("one to three repetitions required")
    if not 0 <= args.prior_gross_usd < preflight["max_run_usd"]:
        raise ValueError("invalid cumulative prior gross amount")
    cap = preflight["max_run_usd"]
    quote = preflight["conservative_total_usd"]
    if args.prior_gross_usd + args.repeats * quote > cap:
        raise ValueError("three-repeat conservative reservation exceeds cumulative cap")
    ledger = {
        "kind": "M7 live cumulative gross budget ledger",
        "preflight_sha256": hashlib.sha256(preflight_bytes).hexdigest(),
        "approved_cumulative_cap_usd": cap,
        "per_repeat_conservative_reservation_usd": quote,
        "planned_repeats": args.repeats,
        "holdout_version": args.holdout_version,
        "completed_repeats": 0,
        "prior_gross_accounted_usd": args.prior_gross_usd,
        "gross_accounted_usd": args.prior_gross_usd,
        "state": "ready",
        "summaries": [],
    }
    write_json(args.ledger, ledger)
    for repeat in range(1, args.repeats + 1):
        if ledger["gross_accounted_usd"] + quote > cap + 1e-12:
            ledger["state"] = "stopped_remaining_cap_insufficient"
            break
        ledger["state"] = f"running_repeat_{repeat}"
        write_json(args.ledger, ledger)
        summary = run(
            args.project,
            args.config,
            args.preflight,
            max_run_usd=None if args.config else cap,
            env_file=args.env_file,
            holdout=True,
            holdout_version=args.holdout_version,
            conditions=preflight["conditions"],
        )
        summary_path = (
            args.ledger.parent / f"m7-v{args.holdout_version - 2}-run-{repeat}-summary.json"
        )
        write_json(summary_path, summary)
        ledger["summaries"].append(str(summary_path))
        ledger["gross_accounted_usd"] += summary.get(
            "gross_cost_accounted_usd", summary["known_gross_cost_usd"]
        )
        raw_budget_issue = any(
            json.loads(path.read_text()).get("budget_bound_exceeded")
            for path in Path(summary["records_dir"]).glob("[0-9][0-9]-*.json")
        )
        if (
            not summary["cost_complete"]
            or summary["failed"]
            or raw_budget_issue
            or ledger["gross_accounted_usd"] > cap
        ):
            ledger["state"] = "stopped_failed_or_unknown_cost"
            write_json(args.ledger, ledger)
            break
        if summary["attempts"] != preflight["attempts_planned"]:
            ledger["state"] = "stopped_incomplete_repeat"
            write_json(args.ledger, ledger)
            break
        ledger["completed_repeats"] += 1
        ledger["state"] = "complete" if repeat == args.repeats else "ready"
        write_json(args.ledger, ledger)
        print(
            json.dumps(
                {
                    "repeat": repeat,
                    "attempts": summary["attempts"],
                    "scored_correct": summary["scored_correct"],
                    "cumulative_gross_usd": ledger["gross_accounted_usd"],
                }
            )
        )
    print(json.dumps(ledger, sort_keys=True))


if __name__ == "__main__":
    main()
