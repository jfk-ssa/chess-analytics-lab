"""Offline ADR 0116 frame v1: source labels and strictly pre-move features."""

import argparse
import json
import math
import random
from pathlib import Path
from typing import TypedDict

import chess
import duckdb

FEATURES = (
    "clock_before_seconds",
    "phase_proxy",
    "ply",
    "color",
    "opening_family",
    "material_balance",
)
SEED = 20261031
PIECE_VALUES = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
    chess.KING: 0,
}


class TrainingRow(TypedDict):
    provider: str
    game_id: str
    error_proxy: bool
    clock_before_seconds: float | None
    phase_proxy: str
    ply: int
    color: str
    opening_family: str | None
    material_balance: int


def opening_family(source_opening: str | None) -> str | None:
    """Match dbt nullif(trim(split_part(source_opening, ':', 1)), '')."""
    return (source_opening.split(":", 1)[0].strip() or None) if source_opening else None


def material_balance(board: chess.Board) -> int:
    """White minus Black in pawn units, before the candidate move."""
    return sum(
        value * (len(board.pieces(piece, chess.WHITE)) - len(board.pieces(piece, chess.BLACK)))
        for piece, value in PIECE_VALUES.items()
    )


def build_frame(warehouse: Path) -> list[TrainingRow]:
    """Replay complete sampled Standard games, including all unevaluable plies.

    Fail on gaps, duplicates, orphan moves, nonstandard games, or illegal UCI.
    The ingestion contract already excludes custom starting positions.
    """
    with duckdb.connect(str(warehouse), read_only=True) as connection:
        moves = connection.execute("""
            select m.provider, m.game_id, m.ply, m.color, m.uci,
                   m.clock_before_seconds, m.phase_proxy,
                   m.centipawn_deterioration, m.error_proxy,
                   g.source_opening, g.ply_count, g.variant
            from fact_move m left join fact_game g using (provider, game_id)
            order by m.provider, m.game_id, m.ply
        """).fetchall()
    frame: list[TrainingRow] = []
    previous: tuple[str, str] | None = None
    board = chess.Board()
    expected_count = 0
    for row in moves:
        provider, game_id, ply, color, uci = row[:5]
        clock, phase, deterioration, label, opening, ply_count, variant = row[5:]
        key = (provider, game_id)
        if key != previous:
            if previous is not None and board.ply() != expected_count:
                raise ValueError(f"incomplete replay: {previous}")
            board.reset()
            previous, expected_count = key, ply_count
        if (
            variant != "Standard"
            or ply != board.ply() + 1
            or color != ("white" if board.turn else "black")
        ):
            raise ValueError(f"invalid replay sequence: {key}, ply {ply}")
        move = chess.Move.from_uci(uci)
        if move not in board.legal_moves:
            raise ValueError(f"illegal UCI: {key}, ply {ply}: {uci}")
        if deterioration is not None:
            if type(label) is not bool:
                raise ValueError(f"missing error_proxy on evaluable move: {key}, ply {ply}")
            frame.append(
                TrainingRow(
                    provider=provider,
                    game_id=game_id,
                    error_proxy=label,
                    clock_before_seconds=clock,
                    phase_proxy=phase,
                    ply=ply,
                    color=color,
                    opening_family=opening_family(opening),
                    material_balance=material_balance(board),
                )
            )
        board.push(move)
    if board.ply() != expected_count:
        raise ValueError(f"incomplete replay: {previous}")
    if not frame:
        raise ValueError("no evaluable moves")
    return frame


def feature_matrix(rows: list[TrainingRow]) -> list[dict[str, str | float | int]]:
    """Allowlist only; identifiers, labels, UCI and annotations cannot enter X."""
    return [
        {
            "clock_before_seconds": row["clock_before_seconds"]
            if row["clock_before_seconds"] is not None
            else math.nan,
            "phase_proxy": row["phase_proxy"],
            "ply": row["ply"],
            "color": row["color"],
            "opening_family": row["opening_family"] or "__missing__",
            "material_balance": row["material_balance"],
        }
        for row in rows
    ]


def grouped_split(
    rows: list[TrainingRow],
    *,
    test_fraction: float = 0.25,
    seed: int = SEED,
) -> tuple[list[TrainingRow], list[TrainingRow]]:
    """Split whole game IDs without consulting labels; preserve input row order."""
    games = sorted({row["game_id"] for row in rows})
    if len(games) < 2 or not 0 < test_fraction < 1:
        raise ValueError("split needs at least two games and 0 < test_fraction < 1")
    random.Random(seed).shuffle(games)
    test = set(games[: min(len(games) - 1, math.ceil(len(games) * test_fraction))])
    return (
        [row for row in rows if row["game_id"] not in test],
        [row for row in rows if row["game_id"] in test],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("warehouse", type=Path)
    parser.add_argument("output", type=Path, help="local frame JSON, e.g. work/mistake-frame.json")
    args = parser.parse_args()
    frame = build_frame(args.warehouse)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(frame, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
