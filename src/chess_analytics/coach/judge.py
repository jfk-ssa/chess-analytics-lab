"""Deterministic explanation heuristic; no Luna request or model-quality claim."""

import json
import re
from collections.abc import Iterator
from decimal import ROUND_HALF_EVEN, Decimal, DecimalException, localcontext
from pathlib import Path

from chess_analytics.coach.budget import JUDGE_MODEL_ID

# Reserved for a future combiner; the offline heuristic scores explanation only.
EXACT_WEIGHT = 0.8
EXPLANATION_WEIGHT = 0.2
JUDGE_RUBRIC = """Score explanation only: faithfulness and groundedness against cited
tool evidence. Flag invented evidence, unsupported numbers, and unsupported causal
claims. Do not re-grade tool choice, filters, or numeric reference correctness;
those belong to the separate, majority-weight exact checks."""
_CITATION = re.compile(r"\[([^\[\]]+)\]")
_SIGNS = "−\u2012\u2013\u2014\ufe63\uff0d"
_NUMBER = re.compile(
    rf"(?:(?<!\d)[+\-{_SIGNS}])?(?:\d[\d,.]*|\.\d+)"
    rf"(?:[eE][+\-{_SIGNS}]?\d*)?(?:\s*%)?"
)
_NUMERIC_TOKEN = re.compile(
    r"[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)?(?:\.(?P<fraction>\d*))?"
    r"(?:[eE](?P<exponent>[+-]?\d+))?"
)


def _governed_constants() -> frozenset[Decimal]:
    path = Path(__file__).resolve().parents[3] / "contracts/mean_centipawn_loss.json"
    contract = json.loads(path.read_text())
    return frozenset({Decimal(str(contract["clamp_centipawns"]))})


GOVERNED_NUMERIC_CONSTANTS = _governed_constants()


def _argument_numbers(value: object) -> Iterator[Decimal]:
    if type(value) in (int, float):
        yield Decimal(str(value))
    elif isinstance(value, dict):
        for key, child in value.items():
            yield from _argument_numbers(child)
            if key == "rating_max_exclusive" and type(child) is int:
                yield Decimal(child - 1)
            elif key == "bucket" and isinstance(child, str):
                yield from (Decimal(part) for part in re.findall(r"\d+", child))
    elif isinstance(value, list):
        for child in value:
            yield from _argument_numbers(child)


def _supported_number(token: str, numbers: set[Decimal]) -> bool:
    if len(token) > 128:
        return False
    percent = token.endswith("%")
    token = token.removesuffix("%").strip()
    if not percent:
        token = token.removesuffix(",").removesuffix(".")
    token = token.translate(str.maketrans({sign: "-" for sign in _SIGNS}))
    match = _NUMERIC_TOKEN.fullmatch(token)
    if match is None or abs(int(match["exponent"] or 0)) > 100:
        return False
    precision = len(match["fraction"] or "")
    if precision > 100:
        return False
    try:
        claim = Decimal(token.replace(",", ""))
        quantum = Decimal(1).scaleb(-precision)
        with localcontext() as context:
            context.prec = 512
            for number in numbers:
                try:
                    display = number * (100 if percent else 1)
                    if display.quantize(quantum, rounding=ROUND_HALF_EVEN) == claim:
                        return True
                except DecimalException:
                    continue
    except DecimalException:
        pass
    return False


def score_explanation_offline(explanation: str, evidence: list[dict]) -> dict:
    """Check citations and numeric membership only, not semantic entailment.

    Evidence values support prose numbers iff quantizing to the displayed decimal
    precision (integers: 0) with ROUND_HALF_EVEN equals the claim. Percent claims
    quantize evidence * 100 at the percent's precision; whitespace before % is OK.
    Grouped thousands and Unicode minus signs are accepted; citation digits do
    not count as claims. Tokens over 128 characters, precision over 100, invalid
    grouping, or exponents outside [-100, 100] are unsupported numbers.

    Only cited values and numeric args/filters (including bucket label integers)
    support claims, plus the contract-constant allowlist when citing the governed
    mean_centipawn_loss metric. An integer rating_max_exclusive also supports the
    inclusive display endpoint max - 1; the raw exclusive endpoint remains
    supported. Equal evidence_id payloads dedupe; conflicting duplicate
    evidence_ids raise ValueError.
    Causality and field-to-claim alignment require the later explanation judge.
    """
    payloads: dict[str, dict] = {}
    for item in evidence:
        key = item["evidence_id"]
        if key in payloads and payloads[key] != item:
            raise ValueError(f"conflicting duplicate evidence_id: {key}")
        payloads[key] = item
    cited = set(_CITATION.findall(explanation))
    reasons = []
    if not cited or cited - payloads.keys():
        reasons.append("missing_or_unknown_evidence")
    numbers: set[Decimal] = set()
    for key in cited & payloads.keys():
        numbers.update(_argument_numbers(payloads[key]["values"]))
        args = payloads[key].get("args", {})
        numbers.update(_argument_numbers(args))
        if args.get("metric_id") == "mean_centipawn_loss":
            numbers.update(GOVERNED_NUMERIC_CONSTANTS)
    for token in _NUMBER.findall(_CITATION.sub("", explanation)):
        if not _supported_number(token, numbers):
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
