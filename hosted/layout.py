"""Equal-width cards for the hosted dashboard.

The track list is ``repeat(auto-fit, minmax(min(100%, 256px), 1fr))``.
256px is 16rem at the CSS reference pixel. Streamlit sets the document
root to 14px, so a literal 16rem is 224px and three tracks fit in the
content box at a 768px viewport. 256px does not: one column at 390px,
two by two for four cards at 768px, and one row at 1280px. Every card
in a row shares that minimum. A short last row keeps the track width of
the row above; the leftover card does not grow into the empty cell.
"""

from __future__ import annotations

from html import escape

_TRACKS = "repeat(auto-fit,minmax(min(100%,256px),1fr))"


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
            'color:#203433;overflow-wrap:normal;word-break:normal">'
            '<div class="cal-k" style="font-size:0.72rem;font-weight:600;'
            "line-height:1.3;overflow-wrap:normal;white-space:nowrap;"
            f'">{escape(label)}</div>'
            '<div class="cal-v" style="font-size:clamp(0.95rem,5.5cqi,1.45rem);'
            "font-weight:600;line-height:1.15;color:#116559;"
            "font-variant-numeric:tabular-nums;white-space:nowrap;"
            f'overflow-wrap:normal">{escape(value)}</div>'
            '<div class="cal-d" style="font-size:clamp(0.68rem,4cqi,0.82rem);'
            "line-height:1.35;color:#3d524c;overflow-wrap:normal;white-space:nowrap;"
            f'word-break:normal">{escape(detail)}</div>'
            "</div>"
        )
    style = (
        "display:grid;"
        f"grid-template-columns:{columns};"
        "column-gap:12px;row-gap:12px;width:100%;align-items:stretch"
    )
    body = "".join(cells)
    return (
        f'<div class="cal-equal" data-equal-width="true" data-cards="{len(cards)}" '
        f'style="{style}">{body}</div>'
    )


def _split_title(title: str) -> tuple[str, str]:
    """Depth label, then the leading SAN. The separator is the card title's dot."""
    head, separator, line = str(title).partition(" · ")
    if not separator:
        return head, ""
    return head, line


def _san_html(san: str) -> str:
    """One nowrap unit per move, so ``4.Nxd4`` stays together and wraps as a whole."""
    spans = [
        '<span class="cal-ply" style="display:inline-block;white-space:nowrap">'
        f"{escape(token)}</span>"
        for token in str(san).split()
        if token
    ]
    return " ".join(spans)


def _share_percent(part: int, total: int) -> str:
    if total <= 0:
        return "0"
    bounded = min(total, max(0, part))
    return f"{100 * bounded / total:.1f}"


def _route_row(san: str, games: int, total: int) -> str:
    share = _share_percent(games, total)
    return (
        '<div class="cal-route" style="display:grid;grid-template-columns:8ch minmax(0,1fr);'
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


def transposition_cards(items: list[dict]) -> str:
    """Equal-width cards for transposing positions.

    Each item has ``title``, ``games``, ``move_orders``, and ``routes``.
    ``title`` is ``After Black's move N · <SAN>``. The depth, the line, and
    the game count are separate rows. The line reserves two lines so sibling
    cards keep the count on the same row. A route is a ``(san, games)`` pair:
    the count is a fixed column and the SAN wraps inside the second column.
    """
    columns = equal_width_columns(len(items))
    cells: list[str] = []
    for item in items:
        total = int(item["games"])
        routes = "".join(_route_row(str(san), int(games), total) for san, games in item["routes"])
        depth, line = _split_title(str(item["title"]))
        orders = int(item["move_orders"])
        order_label = "1 move order" if orders == 1 else f"{orders} move orders"
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
            f'margin-top:14px">{routes}</div></div>'
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
