"""Typed validator for example coach cases, not a frozen case set."""

import math

from chess_analytics.coach.tools import numeric_fields, validate_call


def validate_case(case: dict) -> None:
    """Cases carry expected tool arguments, numeric cells and absolute tolerance."""
    if not isinstance(case, dict) or set(case) != {"id", "question", "expected_calls"}:
        raise ValueError("invalid coach case fields")
    if any(not isinstance(case[k], str) or not case[k].strip() for k in ("id", "question")):
        raise ValueError("case id and question required")
    calls = case["expected_calls"]
    if not isinstance(calls, list) or not 1 <= len(calls) <= 4:
        raise ValueError("case requires one to four expected calls")
    for call in calls:
        if not isinstance(call, dict) or set(call) != {"tool", "args", "values", "tolerance"}:
            raise ValueError("invalid expected call fields")
        validate_call(call["tool"], call["args"])
        tolerance = call["tolerance"]
        if (
            not numeric_fields(call["values"])
            or type(tolerance) not in (int, float)
            or not math.isfinite(tolerance)
            or tolerance < 0
        ):
            raise ValueError("finite expected numeric cells and nonnegative tolerance required")
