"""Offline engine and opening-continuation tools. No download and no live model call."""

import importlib.util
import json
import os
import time
from pathlib import Path

import chess
import duckdb
import pytest

from chess_analytics.analyst.core import (
    _evidence_id,
    answer_caveats,
    execute_plan,
    run_killable_tool,
)
from chess_analytics.analyst.plan_recovery import PLAN_SCHEMA
from chess_analytics.analyst.tool_catalog import TOOLS, TOOLS_BY_NAME, arguments_match
from chess_analytics.analyst.tools import CheckedTools
from chess_analytics.common import digest, write_json

ROOT = Path(__file__).resolve().parents[1]
FAKE = ROOT / "tests/fixtures/engines/fake_uci.py"
HANG = ROOT / "tests/fixtures/engines/hang_uci.py"
START = chess.STARTING_FEN
HISTORICAL_TOOLS = [
    "list_metrics",
    "get_metric_definition",
    "get_dataset_coverage",
    "query_metric",
    "compare_openings",
    "analyze_clock_pressure",
    "compare_clock_buckets",
]


def bare(project: Path, dataset: str = "a" * 24) -> CheckedTools:
    tools = CheckedTools.__new__(CheckedTools)
    tools.project = project
    tools.dataset_id = dataset
    return tools


def write_engine(project: Path, binary: Path, sha: str | None = None) -> None:
    write_json(
        project / "config/engine.json",
        {
            "version": "1",
            "binary_path": str(binary.resolve()),
            "binary_sha256": digest(binary) if sha is None else sha,
        },
    )


def test_example_configs_do_not_name_a_real_binary():
    engine = json.loads((ROOT / "config/engine.example.json").read_text())
    opening = json.loads((ROOT / "config/opening-visits.example.json").read_text())
    assert engine["binary_path"] == "/absolute/path/to/stockfish"
    assert engine["binary_sha256"] == "0" * 64
    assert not Path(engine["binary_path"]).exists()
    assert opening["snapshot_dir"] == "/absolute/path/to/visit-snapshot"
    assert opening["manifest_sha256"] == "0" * 64


def test_registry_publishes_the_new_tools_and_rejects_unbounded_input():
    names = [spec.name for spec in TOOLS]
    assert names[:7] == HISTORICAL_TOOLS
    assert names[7:10] == [
        "evaluate_position",
        "position_continuations",
        "compare_candidate_moves",
    ]
    evaluate = TOOLS_BY_NAME["evaluate_position"].input_schema
    compare = TOOLS_BY_NAME["compare_candidate_moves"].input_schema
    assert arguments_match(evaluate, {"fen": START, "depth": 16})
    assert not arguments_match(evaluate, {"fen": START, "depth": 17})
    assert not arguments_match(evaluate, {"fen": START, "depth": True})
    assert not arguments_match(evaluate, {"fen": START, "uci": "go infinite"})
    assert not arguments_match(compare, {"cohort": "elite_reference", "candidates": ["e2e4"] * 7})


def test_historical_planner_surface_does_not_gain_the_new_tools():
    source = (ROOT / "src/chess_analytics/analyst/provider.py").read_text()
    for name in ("evaluate_position", "position_continuations", "compare_candidate_moves"):
        assert name not in source
    enum = PLAN_SCHEMA["properties"]["actions"]["items"]["properties"]["tool"]["enum"]
    assert enum == HISTORICAL_TOOLS


def test_caveats_attach_to_engine_tools_and_leave_old_plans_alone():
    assert answer_caveats([{"tool": "list_metrics", "args": {}}]) == ["observed_prefix_only"]
    assert answer_caveats(
        [
            {
                "tool": "compare_openings",
                "args": {"filters": {"color": "white", "families": ["Sicilian", "French"]}},
            }
        ]
    ) == [
        "association_not_causation",
        "observed_prefix_only",
        "score_not_win_rate",
        "white_perspective",
    ]
    assert answer_caveats([{"tool": "analyze_clock_pressure", "args": {"bucket": "under_10"}}]) == [
        "exploratory_proxy",
        "missing_evaluation_not_zero",
        "observed_prefix_only",
        "source_evaluation_selection",
    ]
    assert answer_caveats(
        [
            {
                "tool": "query_metric",
                "args": {"metric_id": "opening_usage", "filters": {"family": "French Defense"}},
            }
        ]
    ) == ["observed_prefix_only", "source_tags_only"]
    assert answer_caveats([{"tool": "evaluate_position", "args": {"fen": START}}]) == [
        "engine_eval_depth_limited",
        "engine_not_ground_truth",
        "observed_prefix_only",
    ]
    assert answer_caveats(
        [{"tool": "compare_candidate_moves", "args": {"cohort": "elite_reference"}}]
    ) == [
        "engine_eval_depth_limited",
        "engine_not_ground_truth",
        "observed_prefix_only",
    ]
    assert answer_caveats(
        [{"tool": "position_continuations", "args": {"cohort": "rated_public"}}]
    ) == ["observed_prefix_only"]


