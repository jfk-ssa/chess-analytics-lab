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


def transposition_cards(items: list[dict]) -> str:
    """Equal-width cards for transposing positions.

    Each item has ``title``, ``games``, ``move_orders``, and ``routes``.
    ``title`` is the transpositions-page name of that board. A route is a
    ``(san, games)`` pair. Counts stay on one line. Move text wraps on spaces.
    """
    columns = equal_width_columns(len(items))
    cells: list[str] = []
    for item in items:
        routes: list[str] = []
        for san, games in item["routes"]:
            routes.append(
                '<div class="cal-route" style="display:flex;gap:8px;align-items:baseline;'
                'margin-top:6px;min-width:0">'
                '<span class="cal-n" style="white-space:nowrap;flex:0 0 auto;'
                "font-variant-numeric:tabular-nums;font-weight:600;color:#116559;"
                f'">{escape(f"{int(games):,}")}</span>'
                '<span class="cal-san" style="white-space:normal;overflow-wrap:normal;'
                'word-break:normal;min-width:0">'
                f"{escape(str(san))}</span></div>"
            )
        orders = int(item["move_orders"])
        detail = f"{orders} move orders"
        games_text = f"{int(item['games']):,}"
        cells.append(
            '<div class="cal-card" style="min-width:0;width:100%;box-sizing:border-box;'
            "container-type:inline-size;background:#eaf1eb;border:1px solid #c5d5cc;"
            "border-radius:12px;padding:10px 8px;font-family:Inter,sans-serif;"
            'color:#203433;overflow-wrap:normal;word-break:normal">'
            '<div class="cal-k" style="font-size:0.72rem;font-weight:600;'
            "line-height:1.3;overflow-wrap:normal;white-space:normal;"
            f'">{escape(str(item["title"]))}</div>'
            '<div class="cal-v" style="font-size:clamp(0.95rem,5.5cqi,1.45rem);'
            "font-weight:600;line-height:1.15;color:#116559;"
            "font-variant-numeric:tabular-nums;white-space:nowrap;"
            f'overflow-wrap:normal">{escape(games_text)}</div>'
            '<div class="cal-d" style="font-size:clamp(0.68rem,4cqi,0.82rem);'
            "line-height:1.35;color:#3d524c;overflow-wrap:normal;white-space:nowrap;"
            f'word-break:normal">{escape(detail)}</div>' + "".join(routes) + "</div>"
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
