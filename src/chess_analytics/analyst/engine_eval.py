"""Fixture rubric for the engine tools. Historical scorers are not used here.

`engine-1.0` scores a recorded plan against one frozen case. It checks the
harness: status, caveats, evidence binding, and engine-independent result
fields. Stockfish score, mate, depth, selective depth, best move, and principal
variation live in the reference file and are applied by `scripts/check_engine_v1.py`
only when that binary is the one named in the reference.
"""

import hashlib
import json
import math
import re
from pathlib import Path

from chess_analytics.analyst.core import execute_plan
from chess_analytics.analyst.evaluation import _strict_subset

_EVIDENCE_ID = re.compile(r"ev_[0-9a-f]{20}\Z")
_NUMERIC_KEYS = frozenset(
    {
        "white_cp",
        "white_mate",
        "nodes",
        "depth",
        "seldepth",
        "depth_requested",
        "cp_loss_vs_best",
        "games",
        "observed_games",
        "position_games",
        "cohort_games",
        "next_move_games",
        "observed_share",
        "share_of_position_games",
        "frequency",
    }
)


def case_set_digest(cases: list) -> str:
    """Same canonical JSON hash the M5 manifest uses: sort by id, then sort keys."""
    payload = json.dumps(sorted(cases, key=lambda case: case["id"]), sort_keys=True).encode()
    return hashlib.sha256(payload).hexdigest()


def replay_digest(directory: Path) -> str:
    rows = []
    for path in sorted(directory.glob("*.json")):
        rows.append({"file": path.name, "body": json.loads(path.read_text())})
    return hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()


def load_engine_cases(project: Path) -> tuple[dict, list]:
    manifest_path = project / "evals/cases/engine_v1_manifest.json"
    case_path = project / "evals/cases/engine_v1.json"
    manifest = json.loads(manifest_path.read_text())
    cases = json.loads(case_path.read_text())
    if case_set_digest(cases) != manifest["case_set_sha256"]:
        raise ValueError("engine case set hash changed")
    file_hash = hashlib.sha256(case_path.read_bytes()).hexdigest()
    if file_hash != manifest["case_file_sha256"]:
        raise ValueError("engine case file hash changed")
    return manifest, cases


def replay_engine_case(project: Path, case: dict, *, plans: Path | None = None) -> dict:
    """Replay one engine_v1 plan. A tool ValueError becomes a rejected answer."""
    root = plans or project
    path = root / "evals/replay_plans/engine_v1" / f"{case['id']}.json"
    record = json.loads(path.read_text())
    if record.get("question") != case["question"] or set(record) != {"question", "plan", "kind"}:
        raise ValueError("replay fixture question/schema mismatch")
    if record["kind"] != "fixture_plan_no_model_response":
        raise ValueError("unrecognized replay kind")
    plan = record["plan"]
    if not isinstance(plan, dict) or set(plan) != {"status", "interpretation", "actions"}:
        raise ValueError("replay fixture question/schema mismatch")
    try:
        return execute_plan(project, case["question"], plan, source="fixture_replay")
    except ValueError as exc:
        return _rejection(case["question"], str(exc))


def score_case_engine(case: dict, answer: dict) -> dict:
    """Rubric engine-1.0. Does not call score_case or any historical rubric."""
    failures: list[str] = []
    if answer.get("status") != case["expected_status"]:
        failures.append("status")
    pinned = case.get("dataset_id")
    if pinned is not None and answer.get("dataset_id") != pinned:
        failures.append("dataset_identity")
    status = case["expected_status"]
    if status == "answered":
        failures.extend(_answered_failures(case, answer))
        failures.extend(_caveat_failures(case, answer))
        if answer.get("interpretation") not in case["allowed_interpretations"]:
            failures.append("interpretation")
    elif status == "tool_rejected":
        failures.extend(_rejected_failures(case, answer))
    else:
        failures.extend(_refused_failures(answer))
        failures.extend(_caveat_failures(case, answer))
        if answer.get("interpretation") not in case["allowed_interpretations"]:
            failures.append("interpretation")
    return {
        "case_id": case["id"],
        "category": case["category"],
        "split": case.get("split", "engine_v1"),
        "passed": not failures,
        "failures": _unique(failures),
        "rubric_version": "engine-1.0",
    }


def _answered_failures(case: dict, answer: dict) -> list[str]:
    failures = _evidence_failures(case, answer)
    expected = case.get("expected_result")
    if _illegal_numeric_reference(expected):
        failures.append("result_values")
        return failures
    observed = answer.get("result")
    for key in case.get("result_path") or []:
        observed = observed.get(key) if isinstance(observed, dict) else None
    tolerance = case.get("comparison", {}).get("rates_absolute_tolerance", 1e-6)
    if not _engine_subset(expected, observed, tolerance):
        failures.append("result_values")
    return failures


