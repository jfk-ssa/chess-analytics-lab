"""Deterministic move sampling and source-annotation extraction."""

import hashlib
import io
import json
import re
from pathlib import Path

import chess.pgn
import duckdb

from chess_analytics.common import guard_disk
from chess_analytics.ingest.pgn import records

SITE = re.compile(r'^\[Site "https?://lichess\.org/([A-Za-z0-9]{8})"\]$', re.MULTILINE)
SAMPLE_MODULUS = 20


def selected(game_id: str, modulus: int = SAMPLE_MODULUS) -> bool:
    value = int.from_bytes(hashlib.sha256(game_id.encode()).digest()[:8], "big")
    return value % modulus == 0


def clock_bucket(seconds: float | None) -> str | None:
    if seconds is None or seconds < 0:
        return None
    if seconds < 10:
        return "under_10"
    if seconds < 30:
        return "10_to_29"
    if seconds < 60:
        return "30_to_59"
    return "60_plus"


def evaluation(node) -> tuple[int | None, int | None]:
    value = node.eval()
    if value is None:
        return None, None
    white = value.white()
    return white.score(), white.mate()


def move_rows(
    raw: str, game_id: str, base_seconds: int | None, increment_seconds: int | None
) -> list[dict]:
    game = chess.pgn.read_game(io.StringIO(raw))
    if game is None or game.errors:
        raise ValueError(f"previously accepted game did not replay: {game_id}")
    rows = []
    previous_evaluation = (None, None)
    same_side_clock: dict[str, float | None] = {"white": None, "black": None}
    for node in game.mainline():
        ply = node.ply()
        color = "white" if ply % 2 else "black"
        after_clock = node.clock()
        if after_clock is not None and after_clock < 0:
            after_clock = None
        if (
            after_clock is not None
            and increment_seconds == 0
            and base_seconds is not None
            and after_clock > base_seconds
        ):
            after_clock = None
        before_clock = same_side_clock[color]
        after_evaluation = evaluation(node)
        before_cp, before_mate = previous_evaluation
        after_cp, after_mate = after_evaluation
        deterioration = None
        if before_cp is not None and after_cp is not None:
            direction = 1 if color == "white" else -1
            deterioration = max(0, direction * (before_cp - after_cp))
        rows.append(
            {
                "provider": "lichess",
                "game_id": game_id,
                "ply": ply,
                "color": color,
                "uci": node.move.uci(),
                "clock_after_seconds": after_clock,
                "clock_before_seconds": before_clock,
                "clock_bucket": clock_bucket(before_clock),
                "eval_before_cp_white": before_cp,
                "eval_after_cp_white": after_cp,
                "eval_before_mate_white": before_mate,
                "eval_after_mate_white": after_mate,
                "centipawn_deterioration": deterioration,
                "error_proxy": deterioration >= 200 if deterioration is not None else None,
                "phase_proxy": "early_ply"
                if ply <= 20
                else ("middle_ply" if ply <= 60 else "late_ply"),
            }
        )
        same_side_clock[color] = after_clock
        previous_evaluation = after_evaluation
    return rows


def write_sampled_moves(source: Path, snapshot: Path, target: Path, plan: dict, root: Path) -> dict:
    """Write only hash-selected accepted games, regardless of annotation coverage."""
    with duckdb.connect(str(snapshot / "warehouse.duckdb"), read_only=True) as connection:
        accepted = {
            game_id: (base, increment, ply_count)
            for game_id, base, increment, ply_count in connection.execute(
                "SELECT game_id, base_seconds, increment_seconds, ply_count FROM fact_game"
            ).fetchall()
        }
    target.parent.mkdir(parents=True, exist_ok=True)
    selected_games = 0
    zero_ply_games = 0
    row_count = 0
    expected_rows = 0
    processed_games: set[str] = set()
    write_batch = 16 * 1024 * 1024
    guard_disk(root, plan["max_generated_bytes"], write_batch)
    remaining = write_batch
    with target.open("w") as out:
        for _, raw, _ in records(source, plan):
            match = SITE.search(raw)
            if (
                not match
                or match[1] not in accepted
                or not selected(match[1])
                or match[1] in processed_games
            ):
                continue
            game_id = match[1]
            base, increment, ply_count = accepted[game_id]
            rows = move_rows(raw, game_id, base, increment)
            if len(rows) != ply_count:
                raise ValueError(f"selected game move count drift: {game_id}")
            processed_games.add(game_id)
            selected_games += 1
            zero_ply_games += not rows
            expected_rows += ply_count
            for row in rows:
                line = json.dumps(row, sort_keys=True) + "\n"
                size = len(line.encode())
                if size > remaining:
                    guard_disk(root, plan["max_generated_bytes"], write_batch)
                    remaining = write_batch
                out.write(line)
                remaining -= size
                row_count += 1
    if not selected_games or row_count != expected_rows:
        raise ValueError("move sample empty or incomplete")
    return {
        "selected_games": selected_games,
        "selected_zero_ply_games": zero_ply_games,
        "move_rows": row_count,
        "selection": "SHA256(game_id) first 8 bytes mod 20 == 0",
    }
