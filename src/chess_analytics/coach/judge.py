"""Deterministic explanation heuristic; no Luna request or model-quality claim."""

import re
from decimal import Decimal

from chess_analytics.coach.budget import JUDGE_MODEL_ID

EXACT_WEIGHT = 0.8
EXPLANATION_WEIGHT = 0.2
JUDGE_RUBRIC = """Score explanation only: faithfulness and groundedness against cited
tool evidence. Flag invented evidence, unsupported numbers, and unsupported causal
claims. Do not re-grade tool choice, filters, or numeric reference correctness;
those belong to the separate, majority-weight exact checks."""
_CITATION = re.compile(r"\[([^\[\]]+)\]")
_NUMBER = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?%?")


def score_explanation_offline(explanation: str, evidence: list[dict]) -> dict:
    """Check citations and numeric membership only, not semantic entailment.

    Percentages normalize to fractions; citation digits do not count as claims.
    Causality and field-to-claim alignment require the later explanation judge.
    """
    payloads = {item["evidence_id"]: item for item in evidence}
    cited = set(_CITATION.findall(explanation))
    reasons = []
    if not cited or cited - payloads.keys():
        reasons.append("missing_or_unknown_evidence")
    numbers = {
        Decimal(str(value))
        for key in cited & payloads.keys()
        for value in payloads[key]["values"].values()
        if value is not None
    }
    for token in _NUMBER.findall(_CITATION.sub("", explanation)):
        value = Decimal(token.rstrip("%")) / (100 if token.endswith("%") else 1)
        if value not in numbers:
            reasons.append("unsupported_number")
            break
    return {
        "model_id": JUDGE_MODEL_ID,
        "source": "offline_heuristic",
        "score": 0.0 if reasons else 1.0,
        "reasons": reasons,
    }


def exact_tool_check(expected: dict, observed: dict) -> bool:
    """Thin fixture check; filters and names are exact, numeric cells use case tolerance."""
    if expected["tool"] != observed["tool"] or expected["args"] != observed["args"]:
        return False
    for key, value in expected["values"].items():
        actual = observed["values"].get(key)
        if key not in observed["values"] or type(actual) is bool:
            return False
        if value is None:
            if actual is not None:
                return False
        elif type(actual) not in (int, float) or not abs(actual - value) <= expected["tolerance"]:
            return False
    return True
