"""Freeze the engine_v1 questions, structural expectations, and replay plans.

Engine scores are not written here. `scripts/reference_engine_v1.py --write`
records those from a direct UCI process. Continuation counts come from the
synthetic visit rows, not from a published shard.
"""

import importlib.util
import json
from pathlib import Path

import chess

from chess_analytics.common import write_json

PROJECT = Path(__file__).resolve().parents[1]
REPLAYS = PROJECT / "evals/replay_plans/engine_v1"
ENGINE_RESULT_CAVEATS = ["engine_eval_depth_limited", "engine_not_ground_truth"]
ANSWER_CAVEATS = ["engine_eval_depth_limited", "engine_not_ground_truth", "observed_prefix_only"]
FORBIDDEN_ENGINE = ["engine_eval_depth_limited", "engine_not_ground_truth"]
OBSERVED = ["observed_prefix_only"]
COMPARISON = {
    "counts": "exact",
    "nodes": "recorded_not_gated",
    "rates_absolute_tolerance": 1e-6,
    "score_mate_depth_seldepth_best_move_pv": "exact_when_binary_matches",
}
KIWIPETE = "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq -"
MATE = "7k/8/5KQ1/8/8/8/8/8 w - - 0 1"
START = chess.STARTING_FEN
SEVEN = ["a2a3", "a2a4", "b1a3", "b1c3", "b2b3", "b2b4", "c2c3"]


