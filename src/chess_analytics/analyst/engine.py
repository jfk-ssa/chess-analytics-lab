"""Local engine checks. Callers never pass UCI text; settings are fixed here."""

import json
import re
import sys
from pathlib import Path

import chess
import chess.engine

from chess_analytics.analyst.openings import observed_moves
from chess_analytics.analyst.positions import parse_position, position_key
from chess_analytics.analyst.tool_catalog import (
    ENGINE_CAVEATS,
    ENGINE_DEFAULT_DEPTH,
    ENGINE_MAX_DEPTH,
    ENGINE_MIN_DEPTH,
    MAX_CANDIDATES,
    MAX_MOVE_PREFIX,
    OPENING_COHORTS,
)
from chess_analytics.analyst.worker_launch import worker_command
from chess_analytics.common import digest

THREADS = 1
HASH_MB = 16
PV_LIMIT = 8
_SHA256 = re.compile(r"[0-9a-f]{64}")
_UCI = re.compile(r"[a-h][1-8][a-h][1-8][qrbn]?")
_REQUIRED_OPTIONS = ("Threads", "Hash", "Clear Hash")
_PREFERRED_OPTIONS = (
    ("UCI_AnalyseMode", True),
    ("UCI_LimitStrength", False),
    ("Use NNUE", True),
)


def evaluate_position(
    project: Path,
    dataset_id: str,
    fen: str | None = None,
    moves: list[str] | None = None,
    depth: int | None = None,
) -> dict:
    """Score one position. The result records the binary hash, depth, and nodes."""
    board = parse_position(fen, moves, max_moves=MAX_MOVE_PREFIX)
    selected = _depth(depth)
    binary, sha = _engine_binary(project)
    with _EngineSession(binary) as engine:
        options = _configure(engine)
        name = _engine_name(engine)
        root = _search(engine, board, selected)
    return _envelope(
        dataset_id,
        board,
        selected,
        _engine_record(name, sha, options),
        {"root": _public_search(root)},
    )


def compare_candidate_moves(
    project: Path,
    dataset_id: str,
    candidates: list[str] | None = None,
    cohort: str | None = None,
    fen: str | None = None,
    moves: list[str] | None = None,
    depth: int | None = None,
) -> dict:
    """Centipawn loss versus the engine's best move, beside observed frequency."""
    if cohort not in OPENING_COHORTS:
        raise ValueError("unsupported opening cohort")
    board = parse_position(fen, moves, max_moves=MAX_MOVE_PREFIX)
    selected = _depth(depth)
    parsed = _candidates(board, candidates)
    binary, sha = _engine_binary(project)
    with _EngineSession(binary) as engine:
        name = _engine_name(engine)
        options = _configure(engine)
        root = _search(engine, board, selected)
        best = _best_move(board, root)
        after = {_uci(best): _search(engine, _pushed(board, best), selected)}
        for move in parsed:
            uci = _uci(move)
            if uci not in after:
                after[uci] = _search(engine, _pushed(board, move), selected)
    lookup = observed_moves(project, board, cohort)
    best_uci = _uci(best)
    best_after = after[best_uci]
    rows = [
        _candidate_row(board, move, after[_uci(move)], best_after, best_uci, lookup)
        for move in parsed
    ]
    return _envelope(
        dataset_id,
        board,
        selected,
        _engine_record(name, sha, options),
        {
            "cohort": cohort,
            "root": {**_public_search(root), "after_best": _public_search(best_after)},
            "candidates": rows,
            "continuations_available": lookup["available"],
            "continuations_reason": lookup["reason"],
            "position_games": lookup["position_games"],
            "cohort_games": lookup["cohort_games"],
            "source_kind": lookup["source_kind"],
            "source_sha256": lookup["source_sha256"],
        },
    )


def _engine_name(engine) -> str:
    name = engine.id.get("name") if engine.id else None
    if not isinstance(name, str) or not name.strip():
        raise ValueError("engine failed")
    return name


