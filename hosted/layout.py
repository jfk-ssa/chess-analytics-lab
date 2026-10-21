"""Equal-width cards for the hosted dashboard.

The track list is ``repeat(auto-fill, minmax(min(100%, 256px), 1fr))``.
256px is 16rem at the CSS reference pixel. Streamlit sets the document
root to 14px, so a literal 16rem is 224px and three tracks fit in the
content box at a 768px viewport. 256px does not: one column at 390px,
two by two for four cards at 768px, and one row at 1280px. Every card
in a row shares that minimum. ``auto-fill`` keeps the empty track on a
short last row, so the leftover card stays the same width. The detail
nowraps the fraction and can break at `` · ``.
"""

from __future__ import annotations

import re
from html import escape

_MOVE_NUMBER = re.compile(r"\d+\.")

_TRACKS = "repeat(auto-fill,minmax(min(100%,256px),1fr))"
_OTHER_FLOOR = 10
_OTHER_LABEL = "other orders"


def equal_width_columns(count: int) -> str:
    """Return the shared track list for a row of ``count`` cards."""
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise ValueError("equal-width row needs at least one card")
    return _TRACKS


def equal_width_row(cards: list[tuple[str, str, str]]) -> str:
    """HTML for one row of cards. Each tuple is label, value, detail."""
    columns = equal_width_columns(len(cards))
    cells: list[str] = []
    for label, value, detail in cards:
        cells.append(
            '<div class="cal-card" style="min-width:0;width:100%;box-sizing:border-box;'
            "container-type:inline-size;background:#eaf1eb;border:1px solid #c5d5cc;"
            "border-radius:12px;padding:10px 8px;font-family:Inter,sans-serif;"
            'color:#203433;overflow:visible;overflow-wrap:normal;word-break:normal">'
            '<div class="cal-k" style="font-size:0.72rem;font-weight:600;'
            "line-height:1.3;overflow-wrap:normal;white-space:nowrap;"
            f'">{escape(label)}</div>'
            '<div class="cal-v" style="font-size:clamp(0.95rem,5.5cqi,1.45rem);'
            "font-weight:600;line-height:1.15;color:#116559;"
            "font-variant-numeric:tabular-nums;white-space:nowrap;"
            f'overflow-wrap:normal">{escape(value)}</div>'
            '<div class="cal-d" style="font-size:clamp(0.68rem,4cqi,0.82rem);'
            "line-height:1.35;color:#3d524c;overflow:visible;overflow-wrap:normal;"
            f'word-break:normal">{_detail_html(detail)}</div>'
            "</div>"
        )
    style = (
        "display:grid;"
        f"grid-template-columns:{columns};"
        "column-gap:12px;row-gap:12px;width:100%;align-items:stretch;margin:0 0 16px"
    )
    body = "".join(cells)
    return (
        f'<div class="cal-equal" data-equal-width="true" data-cards="{len(cards)}" '
        f'style="{style}">{body}</div>'
    )


def _detail_html(detail: str) -> str:
    """Nowrap each segment. A break is only at the `` · `` separator."""
    parts = str(detail).split(" · ")
    spans = [f'<span style="white-space:nowrap">{escape(part)}</span>' for part in parts]
    return " · ".join(spans)


def _split_title(title: str) -> tuple[str, str]:
    """Depth label, then the leading SAN. The separator is the card title's dot."""
    head, separator, line = str(title).partition(" · ")
    if not separator:
        return head, ""
    return head, line


def san_groups(san: str) -> list[str]:
    """One group per move number: ``1.e4 c5``, or a lone White move such as ``3.Bc4``."""
    tokens = [token for token in str(san).split() if token]
    groups: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        reply = tokens[index + 1] if index + 1 < len(tokens) else None
        if _MOVE_NUMBER.match(token) and reply is not None and not _MOVE_NUMBER.match(reply):
            groups.append(f"{token} {reply}")
            index += 2
        else:
            groups.append(token)
            index += 1
    return groups


def san_text(san: str) -> str:
    """Plain SAN. A pair stays together; a break is only between move numbers."""
    return " ".join(group.replace(" ", "\u00a0") for group in san_groups(san))


