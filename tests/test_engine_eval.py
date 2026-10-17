"""Offline engine_v1 scorer, manifest, and replay checks. No download and no live model."""

import hashlib
import importlib.util
import json
import math
import shutil
from pathlib import Path

import chess
import pytest

from chess_analytics.analyst.engine import compare_candidate_moves, evaluate_position
from chess_analytics.analyst.engine_eval import (
    case_set_digest,
    load_engine_cases,
    replay_digest,
    replay_engine_case,
    score_case_engine,
)
from chess_analytics.analyst.evaluation import score_case, score_case_portfolio
from chess_analytics.analyst.positions import position_id, position_key
from chess_analytics.common import digest, write_json

ROOT = Path(__file__).resolve().parents[1]
FAKE = ROOT / "tests/fixtures/engines/fake_uci.py"
START = chess.STARTING_FEN
BINARY = "00628bd9c9855c1b7ff93d7f8d51b413586cdc6336fe637f9a14a61531a05aca"
ENGINE_CAVEATS = [
    "engine_eval_depth_limited",
    "engine_not_ground_truth",
    "observed_prefix_only",
]
SEVEN = ["a2a3", "a2a4", "b1a3", "b1c3", "b2b3", "b2b4", "c2c3"]


def _script(name: str):
    path = ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py"), path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _evidence(dataset: str, tool: str, args: dict, result: dict) -> str:
    encoded = json.dumps([dataset, tool, args, result], sort_keys=True, default=str).encode()
    return "ev_" + hashlib.sha256(encoded).hexdigest()[:20]


def _case(**updates) -> dict:
    body = {
        "id": "synthetic",
        "category": "evaluate_position",
        "split": "engine_v1",
        "dataset_id": None,
        "expected_status": "answered",
        "expected_tool": "evaluate_position",
        "expected_tool_args": {"depth": 12, "fen": START},
        "expected_result": {"depth_requested": 12, "white_cp": 40},
        "comparison": {"rates_absolute_tolerance": 1e-6},
        "required_caveats": ENGINE_CAVEATS,
        "forbidden_caveats": [],
        "allowed_interpretations": ["descriptive_observed_prefix"],
    }
    body.update(updates)
    return body


def _answer(case: dict, result: dict, **updates) -> dict:
    dataset = "a" * 24
    body = {"dataset_id": dataset, **result}
    tool = case["expected_tool"]
    args = case["expected_tool_args"]
    evidence = _evidence(dataset, tool, args, body)
    answer = {
        "status": "answered",
        "dataset_id": dataset,
        "result": body,
        "evidence_ids": [evidence],
        "evidence": [{"tool": tool, "args": args, "result": body}],
        "caveats": list(ENGINE_CAVEATS),
        "interpretation": "descriptive_observed_prefix",
        "tool_steps": 1,
    }
    answer.update(updates)
    return answer


def _write_engine(project: Path, binary: Path) -> None:
    write_json(
        project / "config/engine.json",
        {
            "version": "1",
            "binary_path": str(binary.resolve()),
            "binary_sha256": digest(binary),
        },
    )


def _write_opening(project: Path, directory: Path) -> None:
    write_json(
        project / "config/opening-visits.json",
        {
            "version": "1",
            "kind": "visit_shards",
            "snapshot_dir": str(directory.resolve()),
            "manifest_sha256": digest(directory / "manifest.json"),
        },
    )


def _clear_configs(project: Path) -> None:
    for name in ("config/engine.json", "config/opening-visits.json"):
        (project / name).unlink(missing_ok=True)


def _assert_replay(project: Path, case: dict) -> None:
    answer = replay_engine_case(project, case, plans=ROOT)
    scored = score_case_engine(case, answer)
    assert scored["passed"], (
        case["id"],
        scored["failures"],
        answer.get("status"),
        answer.get("error"),
    )


