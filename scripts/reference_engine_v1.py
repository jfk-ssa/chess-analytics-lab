"""Independent engine_v1 references. This file does not call the checked tools.

Searches go through python-chess and a direct UCI process. Opening counts are a
separate SQL read of the synthetic visit rows. Source annotations are read from
the fixture PGN with python-chess, not from the corpus move extractor.
"""

import argparse
import hashlib
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

import chess
import chess.engine
import chess.pgn
import duckdb

from chess_analytics.common import digest, write_json

PROJECT = Path(__file__).resolve().parents[1]
ROWS = "evals/fixtures/engine_v1/rows.json"
CASES = "evals/cases/engine_v1.json"
REPLAYS = "evals/replay_plans/engine_v1"
REFERENCE = "evals/references/engine_v1.json"
MANIFEST = "evals/cases/engine_v1_manifest.json"
SOURCE_PGN = "tests/fixtures/portfolio_annotated.pgn"
PV_LIMIT = 8
THREADS = 1
HASH_MB = 16
EXACT_SEARCH = ("white_cp", "white_mate", "depth", "seldepth", "best_move", "pv")
CONTINUATION_LIMITS = (
    "White decisions in the configured opening window only.",
    "Each game counts once, at its earliest visit to the position.",
    "Observed frequency is not move quality.",
)
_REQUIRED = ("Threads", "Hash", "Clear Hash")
_PREFERRED = (
    ("UCI_AnalyseMode", True),
    ("UCI_LimitStrength", False),
    ("Use NNUE", True),
)
_EVAL = re.compile(r"\[%eval\s+([^\]]+)\]")
_EARLIEST = """
with "earliest" as (
    select "next_move", "provider", "game_id", "ply", "position_id"
    from read_parquet(?)
    where "cohort" = ? and "position_id" = ?
    qualify row_number() over (
        partition by "provider", "game_id", "position_id"
        order by "ply"
    ) = 1
)
select "next_move", count(*) as "games"
from "earliest"
group by "next_move"
order by "games" desc, "next_move"
"""
SOURCE_SPECS = (
    {
        "id": "portfolio_game0_ply3",
        "game_index": 0,
        "ply": 3,
        "role": "engine_case",
    },
    {
        "id": "portfolio_game3_ply1_missing",
        "game_index": 3,
        "ply": 1,
        "role": "missing_not_zero",
    },
    {
        "id": "portfolio_game3_ply5_mate",
        "game_index": 3,
        "ply": 5,
        "role": "mate_not_centipawns",
    },
)


def case_set_digest(cases: list) -> str:
    payload = json.dumps(sorted(cases, key=lambda case: case["id"]), sort_keys=True).encode()
    return hashlib.sha256(payload).hexdigest()


def replay_digest(directory: Path) -> str:
    rows = []
    for path in sorted(directory.glob("*.json")):
        rows.append({"file": path.name, "body": json.loads(path.read_text())})
    return hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()


def position_key(board: chess.Board) -> str:
    return " ".join(board.fen(en_passant="legal").split()[:4])


