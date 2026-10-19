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

from chess_analytics.analyst.evaluation import score_case_portfolio
from chess_analytics.analyst.live_eval import (
    load_live_cases,
    reference_mismatches,
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
def staged(tmp_path_factory):
    from chess_analytics.analyst.live_eval import stage_live_fixture

    return stage_live_fixture(ROOT, tmp_path_factory.mktemp("live-eval-100"))


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
    assert len(loaded) == 40
    assert loaded_manifest["dataset_id_pinned"] is False
    assert loaded_manifest["replay_plans"] is False
    assert len({case["question"] for case in loaded}) == 40
    answered = [case for case in loaded if case["expected_status"] == "answered"]
    assert len(answered) == 32
    families = {case["template_family"] for case in answered}
    assert len(families) == 8
    for family in families:
        rows = [case for case in loaded if case["template_family"] == family]
        assert len(rows) == 4
    assert sum(case["severity"] == "high" for case in loaded) == 8
    assert "dataset_id" not in CASES.read_text()


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


def test_oracle_plans_score_forty(oracle_scores):
    failed = [row["case_id"] for row in oracle_scores if not row["passed"]]
    assert failed == []
    assert len(oracle_scores) == 40


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