def test_engine_rubric_accepts_a_bound_answer_and_walks_lists():
    case = _case()
    assert score_case_engine(case, _answer(case, {"depth_requested": 12, "white_cp": 40}))["passed"]
    listed = _case(
        expected_tool="compare_candidate_moves",
        expected_tool_args={
            "candidates": ["e2e4"],
            "cohort": "elite_reference",
            "depth": 12,
            "fen": START,
        },
        expected_result={"candidates": [{"observed_games": 0, "uci": "e2e4"}]},
    )
    observed = {"candidates": [{"observed_games": 0, "uci": "e2e4", "nodes": 17}]}
    assert score_case_engine(listed, _answer(listed, observed))["passed"]
    short = score_case_engine(listed, _answer(listed, {"candidates": []}))
    assert short["failures"] == ["result_values"]


def test_engine_rubric_rejects_boolean_and_nonfinite_numbers():
    case = _case()
    for value in (True, math.nan, math.inf):
        scored = score_case_engine(case, _answer(case, {"depth_requested": 12, "white_cp": value}))
        assert scored["passed"] is False
        assert "result_values" in scored["failures"]
    for value in (True, math.nan, math.inf):
        bad = _case(expected_result={"white_cp": value})
        scored = score_case_engine(bad, _answer(bad, {"white_cp": value}))
        assert scored["passed"] is False
        assert scored["failures"] == ["result_values"]
        assert scored["rubric_version"] == "engine-1.0"


def test_engine_rubric_checks_evidence_caveats_and_boundary_status():
    case = _case()
    answer = _answer(case, {"depth_requested": 12, "white_cp": 40})
    answer["evidence_ids"] = ["ev_not_a_real_binding00"]
    assert "evidence" in score_case_engine(case, answer)["failures"]
    shifted = _answer(case, {"depth_requested": 12, "white_cp": 40})
    shifted["evidence"][0]["args"] = {"depth": 1, "fen": START}
    assert "evidence" in score_case_engine(case, shifted)["failures"]
    missing = _answer(
        case, {"depth_requested": 12, "white_cp": 40}, caveats=["observed_prefix_only"]
    )
    assert "caveats" in score_case_engine(case, missing)["failures"]
    continuation = _case(
        category="position_continuations",
        expected_tool="position_continuations",
        expected_tool_args={"cohort": "elite_reference", "fen": START},
        expected_result={"available": False},
        required_caveats=["observed_prefix_only"],
        forbidden_caveats=["engine_eval_depth_limited", "engine_not_ground_truth"],
    )
    forbidden = _answer(continuation, {"available": False})
    assert "caveats" in score_case_engine(continuation, forbidden)["failures"]
    rejected = _case(
        expected_status="tool_rejected",
        expected_error="invalid fen",
        expected_result=None,
        expected_tool="evaluate_position",
    )
    refusal = {
        "status": "tool_rejected",
        "dataset_id": None,
        "result": None,
        "evidence_ids": [],
        "evidence": [],
        "caveats": [],
        "interpretation": None,
        "error": "invalid fen",
        "tool_steps": 0,
    }
    assert score_case_engine(rejected, refusal)["passed"]
    refusal["error"] = "engine failed"
    assert "rejection" in score_case_engine(rejected, refusal)["failures"]
    unsupported = _case(
        expected_status="unsupported",
        expected_result=None,
        expected_tool=None,
        expected_tool_args=None,
        required_caveats=["observed_prefix_only"],
        forbidden_caveats=["engine_eval_depth_limited", "engine_not_ground_truth"],
    )
    claim = {
        "status": "unsupported",
        "dataset_id": None,
        "result": None,
        "evidence_ids": [],
        "caveats": ["observed_prefix_only"],
        "interpretation": "descriptive_observed_prefix",
        "tool_steps": 0,
    }
    assert score_case_engine(unsupported, claim)["passed"]


