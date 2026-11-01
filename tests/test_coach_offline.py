"""Synthetic harness checks only; no live, replay-model or corpus accuracy results."""

import ast
import hashlib
import json
import socket
from copy import deepcopy
from decimal import Decimal
from pathlib import Path

import pytest

from chess_analytics.coach import CoachTools, RecordedToolBackend, instructions_sha256, run_offline
from chess_analytics.coach.budget import (
    FIRST_LIVE_COACH_CAP_USD,
    FIRST_LIVE_COACH_MODEL,
    JUDGE_MODEL_ID,
)
from chess_analytics.coach.instructions import COACH_INSTRUCTIONS
from chess_analytics.coach.judge import (
    EXACT_WEIGHT,
    EXPLANATION_WEIGHT,
    GOVERNED_NUMERIC_CONSTANTS,
    exact_tool_check,
    score_explanation_offline,
)
from chess_analytics.coach.schema import validate_case
from chess_analytics.coach.tools import METRIC_IDS

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((ROOT / "tests/fixtures/coach_offline.json").read_text())


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("offline coach attempted network access")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)


def tools():
    return CoachTools(RecordedToolBackend(FIXTURE["recordings"]))


@pytest.mark.parametrize("recording", FIXTURE["recordings"])
def test_recorded_facade(recording):
    facade = tools()
    result = facade.execute(recording["tool"], recording["args"])
    assert result["values"] == recording["result"]["values"]
    assert result["evidence_id"] == recording["result"]["evidence_id"]
    result["values"].clear()
    assert facade.execute(recording["tool"], recording["args"])["values"]
    assert "mean_centipawn_loss" in METRIC_IDS


@pytest.mark.parametrize(
    "name,args",
    [
        ("run_sql", {"sql": "select 1"}),
        ("fetch", {"url": "https://example.com"}),
        ("query_metric", {"metric_id": "invented", "filters": {}}),
        ("query_metric", {"metric_id": "mean_centipawn_loss", "filters": {"sql": "select 1"}}),
        ("query_metric", {"metric_id": "game_draw_rate", "filters": {}, "sql": "select 1"}),
        ("query_metric", {"metric_id": "opening_usage", "filters": {"family": 4}}),
        ("compare_openings", {"filters": {"families": ["Caro-Kann Defense"]}}),
        ("analyze_clock_pressure", {"bucket": "unknown"}),
        ("analyze_clock_pressure", {"bucket": []}),
        ("query_metric", {"metric_id": "mean_centipawn_loss", "filters": "select 1"}),
    ],
)
def test_reject_before_backend(name, args):
    class ForbiddenBackend:
        def execute(self, name, args):
            pytest.fail("invalid call reached backend")

    with pytest.raises(ValueError):
        CoachTools(ForbiddenBackend()).execute(name, args)


@pytest.mark.parametrize("case", FIXTURE["cases"])
def test_fake_coach_and_separate_scores(case):
    validate_case(case)
    answer = run_offline(case, tools())
    assert answer == run_offline(case, tools())
    changed_reference = deepcopy(case)
    changed_reference["expected_calls"][0]["values"] = {"invented": 999}
    assert answer == run_offline(changed_reference, tools())
    assert answer["instructions_sha256"] == instructions_sha256(answer["instructions"])
    for expected, observed in zip(case["expected_calls"], answer["evidence"], strict=True):
        assert exact_tool_check(expected, observed)
        assert not exact_tool_check({**expected, "tool": "wrong"}, observed)
        assert not exact_tool_check({**expected, "args": {}}, observed)
        wrong = {**observed, "values": dict.fromkeys(expected["values"], 999)}
        assert not exact_tool_check(expected, wrong)
    score = score_explanation_offline(answer["explanation"], answer["evidence"])
    assert score["score"] == 1 and score["model_id"] == "gpt-6-luna"
    assert (
        score_explanation_offline(answer["explanation"] + " Loss is 999.", answer["evidence"])[
            "score"
        ]
        == 0
    )
    for explanation in ("No evidence.", "35% [invented_1]", "999 [caro_score_1]"):
        assert score_explanation_offline(explanation, answer["evidence"])["score"] == 0


@pytest.mark.parametrize(
    "patch",
    [
        {"id": ""},
        {"question": 3},
        {"expected_calls": []},
        {"unexpected": True},
        {"expected_calls": [{"tool": "query_metric"}]},
    ],
)
def test_malformed_case(patch):
    with pytest.raises(ValueError):
        validate_case({**FIXTURE["cases"][0], **patch})