def test_invalid_position_depth_and_missing_engine_fail_closed(tmp_path, monkeypatch):
    def refuse(*_args, **_kwargs):
        raise AssertionError("engine started")

    monkeypatch.setattr("chess.engine.SimpleEngine.popen_uci", refuse)
    monkeypatch.setenv("STOCKFISH_PATH", str(FAKE))
    tools = bare(tmp_path)
    with pytest.raises(ValueError, match="invalid fen"):
        tools.execute("evaluate_position", {"fen": "not-a-fen"})
    with pytest.raises(ValueError, match="illegal move prefix"):
        tools.execute("evaluate_position", {"moves": ["e2e5"]})
    with pytest.raises(ValueError, match="provide a fen or a move prefix"):
        tools.execute("evaluate_position", {"fen": START, "moves": ["e2e4"]})
    with pytest.raises(ValueError, match="depth is outside the checked limit"):
        tools.execute("evaluate_position", {"fen": START, "depth": 17})
    with pytest.raises(ValueError, match="depth is outside the checked limit"):
        tools.execute("evaluate_position", {"fen": START, "depth": True})
    with pytest.raises(ValueError, match="engine is not configured"):
        tools.execute("evaluate_position", {"fen": START})
    with pytest.raises(ValueError, match="unsupported tool or arguments"):
        tools.execute("evaluate_position", {"fen": START, "uci": "go infinite"})


def test_engine_config_rejects_a_relative_path_a_missing_file_and_a_bad_hash(tmp_path):
    tools = bare(tmp_path)
    write_json(
        tmp_path / "config/engine.json",
        {"version": "1", "binary_path": "stockfish", "binary_sha256": "0" * 64},
    )
    with pytest.raises(ValueError, match="engine binary path must be absolute"):
        tools.execute("evaluate_position", {"fen": START})
    write_engine(tmp_path, tmp_path / "missing-stockfish", sha="0" * 64)
    with pytest.raises(ValueError, match="engine binary is missing"):
        tools.execute("evaluate_position", {"fen": START})
    write_engine(tmp_path, FAKE, sha="0" * 64)
    with pytest.raises(ValueError, match="engine binary hash mismatch"):
        tools.execute("evaluate_position", {"fen": START})


def test_fake_engine_evidence_is_stable_and_records_the_binary(tmp_path):
    write_engine(tmp_path, FAKE)
    tools = bare(tmp_path)
    args = {"fen": START, "depth": 3}
    first = tools.execute("evaluate_position", args)
    second = tools.execute("evaluate_position", args)
    assert first == second
    assert first["engine"]["name"] == "Fake Engine 1.0"
    assert first["engine"]["binary_sha256"] == digest(FAKE)
    assert first["engine"]["threads"] == 1
    assert first["engine"]["hash_mb"] == 16
    assert "Clear Hash" in first["engine"]["options"]
    assert first["root"]["nodes"] == 17
    assert first["root"]["depth"] == 3
    assert first["root"]["best_move"]["uci"] == "a2a3"
    assert first["caveats"] == ["engine_eval_depth_limited", "engine_not_ground_truth"]
    assert "binary_path" not in json.dumps(first)
    evidence = _evidence_id(tools.dataset_id, "evaluate_position", args, first)
    assert evidence == _evidence_id(tools.dataset_id, "evaluate_position", args, second)
    assert evidence.startswith("ev_")
    prefixed = tools.execute("evaluate_position", {"moves": ["e2e4"], "depth": 2})
    assert prefixed["side_to_move"] == "black"
    assert prefixed["depth_requested"] == 2


