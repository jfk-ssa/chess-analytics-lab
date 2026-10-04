"""Small bounded state machine: plan -> checked tools -> evidence-backed answer."""

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from analyst_m5.tools import CheckedTools

STATUSES = {"answered", "needs_clarification", "unsupported"}
MAX_STEPS = 4
MAX_TOOL_SECONDS = 30
MAX_WORKER_OUTPUT_BYTES = 1_000_000


def run_killable_tool(project: Path, name: str, args: dict, timeout_seconds=MAX_TOOL_SECONDS):
    """Kill a checked tool process if its wall-clock deadline expires."""
    request = json.dumps({"project": str(project.resolve()), "tool": name, "args": args})
    if len(request.encode()) > 100_000:
        raise ValueError("tool request too large")
    clean_env = {"PATH": os.defpath, "PYTHONNOUSERSITE": "1"}
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "analyst_m5.tool_worker"],
            input=request,
            text=True,
            capture_output=True,
            cwd=project,
            env=clean_env,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError("tool worker killed after 30-second deadline") from exc
    if len(completed.stdout.encode()) > MAX_WORKER_OUTPUT_BYTES:
        raise ValueError("tool worker returned too much data")
    try:
        message = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("tool worker returned invalid output") from exc
    if completed.returncode or not message.get("ok"):
        raise ValueError(f"checked tool failed: {message.get('error_type', 'worker_error')}")
    return message["dataset_id"], message["result"]


def _evidence_id(dataset_id: str, tool: str, args: dict, result: dict) -> str:
    encoded = json.dumps([dataset_id, tool, args, result], sort_keys=True, default=str).encode()
    return "ev_" + hashlib.sha256(encoded).hexdigest()[:20]


def execute_plan(project: Path, question: str, plan: dict, *, source: str = "typed") -> dict:
    started = time.monotonic()
    tools = CheckedTools(project)
    if not isinstance(question, str) or not 1 <= len(question) <= 2000:
        raise ValueError("question must be 1–2000 characters")
    if not isinstance(plan, dict) or set(plan) - {"status", "interpretation", "actions"}:
        raise ValueError("invalid plan")
    status = plan.get("status")
    if status not in STATUSES:
        raise ValueError("invalid answer status")
    actions = plan.get("actions", [])
    if not isinstance(actions, list) or len(actions) > MAX_STEPS:
        raise ValueError("tool-step limit exceeded")
    if status != "answered" and actions:
        raise ValueError("non-answer plan cannot execute tools")
    if status == "answered" and not actions:
        raise ValueError("answer requires evidence")
    trace = []
    for step in actions:
        if not isinstance(step, dict) or set(step) != {"tool", "args"}:
            raise ValueError("invalid tool step")
        if source == "live_provider":
            worker_dataset, result = run_killable_tool(project, step["tool"], step["args"])
            if worker_dataset != tools.dataset_id:
                raise ValueError("worker dataset mismatch")
        else:
            tool_started = time.monotonic()
            result = tools.execute(step["tool"], step["args"])
            if time.monotonic() - tool_started > MAX_TOOL_SECONDS:
                raise TimeoutError("tool exceeded 30-second response limit")
        if (
            result.get("analytical_id", result.get("dataset_id", tools.dataset_id))
            != tools.dataset_id
        ):
            raise ValueError("evidence dataset mismatch")
        trace.append(
            {
                "tool": step["tool"],
                "args": step["args"],
                "result": result,
                "evidence_id": _evidence_id(tools.dataset_id, step["tool"], step["args"], result),
            }
        )
    interpretation = plan.get("interpretation") or "descriptive_observed_prefix"
    caveats = ["observed_prefix_only"]
    if any(
        step["tool"] == "compare_openings"
        or step["args"].get("metric_id") in {"opening_player_score", "opening_adjusted_score"}
        for step in actions
    ):
        caveats += ["association_not_causation", "score_not_win_rate"]
    if any(step["args"].get("metric_id") == "opening_usage" for step in actions):
        caveats.append("source_tags_only")
    if any(step["args"].get("filters", {}).get("color") == "white" for step in actions):
        caveats.append("white_perspective")
    if any(
        step["tool"] in {"analyze_clock_pressure", "compare_clock_buckets"}
        or step["args"].get("metric_id") in {"clock_pressure_error_proxy", "evaluation_coverage"}
        for step in actions
    ):
        caveats += [
            "source_evaluation_selection",
            "exploratory_proxy",
            "missing_evaluation_not_zero",
        ]
    if status == "needs_clarification":
        explanation = "Specify the population, outcome, color, rating range, and time control."
    elif status == "unsupported":
        explanation = "This bounded observational dataset cannot establish that claim."
    else:
        explanation = (
            "Result computed by reviewed metric tools; see evidence values and denominators."
        )
    return {
        "status": status,
        "question": question,
        "interpretation": interpretation,
        "dataset_id": tools.dataset_id,
        "source": source,
        "filters": [item["args"] for item in trace],
        "result": trace[-1]["result"] if trace else None,
        "evidence_ids": [item["evidence_id"] for item in trace],
        "evidence": trace,
        "caveats": sorted(set(caveats)),
        "explanation": explanation,
        "tool_steps": len(trace),
        "elapsed_seconds": time.monotonic() - started,
    }


def replay(project: Path, question: str, fixture: Path) -> dict:
    """Replay a recorded plan, never an expected reference answer."""
    record = json.loads(fixture.read_text())
    if record.get("question") != question or set(record) != {"question", "plan", "kind"}:
        raise ValueError("replay fixture question/schema mismatch")
    if record["kind"] != "fixture_plan_no_model_response":
        raise ValueError("unrecognized replay kind")
    return execute_plan(project, question, record["plan"], source="fixture_replay")
