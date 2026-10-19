"""Score one raw model plan against a frozen live-eval case.

The headline bit is ``score_case_live`` from ``live_eval.py``. That function
already accepts one ``analyze_clock_pressure`` call for a single-bucket
clock question and rejects a trailing coverage call. This module does not
copy that rule and it does not call a model.

Semantic repairs are not applied here. The runner scores
``model_plan_before_semantic_repair`` and reports repair counts beside the
pass bit.
"""

from pathlib import Path

from chess_analytics.analyst.core import execute_plan
from chess_analytics.analyst.live_eval import score_case_live

RUBRIC_VERSION = "live-eval-1.0"
_EVIDENCE_FAILURES = {"dataset_identity", "evidence", "unexpected_evidence"}


def score_live_plan(project: Path, case: dict, plan: dict) -> dict:
    """Execute ``plan`` and score it. An invalid plan is a hallucination miss."""
    answer = None
    error = None
    hallucinated = False
    try:
        answer = execute_plan(project, case["question"], plan, source="fixture_replay")
        bound = {**case, "dataset_id": answer["dataset_id"]}
        scored = score_case_live(bound, answer)
    except (OSError, RuntimeError, TimeoutError, ValueError) as exc:
        hallucinated = True
        error = str(exc)
        scored = {
            "case_id": case["id"],
            "failures": ["plan_hallucination"],
            "passed": False,
            "rubric_version": RUBRIC_VERSION,
        }
    failures = list(scored["failures"])
    passed = bool(scored["passed"]) and not hallucinated
    observed = None if answer is None else answer.get("status")
    expected = case["expected_status"]
    severity = case["severity"]
    return {
        "answer_status": observed,
        "case_id": case["id"],
        "caveats": [] if answer is None else list(answer.get("caveats") or []),
        "dimensions": _dimensions(failures, hallucinated),
        "error": error,
        "failures": failures,
        "high_severity_miss": severity == "high" and not passed,
        "over_abstention": _over_abstention(expected, observed),
        "passed": passed,
        "plan_hallucination": hallucinated,
        "rubric_version": scored.get("rubric_version", RUBRIC_VERSION),
        "severity": severity,
        "unsafe_answer": expected != "answered" and observed == "answered",
    }


def _over_abstention(expected: str, observed: str | None) -> bool:
    return expected == "answered" and observed in {"needs_clarification", "unsupported"}


def _dimensions(failures: list[str], hallucinated: bool) -> dict:
    if hallucinated:
        return {
            "answer_correct": False,
            "boundary": False,
            "evidence_grounding": False,
            "plan_valid": False,
            "tool_choice": False,
        }
    found = set(failures)
    return {
        "answer_correct": "result_values" not in found,
        "boundary": "status" not in found,
        "evidence_grounding": not found & _EVIDENCE_FAILURES,
        "plan_valid": True,
        "tool_choice": "tool_or_filters" not in found,
    }
