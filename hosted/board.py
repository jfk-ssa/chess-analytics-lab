"""Small board drawing for a published FEN. No python-chess and no network."""

from __future__ import annotations

from html import escape

_GLYPH = {
    "K": "♔",
    "Q": "♕",
    "R": "♖",
    "B": "♗",
    "N": "♘",
    "P": "♙",
    "k": "♚",
    "q": "♛",
    "r": "♜",
    "b": "♝",
    "n": "♞",
    "p": "♟",
}
_LIGHT = "#f7f4ea"
_DARK = "#c5d5cc"


def fen_svg(fen: str) -> str:
    """SVG board for the piece placement of a FEN. Raises if the board is not 8 ranks."""
    ranks = fen.split()[0].split("/")
    if len(ranks) != 8:
        raise ValueError("fen board is not 8 ranks")
    squares: list[str] = []
    pieces: list[str] = []
    for rank_index in range(8):
        for file_index in range(8):
            color = _LIGHT if (rank_index + file_index) % 2 == 0 else _DARK
            squares.append(
                f'<rect x="{file_index}" y="{rank_index}" width="1" height="1" fill="{color}"/>'
            )
    for rank_index, rank in enumerate(ranks):
        file_index = 0
        for character in rank:
            if character.isdigit():
                file_index += int(character)
                continue
            if character not in _GLYPH or file_index > 7:
                raise ValueError("fen board has a piece this drawer does not know")
            pieces.append(
                f'<text x="{file_index + 0.5}" y="{rank_index + 0.72}" text-anchor="middle" '
                f'font-size="0.72" fill="#203433">{_GLYPH[character]}</text>'
            )
            file_index += 1
        if file_index != 8:
            raise ValueError("fen rank does not cover eight files")
    body = "".join(squares) + "".join(pieces)
    svg = (
        '<svg class="cal-board" viewBox="0 0 8 8" role="img" '
        f'aria-label="{escape(fen)}">'
        f'<rect width="8" height="8" fill="{_LIGHT}"/>{body}</svg>'
    )
    return svg
