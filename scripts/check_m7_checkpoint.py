"""Check the frozen M7 v2 checkpoint gates from key-free, retained live reports."""

import argparse
import hashlib
import json
import math
from pathlib import Path

from chess_analytics.common import write_json


def check(
    preflight_path: Path,
    report_paths: list[Path],
    audit_paths: list[Path],
    prior_gross_accounted_usd: float,
) -> dict:
    if len(report_paths) != 3 or len(audit_paths) != 3:
        raise ValueError("release check requires three reports and three matching audits")
    preflight_bytes = preflight_path.read_bytes()
    preflight = json.loads(preflight_bytes)
    if preflight["kind"] != "m7_typed_planner_holdout_preflight_no_model_calls":
        raise ValueError("M7 frozen preflight required")
    if prior_gross_accounted_usd < 0:
        raise ValueError("prior gross must be nonnegative")
    preflight_hash = hashlib.sha256(preflight_bytes).hexdigest()
    reports = [json.loads(path.read_text()) for path in report_paths]
    audits = [json.loads(path.read_text()) for path in audit_paths]
    planned = preflight["attempts_planned"]
    case_hash = preflight["case_set_sha256"]
    gates = {}
    gates["frozen_inputs_and_complete_repetitions"] = all(
        report["preflight_sha256"] == preflight_hash
        and report["case_set_sha256"] == case_hash
        and report["planned"] == planned
        and report["attempted"] == planned
        and report["completed"] == planned
        and len(report["attempts"]) == planned
        and all(
            (attempt["case_id"], attempt["condition"], attempt["request_sha256"])
            == (cell["case_id"], cell["condition"], cell["request_sha256"])
            and attempt["resolved_model"] == preflight["model"]
            for attempt, cell in zip(report["attempts"], preflight["cells"], strict=True)
        )
        for report in reports
    )
    gates["report_totals_match_attempts"] = all(
        report["answerable"]["attempted"]
        == sum(a["expected_status"] == "answered" for a in report["attempts"])
        and report["answerable"]["passed"]
        == sum(
            a["expected_status"] == "answered" and a["score"]["passed"] for a in report["attempts"]
        )
        and report["ambiguity_or_unsupported"]["attempted"]
        == sum(a["expected_status"] != "answered" for a in report["attempts"])
        and report["ambiguity_or_unsupported"]["passed"]
        == sum(
            a["expected_status"] != "answered" and a["score"]["passed"] for a in report["attempts"]
        )
        and math.isclose(
            report["known_gross_cost_usd"],
            sum(a["gross_cost_usd"] for a in report["attempts"]),
            rel_tol=0,
            abs_tol=1e-12,
        )
        for report in reports
    )
    gates["numerical_answerable_at_least_90_percent_each_repeat"] = all(
        report["answerable"]["attempted"] == 82 and report["answerable"]["passed"] / 82 >= 0.9
        for report in reports
    )
    gates["ambiguity_at_least_90_percent_each_repeat"] = all(
        report["ambiguity_or_unsupported"]["attempted"] == 18
        and report["ambiguity_or_unsupported"]["passed"] / 18 >= 0.9
        for report in reports
    )
    gates["all_high_severity_correct"] = all(
        report["high_severity"] == {"attempted": 10, "passed": 10} for report in reports
    )
    gates["evidence_integrity_and_access_boundary"] = all(
        audit["attempted"] == planned
        and audit["integrity_passed"] == planned
        and audit["high_severity_cases"] == 10
        and all(not row["issues"] for row in audit["rows"])
        and all(
            (row["case_id"], row["condition"], row["score_passed"])
            == (attempt["case_id"], attempt["condition"], attempt["score"]["passed"])
            for row, attempt in zip(audit["rows"], report["attempts"], strict=True)
        )
        for audit, report in zip(audits, reports, strict=True)
    )
    gates["no_unhandled_execution_failure"] = all(
        all(
            attempt["status"] == "completed" and attempt["error"] is None
            for attempt in report["attempts"]
        )
        for report in reports
    )
    gross_cost = sum(report["known_gross_cost_usd"] for report in reports)
    gates["known_cost_within_approved_cap"] = (
        all(report["cost_known_for_every_attempt"] for report in reports)
        and prior_gross_accounted_usd + gross_cost <= preflight["max_run_usd"]
    )
    answerable = {
        "attempted": sum(report["answerable"]["attempted"] for report in reports),
        "passed": sum(report["answerable"]["passed"] for report in reports),
    }
    ambiguity = {
        "attempted": sum(report["ambiguity_or_unsupported"]["attempted"] for report in reports),
        "passed": sum(report["ambiguity_or_unsupported"]["passed"] for report in reports),
    }
    failures = [
        {
            "repeat": repeat,
            "case_id": attempt["case_id"],
            "condition": attempt["condition"],
            "answer_status": attempt["answer_status"],
            "score_failures": attempt["score"]["failures"],
        }
        for repeat, report in enumerate(reports, 1)
        for attempt in report["attempts"]
        if not attempt["score"]["passed"]
    ]
    return {
        "kind": "M7 v2 typed-analyst depth checkpoint check",
        "preflight_sha256": preflight_hash,
        "case_set_sha256": case_hash,
        "model": preflight["model"],
        "gates": gates,
        "live_gates_passed": all(gates.values()),
        "attempted": sum(report["attempted"] for report in reports),
        "passed": sum(
            sum(bool(a["score"]["passed"]) for a in report["attempts"]) for report in reports
        ),
        "answerable": answerable,
        "ambiguity_or_unsupported": ambiguity,
        "gross_cost_usd": gross_cost,
        "prior_gross_accounted_usd": prior_gross_accounted_usd,
        "cumulative_gross_accounted_usd": prior_gross_accounted_usd + gross_cost,
        "approved_cumulative_cap_usd": preflight["max_run_usd"],
        "failures": failures,
        "comparison_scope": "Two typed-planner prompt conditions; no restricted-SQL baseline",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--reports", type=Path, nargs=3, required=True)
    parser.add_argument("--audits", type=Path, nargs=3, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--prior-gross-usd", type=float, required=True)
    args = parser.parse_args()
    result = check(args.preflight, args.reports, args.audits, args.prior_gross_usd)
    write_json(args.out, result)
    print(json.dumps({"live_gates_passed": result["live_gates_passed"], "gates": result["gates"]}))
    if not result["live_gates_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
