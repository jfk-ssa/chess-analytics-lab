"""Export later M6 development revisions without labeling a stopped run final."""

import argparse
import json
from pathlib import Path

from chess_analytics.common import write_json
from scripts.report_m6_live import build


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--summaries", type=Path, nargs="+", required=True)
    parser.add_argument("--preflights", type=Path, nargs="+", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--user-cap-usd", type=float, required=True)
    args = parser.parse_args()
    source = build(args.project, args.summaries, args.preflights, args.user_cap_usd)
    runs = []
    for item in source["runs"]:
        attempts = item["attempts"]
        answered = [a for a in attempts if a["expected_status"] == "answered"]
        abstention = [a for a in attempts if a["expected_status"] != "answered"]
        runs.append(
            {
                "experiment_id": item["experiment_id"],
                "preflight": item["preflight"],
                "attempted": len(attempts),
                "planned": item["preflight"]["attempts_planned"],
                "completed": sum(a["status"] == "completed" for a in attempts),
                "passed": sum(bool((a["score"] or {}).get("passed")) for a in attempts),
                "answered_passed": sum(bool((a["score"] or {}).get("passed")) for a in answered),
                "answered_attempted": len(answered),
                "abstention_passed": sum(
                    bool((a["score"] or {}).get("passed")) for a in abstention
                ),
                "abstention_attempted": len(abstention),
                "corrected_gross_cost_usd": sum(a["gross_cost_usd"] or 0 for a in attempts),
                "previous_recorded_cost_usd": sum(
                    a["previous_recorded_cost_usd"] or 0 for a in attempts
                ),
                "cost_known_for_every_attempt": all(
                    a["gross_cost_usd"] is not None for a in attempts
                ),
                "failures": [
                    {
                        "case_id": a["case_id"],
                        "condition": a["condition"],
                        "status": a["status"],
                        "error_type": a["error_type"],
                        "score_failures": (a["score"] or {}).get("failures"),
                        "model_response_id": a["model_response_id"],
                    }
                    for a in attempts
                    if not (a["score"] or {}).get("passed")
                ],
            }
        )
    report = {
        "kind": "inspected_m6_development_revisions_not_release_holdout",
        "scorer": "M6 2.0; equivalent checked clock-pressure tool accepted",
        "user_cap_usd_across_these_revisions": args.user_cap_usd,
        "total_corrected_gross_cost_usd": sum(r["corrected_gross_cost_usd"] for r in runs),
        "runs": runs,
    }
    write_json(args.out, report)
    print(
        json.dumps({"runs": len(runs), "gross_cost_usd": report["total_corrected_gross_cost_usd"]})
    )


if __name__ == "__main__":
    main()