def display_title(title: str) -> str:
    """Group the SAN after the title separator. The depth label stays as written."""
    head, separator, line = str(title).partition(" · ")
    if not separator:
        return san_text(title)
    return f"{head}{separator}{san_text(line)}"


def _san_html(san: str) -> str:
    """One nowrap span per move pair, with a normal space between pairs."""
    spans = [
        '<span class="cal-ply" style="display:inline-block;white-space:nowrap">'
        f"{escape(group)}</span>"
        for group in san_groups(san)
    ]
    return " ".join(spans)


def _share_percent(part: int, total: int) -> str:
    if total <= 0:
        return "0"
    bounded = min(total, max(0, part))
    return f"{100 * bounded / total:.1f}"


def _count_track(counts: list[int]) -> str:
    """Column for the widest count. Tabular digits are about one ch each."""
    widest = max((len(f"{int(count):,}") for count in counts), default=1)
    return f"{max(widest, 6)}ch"


def _route_row(san: str, games: int, total: int, track: str) -> str:
    share = _share_percent(games, total)
    return (
        f'<div class="cal-route" style="display:grid;grid-template-columns:{track} minmax(0,1fr);'
        'column-gap:10px;row-gap:5px;align-items:start;line-height:1.55">'
        '<div class="cal-n" style="text-align:right;white-space:nowrap;'
        'font-variant-numeric:tabular-nums;font-weight:600;color:#116559">'
        f"{escape(f'{int(games):,}')}</div>"
        '<div class="cal-san" style="min-width:0;overflow-wrap:normal;word-break:normal">'
        f"{_san_html(san)}</div>"
        '<div class="cal-share" style="grid-column:1 / -1;height:3px;background:#d5e2da;'
        'border-radius:999px;overflow:hidden">'
        f'<div style="width:{share}%;height:100%;background:#116559;border-radius:999px"></div>'
        "</div></div>"
    )


def _other_row(games: int, total: int, track: str) -> str:
    """Muted remainder of position games the card does not list as SAN."""
    share = _share_percent(games, total)
    return (
        f'<div class="cal-route cal-other" style="display:grid;grid-template-columns:{track} '
        'minmax(0,1fr);column-gap:10px;row-gap:5px;align-items:start;line-height:1.55">'
        '<div class="cal-n" style="text-align:right;white-space:nowrap;'
        'font-variant-numeric:tabular-nums;font-weight:600;color:#5c726b">'
        f"{escape(f'{int(games):,}')}</div>"
        '<div class="cal-san" style="min-width:0;color:#5c726b;white-space:nowrap">'
        f"{escape(_OTHER_LABEL)}</div>"
        '<div class="cal-share" style="grid-column:1 / -1;height:3px;background:#d5e2da;'
        'border-radius:999px;overflow:hidden">'
        f'<div style="width:{share}%;height:100%;background:#5c726b;border-radius:999px"></div>'
        "</div></div>"
    )


def _order_label(item: dict, shown_count: int, remainder: int) -> str:
    """Distinct orders when the cube has that count, otherwise the rows shown.

    ``move_orders`` is the routes that cleared the floor. That is the
    position's distinct orders when those routes hold every game. A remainder
    includes orders the cube did not store, so the card says how many it lists.
    """
    stored = int(item["move_orders"]) if "move_orders" in item else None
    kept = int(item["kept_games"]) if "kept_games" in item else None
    total = int(item["games"])
    if remainder <= 0:
        count = shown_count
    elif kept is not None and kept == total and stored is not None:
        count = stored
    elif shown_count == 1:
        return "top 1 move order"
    else:
        return f"top {shown_count} move orders"
    if count == 1:
        return "1 move order"
    return f"{count} move orders"


def _visible_routes(item: dict) -> tuple[int, list[tuple[str, int]], str, str]:
    """Headline, rows, order label, and the note for a remainder under 10.

    The headline is the position total. Every share bar uses that total.
    The unlisted games are one ``other orders`` row when they add up to at
    least 10. A remainder of 1–9 stays off the rows. The note then says
    rarer orders are not shown, with no count.
    """
    shown = [(str(san), int(games)) for san, games in item["routes"]]
    shown_games = sum(games for _san, games in shown)
    total = int(item["games"])
    remainder = total - shown_games
    if remainder >= _OTHER_FLOOR:
        rows = [*shown, (_OTHER_LABEL, remainder)]
        note = ""
    else:
        rows = shown
        note = "rarer orders not shown" if remainder > 0 else ""
    return total, rows, _order_label(item, len(shown), remainder), note