def test_historical_scorers_and_prompt_do_not_gain_engine_v1():
    historical = {
        "id": "historical",
        "category": "boundary",
        "split": "test",
        "dataset_id": None,
        "expected_status": "unsupported",
        "required_caveats": [],
        "allowed_interpretations": ["descriptive_observed_prefix"],
    }
    answer = {
        "status": "unsupported",
        "dataset_id": None,
        "caveats": [],
        "interpretation": "descriptive_observed_prefix",
    }
    assert "rubric_version" not in score_case(historical, answer)
    assert score_case_portfolio(historical, answer)["rubric_version"] == "portfolio-1.0"
    for name in (
        "src/chess_analytics/analyst/evaluation.py",
        "src/chess_analytics/analyst/experiment.py",
        "src/chess_analytics/analyst/provider.py",
        "src/chess_analytics/analyst/preflight.py",
    ):
        text = (ROOT / name).read_text()
        assert "engine_eval" not in text
        assert "engine-1.0" not in text
    provider = (ROOT / "src/chess_analytics/analyst/provider.py").read_text()
    for tool in ("evaluate_position", "position_continuations", "compare_candidate_moves"):
        assert tool not in provider
    reference = (ROOT / "scripts/reference_engine_v1.py").read_text()
    assert "chess_analytics.analyst" not in reference


def test_manifest_binds_the_frozen_files_and_replay_schema():
    manifest, cases = load_engine_cases(ROOT)
    assert manifest["cases"] == 18
    assert manifest["answerable"] == 9
    assert manifest["boundary"] == 9
    assert manifest["categories"] == {
        "boundary": 9,
        "compare_candidate_moves": 2,
        "evaluate_position": 4,
        "position_continuations": 2,
        "source_crosscheck": 1,
    }
    assert manifest["rubric_version"] == "engine-1.0"
    assert case_set_digest(cases) == manifest["case_set_sha256"]
    assert digest(ROOT / "evals/cases/engine_v1.json") == manifest["case_file_sha256"]
    assert digest(ROOT / "evals/references/engine_v1.json") == manifest["reference_sha256"]
    assert digest(ROOT / "evals/fixtures/engine_v1/rows.json") == manifest["rows_sha256"]
    plans = ROOT / "evals/replay_plans/engine_v1"
    assert replay_digest(plans) == manifest["replay_plans_sha256"]
    ids = {case["id"] for case in cases}
    assert ids == {path.stem for path in plans.glob("*.json")}
    reference = json.loads((ROOT / "evals/references/engine_v1.json").read_text())
    assert reference["case_set_sha256"] == manifest["case_set_sha256"]
    for case in cases:
        record = json.loads((plans / f"{case['id']}.json").read_text())
        assert record["kind"] == "fixture_plan_no_model_response"
        assert set(record) == {"kind", "plan", "question"}
        assert record["question"] == case["question"]
        assert set(record["plan"]) == {"actions", "interpretation", "status"}


def test_load_rejects_a_changed_case_file(tmp_path):
    destination = tmp_path / "evals" / "cases"
    destination.mkdir(parents=True)
    shutil.copy(
        ROOT / "evals/cases/engine_v1_manifest.json", destination / "engine_v1_manifest.json"
    )
    source = (ROOT / "evals/cases/engine_v1.json").read_text()
    (destination / "engine_v1.json").write_text(
        source.replace("starting position", "starting position ", 1)
    )
    with pytest.raises(ValueError, match="hash changed"):
        load_engine_cases(tmp_path)


def test_frozen_reference_records_one_stockfish_16_measurement():
    reference = json.loads((ROOT / "evals/references/engine_v1.json").read_text())
    engine = reference["engine"]
    assert engine["name"] == "Stockfish 16"
    assert engine["binary_sha256"] == BINARY
    assert engine["binary_bytes"] == 40_418_008
    assert engine["binary_path_recorded"] is False
    assert engine["launch"].startswith("direct python-chess")
    settings = engine["settings"]
    assert settings["threads"] == 1
    assert settings["hash_mb"] == 16
    assert settings["depth"] == 12
    assert settings["movetime"] is None
    assert reference["comparison"]["nodes"] == "recorded_not_gated"
    assert reference["comparison"]["binary_mismatch"].startswith("skip")
    for deltas in reference["repeat"]["node_deltas"].values():
        assert set(deltas) == {0}
    start = reference["cases"]["engine_eval_start"]["search"]
    assert start["white_cp"] == 40
    assert start["nodes"] == 35836
    assert start["pv"][:6] == ["e2e4", "e7e5", "g1f3", "g8f6", "d2d4", "f6e4"]
    kiwipete = reference["cases"]["engine_eval_kiwipete"]["search"]
    assert kiwipete["depth"] == 12
    assert kiwipete["white_cp"] == -122
    assert kiwipete["nodes"] == 28166
    mate = reference["cases"]["engine_eval_mate_in_one"]["search"]
    assert mate["white_cp"] is None
    assert mate["white_mate"] == 1
    cross = reference["cases"]["engine_crosscheck_source_eval"]
    assert cross["source_white_cp"] == -250
    assert cross["search"]["white_cp"] == 34
    assert cross["white_cp_minus_source"] == 284
    assert cross["equality_with_engine_required"] is False
    compared = reference["cases"]["engine_compare_candidates"]
    assert compared["root"]["white_cp"] == 40
    by_uci = {row["uci"]: row for row in compared["candidates"]}
    assert by_uci["e2e4"]["cp_loss_vs_best"] == 0
    assert by_uci["d2d4"]["cp_loss_vs_best"] == 2
    assert by_uci["d2d4"]["search"]["white_cp"] == 32