def _evidence_failures(case: dict, answer: dict) -> list[str]:
    ids = answer.get("evidence_ids")
    trace = answer.get("evidence")
    if not isinstance(ids, list) or not ids or len(ids) > 4:
        return ["evidence"]
    if any(not isinstance(item, str) or _EVIDENCE_ID.fullmatch(item) is None for item in ids):
        return ["evidence"]
    if not isinstance(trace, list) or len(trace) != len(ids):
        return ["evidence"]
    failures: list[str] = []
    dataset = answer.get("dataset_id")
    result = answer.get("result")
    if (
        not isinstance(dataset, str)
        or not isinstance(result, dict)
        or result.get("dataset_id") != dataset
    ):
        failures.append("dataset_identity")
    for step, evidence_id in zip(trace, ids, strict=True):
        if not isinstance(step, dict) or not isinstance(dataset, str):
            failures.append("evidence")
            break
        bound = _bound_evidence(dataset, step.get("tool"), step.get("args"), step.get("result"))
        if bound != evidence_id:
            failures.append("evidence")
            break
    last = trace[-1]
    if (
        not isinstance(last, dict)
        or last.get("tool") != case.get("expected_tool")
        or last.get("args") != case.get("expected_tool_args")
    ):
        failures.append("tool_or_filters")
    return failures


def _rejected_failures(case: dict, answer: dict) -> list[str]:
    failures = []
    if answer.get("evidence_ids"):
        failures.append("unexpected_evidence")
    if answer.get("result") is not None:
        failures.append("result_values")
    expected = case.get("expected_error") or ""
    if not expected or expected not in str(answer.get("error", "")):
        failures.append("rejection")
    if answer.get("interpretation") is not None:
        failures.append("interpretation")
    if answer.get("caveats"):
        failures.append("caveats")
    return failures


def _refused_failures(answer: dict) -> list[str]:
    failures = []
    if answer.get("evidence_ids"):
        failures.append("unexpected_evidence")
    if answer.get("result") is not None:
        failures.append("result_values")
    if answer.get("tool_steps") != 0:
        failures.append("tool_or_filters")
    return failures


def _caveat_failures(case: dict, answer: dict) -> list[str]:
    caveats = answer.get("caveats")
    if not isinstance(caveats, list):
        return ["caveats"]
    if not set(case.get("required_caveats") or []) <= set(caveats):
        return ["caveats"]
    if set(case.get("forbidden_caveats") or []) & set(caveats):
        return ["caveats"]
    return []


def _engine_subset(expected, observed, tolerance: float) -> bool:
    """Subset match that walks lists. Numeric leaves use the portfolio rule."""
    if isinstance(expected, dict):
        return isinstance(observed, dict) and all(
            key in observed and _engine_subset(value, observed[key], tolerance)
            for key, value in expected.items()
        )
    if isinstance(expected, list):
        return (
            isinstance(observed, list)
            and len(expected) == len(observed)
            and all(
                _engine_subset(item, other, tolerance)
                for item, other in zip(expected, observed, strict=True)
            )
        )
    return _strict_subset(expected, observed, tolerance)


def _illegal_numeric_reference(value) -> bool:
    """A bool or non-finite value under a score/count key cannot be a reference."""
    if isinstance(value, dict):
        return any(
            (key in _NUMERIC_KEYS and _illegal_number(item)) or _illegal_numeric_reference(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_illegal_numeric_reference(item) for item in value)
    return False


def _illegal_number(item) -> bool:
    if item is None:
        return False
    if isinstance(item, bool) or not isinstance(item, (int, float)):
        return True
    return not math.isfinite(item)


def _bound_evidence(dataset_id: str, tool, args, result) -> str:
    encoded = json.dumps([dataset_id, tool, args, result], sort_keys=True, default=str).encode()
    return "ev_" + hashlib.sha256(encoded).hexdigest()[:20]


def _rejection(question: str, message: str) -> dict:
    return {
        "status": "tool_rejected",
        "question": question,
        "interpretation": None,
        "dataset_id": None,
        "source": "fixture_replay",
        "filters": [],
        "result": None,
        "evidence_ids": [],
        "evidence": [],
        "caveats": [],
        "explanation": message,
        "error": message,
        "tool_steps": 0,
    }


def _unique(items: list[str]) -> list[str]:
    seen: list[str] = []
    for item in items:
        if item not in seen:
            seen.append(item)
    return seen
