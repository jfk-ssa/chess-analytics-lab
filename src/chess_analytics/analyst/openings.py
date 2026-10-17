"""Observed White continuations from local visit shards or a ranking report.

Nothing here downloads a corpus. A missing project config is an unavailable
result. A present config that fails its hash check is an error.
"""

import json
import re
from pathlib import Path

import chess
import duckdb

from chess_analytics.analyst.positions import parse_position, position_id, position_key
from chess_analytics.analyst.tool_catalog import (
    CONTINUATION_RETURN_LIMIT,
    MAX_MOVE_PREFIX,
    OPENING_COHORTS,
)
from chess_analytics.common import digest

SMALL_SNAPSHOT_HASH_BYTES = 8_000_000
_SHA256 = re.compile(r"[0-9a-f]{64}")
_ARTIFACT = re.compile(r"[A-Za-z0-9_.-]+")
_SHARD = re.compile(r"visits-\d{2}\.parquet")
_SNAPSHOT = re.compile(r"[0-9a-f]{24}")
_LIMITS = (
    "White decisions in the configured opening window only.",
    "Each game counts once, at its earliest visit to the position.",
    "Observed frequency is not move quality.",
)
_SHARD_SQL = """
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


def position_continuations(
    project: Path,
    dataset_id: str,
    cohort: str | None = None,
    fen: str | None = None,
    moves: list[str] | None = None,
) -> dict:
    board = parse_position(fen, moves, max_moves=MAX_MOVE_PREFIX)
    lookup = observed_moves(project, board, cohort)
    shown = lookup["moves"][:CONTINUATION_RETURN_LIMIT]
    position_games = lookup["position_games"]
    cohort_games = lookup["cohort_games"]
    return {
        "dataset_id": dataset_id,
        "available": lookup["available"],
        "reason": lookup["reason"],
        "source_kind": lookup["source_kind"],
        "source_sha256": lookup["source_sha256"],
        "visit_snapshot_id": lookup["visit_snapshot_id"],
        "cohort": lookup["cohort"],
        "fen": board.fen(),
        "position_key": lookup["position_key"],
        "position_id": lookup["position_id"],
        "position_games": position_games,
        "cohort_games": cohort_games,
        "frequency": _rate(position_games, cohort_games),
        "next_move_games": lookup["next_move_games"],
        "continuations": shown,
        "truncated": len(lookup["moves"]) > CONTINUATION_RETURN_LIMIT,
        "window": lookup["window"],
        "limits": list(_LIMITS),
    }


def observed_moves(project: Path, board: chess.Board, cohort: str | None) -> dict:
    """All observed next moves, not only the published top of the ranking."""
    if cohort not in OPENING_COHORTS:
        raise ValueError("unsupported opening cohort")
    key = position_key(board)
    identity = position_id(key)
    if board.turn != chess.WHITE:
        return _empty(key, identity, cohort, configured=True, reason="not_white_to_move")
    config = _opening_config(project)
    if config is None:
        return _empty(
            key, identity, cohort, configured=False, reason="opening_source_not_configured"
        )
    if config["kind"] == "visit_shards":
        return _from_shards(config, key, identity, cohort)
    return _from_report(config, key, identity, cohort)


def _empty(key: str, identity: str, cohort: str, *, configured: bool, reason: str) -> dict:
    return {
        "configured": configured,
        "available": False,
        "reason": reason,
        "source_kind": None,
        "source_sha256": None,
        "visit_snapshot_id": None,
        "cohort": cohort,
        "position_key": key,
        "position_id": identity,
        "position_games": 0 if configured else None,
        "cohort_games": None,
        "next_move_games": 0 if configured else None,
        "moves": [],
        "by_uci": {},
        "window": None,
    }


def _from_shards(config: dict, key: str, identity: str, cohort: str) -> dict:
    directory = config["path"]
    manifest = _manifest(directory, config["sha256"])
    snapshot = manifest.get("snapshot_id")
    if not isinstance(snapshot, str) or _SNAPSHOT.fullmatch(snapshot) is None:
        raise ValueError("opening visit manifest is invalid")
    shards = _shard_paths(directory, manifest)
    cohort_games = _cohort_games(manifest, cohort)
    with duckdb.connect() as db:
        db.execute("set memory_limit='256MB'")
        db.execute("set threads=1")
        rows = db.execute(_SHARD_SQL, [[str(path) for path in shards], cohort, identity]).fetchall()
    moves = _moves_from_rows(chess.Board(key + " 0 1"), rows)
    position_games = sum(count for _, count in rows)
    return _found(
        key,
        identity,
        cohort,
        source_kind="visit_shards",
        source_sha256=config["sha256"],
        visit_snapshot_id=snapshot,
        position_games=position_games,
        cohort_games=cohort_games,
        moves=moves,
        window=_window(manifest),
        absent_reason="position_not_observed",
    )


def _from_report(config: dict, key: str, identity: str, cohort: str) -> dict:
    path = config["path"]
    if digest(path) != config["sha256"]:
        raise ValueError("opening ranking report hash mismatch")
    try:
        report = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError("opening ranking report is invalid") from exc
    if not isinstance(report, dict) or report.get("kind") != "observed_white_opening_positions":
        raise ValueError("opening ranking report is invalid")
    cohorts = report.get("cohorts")
    if not isinstance(cohorts, dict) or not isinstance(cohorts.get(cohort), dict):
        raise ValueError("opening cohort is not in the ranking report")
    view = cohorts[cohort].get("views", {}).get("all")
    if not isinstance(view, dict) or not isinstance(view.get("positions"), dict):
        raise ValueError("opening ranking report is invalid")
    detail = _report_position(view["positions"], key, identity)
    cohort_games = view.get("denominator_games")
    if isinstance(cohort_games, bool) or not isinstance(cohort_games, int):
        raise ValueError("opening ranking report is invalid")
    snapshot = report.get("visit_snapshot_id")
    if snapshot is not None and not isinstance(snapshot, str):
        raise ValueError("opening ranking report is invalid")
    moves = [] if detail is None else _report_moves(detail)
    position_games = 0 if detail is None else _report_games(detail)
    return _found(
        key,
        identity,
        cohort,
        source_kind="ranking_report",
        source_sha256=config["sha256"],
        visit_snapshot_id=snapshot,
        position_games=position_games,
        cohort_games=cohort_games,
        moves=moves,
        window=_window(report),
        absent_reason="position_not_in_published_rankings",
    )


def _found(
    key: str,
    identity: str,
    cohort: str,
    *,
    source_kind: str,
    source_sha256: str,
    visit_snapshot_id: str | None,
    position_games: int,
    cohort_games: int,
    moves: list[dict],
    window: dict | None,
    absent_reason: str,
) -> dict:
    available = position_games > 0
    return {
        "configured": True,
        "available": available,
        "reason": None if available else absent_reason,
        "source_kind": source_kind,
        "source_sha256": source_sha256,
        "visit_snapshot_id": visit_snapshot_id,
        "cohort": cohort,
        "position_key": key,
        "position_id": identity,
        "position_games": position_games,
        "cohort_games": cohort_games,
        "next_move_games": sum(item["games"] for item in moves),
        "moves": moves,
        "by_uci": {item["uci"]: item["games"] for item in moves},
        "window": window,
    }


def _moves_from_rows(board: chess.Board, rows: list[tuple]) -> list[dict]:
    counted = []
    position_games = sum(int(count) for _, count in rows)
    for move, count in rows:
        games = int(count)
        if move is None or move == "":
            continue
        if not isinstance(move, str):
            raise ValueError("opening visit shard is invalid")
        parsed = _legal(board, move)
        counted.append(_move_row(board, parsed, games, position_games))
    return sorted(counted, key=lambda item: (-item["games"], item["uci"]))


def _report_position(positions: dict, key: str, identity: str) -> dict | None:
    detail = positions.get(identity)
    if isinstance(detail, dict):
        return detail
    for value in positions.values():
        if isinstance(value, dict) and value.get("position_key") == key:
            return value
    return None


def _report_games(detail: dict) -> int:
    games = detail.get("games")
    if isinstance(games, bool) or not isinstance(games, int) or games < 0:
        raise ValueError("opening ranking report is invalid")
    return games


def _report_moves(detail: dict) -> list[dict]:
    raw = detail.get("continuations")
    if not isinstance(raw, list):
        raise ValueError("opening ranking report is invalid")
    board = chess.Board(str(detail.get("position_key")) + " 0 1")
    position_games = _report_games(detail)
    counted = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("opening ranking report is invalid")
        games = item.get("games")
        uci = item.get("uci")
        if isinstance(games, bool) or not isinstance(games, int) or not isinstance(uci, str):
            raise ValueError("opening ranking report is invalid")
        parsed = _legal(board, uci)
        counted.append(_move_row(board, parsed, games, position_games))
    return sorted(counted, key=lambda item: (-item["games"], item["uci"]))


def _legal(board: chess.Board, uci: str) -> chess.Move:
    try:
        move = chess.Move.from_uci(uci)
    except ValueError as exc:
        raise ValueError("observed continuation is not legal") from exc
    if move not in board.legal_moves:
        raise ValueError("observed continuation is not legal")
    return move


def _move_row(board: chess.Board, move: chess.Move, games: int, position_games: int) -> dict:
    return {
        "uci": move.uci(),
        "san": board.san(move),
        "games": games,
        "share_of_position_games": _rate(games, position_games),
    }


def _rate(numerator: int | None, denominator: int | None) -> float | None:
    if numerator is None or not denominator:
        return None
    return numerator / denominator


def _window(payload: dict) -> dict | None:
    plan = payload.get("plan")
    if not isinstance(plan, dict):
        return None
    if plan.get("learner_color") not in (None, "white"):
        raise ValueError("opening visits are not white decisions")
    return {
        "learner_color": plan.get("learner_color"),
        "min_ply": plan.get("min_ply"),
        "max_ply": plan.get("max_ply"),
    }


def _cohort_games(manifest: dict, cohort: str) -> int:
    sources = manifest.get("training_sources")
    if not isinstance(sources, list):
        raise ValueError("opening visit manifest is invalid")
    total = 0
    found = False
    for source in sources:
        if not isinstance(source, dict) or source.get("cohort") != cohort:
            continue
        games = source.get("games")
        if isinstance(games, bool) or not isinstance(games, int) or games < 0:
            raise ValueError("opening visit manifest is invalid")
        total += games
        found = True
    if not found:
        raise ValueError("opening cohort is not in the visit manifest")
    return total


def _manifest(directory: Path, expected: str) -> dict:
    path = directory / "manifest.json"
    if not path.is_file():
        raise ValueError("opening visit manifest is missing")
    if digest(path) != expected:
        raise ValueError("opening visit manifest hash mismatch")
    try:
        manifest = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError("opening visit manifest is invalid") from exc
    if not isinstance(manifest, dict) or manifest.get("kind") != "checked_white_opening_visits":
        raise ValueError("opening visit manifest is invalid")
    return manifest


def _shard_paths(directory: Path, manifest: dict) -> list[Path]:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict) or not artifacts:
        raise ValueError("opening visit manifest is invalid")
    root = directory.resolve()
    shards = []
    total = 0
    for name, _expected in artifacts.items():
        if not isinstance(name, str) or _ARTIFACT.fullmatch(name) is None:
            raise ValueError("opening visit manifest is invalid")
        path = (root / name).resolve()
        if path.parent != root or not path.is_file():
            raise ValueError("opening visit artifact is missing")
        if _SHARD.fullmatch(name):
            shards.append(path)
            total += path.stat().st_size
    if not shards:
        raise ValueError("opening visit shards are missing")
    if total <= SMALL_SNAPSHOT_HASH_BYTES:
        for name, expected in artifacts.items():
            path = root / name
            if not isinstance(expected, str) or digest(path) != expected:
                raise ValueError("opening visit artifact hash mismatch")
    shards.sort()
    return shards


def _opening_config(project: Path) -> dict | None:
    path = project / "config" / "opening-visits.json"
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError("opening config is invalid") from exc
    if not isinstance(payload, dict) or payload.get("version") != "1":
        raise ValueError("opening config is invalid")
    kind = payload.get("kind")
    if kind == "visit_shards" and set(payload) == {
        "version",
        "kind",
        "snapshot_dir",
        "manifest_sha256",
    }:
        directory = _resolve(project, payload["snapshot_dir"])
        if not directory.is_dir():
            raise ValueError("opening visit snapshot is missing")
        return {"kind": kind, "path": directory, "sha256": _sha(payload["manifest_sha256"])}
    if kind == "ranking_report" and set(payload) == {
        "version",
        "kind",
        "report_path",
        "report_sha256",
    }:
        report = _resolve(project, payload["report_path"])
        if not report.is_file():
            raise ValueError("opening ranking report is missing")
        return {"kind": kind, "path": report, "sha256": _sha(payload["report_sha256"])}
    raise ValueError("opening config is invalid")


def _resolve(project: Path, raw) -> Path:
    if not isinstance(raw, str) or not raw or "\x00" in raw:
        raise ValueError("opening config is invalid")
    path = Path(raw)
    if not path.is_absolute():
        path = project / path
    return path.resolve()


def _sha(value) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError("opening config is invalid")
    return value