def test_position_identity_and_source_annotations_match_independent_code():
    module = _script("reference_engine_v1.py")
    start = chess.Board()
    capture = chess.Board("4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 1")
    assert position_key(start) == module.position_key(start)
    assert position_id(position_key(capture)) == module.position_id(module.position_key(capture))
    fresh = module.source_annotations(ROOT)
    reference = json.loads((ROOT / "evals/references/engine_v1.json").read_text())
    assert fresh == reference["source_annotations"]
    by_id = {row["id"]: row for row in fresh}
    assert by_id["portfolio_game0_ply3"]["white_cp"] == -250
    assert by_id["portfolio_game0_ply3"]["white_mate"] is None
    assert by_id["portfolio_game3_ply1_missing"]["white_cp"] is None
    assert by_id["portfolio_game3_ply1_missing"]["available"] is False
    assert by_id["portfolio_game3_ply5_mate"]["white_mate"] == 3
    assert by_id["portfolio_game3_ply5_mate"]["white_cp"] is None
    elite = reference["opening"]["cohorts"]["elite_reference"]
    assert elite["position_games"] == 3
    assert elite["cohort_games"] == 4
    assert elite["frequency"] == 0.75
    assert elite["continuations"] == [
        {"games": 2, "san": "d4", "share_of_position_games": 2 / 3, "uci": "d2d4"}
    ]
    rated = reference["opening"]["cohorts"]["rated_public"]
    assert rated["position_games"] == 1
    assert rated["cohort_games"] == 7
    assert rated["frequency"] == 1 / 7
    assert rated["continuations"][0]["uci"] == "e2e4"


def test_search_comparison_ignores_nodes_and_loss_uses_the_score_after_the_move():
    check = _script("check_engine_v1.py")
    expected = {
        "white_cp": 40,
        "white_mate": None,
        "depth": 12,
        "seldepth": 16,
        "best_move": None,
        "pv": [],
    }
    same_nodes = {**expected, "nodes": 10}
    other_nodes = {**expected, "nodes": 12}
    assert check.search_failures(other_nodes, same_nodes) == []
    assert check.node_delta(other_nodes, same_nodes) == 2
    changed = {**other_nodes, "white_cp": 41}
    assert check.search_failures(changed, same_nodes) == ["white_cp"]
    assert check.cp_loss(34, 32, white=True) == 2
    assert check.cp_loss(34, 32, white=False) == -2
    assert check.cp_loss(None, 32, white=True) is None


