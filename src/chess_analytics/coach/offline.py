"""Fixture oracle path: recorded calls, no provider, environment reads, or retries."""

from copy import deepcopy

from chess_analytics.coach.instructions import COACH_INSTRUCTIONS, instructions_sha256
from chess_analytics.coach.schema import validate_case
from chess_analytics.coach.tools import CoachTools


def run_offline(case: dict, tools: CoachTools) -> dict:
    """Use the example case's call plan; all explanation numbers come from tools."""
    validate_case(case)
    plan = [
        {"tool": call["tool"], "args": deepcopy(call["args"])} for call in case["expected_calls"]
    ]
    evidence = [tools.execute(call["tool"], call["args"]) for call in plan]
    lines = ["Synthetic fixture evidence only; cohort associations do not establish causality."]
    for item in evidence:
        cells = ", ".join(f"{key}={value}" for key, value in sorted(item["values"].items()))
        lines.append(f"{item['tool']}: {cells} [{item['evidence_id']}].")
    return {
        "case_id": case["id"],
        "source": "fixture_fake",
        "plan": plan,
        "explanation": " ".join(lines),
        "evidence": evidence,
        "instructions": COACH_INSTRUCTIONS,
        "instructions_sha256": instructions_sha256(),
    }
