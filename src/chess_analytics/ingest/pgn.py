"""Lichess export framing v1: Event starts a record, bounded before parsing.

This is deliberately not a general PGN import service. Unsupported framing fails
closed. Original records and headers remain available for quarantine diagnosis.
"""

import io
import json
import re
from contextlib import contextmanager
from datetime import datetime

import chess
import chess.pgn
import zstandard

from chess_analytics.common import hash_json


class QuietGameBuilder(chess.pgn.GameBuilder):
    def handle_error(self, error):
        # Retain the source in quarantine instead of logging player names to the terminal.
        self.game.errors.append(error)


@contextmanager
def source_stream(path):
    with path.open("rb") as raw:
        if path.suffix == ".zst":
            with zstandard.ZstdDecompressor().stream_reader(raw) as reader:
                yield io.BufferedReader(reader)
        else:
            yield raw


def records(path, plan):
    total, size, ordinal = 0, 0, 0
    lines = []
    with source_stream(path) as f:
        while line := f.readline(plan["max_record_bytes"] + 1):
            total += len(line)
            if total > plan["max_decompressed_bytes"]:
                raise ValueError("decompressed byte limit exceeded")
            if line.startswith(b'[Event "') and lines:
                ordinal += 1
                if ordinal > plan["max_games"]:
                    raise ValueError("complete archive exceeds game limit")
                yield ordinal, b"".join(lines).decode("utf-8"), total - len(line)
                lines, size = [], 0
            if not lines and not line.strip():
                continue
            if not lines and not line.startswith(b'[Event "'):
                raise ValueError("unsupported PGN framing: expected Event header")
            size += len(line)
            if size > plan["max_record_bytes"]:
                raise ValueError("single PGN record exceeds byte limit")
            lines.append(line)
        if lines:
            ordinal += 1
            if ordinal > plan["max_games"]:
                raise ValueError("complete archive exceeds game limit")
            yield ordinal, b"".join(lines).decode("utf-8"), total


def normalize(raw, ordinal):
    headers = {}
    body_lines = []
    body_started = False
    for line in raw.splitlines():
        if line.startswith("[") and not body_started:
            match = re.fullmatch(r'\[(\w+) "((?:[^"\\]|\\.)*)"\]', line)
            if not match or match[1] in headers:
                return "quarantine", "malformed_header", None
            headers[match[1]] = match[2]
        elif line.strip():
            body_started = True
            body_lines.append(line)
    if headers.get("Variant", "Standard") != "Standard":
        return "excluded", "unsupported_variant", None
    if not headers.get("Event", "").startswith("Rated "):
        return "excluded", "not_rated", None
    if headers.get("SetUp", "0") != "0" or "FEN" in headers:
        return "excluded", "nonstandard_start", None
    site = re.fullmatch(r"https?://lichess\.org/([A-Za-z0-9]{8})", headers.get("Site", ""))
    if not site or headers.get("Result") not in {"1-0", "0-1", "1/2-1/2", "*"}:
        return "quarantine", "required_header", None
    # Reject the forgiving parser's acceptance of a truncated trailing game.
    body = re.sub(r"\{[^}]*\}|;[^\n]*", " ", "\n".join(body_lines), flags=re.S).strip()
    if not body or body.split()[-1] != headers["Result"]:
        return "quarantine", "missing_or_mismatched_termination", None
    game = chess.pgn.read_game(io.StringIO(raw), Visitor=QuietGameBuilder)
    if game is None or game.errors:
        return "quarantine", "illegal_or_malformed_moves", None
    board = game.board()
    moves = []
    for move in game.mainline_moves():
        if move not in board.legal_moves:
            return "quarantine", "illegal_or_malformed_moves", None
        moves.append(move.uci())
        board.push(move)
    utc_date = headers.get("UTCDate")
    if utc_date and "?" in utc_date:
        utc_date = None
    utc_time = headers.get("UTCTime")
    played_at = None
    try:
        date = datetime.strptime(utc_date, "%Y.%m.%d").date().isoformat() if utc_date else None
        if date and utc_time and "?" not in utc_time:
            played_at = datetime.strptime(f"{date} {utc_time}", "%Y-%m-%d %H:%M:%S")
            played_at = played_at.isoformat() + "+00:00"
    except ValueError:
        return "quarantine", "invalid_utc", None
    tc = headers.get("TimeControl")
    tc_match = re.fullmatch(r"(\d+)\+(\d+)", tc or "")
    ratings = []
    for color in ("White", "Black"):
        value = headers.get(color + "Elo", "?")
        if value not in {"?", "-", ""} and not value.isdigit():
            return "quarantine", "invalid_rating", None
        ratings.append(int(value) if value.isdigit() else None)
    result = headers["Result"]
    score = {"1-0": 1.0, "0-1": 0.0, "1/2-1/2": 0.5, "*": None}[result]
    row = {
        "provider": "lichess",
        "game_id": site[1],
        "source_ordinal": ordinal,
        "result": result,
        "rated": True,
        "variant": "Standard",
        "utc_date": date,
        "played_at": played_at,
        "timestamp_precision": "second" if played_at else ("date" if date else "unknown"),
        "time_control": tc,
        "base_seconds": int(tc_match[1]) if tc_match else None,
        "increment_seconds": int(tc_match[2]) if tc_match else None,
        "source_opening": headers.get("Opening"),
        "source_eco": headers.get("ECO"),
        "termination": headers.get("Termination"),
        "marked_bot": any(headers.get(c + "Title") == "BOT" for c in ("White", "Black")),
        "ply_count": len(moves),
        "headers_json": json.dumps(headers, sort_keys=True),
        "record_fingerprint": hash_json({"pgn": raw.strip()}),
    }
    players = []
    for index, color in enumerate(("white", "black")):
        name = headers.get(color.title())
        players.append(
            {
                "provider": "lichess",
                "game_id": site[1],
                "color": color,
                "player_key": (
                    name.lower()
                    if isinstance(name, str) and name not in {"?", "Anonymous"}
                    else None
                ),
                "rating": ratings[index],
                "opponent_rating": ratings[1 - index],
                "score": score if index == 0 or score is None else 1 - score,
            }
        )
    return "accepted", None, (row, players)