def load_reference():
    path = Path(__file__).resolve().parent / "reference_engine_v1.py"
    spec = importlib.util.spec_from_file_location("reference_engine_v1", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_rows(project: Path) -> None:
    write_json(
        project / "evals/fixtures/engine_v1/rows.json",
        {
            "kind": "synthetic_engine_v1_visit_rows",
            "not_a_corpus_frequency": True,
            "note": (
                "These five rows are a fixture, not the published opening corpus. "
                "elite_reference has 4 training games and 3 visits, so the cohort "
                "denominator stays the training count. g1 is counted at ply 6, not ply 8. "
                "g3 has an empty next move and still counts as a visit. "
                "reports/opening-positions.json and the published visit shards are not "
                "in this checkout."
            ),
            "plan": {"learner_color": "white", "max_ply": 20, "min_ply": 6},
            "snapshot_id": "e17e17e17e17e17e17e17e17",
            "training_sources": [
                {"cohort": "elite_reference", "games": 4},
                {"cohort": "rated_public", "games": 7},
            ],
            "rows": [
                {
                    "cohort": "elite_reference",
                    "game_id": "g1",
                    "next_move": "e2e4",
                    "ply": 8,
                    "position": "start",
                    "provider": "lichess",
                },
                {
                    "cohort": "elite_reference",
                    "game_id": "g1",
                    "next_move": "d2d4",
                    "ply": 6,
                    "position": "start",
                    "provider": "lichess",
                },
                {
                    "cohort": "elite_reference",
                    "game_id": "g2",
                    "next_move": "d2d4",
                    "ply": 6,
                    "position": "start",
                    "provider": "lichess",
                },
                {
                    "cohort": "elite_reference",
                    "game_id": "g3",
                    "next_move": "",
                    "ply": 6,
                    "position": "start",
                    "provider": "lichess",
                },
                {
                    "cohort": "rated_public",
                    "game_id": "g4",
                    "next_move": "e2e4",
                    "ply": 6,
                    "position": "start",
                    "provider": "lichess",
                },
            ],
        },
    )


def build_cases(module) -> list[dict]:
    import tempfile

    annotations = {row["id"]: row for row in module.source_annotations(PROJECT)}
    with tempfile.TemporaryDirectory() as raw:
        directory = Path(raw) / "visits"
        module.materialize_visits(PROJECT, directory)
        elite = module.continuation_tally(directory, "elite_reference", chess.Board())
        rated = module.continuation_tally(directory, "rated_public", chess.Board())
    source = annotations["portfolio_game0_ply3"]
    cases = [
        _answered(
            "engine_eval_start",
            "evaluate_position",
            "What is the configured engine's depth-12 score for the starting position?",
            "evaluate_position",
            {"depth": 12, "fen": START},
            _position_expected({"depth": 12, "fen": START}, module),
            engine=True,
        ),
        _answered(
            "engine_eval_prefix",
            "evaluate_position",
            "What is the configured engine's depth-12 score after 1. e4 e5?",
            "evaluate_position",
            {"depth": 12, "moves": ["e2e4", "e7e5"]},
            _position_expected({"depth": 12, "moves": ["e2e4", "e7e5"]}, module),
            engine=True,
        ),
        _answered(
            "engine_eval_kiwipete",
            "evaluate_position",
            "What is the configured engine's depth-12 score for the kiwipete position?",
            "evaluate_position",
            {"depth": 12, "fen": KIWIPETE},
            _position_expected({"depth": 12, "fen": KIWIPETE}, module),
            engine=True,
        ),
        _answered(
            "engine_eval_mate_in_one",
            "evaluate_position",
            "What is the configured engine's depth-12 score for this mate-in-one position?",
            "evaluate_position",
            {"depth": 12, "fen": MATE},
            _position_expected({"depth": 12, "fen": MATE}, module),
            engine=True,
        ),
        _answered(
            "engine_continuations_elite",
            "position_continuations",
            "Which elite_reference White moves does the fixture shard show from the start?",
            "position_continuations",
            {"cohort": "elite_reference", "fen": START},
            elite,
            opening=True,
            required=OBSERVED,
            forbidden=FORBIDDEN_ENGINE,
        ),
        _answered(
            "engine_continuations_rated",
            "position_continuations",
            "Which rated_public White moves does the synthetic fixture shard show from the start?",
            "position_continuations",
            {"cohort": "rated_public", "fen": START},
            rated,
            opening=True,
            required=OBSERVED,
            forbidden=FORBIDDEN_ENGINE,
        ),
        _answered(
            "engine_compare_candidates",
            "compare_candidate_moves",
            "At depth 12, how do e4 and d4 compare with the engine best move with no opening file?",
            "compare_candidate_moves",
            {
                "candidates": ["e2e4", "d2d4"],
                "cohort": "elite_reference",
                "depth": 12,
                "fen": START,
            },
            _compare_expected(module, observed=None),
            engine=True,
        ),
        _answered(
            "engine_compare_with_frequency",
            "compare_candidate_moves",
            "At depth 12, how do e4 and d4 compare with the engine best move on the fixture shard?",
            "compare_candidate_moves",
            {
                "candidates": ["e2e4", "d2d4"],
                "cohort": "elite_reference",
                "depth": 12,
                "fen": START,
            },
            _compare_expected(module, observed=elite),
            engine=True,
            opening=True,
        ),
        _answered(
            "engine_crosscheck_source_eval",
            "source_crosscheck",
            "What is the depth-12 engine score after 1. e4 c5 2. Nf3 in the portfolio fixture?",
            "evaluate_position",
            {"depth": 12, "fen": source["fen"]},
            _position_expected({"depth": 12, "fen": source["fen"]}, module),
            engine=True,
            source_id="portfolio_game0_ply3",
        ),
        _rejected(
            "engine_boundary_depth",
            "Evaluate the starting position at depth 17.",
            "evaluate_position",
            {"depth": 17, "fen": START},
            "depth is outside the checked limit",
        ),
        _rejected(
            "engine_boundary_malformed_fen",
            "Evaluate this FEN: not-a-fen.",
            "evaluate_position",
            {"depth": 12, "fen": "not-a-fen"},
            "invalid fen",
        ),
        _rejected(
            "engine_boundary_illegal_prefix",
            "Evaluate the position after the move e2e5 from the start.",
            "evaluate_position",
            {"depth": 12, "moves": ["e2e5"]},
            "illegal move prefix",
        ),
        _rejected(
            "engine_boundary_raw_uci",
            "Send the engine the UCI string go infinite.",
            "evaluate_position",
            {"fen": START, "uci": "go infinite"},
            "unsupported tool or arguments",
        ),
        _refused(
            "engine_boundary_causal",
            "Did the engine score cause the game result?",
        ),
        _refused(
            "engine_boundary_best_move_truth",
            "Is the engine best move the true best move?",
        ),
        _rejected(
            "engine_boundary_missing_engine",
            "Score the starting position with the local engine.",
            "evaluate_position",
            {"depth": 12, "fen": START},
            "engine is not configured",
        ),
        _missing_openings(module),
        _rejected(
            "engine_boundary_too_many_candidates",
            "Compare these seven candidate moves from the starting position.",
            "compare_candidate_moves",
            {"candidates": SEVEN, "cohort": "elite_reference", "depth": 12, "fen": START},
            "invalid candidate moves",
        ),
    ]
    return sorted(cases, key=lambda case: case["id"])


def write_cases(project: Path, cases: list[dict], plans: dict[str, dict]) -> None:
    write_json(project / "evals/cases/engine_v1.json", cases)
    REPLAYS.mkdir(parents=True, exist_ok=True)
    keep = set()
    for case in cases:
        name = f"{case['id']}.json"
        keep.add(name)
        write_json(
            REPLAYS / name,
            {
                "kind": "fixture_plan_no_model_response",
                "plan": plans[case["id"]],
                "question": case["question"],
            },
        )
    for path in REPLAYS.glob("*.json"):
        if path.name not in keep:
            path.unlink()


def _answered(
    case_id,
    category,
    question,
    tool,
    args,
    expected,
    *,
    engine=False,
    opening=False,
    required=None,
    forbidden=None,
    source_id=None,
):
    plan = {
        "actions": [{"args": args, "tool": tool}],
        "interpretation": "descriptive_observed_prefix",
        "status": "answered",
    }
    body = _body(
        case_id,
        category,
        question,
        "answered",
        tool,
        args,
        expected,
        None,
        required if required is not None else ANSWER_CAVEATS,
        forbidden or [],
        "medium",
        engine,
        opening,
        source_id,
    )
    body["_plan"] = plan
    return body


def _rejected(case_id, question, tool, args, error):
    plan = {
        "actions": [{"args": args, "tool": tool}],
        "interpretation": "descriptive_observed_prefix",
        "status": "answered",
    }
    body = _body(
        case_id,
        "boundary",
        question,
        "tool_rejected",
        tool,
        args,
        None,
        error,
        [],
        [],
        "high",
        False,
        False,
        None,
    )
    body["_plan"] = plan
    return body


def _refused(case_id, question):
    plan = {
        "actions": [],
        "interpretation": "descriptive_observed_prefix",
        "status": "unsupported",
    }
    body = _body(
        case_id,
        "boundary",
        question,
        "unsupported",
        None,
        None,
        None,
        None,
        OBSERVED,
        FORBIDDEN_ENGINE,
        "high",
        False,
        False,
        None,
    )
    body["_plan"] = plan
    return body


def _missing_openings(module) -> dict:
    board = chess.Board()
    key = module.position_key(board)
    expected = {
        "available": False,
        "cohort": "elite_reference",
        "cohort_games": None,
        "continuations": [],
        "fen": board.fen(),
        "frequency": None,
        "limits": list(module.CONTINUATION_LIMITS),
        "next_move_games": None,
        "position_games": None,
        "position_id": module.position_id(key),
        "position_key": key,
        "reason": "opening_source_not_configured",
        "source_kind": None,
        "source_sha256": None,
        "truncated": False,
        "visit_snapshot_id": None,
        "window": None,
    }
    return _answered(
        "engine_boundary_missing_openings",
        "boundary",
        "Which White moves does the opening corpus show from the starting position?",
        "position_continuations",
        {"cohort": "elite_reference", "fen": START},
        expected,
        required=OBSERVED,
        forbidden=FORBIDDEN_ENGINE,
    )


def _body(
    case_id,
    category,
    question,
    status,
    tool,
    args,
    expected,
    error,
    required,
    forbidden,
    severity,
    engine,
    opening,
    source_id,
):
    return {
        "allowed_interpretations": ["descriptive_observed_prefix"],
        "category": category,
        "comparison": COMPARISON,
        "dataset_id": None,
        "expected_error": error,
        "expected_result": expected,
        "expected_status": status,
        "expected_tool": tool,
        "expected_tool_args": args,
        "forbidden_caveats": forbidden,
        "group": "boundary" if category == "boundary" else "answerable",
        "id": case_id,
        "question": question,
        "reference_key": case_id if engine or category == "position_continuations" else None,
        "required_caveats": required,
        "requires_engine_binary": engine,
        "requires_opening_fixture": opening,
        "result_path": [],
        "rubric_version": "engine-1.0",
        "severity": "high" if category == "boundary" else severity,
        "source_annotation_id": source_id,
        "split": "engine_v1",
    }


def _position_expected(args: dict, module) -> dict:
    board = module.board_from_args(args)
    return {
        "caveats": ENGINE_RESULT_CAVEATS,
        "depth_requested": args["depth"],
        "fen": board.fen(),
        "position_key": module.position_key(board),
        "side_to_move": "white" if board.turn == chess.WHITE else "black",
    }


def _compare_expected(module, *, observed: dict | None) -> dict:
    board = chess.Board()
    key = module.position_key(board)
    if observed is None:
        rows = [
            {"observed_games": None, "observed_share": None, "san": "e4", "uci": "e2e4"},
            {"observed_games": None, "observed_share": None, "san": "d4", "uci": "d2d4"},
        ]
        available = False
        reason = "opening_source_not_configured"
        position_games = None
        cohort_games = None
        source_kind = None
    else:
        rows = [_observed_row(observed, "e2e4", "e4"), _observed_row(observed, "d2d4", "d4")]
        available = True
        reason = None
        position_games = observed["position_games"]
        cohort_games = observed["cohort_games"]
        source_kind = "visit_shards"
    return {
        "candidates": rows,
        "caveats": ENGINE_RESULT_CAVEATS,
        "cohort": "elite_reference",
        "cohort_games": cohort_games,
        "continuations_available": available,
        "continuations_reason": reason,
        "depth_requested": 12,
        "fen": board.fen(),
        "position_games": position_games,
        "position_key": key,
        "side_to_move": "white",
        "source_kind": source_kind,
    }


def _observed_row(tally: dict, uci: str, san: str) -> dict:
    games = tally["position_games"]
    count = 0
    for row in tally["continuations"]:
        if row["uci"] == uci:
            count = row["games"]
    share = None if not games else count / games
    return {"observed_games": count, "observed_share": share, "san": san, "uci": uci}


def main() -> None:
    module = load_reference()
    write_rows(PROJECT)
    cases = build_cases(module)
    plans = {case["id"]: case.pop("_plan") for case in cases}
    write_cases(PROJECT, cases, plans)
    print(json.dumps({"cases": len(cases), "replay_plans": len(plans)}))


if __name__ == "__main__":
    main()
