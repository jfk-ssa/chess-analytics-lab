"""Evaluate the precommitted June M7 gate from retained, key-free live exports."""

import argparse
import hashlib
import json
import math
from pathlib import Path

from chess_analytics.common import write_json


def check(preflight_path: Path, report_paths: list[Path], audit_paths: list[Path]) -> dict:
    if len(report_paths) != 3 or len(audit_paths) != 3:
        raise ValueError("three reports and audits required")
    frozen = preflight_path.read_bytes()
    preflight = json.loads(frozen)
    if preflight["case_file"] != "evals/cases/m7_holdout_v6.json" or preflight["conditions"] != [
        "semantic_context"
    ]:
        raise ValueError("June product-condition preflight required")
    reports = [json.loads(path.read_text()) for path in report_paths]
    audits = [json.loads(path.read_text()) for path in audit_paths]
    digest = hashlib.sha256(frozen).hexdigest()
    planned = preflight["attempts_planned"]
    # Includes all inspected M7 spend and full reservations for unknown-cost attempts.
    prior = 0.086041340
    gates = {}
    gates["frozen_complete_runs"] = all(
        report["preflight_sha256"] == digest
        and report["case_set_sha256"] == preflight["case_set_sha256"]
        and report["planned"] == report["attempted"] == report["completed"] == planned
        and len(report["attempts"]) == planned
        and all(
            (attempt["case_id"], attempt["condition"], attempt["request_sha256"])
            == (cell["case_id"], cell["condition"], cell["request_sha256"])
            and attempt["resolved_model"] == preflight["model"]
            for attempt, cell in zip(report["attempts"], preflight["cells"], strict=True)
        )
        for report in reports
    )
    gates["totals_match_raw_attempts"] = all(
        report["answerable"]
        == {
            "attempted": sum(a["expected_status"] == "answered" for a in report["attempts"]),
            "passed": sum(
                a["expected_status"] == "answered" and a["score"]["passed"]
                for a in report["attempts"]
            ),
        }
        and report["ambiguity_or_unsupported"]
        == {
            "attempted": sum(a["expected_status"] != "answered" for a in report["attempts"]),
            "passed": sum(
                a["expected_status"] != "answered" and a["score"]["passed"]
                for a in report["attempts"]
            ),
        }
        and math.isclose(
            report["known_gross_cost_usd"],
            sum(a["gross_cost_usd"] for a in report["attempts"]),
            rel_tol=0,
            abs_tol=1e-12,
        )
        for report in reports
    )
    gates["answerable_at_least_90_percent_each"] = all(
        report["answerable"]["attempted"] == 41 and report["answerable"]["passed"] >= 37
        for report in reports
    )
    gates["boundary_at_least_90_percent_each"] = all(
        report["ambiguity_or_unsupported"] == {"attempted": 9, "passed": 9} for report in reports
    )
    gates["all_high_severity_correct"] = all(
        report["high_severity"] == {"attempted": 5, "passed": 5} for report in reports
    )
    gates["evidence_and_access_integrity"] = all(
        audit["attempted"] == audit["integrity_passed"] == planned
        and audit["high_severity_cases"] == 5
        and all(not row["issues"] for row in audit["rows"])
        and all(
            (row["case_id"], row["condition"], row["score_passed"])
            == (attempt["case_id"], attempt["condition"], attempt["score"]["passed"])
            for row, attempt in zip(audit["rows"], report["attempts"], strict=True)
        )
        for audit, report in zip(audits, reports, strict=True)
    )
    gates["no_execution_failure_or_unknown_cost"] = all(
        report["cost_known_for_every_attempt"]
        and all(a["status"] == "completed" and a["error"] is None for a in report["attempts"])
        for report in reports
    )
    gross = sum(report["known_gross_cost_usd"] for report in reports)
    gates["cumulative_gross_cap"] = prior + gross <= preflight["max_run_usd"]
    failures = [
        {
            "repeat": repeat,
            "case_id": attempt["case_id"],
            "score_failures": attempt["score"]["failures"],
            "answer_status": attempt["answer_status"],
        }
        for repeat, report in enumerate(reports, 1)
        for attempt in report["attempts"]
        if not attempt["score"]["passed"]
    ]
    return {
        "kind": "M7 June v6 independent-data semantic-context checkpoint",
        "gates": gates,
        "live_gates_passed": all(gates.values()),
        "scored_per_repeat": [
            sum(a["score"]["passed"] for a in report["attempts"]) for report in reports
        ],
        "answerable_per_repeat": [report["answerable"] for report in reports],
        "boundary_per_repeat": [report["ambiguity_or_unsupported"] for report in reports],
        "gross_cost_usd": gross,
        "prior_gross_accounted_usd": prior,
        "cumulative_gross_accounted_usd": prior + gross,
        "approved_cumulative_cap_usd": preflight["max_run_usd"],
        "preflight_sha256": digest,
        "case_set_sha256": preflight["case_set_sha256"],
        "failures": failures,
        "scope": "50 frozen cases on an observed June 1 prefix; product semantic-context mode",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--reports", type=Path, nargs=3, required=True)
    parser.add_argument("--audits", type=Path, nargs=3, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = check(args.preflight, args.reports, args.audits)
    write_json(args.out, result)
    print(json.dumps({"live_gates_passed": result["live_gates_passed"], "gates": result["gates"]}))
    if not result["live_gates_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