def test_compare_pairs_loss_with_missing_frequencies_until_visits_exist(tmp_path):
    write_engine(tmp_path, FAKE)
    tools = bare(tmp_path)
    result = tools.execute(
        "compare_candidate_moves",
        {
            "fen": START,
            "depth": 2,
            "cohort": "elite_reference",
            "candidates": ["a2a3", "e2e4"],
        },
    )
    best, other = result["candidates"]
    assert best["uci"] == "a2a3" and best["is_engine_best"] and best["cp_loss_vs_best"] == 0
    assert other["cp_loss_vs_best"] == result["root"]["after_best"]["white_cp"] - other["white_cp"]
    assert other["observed_games"] is None
    assert result["continuations_available"] is False
    assert result["continuations_reason"] == "opening_source_not_configured"
    with pytest.raises(ValueError, match="invalid candidate moves"):
        tools.execute(
            "compare_candidate_moves",
            {"fen": START, "cohort": "elite_reference", "candidates": ["e2e4"] * 7},
        )
    with pytest.raises(ValueError, match="illegal candidate move"):
        tools.execute(
            "compare_candidate_moves",
            {"fen": START, "cohort": "elite_reference", "candidates": ["e2e5"]},
        )
    with pytest.raises(ValueError, match="duplicate candidate move"):
        tools.execute(
            "compare_candidate_moves",
            {"fen": START, "cohort": "elite_reference", "candidates": ["e2e4", "e2e4"]},
        )


def test_continuations_are_unavailable_without_local_data_and_reject_bad_cohorts(tmp_path):
    tools = bare(tmp_path)
    missing = tools.execute("position_continuations", {"fen": START, "cohort": "elite_reference"})
    assert missing["available"] is False
    assert missing["reason"] == "opening_source_not_configured"
    assert missing["continuations"] == []
    black = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"
    side = tools.execute("position_continuations", {"fen": black, "cohort": "rated_public"})
    assert side["reason"] == "not_white_to_move"
    with pytest.raises(ValueError, match="unsupported opening cohort"):
        tools.execute("position_continuations", {"fen": START, "cohort": "all"})


def _visits(directory: Path, rows: list[tuple]) -> None:
    directory.mkdir(parents=True)
    with duckdb.connect() as db:
        db.execute(
            """create table visits(
                cohort varchar, provider varchar, game_id varchar,
                ply integer, position_id varchar, next_move varchar)"""
        )
        db.executemany("insert into visits values (?, ?, ?, ?, ?, ?)", rows)
        db.execute("copy visits to ? (format parquet)", [str(directory / "visits-00.parquet")])


def _shard_config(project: Path, directory: Path, sources: list[dict]) -> None:
    parquet = directory / "visits-00.parquet"
    manifest = {
        "kind": "checked_white_opening_visits",
        "snapshot_id": "a" * 24,
        "plan": {"learner_color": "white", "min_ply": 6, "max_ply": 20},
        "training_sources": sources,
        "artifacts": {"visits-00.parquet": digest(parquet)},
    }
    write_json(directory / "manifest.json", manifest)
    write_json(
        project / "config/opening-visits.json",
        {
            "version": "1",
            "kind": "visit_shards",
            "snapshot_dir": str(directory),
            "manifest_sha256": digest(directory / "manifest.json"),
        },
    )


def test_visit_shards_keep_the_earliest_white_continuation(tmp_path):
    from chess_analytics.analyst.positions import position_id

    identity = position_id(" ".join(START.split()[:4]))
    directory = tmp_path / "visits"
    _visits(
        directory,
        [
            ("elite_reference", "lichess", "g1", 8, identity, "e2e4"),
            ("elite_reference", "lichess", "g1", 6, identity, "d2d4"),
            ("elite_reference", "lichess", "g2", 6, identity, "d2d4"),
            ("elite_reference", "lichess", "g3", 6, identity, ""),
            ("rated_public", "lichess", "g4", 6, identity, "e2e4"),
        ],
    )
    _shard_config(
        tmp_path,
        directory,
        [{"cohort": "elite_reference", "games": 4}, {"cohort": "rated_public", "games": 7}],
    )
    tools = bare(tmp_path)
    elite = tools.execute("position_continuations", {"fen": START, "cohort": "elite_reference"})
    assert elite["available"] is True
    assert elite["position_games"] == 3
    assert elite["cohort_games"] == 4
    assert elite["frequency"] == 0.75
    assert elite["next_move_games"] == 2
    assert elite["continuations"] == [
        {"uci": "d2d4", "san": "d4", "games": 2, "share_of_position_games": 2 / 3}
    ]
    assert elite["truncated"] is False
    assert elite["source_kind"] == "visit_shards"
    assert elite["window"] == {"learner_color": "white", "min_ply": 6, "max_ply": 20}
    public = tools.execute("position_continuations", {"fen": START, "cohort": "rated_public"})
    assert public["continuations"][0]["uci"] == "e2e4"
    assert public["cohort_games"] == 7
    absent = tools.execute(
        "position_continuations",
        {"moves": ["e2e4", "e7e5"], "cohort": "elite_reference"},
    )
    assert absent["reason"] == "position_not_observed"