def position_id(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()[:24]


def board_from_args(args: dict) -> chess.Board:
    fen = args.get("fen")
    moves = args.get("moves")
    if fen is not None:
        fields = fen.split()
        if len(fields) == 4:
            fen = fen + " 0 1"
        return chess.Board(fen)
    board = chess.Board()
    for move in moves:
        board.push_uci(move)
    return board


def load_rows(project: Path) -> dict:
    return json.loads((project / ROWS).read_text())


def materialize_visits(project: Path, directory: Path) -> dict:
    """Write one parquet shard and its manifest from the frozen synthetic rows."""
    spec = load_rows(project)
    identity = position_id(position_key(chess.Board()))
    directory.mkdir(parents=True, exist_ok=True)
    records = []
    for row in spec["rows"]:
        if row.get("position") != "start":
            raise ValueError("synthetic visit row is not the starting position")
        records.append(
            (
                row["cohort"],
                row["provider"],
                row["game_id"],
                row["ply"],
                identity,
                row["next_move"],
            )
        )
    target = directory / "visits-00.parquet"
    with duckdb.connect() as db:
        db.execute(
            """
            create table "visits" (
                "cohort" varchar,
                "provider" varchar,
                "game_id" varchar,
                "ply" integer,
                "position_id" varchar,
                "next_move" varchar
            )
            """
        )
        db.executemany('insert into "visits" values (?, ?, ?, ?, ?, ?)', records)
        db.execute('copy "visits" to ? (format parquet)', [str(target)])
    manifest = {
        "kind": "checked_white_opening_visits",
        "synthetic": True,
        "not_a_corpus_frequency": True,
        "snapshot_id": spec["snapshot_id"],
        "plan": spec["plan"],
        "training_sources": spec["training_sources"],
        "artifacts": {"visits-00.parquet": digest(target)},
    }
    write_json(directory / "manifest.json", manifest)
    return manifest


def continuation_tally(directory: Path, cohort: str, board: chess.Board) -> dict:
    spec_manifest = json.loads((directory / "manifest.json").read_text())
    identity = position_id(position_key(board))
    paths = sorted(directory.glob("visits-*.parquet"))
    with duckdb.connect() as db:
        fetched = db.execute(
            _EARLIEST, [[str(path) for path in paths], cohort, identity]
        ).fetchall()
    position_games = sum(int(count) for _, count in fetched)
    moves = []
    for move, count in fetched:
        games = int(count)
        if move is None or move == "":
            continue
        parsed = chess.Move.from_uci(move)
        moves.append(
            {
                "uci": parsed.uci(),
                "san": board.san(parsed),
                "games": games,
                "share_of_position_games": games / position_games,
            }
        )
    cohort_games = _cohort_games(spec_manifest, cohort)
    return {
        "available": position_games > 0,
        "reason": None if position_games else "position_not_observed",
        "cohort": cohort,
        "fen": board.fen(),
        "position_key": position_key(board),
        "position_id": identity,
        "position_games": position_games,
        "cohort_games": cohort_games,
        "frequency": None if not cohort_games else position_games / cohort_games,
        "next_move_games": sum(item["games"] for item in moves),
        "continuations": moves,
        "truncated": False,
        "window": {
            "learner_color": spec_manifest["plan"].get("learner_color"),
            "min_ply": spec_manifest["plan"].get("min_ply"),
            "max_ply": spec_manifest["plan"].get("max_ply"),
        },
        "limits": list(CONTINUATION_LIMITS),
        "visit_snapshot_id": spec_manifest["snapshot_id"],
        "source_kind": "visit_shards",
    }


def source_annotations(project: Path) -> list[dict]:
    games = _games(project / SOURCE_PGN)
    rows = []
    for spec in SOURCE_SPECS:
        node = _ply(games[spec["game_index"]], spec["ply"])
        raw = _raw_eval(node.comment)
        cp, mate = _white_eval(node)
        rows.append(
            {
                "id": spec["id"],
                "role": spec["role"],
                "fixture": SOURCE_PGN,
                "game_index": spec["game_index"],
                "site": games[spec["game_index"]].headers.get("Site"),
                "ply": spec["ply"],
                "uci": node.move.uci(),
                "fen": node.board().fen(),
                "raw_eval": raw,
                "white_cp": cp,
                "white_mate": mate,
                "available": raw is not None,
                "missing_stored_as_zero": False,
                "centipawn_substituted_for_mate": mate is not None and cp is not None,
                "equality_with_engine_required": False,
            }
        )
    return rows


def read_engine_config(project: Path) -> dict | None:
    path = project / "config" / "engine.json"
    if not path.is_file():
        return None
    payload = json.loads(path.read_text())
    binary = Path(payload["binary_path"])
    if not binary.is_file():
        return {"reason": "engine_binary_missing"}
    actual = digest(binary)
    if actual != payload.get("binary_sha256"):
        return {"reason": "engine_config_hash_mismatch"}
    return {"binary": binary, "binary_sha256": actual, "binary_bytes": binary.stat().st_size}


def build_reference(project: Path, identity: dict) -> dict:
    cases = json.loads((project / CASES).read_text())
    annotations = source_annotations(project)
    by_source = {row["id"]: row for row in annotations}
    opening = _opening_block(project)
    first = _engine_cases(project, cases, identity["binary"], by_source)
    second = _engine_cases(project, cases, identity["binary"], by_source)
    _require_repeat(first, second)
    return {
        "kind": "engine_v1 independent reference; no checked-tool calls and no model responses",
        "case_set": "engine_v1",
        "case_set_sha256": case_set_digest(cases),
        "generated_utc": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "comparison": _comparison_policy(),
        "engine": _engine_block(identity, first["options"], first["name"]),
        "opening": opening,
        "source_annotations": annotations,
        "cases": first["cases"],
        "repeat": {
            "sessions": 2,
            "score_mate_depth_seldepth_best_move_pv": "matched",
            "nodes": "recorded_not_gated",
            "node_deltas": _node_deltas(first["cases"], second["cases"]),
        },
    }


def write_outputs(project: Path, reference: dict) -> dict:
    reference_path = project / REFERENCE
    write_json(reference_path, reference)
    cases = json.loads((project / CASES).read_text())
    case_path = project / CASES
    manifest = {
        "kind": "engine_v1 fixture and replay evidence; not model accuracy",
        "case_file": CASES,
        "case_set_sha256": case_set_digest(cases),
        "case_file_sha256": digest(case_path),
        "cases": len(cases),
        "answerable": sum(case["group"] == "answerable" for case in cases),
        "boundary": sum(case["group"] == "boundary" for case in cases),
        "categories": _categories(cases),
        "why_this_size": (
            "Eighteen cases cover the three tools, two cross-checks, and the "
            "named safety limits. The set is not a sample of positions."
        ),
        "replay_plan_dir": REPLAYS,
        "replay_plans": len(list((project / REPLAYS).glob("*.json"))),
        "replay_plans_sha256": replay_digest(project / REPLAYS),
        "reference_file": REFERENCE,
        "reference_sha256": digest(reference_path),
        "rubric_version": "engine-1.0",
        "canonicalization": "sha256 of json.dumps(cases sorted by id, sort_keys=True) utf-8",
        "rows_file": ROWS,
        "rows_sha256": digest(project / ROWS),
        "engine": reference["engine"],
        "opening_fixture": {
            "kind": "synthetic_visit_rows",
            "path": ROWS,
            "published_shards": "not in this checkout",
            "published_ranking_report": "not in this checkout",
            "parquet_bytes": "materialized locally from the frozen rows; not a committed artifact",
        },
        "source_eval_crosscheck": {
            "fixture": SOURCE_PGN,
            "equality_required": False,
            "corpus_source_evals": "not used; the analytical corpus is not in this checkout",
        },
        "comparison": reference["comparison"],
        "live_provider": "no live run; a future live run needs its own freeze and a finite cap",
        "built_by": ["scripts/build_engine_v1_cases.py", "scripts/reference_engine_v1.py"],
    }
    write_json(project / MANIFEST, manifest)
    return manifest


def _opening_block(project: Path) -> dict:
    import tempfile

    with tempfile.TemporaryDirectory() as raw:
        directory = Path(raw) / "visits"
        materialize_visits(project, directory)
        board = chess.Board()
        return {
            "kind": "synthetic_visit_shard",
            "not_a_corpus_frequency": True,
            "rows_file": ROWS,
            "rows_sha256": digest(project / ROWS),
            "cohorts": {
                cohort: continuation_tally(directory, cohort, board)
                for cohort in ("elite_reference", "rated_public")
            },
        }


def _engine_cases(project: Path, cases: list, binary: Path, by_source: dict) -> dict:
    session = _Session(binary)
    try:
        built = {}
        for case in cases:
            if not case["requires_engine_binary"]:
                continue
            built[case["id"]] = _one_case(session, case, by_source)
        return {"name": session.name, "options": session.options, "cases": built}
    finally:
        session.close()


def _one_case(session, case: dict, by_source: dict) -> dict:
    args = case["expected_tool_args"]
    board = board_from_args(args)
    depth = args.get("depth", 12)
    if case["expected_tool"] == "evaluate_position":
        record = {
            "kind": "evaluate_position",
            "fen": board.fen(),
            "search": session.search(board, depth),
        }
        source_id = case.get("source_annotation_id")
        if source_id:
            _attach_source(record, board, by_source[source_id])
        return record
    if case["expected_tool"] != "compare_candidate_moves":
        raise ValueError(f"no independent reference for {case['id']}")
    return _compare(session, board, depth, args["candidates"])


def _compare(session, board: chess.Board, depth: int, candidates: list[str]) -> dict:
    root = session.search(board, depth)
    best = root["best_move"]
    if best is None:
        raise RuntimeError("engine returned no best move")
    best_move = chess.Move.from_uci(best["uci"])
    children = {}
    after_best = session.search(_pushed(board, best_move), depth)
    children[best["uci"]] = after_best
    rows = []
    for uci in candidates:
        move = chess.Move.from_uci(uci)
        if uci not in children:
            children[uci] = session.search(_pushed(board, move), depth)
        search = children[uci]
        rows.append(
            {
                "uci": uci,
                "san": board.san(move),
                "search": search,
                "cp_loss_vs_best": _loss(after_best["white_cp"], search["white_cp"], board.turn),
                "is_engine_best": uci == best["uci"],
            }
        )
    return {
        "kind": "compare_candidate_moves",
        "fen": board.fen(),
        "root": root,
        "best_uci": best["uci"],
        "after_best": after_best,
        "candidates": rows,
    }


def _attach_source(record: dict, board: chess.Board, annotation: dict) -> None:
    if board.fen() != annotation["fen"]:
        raise RuntimeError("case position does not match the source annotation")
    record["source_annotation_id"] = annotation["id"]
    record["source_white_cp"] = annotation["white_cp"]
    record["source_white_mate"] = annotation["white_mate"]
    record["equality_with_engine_required"] = False
    if annotation["white_cp"] is not None and record["search"]["white_cp"] is not None:
        record["white_cp_minus_source"] = record["search"]["white_cp"] - annotation["white_cp"]


def _require_repeat(first: dict, second: dict) -> None:
    for case_id, record in first["cases"].items():
        if not _same_exact(record, second["cases"][case_id]):
            raise RuntimeError(f"independent repeat disagreed on {case_id}")


def _same_exact(left: dict, right: dict) -> bool:
    if left["kind"] != right["kind"]:
        return False
    if left["kind"] == "evaluate_position":
        return _search_exact(left["search"], right["search"])
    if not _search_exact(left["root"], right["root"]):
        return False
    if not _search_exact(left["after_best"], right["after_best"]):
        return False
    pairs = zip(left["candidates"], right["candidates"], strict=True)
    return all(
        item["uci"] == other["uci"]
        and item["cp_loss_vs_best"] == other["cp_loss_vs_best"]
        and _search_exact(item["search"], other["search"])
        for item, other in pairs
    )


def _search_exact(left: dict, right: dict) -> bool:
    return all(left.get(key) == right.get(key) for key in EXACT_SEARCH)


def _node_deltas(first: dict, second: dict) -> dict:
    deltas = {}
    for case_id, record in first.items():
        deltas[case_id] = _collect_nodes(second[case_id], record)
    return deltas


def _collect_nodes(observed: dict, expected: dict) -> list[int]:
    if observed["kind"] == "evaluate_position":
        return [observed["search"]["nodes"] - expected["search"]["nodes"]]
    deltas = [observed["root"]["nodes"] - expected["root"]["nodes"]]
    deltas.append(observed["after_best"]["nodes"] - expected["after_best"]["nodes"])
    for item, other in zip(observed["candidates"], expected["candidates"], strict=True):
        deltas.append(item["search"]["nodes"] - other["search"]["nodes"])
    return deltas


def _engine_block(identity: dict, options: list[str], name: str) -> dict:
    return {
        "available": True,
        "name": name,
        "binary_sha256": identity["binary_sha256"],
        "binary_bytes": identity["binary_bytes"],
        "binary_path_recorded": False,
        "settings": {
            "threads": THREADS,
            "hash_mb": HASH_MB,
            "clear_hash_before_each_search": True,
            "depth": 12,
            "uci_analyse_mode": True,
            "uci_limit_strength": False,
            "use_nnue": True,
            "multipv_sent": False,
            "ponder_sent": False,
            "movetime": None,
            "options_set": options,
        },
        "launch": "direct python-chess SimpleEngine; not the checked tool parent-death wrapper",
        "host_claim": (
            "One machine on the day this file was written. "
            "Not a claim that another CPU or build repeats it."
        ),
    }


def _comparison_policy() -> dict:
    return {
        "score_mate_depth_seldepth_best_move_pv": "exact",
        "nodes": "recorded_not_gated",
        "rates_absolute_tolerance": 1e-6,
        "binary_mismatch": "skip; not scored as a tool failure",
        "missing_engine": "skip",
        "different_binary": (
            "If the configured file's SHA-256 is not the reference hash, "
            "engine comparison does not run."
        ),
    }


def _loss(best_cp: int | None, candidate_cp: int | None, turn: chess.Color) -> int | None:
    if best_cp is None or candidate_cp is None:
        return None
    if turn == chess.WHITE:
        return best_cp - candidate_cp
    return candidate_cp - best_cp


def _pushed(board: chess.Board, move: chess.Move) -> chess.Board:
    child = board.copy()
    child.push(move)
    return child


def _cohort_games(manifest: dict, cohort: str) -> int:
    total = 0
    found = False
    for source in manifest["training_sources"]:
        if source["cohort"] != cohort:
            continue
        total += source["games"]
        found = True
    if not found:
        raise ValueError(f"opening cohort is not in the visit manifest: {cohort}")
    return total


def _games(path: Path) -> list:
    games = []
    with path.open() as handle:
        while True:
            game = chess.pgn.read_game(handle)
            if game is None:
                break
            games.append(game)
    return games


def _ply(game, ply: int):
    for node in game.mainline():
        if node.ply() == ply:
            return node
    raise ValueError(f"ply {ply} is not in the fixture game")


def _raw_eval(comment: str) -> str | None:
    match = _EVAL.search(comment or "")
    if match is None:
        return None
    return match.group(1).strip()


def _white_eval(node) -> tuple[int | None, int | None]:
    value = node.eval()
    if value is None:
        return None, None
    white = value.white()
    return white.score(mate_score=None), white.mate()


def _categories(cases: list) -> dict:
    counts: dict[str, int] = {}
    for case in cases:
        counts[case["category"]] = counts.get(case["category"], 0) + 1
    return dict(sorted(counts.items()))


class _Session:
    def __init__(self, binary: Path):
        command = [sys.executable, str(binary)] if binary.suffix == ".py" else [str(binary)]
        try:
            self.engine = chess.engine.SimpleEngine.popen_uci(command, timeout=10)
        except (chess.engine.EngineError, OSError, TimeoutError) as exc:
            raise RuntimeError("engine failed") from exc
        self.name = self.engine.id.get("name") if self.engine.id else None
        if not isinstance(self.name, str) or not self.name.strip():
            self.close()
            raise RuntimeError("engine failed")
        self.options = _configure(self.engine)

    def search(self, board: chess.Board, depth: int) -> dict:
        self.engine.configure({"Clear Hash": None})
        info = self.engine.analyse(board, chess.engine.Limit(depth=depth))
        return _public_search(board, info)

    def close(self) -> None:
        try:
            self.engine.quit()
        except chess.engine.EngineError:
            self.engine.close()


def _configure(engine) -> list[str]:
    missing = [name for name in _REQUIRED if name not in engine.options]
    if missing:
        raise RuntimeError("engine failed")
    options = {"Threads": THREADS, "Hash": HASH_MB}
    for name, value in _PREFERRED:
        if name in engine.options:
            options[name] = value
    engine.configure(options)
    engine.configure({"Clear Hash": None})
    return sorted([*options, "Clear Hash"])


def _public_search(board: chess.Board, info: dict) -> dict:
    score = info.get("score")
    if score is None:
        raise RuntimeError("engine returned no score")
    white = score.white()
    cp = white.score(mate_score=None)
    mate = white.mate()
    nodes = info.get("nodes")
    achieved = info.get("depth")
    if isinstance(nodes, bool) or not isinstance(nodes, int) or nodes < 0:
        raise RuntimeError("engine returned no node count")
    if isinstance(achieved, bool) or not isinstance(achieved, int):
        raise RuntimeError("engine returned no depth")
    pv = []
    for move in info.get("pv") or []:
        if not isinstance(move, chess.Move):
            continue
        pv.append(move.uci())
        if len(pv) == PV_LIMIT:
            break
    best = None
    if pv:
        move = chess.Move.from_uci(pv[0])
        if move in board.legal_moves:
            best = {"uci": pv[0], "san": board.san(move)}
    seldepth = info.get("seldepth")
    if isinstance(seldepth, bool) or not isinstance(seldepth, int):
        seldepth = None
    return {
        "white_cp": cp,
        "white_mate": mate,
        "nodes": nodes,
        "depth": achieved,
        "seldepth": seldepth,
        "best_move": best,
        "pv": pv,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write engine_v1 independent references")
    parser.add_argument("--project", type=Path, default=PROJECT)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    identity = read_engine_config(args.project)
    if identity is None or "reason" in identity:
        reason = None if identity is None else identity["reason"]
        print(json.dumps({"status": "skipped", "reason": reason or "engine_not_configured"}))
        return 0
    if not args.write:
        print(
            json.dumps(
                {
                    "status": "not_written",
                    "engine_configured": True,
                    "binary_sha256": identity["binary_sha256"],
                }
            )
        )
        return 0
    reference = build_reference(args.project, identity)
    manifest = write_outputs(args.project, reference)
    print(
        json.dumps(
            {
                "status": "written",
                "binary_sha256": identity["binary_sha256"],
                "engine_name": reference["engine"]["name"],
                "reference_sha256": manifest["reference_sha256"],
                "case_set_sha256": manifest["case_set_sha256"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
