"""Independent Python normalization for imported-game/browser replay parity.

This leaves the frozen Lichess corpus normalizer unchanged. Callers supply a
parsed game; file framing, browser resource limits and session storage are separate.
"""

import hashlib
import json
import re
import unicodedata
from datetime import date
from typing import TextIO
from urllib.parse import urlsplit
from weakref import WeakKeyDictionary

import chess
import chess.pgn


def folded(value: str) -> str:
    return unicodedata.normalize("NFC", value).lower()


def hashed(value: object) -> str:
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()


def provider_identity(headers: chess.pgn.Headers) -> tuple[str, str | None]:
    found = []
    for value in (headers.get("Site"), headers.get("Link")):
        if not value:
            continue
        brand = folded(value.strip())
        if brand in {"chess.com", "www.chess.com"}:
            found.append(("chesscom", None))
        if brand in {"lichess.org", "www.lichess.org"}:
            found.append(("lichess", None))
        try:
            parsed = urlsplit(value)
        except ValueError:
            continue
        if parsed.scheme not in {"http", "https"}:
            continue
        if parsed.hostname in {"chess.com", "www.chess.com"}:
            match = re.fullmatch(r"/game/(live|daily)/(\d+)/?", parsed.path)
            found.append(("chesscom", f"{match[1]}:{match[2]}" if match else None))
        if parsed.hostname in {"lichess.org", "www.lichess.org"}:
            match = re.fullmatch(
                r"/([A-Za-z0-9]{8})(?:[A-Za-z0-9]{4})?(?:/(?:white|black))?/?", parsed.path
            )
            found.append(("lichess", match[1] if match else None))
    if len({provider for provider, _ in found}) > 1:
        raise ValueError("conflicting_provider_headers")
    ids = {identifier for _, identifier in found if identifier}
    if len(ids) > 1:
        raise ValueError("conflicting_game_id_headers")
    return found[0][0] if found else "pgn", next(iter(ids), None)


def import_date(headers: chess.pgn.Headers) -> str | None:
    value = headers.get("UTCDate") or headers.get("Date", "")
    try:
        if not re.fullmatch(r"\d{4}\.\d{2}\.\d{2}", value):
            return None
        return date.fromisoformat(value.replace(".", "-")).isoformat()
    except ValueError:
        return None


_RESULTS = frozenset({"1-0", "0-1", "1/2-1/2"})
# python-chess keeps a Result header and drops a disagreeing movetext token.
_RECORDED: WeakKeyDictionary[chess.pgn.Game, tuple[bool, str | None, str | None]] = (
    WeakKeyDictionary()
)


class ImportGameBuilder(chess.pgn.GameBuilder):
    """Remember the Result header and the movetext result before either is dropped."""

    def begin_game(self) -> None:
        super().begin_game()
        self._result_header_present = False
        self._result_header: str | None = None
        self._movetext_result: str | None = None

    def visit_header(self, tagname: str, tagvalue: str) -> None:
        super().visit_header(tagname, tagvalue)
        if tagname == "Result":
            self._result_header_present = True
            self._result_header = tagvalue

    def visit_result(self, result: str) -> None:
        self._movetext_result = result
        super().visit_result(result)

    def result(self) -> chess.pgn.Game:
        game = super().result()
        _RECORDED[game] = (
            self._result_header_present,
            self._result_header,
            self._movetext_result,
        )
        return game


def read_imported_game(handle: TextIO) -> chess.pgn.Game | None:
    """Parse one game and retain both result spellings for conflict checks."""
    return chess.pgn.read_game(handle, Visitor=ImportGameBuilder)


def completed_result(game: chess.pgn.Game) -> str:
    recorded = _RECORDED.get(game)
    if recorded is None:
        result = game.headers.get("Result")
        if result not in _RESULTS:
            raise ValueError("unfinished_or_missing_result")
        return result
    header_present, header, movetext = recorded
    if movetext not in _RESULTS:
        raise ValueError("unfinished_or_missing_result")
    if header_present and header != movetext:
        raise ValueError("conflicting_result")
    return movetext


def rated_value(headers: chess.pgn.Headers) -> bool | None:
    rated = folded(headers.get("Rated", ""))
    if rated in {"true", "false"}:
        return rated == "true"
    event = headers.get("Event", "")
    if re.match(r"rated\b", event, re.IGNORECASE):
        return True
    if re.match(r"(casual|unrated)\b", event, re.IGNORECASE):
        return False
    return None


def normalize_game(game: chess.pgn.Game) -> dict:
    headers = game.headers
    if game.errors:
        raise ValueError("illegal_or_invalid_mainline")
    if folded(headers.get("Variant", "Standard")) != "standard":
        raise ValueError("unsupported_variant")
    if headers.get("FEN") or headers.get("SetUp", "0") != "0":
        raise ValueError("unsupported_setup")
    result = completed_result(game)
    # Trim and NFC-normalize before rejecting "?" or over-long names. The stored
    # name is that normalized form; surrounding spaces do not make "?" a player.
    white, black = (
        unicodedata.normalize("NFC", headers.get(c, "").strip()) for c in ("White", "Black")
    )
    if any(not name or name == "?" or len(name) > 200 for name in (white, black)):
        raise ValueError("missing_or_invalid_players")
    board = chess.Board()
    seen = {" ".join(board.fen(en_passant="legal").split()[:4])}
    moves, sans, visits = [], [], []
    repeated = False
    for ply, move in enumerate(game.mainline_moves(), 1):
        sans.append((f"{(ply + 1) // 2}." if ply % 2 else "") + board.san(move))
        board.push(move)
        moves.append(move.uci())
        if ply <= 20:
            key = " ".join(board.fen(en_passant="legal").split()[:4])
            repeated |= key in seen
            seen.add(key)
            if ply >= 6 and ply % 2 == 0:
                visits.append(
                    {
                        "ply": ply,
                        "id": hashlib.sha256(key.encode()).hexdigest()[:24],
                        "position_key": key,
                        "full_fen": board.fen(),
                        "route": " ".join(moves),
                        "route_has_repeat": repeated,
                        "san_route": " ".join(sans),
                    }
                )
    for visit in visits:
        visit["next_move"] = moves[visit["ply"]] if visit["ply"] < len(moves) else None
    provider, native_id = provider_identity(headers)
    played = import_date(headers)
    semantic = [folded(white), folded(black), played, moves]
    time_control = headers.get("TimeControl")
    return {
        "provider": provider,
        "nativeId": native_id,
        "id": native_id or "sha256:" + hashed(semantic),
        "fingerprint": hashed([folded(white), folded(black), moves, result]),
        "white": white,
        "black": black,
        "date": played,
        "result": result,
        "rated": rated_value(headers),
        "time_control": time_control if time_control not in {None, "", "*", "-"} else None,
        "plies": len(moves),
        "moves": moves,
        "visits": visits,
    }
