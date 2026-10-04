"""Build and validate M7 clock development cases from the independent M3 tally."""

import hashlib
import json
from pathlib import Path

from analyst_m5.core import execute_plan
from analyst_m5.evaluation import score_case_m6_holdout
from chess_analytics.common import write_json

PROJECT = Path(__file__).resolve().parents[1]
BUCKETS = {
    "under_10": "under 10 seconds",
    "10_to_29": "10 through 29 seconds",
    "30_to_59": "30 through 59 seconds",
    "60_plus": "at least 60 seconds",
}


def build(project: Path = PROJECT) -> tuple[list[dict], dict]:
    reference_path = project / "reports/M3-independent-reference.json"
    reference = json.loads(reference_path.read_text())
    dataset = json.loads((project / "reports/M3-analytical-manifest.json").read_text())[
        "analytical_id"
    ]
    cases = []
    for bucket, label in BUCKETS.items():
        row = reference["clock_buckets"][bucket]
        expected = {
            "eligible_moves": row["eligible"],
            "evaluable_moves": row["evaluable"],
            "evaluation_coverage": row["evaluable"] / row["eligible"],
        }
        questions = (
            f"For sampled moves with {label} left, how many had comparable "
            "evaluations, and what fraction is that?",
            f"Report before/after evaluation availability for the {bucket} "
            "clock bucket in the observed sample.",
        )
        for variation, question in enumerate(questions, 1):
            cases.append(
                {
                    "id": f"m7_clock_{bucket}_{variation}",
                    "question": question,
                    "category": "missing_data",
                    "split": "m7_clock_development",
                    "dataset_id": dataset,
                    "expected_status": "answered",
                    "expected_result": expected,
                    "expected_tool": "query_metric",
                    "expected_tool_args": {
                        "metric_id": "evaluation_coverage",
                        "filters": {"bucket": bucket},
                    },
                    "comparison": {"rates_absolute_tolerance": 1e-6},
                    "required_caveats": [
                        "observed_prefix_only",
                        "source_evaluation_selection",
                        "missing_evaluation_not_zero",
                    ],
                    "allowed_interpretations": ["descriptive_observed_prefix"],
                    "reference_file": "reports/M3-independent-reference.json",
                    "reference_key": f"clock_buckets.{bucket}",
                }
            )
    controls = (
        (
            "missing_bucket",
            "What is the evaluation coverage of my sampled moves? "
            "I have not chosen a clock bucket.",
            "needs_clarification",
        ),
        (
            "private_account",
            "Read my private account games and calculate their evaluation coverage.",
            "unsupported",
        ),
        (
            "causal_effect",
            "Did being under 10 seconds cause the centipawn errors in these games?",
            "unsupported",
        ),
        (
            "full_month",
            "Project the evaluation coverage for all August 2026 Lichess games from this prefix.",
            "unsupported",
        ),
    )
    for name, question, status in controls:
        cases.append(
            {
                "id": f"m7_clock_{name}",
                "question": question,
                "category": "ambiguity" if status == "needs_clarification" else "unsupported",
                "split": "m7_clock_development",
                "dataset_id": dataset,
                "expected_status": status,
                "expected_result": None,
                "expected_tool": None,
                "expected_tool_args": None,
                "comparison": {"rates_absolute_tolerance": 1e-6},
                "required_caveats": ["observed_prefix_only"],
                "allowed_interpretations": ["descriptive_observed_prefix"],
                "reference_file": "reports/M3-independent-reference.json",
                "reference_key": "scope and access boundary",
            }
        )
    scores = []
    for case in cases:
        status = case["expected_status"]
        actions = (
            [{"tool": case["expected_tool"], "args": case["expected_tool_args"]}]
            if status == "answered"
            else []
        )
        answer = execute_plan(
            project,
            case["question"],
            {"status": status, "interpretation": "descriptive_observed_prefix", "actions": actions},
            source="offline_oracle",
        )
        scores.append(score_case_m6_holdout(case, answer))
    encoded = json.dumps(cases, sort_keys=True, separators=(",", ":")).encode()
    report = {
        "kind": "M7 offline checked-tool/oracle development validation; no model responses",
        "dataset_id": dataset,
        "reference_sha256": hashlib.sha256(reference_path.read_bytes()).hexdigest(),
        "case_set_sha256": hashlib.sha256(encoded).hexdigest(),
        "cases": len(cases),
        "answerable": sum(c["expected_status"] == "answered" for c in cases),
        "clarification": sum(c["expected_status"] == "needs_clarification" for c in cases),
        "unsupported": sum(c["expected_status"] == "unsupported" for c in cases),
        "oracle_passed": sum(score["passed"] for score in scores),
        "failures": [score for score in scores if not score["passed"]],
    }
    return cases, report


if __name__ == "__main__":
    case_rows, validation = build()
    write_json(PROJECT / "evals/cases/m7_clock_dev.json", case_rows)
    write_json(PROJECT / "reports/M7-clock-dev-offline.json", validation)
    print(json.dumps(validation))
    if validation["oracle_passed"] != validation["cases"]:
        raise SystemExit(1)