@pytest.mark.parametrize(
    "result",
    [
        {"values": {"value": 0.35}},
        {"evidence_id": "bad id", "values": {"value": 0.35}},
        {"evidence_id": "caro_1", "values": {"value": True}},
        {"evidence_id": "caro_1", "values": {"value": float("nan")}},
    ],
)
def test_invalid_payload(result):
    recording = {**FIXTURE["recordings"][0], "result": result}
    with pytest.raises(ValueError, match="payload requires"):
        CoachTools(RecordedToolBackend([recording])).execute(recording["tool"], recording["args"])


def test_tolerance_null_and_recording_boundaries():
    evidence = [tools().execute("query_metric", FIXTURE["recordings"][0]["args"])]
    assert score_explanation_offline("Score is 35% [caro_score_1]", evidence)["score"] == 1
    assert score_explanation_offline("Loss is 42.5 [caro_score_1]", evidence)["score"] == 0
    expected = {"tool": "query_metric", "args": {}, "values": {"value": None}, "tolerance": 0}
    assert exact_tool_check(expected, {**expected})
    assert not exact_tool_check(expected, {**expected, "values": {}})
    expected.update(values={"value": 0.35}, tolerance=0.000001)
    assert exact_tool_check(expected, {**expected, "values": {"value": 0.3500001}})
    assert not exact_tool_check(expected, {**expected, "values": {"value": True}})
    case = deepcopy(FIXTURE["cases"][0])
    for tolerance in (-1, True, float("nan"), float("inf")):
        case["expected_calls"][0]["tolerance"] = tolerance
        with pytest.raises(ValueError):
            validate_case(case)
    with pytest.raises(ValueError, match="no recorded"):
        tools().execute("analyze_clock_pressure", {"bucket": "60_plus"})
    with pytest.raises(ValueError, match="duplicate"):
        RecordedToolBackend([FIXTURE["recordings"][0]] * 2)


@pytest.mark.parametrize(
    "claim,value,supported",
    [
        ("There are 1,000 games", 1, False),
        ("There are 1,000 games", 1000, True),
        ("−20 games", 20, False),
        ("−20 games", -20, True),
        ("-20 games", -20, True),
        ("+20 games", 20, True),
        ("–20 games", -20, True),
        ("41.3", 41.27, True),
        ("41.3.", 41.27, True),
        ("41.3,", 41.27, True),
        ("41.27", 41.27, True),
        ("41.2", 41.27, False),
        ("41.270", 41.27, True),
        ("41.271", 41.27, False),
        ("2.4", 2.45, True),
        ("2.5", 2.45, False),
        ("2.6", 2.55, True),
        ("52%", 0.5217, True),
        ("52 %", 0.5217, True),
        ("52.17%", 0.5217, True),
        ("52.17 %", 0.5217, True),
        ("52.18%", 0.5217, False),
        ("52%", 0.525, True),
        ("53%", 0.525, False),
        ("20", 21, False),
        ("1,234,567.8", 1234567.75, True),
        ("1e2", 100, True),
    ],
)
def test_explanation_numeric_presentation(claim, value, supported):
    evidence = [{"evidence_id": "e1", "values": {"value": value, "losses": 0}}]
    result = score_explanation_offline(f"{claim} [e1]", evidence)
    assert result["score"] == float(supported)
    assert result["reasons"] == ([] if supported else ["unsupported_number"])


@pytest.mark.parametrize(
    "claim",
    [
        "1,00",
        "1,,000",
        "1,000,00",
        "1,000.2,5",
        "1,000,,",
        "1,00%",
        "1,000,%",
        "1.0.0",
        "1e+",
        "1e1000000",
        "1e-1000000",
        "−1e1000000",
        "−1e-1000000",
        "1e" + "9" * 128,
        "1" * 129,
        "0." + "0" * 101,
    ],
)
def test_invalid_or_extreme_numeric_claims_fail_closed(claim):
    evidence = [{"evidence_id": "e1", "values": {"one": 1, "zero": 0, "games": 1000}}]
    result = score_explanation_offline(f"Rate {claim} [e1]", evidence)
    assert result["score"] == 0
    assert result["reasons"] == ["unsupported_number"]


