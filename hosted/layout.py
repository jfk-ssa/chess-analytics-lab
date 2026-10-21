"""Equal-width cards for the hosted dashboard.

``grid-template-columns: repeat(N, minmax(0, 1fr))`` is inline on the row.
A stylesheet can change type and color. It cannot give one card a larger track,
and a long value cannot widen its column because the track's minimum is zero.
"""

from __future__ import annotations

from html import escape


def equal_width_columns(count: int) -> str:
    """Return the grid template that makes ``count`` columns the same width."""
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise ValueError("equal-width row needs at least one card")
    return f"repeat({count},minmax(0,1fr))"


def equal_width_row(cards: list[tuple[str, str, str]]) -> str:
    """HTML for one row of cards. Each tuple is label, value, detail."""
    columns = equal_width_columns(len(cards))
    cells: list[str] = []
    for label, value, detail in cards:
        cells.append(
            '<div class="cal-card" style="min-width:0;width:100%;box-sizing:border-box;'
            "overflow-wrap:anywhere;container-type:inline-size;background:#eaf1eb;"
            "border:1px solid #c5d5cc;border-radius:12px;padding:10px 8px;"
            'font-family:Inter,sans-serif;color:#203433">'
            '<div class="cal-k" style="font-size:0.72rem;font-weight:600;'
            f'line-height:1.3">{escape(label)}</div>'
            '<div class="cal-v" style="font-size:clamp(0.75rem,22cqi,1.65rem);'
            "font-weight:600;line-height:1.15;color:#116559;"
            f'font-variant-numeric:tabular-nums">{escape(value)}</div>'
            '<div class="cal-d" style="font-size:clamp(0.68rem,16cqi,0.82rem);'
            f'line-height:1.35;color:#3d524c">{escape(detail)}</div>'
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
