"""Summarize repeated frozen holdout runs without hiding stopped cells."""

import argparse
import json
import statistics
from pathlib import Path

from chess_analytics.common import write_json


def _median(rows):
    return statistics.median(rows) if rows else None


def build(preflight_path: Path, report_paths: list[Path]) -> dict:
    preflight = json.loads(preflight_path.read_text())
    reports = [json.loads(path.read_text()) for path in report_paths]
    if not reports or any(r["case_set_sha256"] != preflight["case_set_sha256"] for r in reports):
        raise ValueError("repeat case set mismatch")
    runs = []
    for index, report in enumerate(reports, 1):
        attempts = report["attempts"]
        passed = sum(bool((a["score"] or {}).get("passed")) for a in attempts)
        runs.append(
            {
                "repeat": index,
                "attempted": len(attempts),
                "planned": preflight["attempts_planned"],
                "not_attempted": preflight["attempts_planned"] - len(attempts),
                "completed": report["completed"],
                "passed": passed,
                "answerable": report["answerable"],
                "ambiguity_or_unsupported": report["ambiguity_or_unsupported"],
                "high_severity": report["high_severity"],
                "gross_cost_usd": report["known_gross_cost_usd"],
                "gross_cost_per_passed_usd": (
                    report["known_gross_cost_usd"] / passed if passed else None
                ),
                "median_latency_seconds": _median([a["elapsed_seconds"] for a in attempts]),
                "cached_input_tokens": sum(
                    (a["usage"] or {}).get("input_tokens_details", {}).get("cached_tokens", 0)
                    for a in attempts
                ),
                "cache_write_tokens": sum(
                    (a["usage"] or {}).get("input_tokens_details", {}).get("cache_write_tokens", 0)
                    for a in attempts
                ),
                "failures": [
                    {
                        "case_id": a["case_id"],
                        "condition": a["condition"],
                        "status": a["status"],
                        "error_type": a["error_type"],
                        "score_failures": (a["score"] or {}).get("failures"),
                    }
                    for a in attempts
                    if not (a["score"] or {}).get("passed")
                ],
            }
        )
    cells = []
    for index, cell in enumerate(preflight["cells"]):
        outcomes = []
        for report in reports:
            if index >= len(report["attempts"]):
                outcomes.append("not_attempted")
            else:
                attempt = report["attempts"][index]
                if (attempt["case_id"], attempt["condition"]) != (
                    cell["case_id"],
                    cell["condition"],
                ):
                    raise ValueError("repeat attempt order mismatch")
                outcomes.append("passed" if (attempt["score"] or {}).get("passed") else "failed")
        cells.append(
            {"case_id": cell["case_id"], "condition": cell["condition"], "outcomes": outcomes}
        )
    aggregate_cost = sum(r["gross_cost_usd"] for r in runs)
    return {
        "kind": "three frozen holdout repetitions; stopped runs retained",
        "case_set_sha256": preflight["case_set_sha256"],
        "planned_attempts": len(reports) * preflight["attempts_planned"],
        "attempted": sum(r["attempted"] for r in runs),
        "not_attempted_due_to_stops": sum(r["not_attempted"] for r in runs),
        "full_repetitions": sum(r["attempted"] == r["planned"] for r in runs),
        "gross_cost_usd": aggregate_cost,
        "cost_known_for_every_attempt": all(r["cost_known_for_every_attempt"] for r in reports),
        "user_cumulative_cap_usd": preflight["max_run_usd"],
        "cumulative_cap_respected": aggregate_cost <= preflight["max_run_usd"],
        "runs": runs,
        "cells": cells,
        "interpretation": (
            "Only the first run completed. Later stopped runs show execution and answer "
            "variability; missing cells are not counted as successes or silently excluded. "
            "This does not establish repeatable release performance."
        ),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--reports", type=Path, nargs="+", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = build(args.preflight, args.reports)
    write_json(args.out, result)
    print(
        json.dumps(
            {
                key: result[key]
                for key in ("planned_attempts", "attempted", "full_repetitions", "gross_cost_usd")
            }
        )
    )


if __name__ == "__main__":
    main()