def test_cited_cohort_and_contract_constants():
    facade = tools()
    evidence = [facade.execute(item["tool"], item["args"]) for item in FIXTURE["recordings"][:2]]
    for claim in (
        "Black scored 35% at ratings 1400–1599, 300+0 [caro_score_1]",
        "Rating maximum exclusive 1600 [caro_score_1]",
        "Clamp 1000cp [accuracy_1]",
        "Clamp 1,000 [accuracy_1]",
    ):
        assert score_explanation_offline(claim, evidence)["score"] == 1
    for claim in (
        "In 2024 Black scored 35% [caro_score_1]",
        "Ratings 1400–1598 [caro_score_1]",
        "Rating 1400 [accuracy_1]",
        "Clamp 1001cp [accuracy_1]",
        "There are 1000 games [caro_score_1]",
    ):
        assert score_explanation_offline(claim, evidence)["reasons"] == ["unsupported_number"]
    contract = json.loads((ROOT / "contracts/mean_centipawn_loss.json").read_text())
    assert frozenset({Decimal(contract["clamp_centipawns"])}) == GOVERNED_NUMERIC_CONSTANTS


@pytest.mark.parametrize(
    "args,claim",
    [
        ({"bucket": "under_10"}, "Under 10 seconds"),
        ({"filters": {"bucket": "10_to_29"}}, "10–29 seconds"),
        ({"filters": {"bucket": "30_to_59"}}, "30–59 seconds"),
        ({"filters": {"bucket": "60_plus"}}, "60 seconds or more"),
        ({"filters": {"nested": [{"fraction": 0.125}]}}, "12.5 %"),
        ({"filters": {"rating_max_exclusive": 1600}}, "1599"),
    ],
)
def test_numbers_from_nested_cited_arguments(args, claim):
    evidence = [{"evidence_id": "e1", "values": {"value": None}, "args": args}]
    assert score_explanation_offline(f"{claim} [e1]", evidence)["score"] == 1


def test_noninteger_half_open_bound_does_not_support_max_minus_one():
    evidence = [
        {"evidence_id": "e1", "values": {"value": None}, "args": {"rating_max_exclusive": 1600.0}}
    ]
    assert score_explanation_offline("1599 [e1]", evidence)["reasons"] == ["unsupported_number"]


@pytest.mark.parametrize("field", ["values", "args"])
@pytest.mark.parametrize("reverse", [False, True])
def test_conflicting_evidence_ids_raise(field, reverse):
    first = {"evidence_id": "e1", "values": {"value": 0.35}, "args": {"filters": {}}}
    second = deepcopy(first)
    second[field] = {"value": 0.5}
    evidence = [first, second]
    with pytest.raises(ValueError, match="duplicate evidence_id"):
        score_explanation_offline("Score 35% [e1]", evidence[::-1] if reverse else evidence)


def test_equal_evidence_ids_dedupe():
    first = {"evidence_id": "e1", "values": {"value": 0.35}, "args": {"filters": {}}}
    assert score_explanation_offline("Score 35% [e1]", [first, deepcopy(first)])["score"] == 1


@pytest.mark.parametrize(
    "name,filters",
    [
        ("compare_openings", {"families": ["Caro-Kann Defense", "Caro-Kann Defense"]}),
        ("compare_openings", {"families": [" Caro-Kann Defense", "French Defense"]}),
        ("compare_openings", {"families": ["Caro-Kann Defense", "French Defense "]}),
        ("query_metric", {"family": " Caro-Kann Defense "}),
        ("query_metric", {"family": ""}),
        ("query_metric", {"family": " "}),
        ("query_metric", {"family": "f" * 81}),
    ],
)
def test_invalid_families_rejected_before_backend(name, filters):
    class ForbiddenBackend:
        def execute(self, name, args):
            pytest.fail("invalid family reached backend")

    if name == "compare_openings":
        cohort = deepcopy(FIXTURE["recordings"][2]["args"]["filters"])
        args = {"filters": {**cohort, **filters}}
    else:
        args = {"metric_id": "opening_usage", "filters": filters}
    with pytest.raises(ValueError, match="opening famil"):
        CoachTools(ForbiddenBackend()).execute(name, args)


def test_config_hash_and_import_boundary():
    assert (FIRST_LIVE_COACH_MODEL, FIRST_LIVE_COACH_CAP_USD, JUDGE_MODEL_ID) == (
        "grok-4.7",
        5.0,
        "gpt-6-luna",
    )
    assert EXACT_WEIGHT > 0.5 and EXACT_WEIGHT + EXPLANATION_WEIGHT == 1
    assert instructions_sha256() == instructions_sha256()
    assert instructions_sha256() == hashlib.sha256(COACH_INSTRUCTIONS.encode()).hexdigest()
    assert instructions_sha256(COACH_INSTRUCTIONS + "\n") != instructions_sha256()
    for path in (ROOT / "src/chess_analytics/coach").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            assert all(
                name.split(".")[0] not in {"urllib", "httpx", "requests", "socket", "os"}
                for name in names
            )
            assert all(not name.startswith("chess_analytics.analyst") for name in names)