def _envelope(dataset_id: str, board: chess.Board, depth: int, engine: dict, body: dict) -> dict:
    white = board.turn == chess.WHITE
    return {
        "dataset_id": dataset_id,
        "fen": board.fen(),
        "position_key": position_key(board),
        "side_to_move": "white" if white else "black",
        "depth_requested": depth,
        "engine": engine,
        "caveats": list(ENGINE_CAVEATS),
        **body,
    }


def _engine_record(name: str, sha: str, options: list[str]) -> dict:
    return {
        "name": name,
        "binary_sha256": sha,
        "threads": THREADS,
        "hash_mb": HASH_MB,
        "clear_hash": True,
        "options": options,
    }


def _public_search(search: dict) -> dict:
    return {
        "white_cp": search["white_cp"],
        "white_mate": search["white_mate"],
        "nodes": search["nodes"],
        "depth": search["depth"],
        "seldepth": search["seldepth"],
        "best_move": search["best_move"],
        "pv": search["pv"],
    }


def _candidate_row(board, move, search, best_after, best_uci: str, lookup: dict) -> dict:
    uci = _uci(move)
    games, share = _observed(lookup, uci)
    return {
        "uci": uci,
        "san": board.san(move),
        "white_cp": search["white_cp"],
        "white_mate": search["white_mate"],
        "nodes": search["nodes"],
        "depth": search["depth"],
        "cp_loss_vs_best": _loss(best_after["white_cp"], search["white_cp"], board.turn),
        "is_engine_best": uci == best_uci,
        "observed_games": games,
        "observed_share": share,
    }


def _observed(lookup: dict, uci: str) -> tuple[int | None, float | None]:
    if not lookup["configured"]:
        return None, None
    games = lookup["position_games"]
    if not games:
        return 0, None
    count = lookup["by_uci"].get(uci, 0)
    return count, count / games


def _loss(best_cp: int | None, candidate_cp: int | None, turn: chess.Color) -> int | None:
    if best_cp is None or candidate_cp is None:
        return None
    if turn == chess.WHITE:
        return best_cp - candidate_cp
    return candidate_cp - best_cp


def _candidates(board: chess.Board, values: list[str] | None) -> list[chess.Move]:
    if not isinstance(values, list) or not 1 <= len(values) <= MAX_CANDIDATES:
        raise ValueError("invalid candidate moves")
    parsed = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str) or _UCI.fullmatch(value) is None:
            raise ValueError("invalid candidate moves")
        if value in seen:
            raise ValueError("duplicate candidate move")
        try:
            move = chess.Move.from_uci(value)
        except ValueError as exc:
            raise ValueError("invalid candidate moves") from exc
        if move not in board.legal_moves:
            raise ValueError("illegal candidate move")
        seen.add(value)
        parsed.append(move)
    return parsed


def _best_move(board: chess.Board, search: dict) -> chess.Move:
    best = search["best_move"]
    if best is None:
        raise ValueError("engine returned no best move")
    move = chess.Move.from_uci(best["uci"])
    if move not in board.legal_moves:
        raise ValueError("engine returned no best move")
    return move


def _pushed(board: chess.Board, move: chess.Move) -> chess.Board:
    child = board.copy()
    child.push(move)
    return child


def _uci(move: chess.Move) -> str:
    return move.uci()


def _depth(value: int | None) -> int:
    if value is None:
        return ENGINE_DEFAULT_DEPTH
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("depth is outside the checked limit")
    if not ENGINE_MIN_DEPTH <= value <= ENGINE_MAX_DEPTH:
        raise ValueError("depth is outside the checked limit")
    return value


def _engine_binary(project: Path) -> tuple[Path, str]:
    path = project / "config" / "engine.json"
    if not path.is_file():
        raise ValueError("engine is not configured")
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError("engine config is invalid") from exc
    if not isinstance(payload, dict) or set(payload) != {"version", "binary_path", "binary_sha256"}:
        raise ValueError("engine config is invalid")
    if payload["version"] != "1":
        raise ValueError("engine config is invalid")
    raw = payload["binary_path"]
    expected = payload["binary_sha256"]
    if not isinstance(raw, str) or not isinstance(expected, str):
        raise ValueError("engine config is invalid")
    binary = Path(raw)
    if not binary.is_absolute():
        raise ValueError("engine binary path must be absolute")
    if _SHA256.fullmatch(expected) is None:
        raise ValueError("engine config is invalid")
    if not binary.is_file():
        raise ValueError("engine binary is missing")
    actual = digest(binary)
    if actual != expected:
        raise ValueError("engine binary hash mismatch")
    return binary, actual