def test_many_continuations_are_capped_and_hashes_are_checked(tmp_path):
    from chess_analytics.analyst.positions import position_id

    identity = position_id(" ".join(START.split()[:4]))
    moves = ["a2a3", "a2a4", "b1a3", "b1c3", "b2b3", "b2b4", "c2c3", "c2c4", "d2d3"]
    directory = tmp_path / "visits"
    _visits(
        directory,
        [
            ("elite_reference", "lichess", f"g{index}", 6, identity, move)
            for index, move in enumerate(moves)
        ],
    )
    _shard_config(tmp_path, directory, [{"cohort": "elite_reference", "games": 9}])
    tools = bare(tmp_path)
    capped = tools.execute("position_continuations", {"fen": START, "cohort": "elite_reference"})
    assert capped["truncated"] is True
    assert len(capped["continuations"]) == 8
    parquet = directory / "visits-00.parquet"
    payload = bytearray(parquet.read_bytes())
    payload[-1] ^= 1
    parquet.write_bytes(payload)
    with pytest.raises(ValueError, match="opening visit artifact hash mismatch"):
        tools.execute("position_continuations", {"fen": START, "cohort": "elite_reference"})
    parquet.write_bytes(bytes(payload[:-1]) + bytes([payload[-1] ^ 1]))
    config = tmp_path / "config/opening-visits.json"
    body = json.loads(config.read_text())
    body["manifest_sha256"] = "0" * 64
    write_json(config, body)
    with pytest.raises(ValueError, match="opening visit manifest hash mismatch"):
        tools.execute("position_continuations", {"fen": START, "cohort": "elite_reference"})


def test_ranking_report_answers_only_published_positions(tmp_path):
    from chess_analytics.analyst.positions import position_id, position_key

    board = chess.Board(START)
    key = position_key(board)
    identity = position_id(key)
    report = {
        "kind": "observed_white_opening_positions",
        "visit_snapshot_id": "b" * 24,
        "plan": {"learner_color": "white", "min_ply": 6, "max_ply": 20},
        "cohorts": {
            "elite_reference": {
                "views": {
                    "all": {
                        "denominator_games": 10,
                        "positions": {
                            identity: {
                                "position_key": key,
                                "games": 2,
                                "continuations": [
                                    {"uci": "e2e4", "san": "e4", "games": 2},
                                ],
                            }
                        },
                    }
                }
            }
        },
    }
    path = tmp_path / "opening-positions.json"
    write_json(path, report)
    write_json(
        tmp_path / "config/opening-visits.json",
        {
            "version": "1",
            "kind": "ranking_report",
            "report_path": "opening-positions.json",
            "report_sha256": digest(path),
        },
    )
    tools = bare(tmp_path)
    found = tools.execute("position_continuations", {"fen": START, "cohort": "elite_reference"})
    assert found["source_kind"] == "ranking_report"
    assert found["continuations"][0]["san"] == "e4"
    assert found["frequency"] == 0.2
    missed = tools.execute(
        "position_continuations",
        {"moves": ["e2e4", "c7c5"], "cohort": "elite_reference"},
    )
    assert missed["reason"] == "position_not_in_published_rankings"
    write_engine(tmp_path, FAKE)
    compared = tools.execute(
        "compare_candidate_moves",
        {"fen": START, "cohort": "elite_reference", "candidates": ["e2e4", "d2d4"], "depth": 2},
    )
    by_uci = {row["uci"]: row for row in compared["candidates"]}
    assert by_uci["e2e4"]["observed_games"] == 2
    assert by_uci["e2e4"]["observed_share"] == 1
    assert by_uci["d2d4"]["observed_games"] == 0
    assert compared["continuations_available"] is True


