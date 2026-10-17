"""Validated position input for engine and opening tools. No engine is started here."""

import hashlib
import re

import chess

MAX_FEN_LENGTH = 128
_UCI = re.compile(r"[a-h][1-8][a-h][1-8][qrbn]?")


def position_key(board: chess.Board) -> str:
    """First four FEN fields, with en passant only when a capture is legal.

    This is the opening-visit identity `standard-fen-first-four-legal-ep-1.0`.
    """
    return " ".join(board.fen(en_passant="legal").split()[:4])


def position_id(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()[:24]


def parse_position(fen: str | None, moves: list[str] | None, *, max_moves: int) -> chess.Board:
    """Accept one FEN or one UCI prefix from the start position, never both."""
    if (fen is None) == (moves is None):
        raise ValueError("provide a fen or a move prefix")
    if fen is not None:
        return _board_from_fen(fen)
    return _board_from_moves(moves, max_moves)


def _board_from_fen(fen: str) -> chess.Board:
    if (
        not isinstance(fen, str)
        or not 1 <= len(fen) <= MAX_FEN_LENGTH
        or any(char in fen for char in "\n\r")
    ):
        raise ValueError("invalid fen")
    fields = fen.split()
    if len(fields) == 4:
        fen = fen + " 0 1"
    elif len(fields) != 6:
        raise ValueError("invalid fen")
    try:
        return chess.Board(fen)
    except ValueError as exc:
        raise ValueError("invalid fen") from exc


def _board_from_moves(moves: list[str] | None, max_moves: int) -> chess.Board:
    if not isinstance(moves, list) or not 1 <= len(moves) <= max_moves:
        raise ValueError("invalid move prefix")
    board = chess.Board()
    for move in moves:
        if not isinstance(move, str) or _UCI.fullmatch(move) is None:
            raise ValueError("invalid move prefix")
        try:
            parsed = chess.Move.from_uci(move)
        except ValueError as exc:
            raise ValueError("invalid move prefix") from exc
        if parsed not in board.legal_moves:
            raise ValueError("illegal move prefix")
        board.push(parsed)
    return board
