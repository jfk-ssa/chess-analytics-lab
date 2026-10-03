"""Offline harness validation; fixture plans are not model responses."""

import hashlib
import json
import time
from pathlib import Path

from analyst_m5.core import replay
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