def test_check_skips_a_missing_or_different_engine_and_fails_closed_without_files(tmp_path):
    check = _script("check_engine_v1.py")
    module = _script("reference_engine_v1.py")
    reference = json.loads((ROOT / "evals/references/engine_v1.json").read_text())
    missing = check._check_engine(tmp_path, module, reference, [])
    assert missing == {"status": "skipped", "reason": "engine_not_configured"}
    _write_engine(tmp_path, FAKE)
    different = check._check_engine(tmp_path, module, reference, [])
    assert different["status"] == "skipped"
    assert different["reason"] == "engine_binary_differs"
    assert check.main(["--project", str(tmp_path)]) == 1
    assert module.main(["--project", str(tmp_path / "empty")]) == 0
    result = check.check(ROOT)
    assert result["sources"]["passed"] is True
    assert result["opening"]["passed"] is True
    engine = result["engine"]
    if engine["status"] == "skipped":
        assert engine["reason"] in {
            "engine_not_configured",
            "engine_binary_missing",
            "engine_config_hash_mismatch",
            "engine_binary_differs",
        }
    else:
        assert engine["status"] == "passed"
        assert engine["failures"] == []
    assert result["status"] == "passed"


def test_fake_engine_agrees_between_the_direct_process_and_the_tool(tmp_path):
    module = _script("reference_engine_v1.py")
    check = _script("check_engine_v1.py")
    session = module._Session(FAKE)
    try:
        searched = session.search(chess.Board(), 2)
    finally:
        session.close()
    _write_engine(tmp_path, FAKE)
    result = evaluate_position(tmp_path, "0" * 24, fen=START, depth=2)
    assert check.search_failures(result["root"], searched) == []
    assert result["root"]["nodes"] == 17
    mutated = {**searched, "white_cp": searched["white_cp"] + 1}
    assert "white_cp" in check.search_failures(result["root"], mutated)
    nodes_only = {**searched, "nodes": searched["nodes"] + 5}
    assert check.search_failures(result["root"], nodes_only) == []


def test_direct_handlers_keep_specific_limit_errors(tmp_path):
    with pytest.raises(ValueError, match="depth is outside the checked limit"):
        evaluate_position(tmp_path, "0" * 24, fen=START, depth=17)
    with pytest.raises(ValueError, match="invalid candidate moves"):
        compare_candidate_moves(
            tmp_path,
            "0" * 24,
            candidates=SEVEN,
            cohort="elite_reference",
            fen=START,
            depth=12,
        )
    with pytest.raises(ValueError, match="engine is not configured"):
        evaluate_position(tmp_path, "0" * 24, fen=START, depth=2)


@pytest.fixture(scope="module")
def analytical_project(tmp_path_factory):
    from chess_analytics.common import read_json, writer_lock
    from chess_analytics.corpus.publish import build_analytical
    from chess_analytics.corpus.source import extracted_path
    from chess_analytics.ingest.pipeline import ingest
    from chess_analytics.portfolio_demo import _stage_project
    from chess_analytics.warehouse.snapshots import build

    project = tmp_path_factory.mktemp("engine-eval") / "project"
    _stage_project(ROOT, project)
    root = project / "data"
    plan = read_json(project / "config/datasets.json")["analytical"]
    with writer_lock(root):
        ingest(project, root, "analytical", extracted_path(root, plan), plan)
        build(project, root, "analytical")
        build_analytical(project, root)
    return project


def test_boundary_replays_reject_without_an_engine_or_opening_shard(analytical_project):
    _clear_configs(analytical_project)
    _, cases = load_engine_cases(ROOT)
    selected = [case for case in cases if case["group"] == "boundary"]
    assert len(selected) == 9
    for case in selected:
        _assert_replay(analytical_project, case)


def test_answerable_replays_use_the_fake_engine_for_structural_fields(analytical_project):
    _clear_configs(analytical_project)
    _write_engine(analytical_project, FAKE)
    _, cases = load_engine_cases(ROOT)
    selected = [
        case
        for case in cases
        if case["requires_engine_binary"] and not case["requires_opening_fixture"]
    ]
    assert len(selected) == 6
    for case in selected:
        _assert_replay(analytical_project, case)


def test_opening_replays_use_the_synthetic_visit_rows(analytical_project):
    _write_engine(analytical_project, FAKE)
    directory = analytical_project / "engine-v1-visits"
    _script("reference_engine_v1.py").materialize_visits(ROOT, directory)
    _write_opening(analytical_project, directory)
    _, cases = load_engine_cases(ROOT)
    selected = [case for case in cases if case["requires_opening_fixture"]]
    assert len(selected) == 3
    for case in selected:
        _assert_replay(analytical_project, case)
