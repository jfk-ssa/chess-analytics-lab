"""Write the 100-game live-eval PGN. Seed 20261018. No random draws.

The seed names this specification. Re-running the script is a pure function of
the tables below and writes byte-identical UTF-8 with LF newlines. Game ids are
the first 100 lowercase hex ids that the warehouse move sampler keeps, matching
``chess_analytics.corpus.moves.selected``. Every line is a short legal game.
Names, ratings, and results are synthetic. No third-party game is copied.
"""

import io
from datetime import date, timedelta
from pathlib import Path

import chess.pgn

from chess_analytics.corpus.moves import selected

PROJECT = Path(__file__).resolve().parents[1]
DESTINATION = PROJECT / "tests/fixtures/live_eval_100.pgn"
SEED = 20261018
GAME_COUNT = 100
CLOCKS = (45, 50, 8, 6, 4, 3)
FAMILY_ENDS = (
    (18, "Sicilian Defense", "B20", ("e4", "c5", "Nf3", "d6", "d4", "cxd4")),
    (32, "French Defense", "C00", ("e4", "e6", "d4", "d5", "Nc3", "Nf6")),
    (42, "Italian Game", "C50", ("e4", "e5", "Nf3", "Nc6", "Bc4", "Bc5")),
    (52, "Ruy Lopez", "C60", ("e4", "e5", "Nf3", "Nc6", "Bb5", "a6")),
    (60, "Queen's Gambit", "D06", ("d4", "d5", "c4", "e6", "Nc3", "Nf6")),
    (68, "Caro-Kann Defense", "B10", ("e4", "c6", "d4", "d5", "Nc3", "dxe4")),
    (76, "English Opening", "A20", ("c4", "e5", "Nc3", "Nf6", "Nf3", "Nc6")),
    (82, "King's Indian Defense", "E60", ("d4", "Nf6", "c4", "g6", "Nc3", "Bg7")),
    (88, "Nimzo-Indian Defense", "E20", ("d4", "Nf6", "c4", "e6", "Nc3", "Bb4")),
    (93, "Scandinavian Defense", "B01", ("e4", "d5", "exd5", "Qxd5", "Nc3", "Qa5")),
    (97, "Pirc Defense", "B07", ("e4", "d6", "d4", "Nf6", "Nc3", "g6")),
    (100, "Alekhine Defense", "B02", ("e4", "Nf6", "e5", "Nd5", "d4", "d6")),
)
WHITE_ELO = {0: 1500, 1: 1550, 2: 1700, 3: 1450, 4: 1200}
TIME_CONTROL = {0: "180+2", 1: "300+0", 2: "600+5"}
RESULT = {0: "1-0", 1: "1/2-1/2", 2: "0-1"}


def family_row(index: int) -> tuple[str, str, tuple[str, ...]]:
    """Opening family, ECO code, and six SAN plies for this game index."""
    for end, name, eco, sans in FAMILY_ENDS:
        if index < end:
            return name, eco, sans
    raise ValueError(f"game index outside 0..{GAME_COUNT - 1}: {index}")


def sampler_ids(count: int) -> list[str]:
    """First ``count`` 8-hex ids kept by the move sampler. Search order is fixed."""
    found: list[str] = []
    number = 0
    while len(found) < count:
        game_id = f"{number:08x}"
        if selected(game_id):
            found.append(game_id)
        number += 1
        if number > 100_000:
            raise RuntimeError("sampler id search exceeded 100000")
    return found


def eval_pawns(index: int, ply: int) -> float | None:
    """White-perspective pawns after this ply, or None when the game has no evals.

    Kind 0 omits evals. Kind 1 is flat. Kind 2 drops 2.50 pawns on ply 3 and
    stays there, so only that white move is a 250 centipawn error. Kind 3 is
    flat until ply 6, so only that black move is a 250 centipawn error.
    """
    kind = index % 4
    if kind == 0:
        return None
    if kind == 1:
        return 0.0
    if kind == 2:
        return 0.0 if ply < 3 else -2.5
    return 2.5 if ply == 6 else 0.0


def _comment(seconds: int, pawns: float | None) -> str:
    clock = f"[%clk 0:00:{seconds:02d}]"
    if pawns is None:
        return "{" + clock + "}"
    return "{" + clock + f" [%eval {pawns:.2f}]" + "}"


def _movetext(index: int, sans: tuple[str, ...], result: str) -> str:
    chunks = []
    for ply, san in enumerate(sans, start=1):
        prefix = f"{(ply + 1) // 2}. " if ply % 2 else ""
        chunks.append(f"{prefix}{san} {_comment(CLOCKS[ply - 1], eval_pawns(index, ply))}")
    return " ".join(chunks) + f" {result}"


def event_name(index: int) -> str:
    """Rated speed from the Lichess estimate, base plus 40 times the increment.

    Under 180 seconds is Bullet, under 480 is Blitz, and the rest here is Rapid.
    60+0 is Bullet, 180+2 and 300+0 are Blitz, and 600+5 is Rapid.
    """
    control = TIME_CONTROL.get(index % 10, "60+0")
    base, increment = (int(part) for part in control.split("+"))
    estimated = base + 40 * increment
    if estimated < 180:
        speed = "Bullet"
    elif estimated < 480:
        speed = "Blitz"
    else:
        speed = "Rapid"
    return f"Rated {speed} synthetic live eval"


def render_game(index: int, game_id: str) -> str:
    """One rated standard game. Clocks stay in under_10 and 30_to_59 only."""
    name, eco, sans = family_row(index)
    white = WHITE_ELO[index % 5]
    result = RESULT[index % 3]
    played = date(2020, 1, 1) + timedelta(days=index)
    headers = (
        ("Event", event_name(index)),
        ("Site", f"https://lichess.org/{game_id}"),
        ("UTCDate", played.strftime("%Y.%m.%d")),
        ("White", f"FixtureLiveW{index:03d}"),
        ("Black", f"FixtureLiveB{index:03d}"),
        ("WhiteElo", str(white)),
        ("BlackElo", str(white + 20)),
        ("Result", result),
        ("TimeControl", TIME_CONTROL.get(index % 10, "60+0")),
        ("ECO", eco),
        ("Opening", f"{name}: Test Line"),
        ("Seed", str(SEED)),
    )
    lines = [f'[{key} "{value}"]' for key, value in headers]
    lines.append("")
    lines.append(_movetext(index, sans, result))
    return "\n".join(lines)


def render_pgn() -> str:
    """The full fixture, including a trailing newline and no carriage returns."""
    ids = sampler_ids(GAME_COUNT)
    body = "\n\n".join(render_game(index, ids[index]) for index in range(GAME_COUNT))
    return body + "\n"


def games_are_legal(text: str) -> int:
    """Raise if any game fails python-chess or the legal-move walk. Return the count."""
    handle = io.StringIO(text)
    count = 0
    while game := chess.pgn.read_game(handle):
        if game.errors:
            raise ValueError(f"illegal or malformed moves in game {count}")
        board = game.board()
        for move in game.mainline_moves():
            if move not in board.legal_moves:
                raise ValueError(f"illegal move in game {count}: {move}")
            board.push(move)
        count += 1
    if count != GAME_COUNT:
        raise ValueError(f"expected {GAME_COUNT} games, parsed {count}")
    return count


def main() -> None:
    text = render_pgn()
    games_are_legal(text)
    DESTINATION.write_text(text, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