def test_position_key_matches_the_opening_builder():
    spec = importlib.util.spec_from_file_location(
        "build_opening_positions", ROOT / "scripts/build_opening_positions.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    from chess_analytics.analyst.positions import position_key

    start = chess.Board()
    assert position_key(start) == module.position_key(start)
    without = start.copy()
    without.castling_rights = 0
    assert position_key(without) == module.position_key(without)
    capture = chess.Board("4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 1")
    assert position_key(capture) == module.position_key(capture)
    assert position_key(capture).endswith(" d6")


@pytest.fixture(scope="module")
def analytical_project(tmp_path_factory):
    from chess_analytics.common import read_json, writer_lock
    from chess_analytics.corpus.publish import build_analytical
    from chess_analytics.corpus.source import extracted_path
    from chess_analytics.ingest.pipeline import ingest
    from chess_analytics.portfolio_demo import _stage_project
    from chess_analytics.warehouse.snapshots import build

    project = tmp_path_factory.mktemp("engine-analytical") / "project"
    _stage_project(ROOT, project)
    root = project / "data"
    plan = read_json(project / "config/datasets.json")["analytical"]
    with writer_lock(root):
        ingest(project, root, "analytical", extracted_path(root, plan), plan)
        build(project, root, "analytical")
        build_analytical(project, root)
    return project


def test_execute_plan_wires_engine_caveats_without_changing_list_metrics(analytical_project):
    write_engine(analytical_project, FAKE)
    engine = execute_plan(
        analytical_project,
        "What does the local engine say about the starting position?",
        {
            "status": "answered",
            "interpretation": "descriptive_observed_prefix",
            "actions": [
                {"tool": "evaluate_position", "args": {"fen": START, "depth": 2}},
            ],
        },
    )
    assert engine["caveats"] == [
        "engine_eval_depth_limited",
        "engine_not_ground_truth",
        "observed_prefix_only",
    ]
    assert engine["evidence_ids"][0].startswith("ev_")
    assert engine["tool_steps"] == 1
    listed = execute_plan(
        analytical_project,
        "List metrics.",
        {
            "status": "answered",
            "interpretation": "descriptive_observed_prefix",
            "actions": [{"tool": "list_metrics", "args": {}}],
        },
    )
    assert listed["caveats"] == ["observed_prefix_only"]
    absent = execute_plan(
        analytical_project,
        "Which White moves were played from the start?",
        {
            "status": "answered",
            "interpretation": "descriptive_observed_prefix",
            "actions": [
                {
                    "tool": "position_continuations",
                    "args": {"fen": START, "cohort": "elite_reference"},
                }
            ],
        },
    )
    assert absent["caveats"] == ["observed_prefix_only"]
    assert absent["result"]["reason"] == "opening_source_not_configured"


def test_worker_evidence_matches_the_plan_and_a_hung_engine_is_killed(analytical_project):
    write_engine(analytical_project, FAKE)
    args = {"fen": START, "depth": 2}
    dataset_id, result = run_killable_tool(analytical_project, "evaluate_position", args)
    answer = execute_plan(
        analytical_project,
        "Score the start.",
        {
            "status": "answered",
            "interpretation": "descriptive_observed_prefix",
            "actions": [{"tool": "evaluate_position", "args": args}],
        },
    )
    assert dataset_id == answer["dataset_id"]
    assert result == answer["evidence"][0]["result"]
    assert _evidence_id(dataset_id, "evaluate_position", args, result) == answer["evidence_ids"][0]
    write_engine(analytical_project, HANG)
    pid_path = analytical_project / "engine-hang.pid"
    pid_path.unlink(missing_ok=True)
    with pytest.raises(TimeoutError, match="killed"):
        run_killable_tool(
            analytical_project,
            "evaluate_position",
            {"fen": START, "depth": 1},
            timeout_seconds=3,
        )
    pid = int(pid_path.read_text())
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.05)
    pytest.fail("engine process survived the worker kill")


def test_real_stockfish_repeats_when_a_local_config_exists(tmp_path):
    config = ROOT / "config/engine.json"
    if not config.is_file():
        pytest.skip("engine config is not present")
    payload = json.loads(config.read_text())
    binary = Path(payload["binary_path"])
    if not binary.is_file() or digest(binary) != payload["binary_sha256"]:
        pytest.skip("configured engine binary is not available")
    write_json(tmp_path / "config/engine.json", payload)
    tools = bare(tmp_path)
    args = {"fen": START, "depth": 12}
    first = tools.execute("evaluate_position", args)
    second = tools.execute("evaluate_position", args)
    assert first["root"]["white_cp"] == second["root"]["white_cp"]
    assert first["root"]["nodes"] == second["root"]["nodes"]
    assert first["root"]["pv"] == second["root"]["pv"]
    assert first["engine"]["name"]
    assert first["engine"]["binary_sha256"] == payload["binary_sha256"]
    assert first["engine"]["threads"] == 1
    assert first["engine"]["hash_mb"] == 16
    assert _evidence_id("a" * 24, "evaluate_position", args, first) == _evidence_id(
        "a" * 24, "evaluate_position", args, second
    )
    compared = {
        "fen": START,
        "depth": 12,
        "cohort": "elite_reference",
        "candidates": ["e2e4", "d2d4"],
    }
    left = tools.execute("compare_candidate_moves", compared)
    right = tools.execute("compare_candidate_moves", compared)
    assert left["candidates"] == right["candidates"]
    assert left["root"]["nodes"] == right["root"]["nodes"]
    assert left["root"]["white_cp"] == right["root"]["white_cp"]