def _route_rows(pairs: list[tuple[str, int]], total: int, track: str) -> str:
    rows: list[str] = []
    for san, games in pairs:
        if san == _OTHER_LABEL:
            rows.append(_other_row(games, total, track))
        else:
            rows.append(_route_row(san, games, total, track))
    return "".join(rows)


def transposition_cards(items: list[dict]) -> str:
    """Equal-width cards for transposing positions.

    Each item has ``title``, ``games``, ``move_orders``, and ``routes``.
    ``games`` is the position total. ``kept_games``, when present, is the
    routes the cube kept. ``title`` is ``After Black's move N · <SAN>``.
    The depth, the line, and the game count are separate rows. The line
    reserves two lines so sibling cards keep the count on the same row. A
    route is a ``(san, games)`` pair: the count column is the widest count,
    about six tabular characters, and the SAN wraps inside the second column.
    Share bars use the position total. Games the card does not list are an
    other-orders row when they add up to at least 10. A remainder of 1–9 is
    a caption, with no count.
    """
    columns = equal_width_columns(len(items))
    cells: list[str] = []
    for item in items:
        total, route_pairs, order_label, gap = _visible_routes(item)
        track = _count_track([games for _san, games in route_pairs])
        routes = _route_rows(route_pairs, total, track)
        depth, line = _split_title(str(item["title"]))
        gap_html = ""
        if gap:
            gap_html = (
                '<div class="cal-gap" style="margin-top:10px;font-size:0.78rem;'
                'line-height:1.3;color:#5c726b;white-space:nowrap">'
                f"{escape(gap)}</div>"
            )
        cells.append(
            '<div class="cal-card" style="min-width:0;width:100%;height:100%;'
            "box-sizing:border-box;display:flex;flex-direction:column;align-self:stretch;"
            "container-type:inline-size;background:#eaf1eb;border:1px solid #c5d5cc;"
            "border-radius:12px;padding:14px 12px;font-family:Inter,sans-serif;"
            'color:#203433;overflow-wrap:normal;word-break:normal">'
            '<div class="cal-head" style="display:flex;flex-direction:column;gap:8px">'
            '<div class="cal-k" style="font-size:0.72rem;font-weight:600;line-height:1.3;'
            'color:#5c726b;white-space:nowrap;overflow-wrap:normal">'
            f"{escape(depth)}</div>"
            '<div class="cal-line" style="font-size:0.95rem;font-weight:600;line-height:1.45;'
            'min-height:2.9em;overflow-wrap:normal;word-break:normal">'
            f"{_san_html(line)}</div>"
            '<div class="cal-stats" style="display:flex;align-items:baseline;'
            'justify-content:space-between;gap:12px">'
            '<div style="white-space:nowrap">'
            '<span class="cal-v" style="font-size:clamp(1.15rem,6cqi,1.6rem);'
            "font-weight:600;line-height:1.1;color:#116559;"
            'font-variant-numeric:tabular-nums;white-space:nowrap">'
            f"{escape(f'{total:,}')}</span>"
            '<span class="cal-games" style="font-size:0.78rem;color:#5c726b;'
            'white-space:nowrap"> games</span></div>'
            '<div class="cal-d" style="font-size:0.78rem;line-height:1.3;color:#3d524c;'
            f'white-space:nowrap">{escape(order_label)}</div></div></div>'
            '<div class="cal-routes" style="display:flex;flex-direction:column;gap:12px;'
            f'margin-top:14px">{routes}</div>{gap_html}</div>'
        )
    style = (
        "display:grid;"
        f"grid-template-columns:{columns};"
        "column-gap:12px;row-gap:12px;width:100%;align-items:stretch"
    )
    body = "".join(cells)
    return (
        f'<div class="cal-equal" data-equal-width="true" data-cards="{len(items)}" '
        f'style="{style}">{body}</div>'
    )
