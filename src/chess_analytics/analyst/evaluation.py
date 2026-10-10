"""Offline harness validation; fixture plans are not model responses."""

import hashlib
import json
import math
import time
from pathlib import Path

from chess_analytics.analyst.core import replay
from chess_analytics.common import write_json


def _subset(expected, observed, tolerance=1e-6):
    if isinstance(expected, dict):
        return isinstance(observed, dict) and all(
            key in observed and _subset(value, observed[key], tolerance)
            for key, value in expected.items()
        )
    if isinstance(expected, float):
        return isinstance(observed, (int, float)) and abs(expected - observed) <= tolerance
    return expected == observed


def score_case(case: dict, answer: dict) -> dict:
    failures = []
    if answer.get("status") != case["expected_status"]:
        failures.append("status")
    if answer.get("dataset_id") != case["dataset_id"]:
        failures.append("dataset_identity")
    if case["expected_status"] == "answered":
        observed = answer.get("result")
        for key in case.get("result_path", []):
            observed = observed.get(key) if isinstance(observed, dict) else None
        if not _subset(
            case["expected_result"], observed, case["comparison"]["rates_absolute_tolerance"]
        ):
            failures.append("result_values")
        if not answer.get("evidence_ids") or len(answer["evidence_ids"]) > 4:
            failures.append("evidence")
        if case.get("expected_tool") is not None:
            trace = answer.get("evidence") or []
            if (
                not trace
                or trace[-1].get("tool") != case["expected_tool"]
                or trace[-1].get("args") != case["expected_tool_args"]
            ):
                failures.append("tool_or_filters")
    elif answer.get("evidence_ids"):
        failures.append("unexpected_evidence")
    if not set(case["required_caveats"]) <= set(answer.get("caveats", [])):
        failures.append("caveats")
    if answer.get("interpretation") not in case["allowed_interpretations"]:
        failures.append("interpretation")
    return {
        "case_id": case["id"],
        "category": case["category"],
        "split": case["split"],
        "passed": not failures,
        "failures": failures,
    }


def _strict_subset(expected, observed, tolerance=1e-6):
    """Typed numerical comparison for new portfolio fixtures; historical rubrics stay frozen."""
    if isinstance(expected, dict):
        return isinstance(observed, dict) and all(
            key in observed and _strict_subset(value, observed[key], tolerance)
            for key, value in expected.items()
        )
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        return (
            isinstance(observed, (int, float))
            and not isinstance(observed, bool)
            and math.isfinite(expected)
            and math.isfinite(observed)
            and abs(expected - observed) <= tolerance
        )
    return type(expected) is type(observed) and expected == observed


def score_case_portfolio(case: dict, answer: dict) -> dict:
    """Versioned rubric for new offline checks; does not alter M5–M7 scoring."""
    scored = score_case(case, answer)
    if case["expected_status"] == "answered":
        observed = answer.get("result")
        for key in case.get("result_path", []):
            observed = observed.get(key) if isinstance(observed, dict) else None
        if (
            not _strict_subset(
                case["expected_result"], observed, case["comparison"]["rates_absolute_tolerance"]
            )
            and "result_values" not in scored["failures"]
        ):
            scored["failures"].append("result_values")
    scored["passed"] = not scored["failures"]
    scored["rubric_version"] = "portfolio-1.0"
    return scored


def score_case_m6(case: dict, answer: dict) -> dict:
    """Versioned live rubric: equivalent checked clock tool counts, values still exact."""
    scored = score_case(case, answer)
    expected = case.get("expected_tool_args") or {}
    trace = answer.get("evidence") or []
    equivalent_clock_call = (
        case.get("expected_tool") == "query_metric"
        and expected.get("metric_id") == "clock_pressure_error_proxy"
        and trace
        and trace[-1].get("tool") == "analyze_clock_pressure"
        and trace[-1].get("args") == expected.get("filters")
    )
    if equivalent_clock_call and "tool_or_filters" in scored["failures"]:
        scored["failures"].remove("tool_or_filters")
        scored["passed"] = not scored["failures"]
    scored["rubric_version"] = "m6-2.0"
    return scored


def score_case_m6_holdout(case: dict, answer: dict) -> dict:
    """Holdout rubric: equivalent checked clock views can support either metric."""
    scored = score_case_m6(case, answer)
    expected = case.get("expected_tool_args") or {}
    trace = answer.get("evidence") or []
    if (
        "tool_or_filters" in scored["failures"]
        and expected.get("metric_id") in {"clock_pressure_error_proxy", "evaluation_coverage"}
        and trace
        and trace[-1].get("args") == expected.get("filters")
        and trace[-1].get("tool") == "analyze_clock_pressure"
    ):
        scored["failures"].remove("tool_or_filters")
        scored["passed"] = not scored["failures"]
    scored["rubric_version"] = "m6-2.1"
    return scored


def score_case_m7(case: dict, answer: dict) -> dict:
    """Freeze the M7 rubric before live calls; retain M6 equivalence rules."""
    scored = score_case_m6_holdout(case, answer)
    scored["rubric_version"] = "m7-1.0"
    return scored


def evaluate(project: Path, *, split: str = "both") -> dict:
    if split not in {"dev", "test", "both"}:
        raise ValueError("invalid evaluation split")
    selected = ("dev", "test") if split == "both" else (split,)
    manifest = json.loads((project / "evals/cases/m5_manifest.json").read_text())
    cases = [
        case
        for name in selected
        for case in json.loads((project / f"evals/cases/m5_{name}.json").read_text())
    ]
    all_cases = [
        case
        for name in ("dev", "test")
        for case in json.loads((project / f"evals/cases/m5_{name}.json").read_text())
    ]
    digest = hashlib.sha256(
        json.dumps(sorted(all_cases, key=lambda case: case["id"]), sort_keys=True).encode()
    ).hexdigest()
    if digest != manifest["case_set_sha256"]:
        raise ValueError("case set hash changed")
    outcomes = []
    started = time.monotonic()
    for case in cases:
        try:
            fixture = project / "evals/replay_plans" / f"{case['id']}.json"
            answer = replay(project, case["question"], fixture)
            scored = score_case(case, answer)
            scored["answer"] = answer
        except Exception as exc:  # preserve all case failures, including unexpected tool errors
            scored = {
                "case_id": case["id"],
                "category": case["category"],
                "split": case["split"],
                "passed": False,
                "failures": [f"exception:{type(exc).__name__}:{exc}"],
            }
        outcomes.append(scored)
    category = {}
    for name in sorted({case["category"] for case in cases}):
        rows = [item for item in outcomes if item["category"] == name]
        category[name] = {"passed": sum(item["passed"] for item in rows), "total": len(rows)}
    return {
        "kind": "offline fixture replay and scorer validation; not model accuracy",
        "dataset_id": manifest["dataset_id"],
        "case_set_sha256": digest,
        "split": split,
        "passed": sum(item["passed"] for item in outcomes),
        "total": len(outcomes),
        "category": category,
        "elapsed_seconds": time.monotonic() - started,
        "outcomes": outcomes,
    }


def save(project: Path, split="both") -> dict:
    result = evaluate(project, split=split)
    write_json(project / "reports" / f"M5-{split}-harness.json", result)
    return {
        key: result[key]
        for key in ("kind", "dataset_id", "case_set_sha256", "split", "passed", "total", "category")
    }
