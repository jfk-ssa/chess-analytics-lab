#!/usr/bin/env python3
"""Deterministic UCI stand-in. No network and no time-based scores."""

import hashlib
import sys

import chess


def _cp(fen: str) -> int:
    digest = hashlib.sha256(fen.encode()).hexdigest()
    return int(digest[:4], 16) % 201 - 100


def _best(board: chess.Board) -> str | None:
    legal = sorted(board.legal_moves, key=lambda move: move.uci())
    if not legal:
        return None
    return legal[0].uci()


def _board(command: str) -> chess.Board:
    if command.startswith("position fen "):
        body = command.removeprefix("position fen ")
        fen, _, tail = body.partition(" moves ")
        board = chess.Board(fen)
        if tail:
            for uci in tail.split():
                board.push_uci(uci)
        return board
    board = chess.Board()
    if " moves " in command:
        for uci in command.split(" moves ", 1)[1].split():
            board.push_uci(uci)
    return board


def _depth(command: str) -> int:
    parts = command.split()
    if "depth" in parts:
        return int(parts[parts.index("depth") + 1])
    return 1


def main() -> int:
    position = "position startpos"
    while True:
        line = sys.stdin.readline()
        if not line:
            return 0
        text = line.strip()
        if text == "uci":
            print("id name Fake Engine 1.0", flush=True)
            print("id author chess-analytics-lab-tests", flush=True)
            print("option name Threads type spin default 1 min 1 max 512", flush=True)
            print("option name Hash type spin default 16 min 1 max 1024", flush=True)
            print("option name Clear Hash type button", flush=True)
            print("option name UCI_AnalyseMode type check default false", flush=True)
            print("option name UCI_LimitStrength type check default false", flush=True)
            print("option name Use NNUE type check default true", flush=True)
            print("uciok", flush=True)
        elif text == "isready":
            print("readyok", flush=True)
        elif text == "quit":
            return 0
        elif text.startswith("position "):
            position = text
        elif text.startswith("go"):
            board = _board(position)
            best = _best(board)
            depth = _depth(text)
            if best is None:
                print(f"info depth {depth} seldepth {depth} score mate 0 nodes 17", flush=True)
                print("bestmove (none)", flush=True)
            else:
                cp = _cp(board.fen())
                print(
                    f"info depth {depth} seldepth {depth} score cp {cp} nodes 17 pv {best}",
                    flush=True,
                )
                print(f"bestmove {best}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
