"""The 100-game live-eval fixture, its oracle, and the 40-case set.

These tests do not call a model. They check that the generator is byte-stable,
that checked tools match the independent PGN reference, and that an oracle plan
scores 40/40. Mutated inputs must fail the check that would have passed.
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from chess_analytics.analyst.core import execute_plan
from chess_analytics.analyst.evaluation import score_case_portfolio
from chess_analytics.analyst.live_eval import (
    load_live_cases,
    reference_mismatches,
    score_case_live,
    score_oracle_plans,
    verify_live_set,
)
from chess_analytics.ingest.pgn import normalize

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/live_eval_100.pgn"
EXPECTED = ROOT / "tests/fixtures/live_eval_100_expected.json"
CASES = ROOT / "evals/cases/analyst_live_v1.json"
MANIFEST = ROOT / "evals/cases/analyst_live_v1_manifest.json"


def _load(name: str, relative: str):
    path = ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {relative}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _first_record(text: str) -> str:
    start = text.index("[Event ")
    nxt = text.find("\n\n[Event ", start + 1)
    return text[start:] if nxt == -1 else text[start:nxt]


@pytest.fixture(scope="module")
def staged(live_eval_stage):
    return live_eval_stage


@pytest.fixture(scope="module")
def references(staged):
    from chess_analytics.analyst.live_eval import collect_references

    return collect_references(staged)


@pytest.fixture(scope="module")
def oracle_scores(staged):
    return score_oracle_plans(ROOT, staged)


def test_generator_is_byte_identical():
    module = _load("generate_live_eval_100", "scripts/generate_live_eval_100.py")
    rendered = module.render_pgn().encode()
    assert rendered == FIXTURE.read_bytes()
    assert module.render_pgn().encode() == rendered
    assert module.games_are_legal(FIXTURE.read_text(encoding="utf-8")) == 100
    assert b"\r" not in rendered


def test_expected_reference_is_byte_identical():
    module = _load("live_eval_100_expected", "scripts/live_eval_100_expected.py")
    payload = module.references_for(FIXTURE.read_text(encoding="utf-8"))
    encoded = json.dumps(payload, indent=2, sort_keys=True).encode() + b"\n"
    assert encoded == EXPECTED.read_bytes()
    assert payload["hand_counts"]["draws"] == 33
    assert payload["hand_counts"]["sicilian_white_games"] == 7
    assert payload["hand_counts"]["french_white_games"] == 5
    assert payload["hand_counts"]["under_10_errors"] == 25
    assert payload["hand_counts"]["empty_eligible_moves"] == 0


def test_case_set_matches_builder_and_manifest():
    module = _load("build_analyst_live_cases", "scripts/build_analyst_live_cases.py")
    expected = json.loads(EXPECTED.read_text())
    cases = module.build_cases(expected)
    encoded = json.dumps(cases, indent=2, sort_keys=True).encode() + b"\n"
    assert encoded == CASES.read_bytes()
    manifest = module.build_manifest(cases, FIXTURE.read_bytes(), EXPECTED.read_bytes(), encoded)
    manifest_bytes = json.dumps(manifest, indent=2, sort_keys=True).encode() + b"\n"
    assert manifest_bytes == MANIFEST.read_bytes()
    loaded_manifest, loaded = load_live_cases(ROOT)
    assert len(loaded) == 48
    assert loaded_manifest["dataset_id_pinned"] is False
    assert loaded_manifest["replay_plans"] is False
    assert len({case["question"] for case in loaded}) == 48
    answered = [case for case in loaded if case["expected_status"] == "answered"]
    assert len(answered) == 39
    quads = {
        "clock_bucket",
        "clock_compare",
        "clock_empty",
        "compare_openings",
        "coverage",
        "draw_rate",
        "opening_usage",
        "white_score",
    }
    singles = {
        "clock_gap_empty",
        "distractor_causal",
        "distractor_sql",
        "indirect_compare",
        "indirect_opening",
        "indirect_result",
        "negation_fetch",
    }
    for family in quads:
        rows = [case for case in loaded if case["template_family"] == family]
        assert len(rows) == 4
    for family in singles:
        rows = [case for case in loaded if case["template_family"] == family]
        assert len(rows) == 1
    assert sum(case["severity"] == "high" for case in loaded) == 9
    assert "dataset_id" not in CASES.read_text()
    questions = "\n".join(case["question"] for case in loaded)
    leaked = (
        "10_to_29",
        "under_10",
        "30_to_59",
        "outside the metric contracts",
        "opening-usage",
        "dataset coverage",
        "1400 to 1600",
        "empty 10",
    )
    for phrase in leaked:
        assert phrase not in questions
    assert "1400\u20131599" in questions


def test_manifest_hash_rejects_a_changed_digest():
    manifest, cases = load_live_cases(ROOT)
    bad = {**manifest, "case_set_sha256": "0" * 64}
    with pytest.raises(ValueError, match="case set hash changed"):
        verify_live_set(bad, cases, FIXTURE.read_bytes(), EXPECTED.read_bytes(), CASES.read_bytes())


def test_illegal_move_fails_legality_and_import():
    module = _load("generate_live_eval_100", "scripts/generate_live_eval_100.py")
    mutated = FIXTURE.read_text(encoding="utf-8").replace(" cxd4 ", " Ke2 ", 1)
    with pytest.raises(ValueError, match="illegal"):
        module.games_are_legal(mutated)
    status, reason, row = normalize(_first_record(mutated), 1)
    assert status == "quarantine"
    assert reason == "illegal_or_malformed_moves"
    assert row is None


def test_changed_result_fails_the_hand_tally():
    module = _load("live_eval_100_expected", "scripts/live_eval_100_expected.py")
    original = FIXTURE.read_text(encoding="utf-8")
    mutated = original.replace('[Result "1-0"]', '[Result "1/2-1/2"]', 1)
    mutated = mutated.replace(" 1-0\n", " 1/2-1/2\n", 1)
    assert module.draw_count(original) == 33
    assert module.draw_count(mutated) == 34
    module.references_for(original)
    with pytest.raises(ValueError, match="hand tally"):
        module.references_for(mutated)


@pytest.mark.dbt
def test_tools_match_the_independent_oracle(references):
    expected = json.loads(EXPECTED.read_text())
    assert reference_mismatches(references["values"], expected) == []
    assert references["values"]["coverage"]["accepted"] == 100
    assert references["values"]["coverage"]["selected_games"] == 100
    assert references["paths"]["clock.under_10"] == "reviewed_sql"
    assert references["paths"]["clock.10_to_29"] == "reviewed_sql"
    draw_path = references["paths"]["game_draw_rate"]
    if Path(sys.executable).with_name("dbt").is_file():
        assert draw_path == "governed"
        assert references["paths"]["compare_openings"] == "governed"
    else:
        assert draw_path == "reviewed_sql"


def test_mutated_oracle_value_disagrees(references):
    expected = json.loads(EXPECTED.read_text())
    expected["game_draw_rate"]["numerator"] = 34
    mismatches = reference_mismatches(references["values"], expected)
    assert any(item.startswith("game_draw_rate.numerator") for item in mismatches)


def test_oracle_plans_score_every_case(oracle_scores):
    failed = [row["case_id"] for row in oracle_scores if not row["passed"]]
    assert failed == []
    assert len(oracle_scores) == 48


def test_mutated_case_expectation_fails(oracle_scores):
    _manifest, cases = load_live_cases(ROOT)
    case = next(item for item in cases if item["id"] == "usage_sicilian_1")
    scored = next(row for row in oracle_scores if row["case_id"] == "usage_sicilian_1")
    assert scored["passed"]
    mutated = {
        **case,
        "expected_result": {
            **case["expected_result"],
            "numerator": case["expected_result"]["numerator"] + 1,
        },
    }
    again = score_case_portfolio(
        {**mutated, "dataset_id": scored["answer"]["dataset_id"]}, scored["answer"]
    )
    assert again["passed"] is False
    assert "result_values" in again["failures"]


_REFUSAL = ("sql", "fetch", "private", "spending cap", "caused", "centipawn", "best move")
_DRAW_ARGS = {"filters": {}, "metric_id": "game_draw_rate"}
_USAGE_ARGS = {"filters": {"family": "Sicilian Defense"}, "metric_id": "opening_usage"}
_SCORE_ARGS = {
    "filters": {
        "base_seconds": 60,
        "color": "white",
        "family": "Sicilian Defense",
        "increment_seconds": 0,
        "rating_max_exclusive": 1600,
        "rating_min": 1400,
    },
    "metric_id": "opening_player_score",
}
_COMPARE_ARGS = {
    "filters": {
        "base_seconds": 60,
        "color": "white",
        "families": ["Sicilian Defense", "French Defense"],
        "increment_seconds": 0,
        "rating_max_exclusive": 1600,
        "rating_min": 1400,
    }
}
_UNDER_ARGS = {"filters": {"bucket": "under_10"}, "metric_id": "clock_pressure_error_proxy"}
_EMPTY_ARGS = {"filters": {"bucket": "10_to_29"}, "metric_id": "clock_pressure_error_proxy"}
_CLOCK_COMPARE_ARGS = {"first": "under_10", "second": "30_to_59"}
_HARD_MISSES = {
    "clarify_own_line",
    "clock_gap_empty_1",
    "distractor_causal_1",
    "distractor_sql_1",
    "indirect_compare_1",
    "indirect_opening_1",
    "indirect_result_1",
    "negation_fetch_1",
}


def _answered(tool: str, args: dict) -> dict:
    return {
        "actions": [{"args": args, "tool": tool}],
        "interpretation": "descriptive_observed_prefix",
        "status": "answered",
    }


def _keyword_plan(question: str) -> dict:
    """Phrase router from the cold review. It reads the question and nothing else."""
    text = question.lower()
    if any(token in text for token in _REFUSAL):
        status = "unsupported"
        actions: list = []
    elif "which opening should i" in text:
        status = "needs_clarification"
        actions = []
    elif "sicilian" in text and "french" in text:
        status, actions = "answered", _answered("compare_openings", _COMPARE_ARGS)["actions"]
    elif "sicilian" in text and "score" in text:
        status, actions = "answered", _answered("query_metric", _SCORE_ARGS)["actions"]
    elif "sicilian" in text:
        status, actions = "answered", _answered("query_metric", _USAGE_ARGS)["actions"]
    elif "draw" in text:
        status, actions = "answered", _answered("query_metric", _DRAW_ARGS)["actions"]
    elif ("under 10" in text or "under_10" in text) and ("30 to 59" in text or "30_to_59" in text):
        status, actions = (
            "answered",
            _answered("compare_clock_buckets", _CLOCK_COMPARE_ARGS)["actions"],
        )
    elif "10 to 29" in text or "10_to_29" in text:
        status, actions = "answered", _answered("query_metric", _EMPTY_ARGS)["actions"]
    elif "under 10" in text or "under_10" in text:
        status, actions = "answered", _answered("query_metric", _UNDER_ARGS)["actions"]
    elif any(word in text for word in ("coverage", "accepted", "sampled", "how complete")):
        status, actions = "answered", _answered("get_dataset_coverage", {})["actions"]
    else:
        status, actions = "unsupported", []
    return {
        "actions": actions,
        "interpretation": "descriptive_observed_prefix",
        "status": status,
    }


def _score_plan(staged, case: dict, plan: dict, cache: dict) -> bool:
    key = json.dumps(plan, sort_keys=True)
    if key not in cache:
        cache[key] = execute_plan(staged, case["question"], plan, source="fixture_replay")
    answer = cache[key]
    dataset_id = answer["dataset_id"]
    return score_case_live({**case, "dataset_id": dataset_id}, answer)["passed"]


def test_event_label_matches_time_control():
    import io

    import chess.pgn

    text = FIXTURE.read_text(encoding="utf-8")
    counts = {"Blitz": 0, "Bullet": 0, "Rapid": 0}
    handle = io.StringIO(text)
    seen = 0
    while game := chess.pgn.read_game(handle):
        base, increment = (int(part) for part in game.headers["TimeControl"].split("+"))
        estimated = base + 40 * increment
        if estimated < 180:
            speed = "Bullet"
        elif estimated < 480:
            speed = "Blitz"
        else:
            speed = "Rapid"
        assert game.headers["Event"] == f"Rated {speed} synthetic live eval"
        counts[speed] += 1
        seen += 1
    assert seen == 100
    assert counts == {"Blitz": 20, "Bullet": 70, "Rapid": 10}


def test_keyword_router_and_constant_plans(staged):
    _manifest, cases = load_live_cases(ROOT)
    cache: dict = {}
    router_hits = []
    for case in cases:
        if _score_plan(staged, case, _keyword_plan(case["question"]), cache):
            router_hits.append(case["id"])
    missed = {case["id"] for case in cases} - set(router_hits)
    assert len(cases) == 48
    assert len(router_hits) == 40
    assert missed == _HARD_MISSES
    constants = {
        "unsupported": {
            "actions": [],
            "interpretation": "descriptive_observed_prefix",
            "status": "unsupported",
        },
        "needs_clarification": {
            "actions": [],
            "interpretation": "descriptive_observed_prefix",
            "status": "needs_clarification",
        },
        "answered_list_metrics": _answered("list_metrics", {}),
        "answered_draw_rate": _answered("query_metric", _DRAW_ARGS),
    }
    counts = {}
    for name, plan in constants.items():
        counts[name] = sum(_score_plan(staged, case, plan, cache) for case in cases)
    assert counts == {
        "answered_draw_rate": 7,
        "answered_list_metrics": 0,
        "needs_clarification": 2,
        "unsupported": 7,
    }


def test_single_bucket_clock_equivalence(staged):
    _manifest, cases = load_live_cases(ROOT)
    case = next(item for item in cases if item["id"] == "clock_under_10_1")
    pointer = json.loads((staged / "data/analytical-moves-current.json").read_text())
    bound = {**case, "dataset_id": pointer["analytical_id"]}
    specialized = {
        "actions": [{"args": {"bucket": "under_10"}, "tool": "analyze_clock_pressure"}],
        "interpretation": "descriptive_observed_prefix",
        "status": "answered",
    }
    answer = execute_plan(staged, case["question"], specialized, source="fixture_replay")
    portfolio = score_case_portfolio(bound, answer)
    live = score_case_live(bound, answer)
    assert portfolio["passed"] is False
    assert "tool_or_filters" in portfolio["failures"]
    assert live["passed"] is True
    followed = {
        "actions": [
            {"args": {"bucket": "under_10"}, "tool": "analyze_clock_pressure"},
            {"args": {}, "tool": "get_dataset_coverage"},
        ],
        "interpretation": "descriptive_observed_prefix",
        "status": "answered",
    }
    second = execute_plan(staged, case["question"], followed, source="fixture_replay")
    assert score_case_live(bound, second)["passed"] is False