def _command(binary: Path) -> list[str]:
    """Exec the pinned binary, or a `.py` engine under this interpreter.

    A script shebang would use system Python and miss the project environment.
    The hash is still the configured file, not this interpreter.
    """
    if binary.suffix == ".py":
        return worker_command([sys.executable, str(binary)])
    return worker_command([str(binary)])


class _EngineSession:
    def __init__(self, binary: Path):
        self.binary = binary
        self.engine = None

    def __enter__(self):
        try:
            self.engine = chess.engine.SimpleEngine.popen_uci(_command(self.binary), timeout=10)
        except (chess.engine.EngineError, OSError, TimeoutError) as exc:
            raise ValueError("engine failed") from exc
        return self.engine

    def __exit__(self, exc_type, exc, tb):
        if self.engine is not None:
            try:
                self.engine.quit()
            except chess.engine.EngineError:
                self.engine.close()
        return False


def _configure(engine) -> list[str]:
    missing = [name for name in _REQUIRED_OPTIONS if name not in engine.options]
    if missing:
        raise ValueError("engine failed")
    options: dict = {"Threads": THREADS, "Hash": HASH_MB}
    for name, value in _PREFERRED_OPTIONS:
        if name in engine.options:
            options[name] = value
    try:
        engine.configure(options)
        engine.configure({"Clear Hash": None})
    except (chess.engine.EngineError, TimeoutError) as exc:
        raise ValueError("engine failed") from exc
    return sorted([*options, "Clear Hash"])


def _search(engine, board: chess.Board, depth: int) -> dict:
    try:
        engine.configure({"Clear Hash": None})
        info = engine.analyse(board, chess.engine.Limit(depth=depth))
    except (chess.engine.EngineError, chess.engine.EngineTerminatedError, TimeoutError) as exc:
        raise ValueError("engine failed") from exc
    if not isinstance(info, dict):
        raise ValueError("engine failed")
    cp, mate = _white_score(info)
    nodes = info.get("nodes")
    achieved = info.get("depth")
    if isinstance(nodes, bool) or not isinstance(nodes, int) or nodes < 0:
        raise ValueError("engine returned no node count")
    if isinstance(achieved, bool) or not isinstance(achieved, int):
        raise ValueError("engine returned no depth")
    pv = _pv(info)
    seldepth = info.get("seldepth")
    if isinstance(seldepth, bool) or not isinstance(seldepth, int):
        seldepth = None
    best = None
    if pv:
        move = chess.Move.from_uci(pv[0])
        if move in board.legal_moves:
            best = {"uci": pv[0], "san": board.san(move)}
    return {
        "white_cp": cp,
        "white_mate": mate,
        "nodes": nodes,
        "depth": achieved,
        "seldepth": seldepth,
        "best_move": best,
        "pv": pv,
    }


def _white_score(info: dict) -> tuple[int | None, int | None]:
    score = info.get("score")
    if score is None:
        raise ValueError("engine returned no score")
    white = score.white()
    cp = white.score(mate_score=None)
    mate = white.mate()
    if cp is not None and (isinstance(cp, bool) or not isinstance(cp, int)):
        raise ValueError("engine returned no score")
    if mate is not None and (isinstance(mate, bool) or not isinstance(mate, int)):
        raise ValueError("engine returned no score")
    return cp, mate


def _pv(info: dict) -> list[str]:
    moves = []
    for move in info.get("pv") or []:
        if not isinstance(move, chess.Move):
            continue
        moves.append(move.uci())
        if len(moves) == PV_LIMIT:
            break
    return moves
