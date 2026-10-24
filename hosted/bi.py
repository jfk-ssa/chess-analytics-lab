"""Interactive sections of the hosted dashboard. Filters apply to every section."""

from __future__ import annotations

from datetime import date

import streamlit as st  # pyright: ignore[reportMissingImports]

from chess_analytics.dashboard_cube import (
    CLOCK_BANDS,
    RATING_BANDS,
    Drill,
    Filters,
    _grain_present,
    _join_or,
    active_filter_text,
    clock_display,
    clock_games,
    continuations,
    kpis,
    month_display,
    opening_families,
    opening_lines,
    position_cohort,
    select_clock,
    select_family,
    select_line,
    select_position,
    transpositions,
)

_BAND = {
    "under_1200": "Under 1200",
    "1200_1599": "1200–1599",
    "1600_1999": "1600–1999",
    "2000_plus": "2000+",
    "1400_1599": "1400–1599",
}
_CLOCK = {
    "under_10": "Under 10s",
    "10_to_29": "10–29s",
    "30_to_59": "30–59s",
    "60_plus": "60s+",
}
_COLOR = {"All": None, "White": "white", "Black": "black"}


def render(layout, charts, connection, date_bounds: tuple[date, date]) -> None:
    filters = _sidebar(connection, date_bounds)
    drill = _drill_for(filters)
    cards = [(item.label, item.value, item.detail) for item in kpis(connection, filters)]
    st.markdown(layout.kpi_strip(cards), unsafe_allow_html=True)
    _openings(layout, charts, connection, filters, drill)
    _transpositions(layout, connection, filters)
    _clock(layout, charts, connection, filters, drill)
    _months(charts, connection, filters)


def _sidebar(connection, date_bounds: tuple[date, date]) -> Filters:
    start, end = date_bounds
    st.session_state.setdefault("date_bounds", date_bounds)
    st.session_state.setdefault("filter_dates", date_bounds)
    st.session_state.setdefault("filter_time", "All")
    st.session_state.setdefault("filter_color", "All")
    st.session_state.setdefault("filter_rating", "All")
    st.session_state.setdefault("filter_family", "All")
    st.session_state.setdefault("drill", Drill())
    pending = st.session_state.pop("pending_family", None)
    if pending is not None:
        st.session_state.filter_family = pending
    st.sidebar.button("Reset filters", on_click=_reset)
    st.sidebar.date_input("Date range", key="filter_dates", min_value=start, max_value=end)
    times = ["All", *_ordered(connection, "time_control")]
    st.sidebar.selectbox("Time control", _keep(times, "filter_time"), key="filter_time")
    st.sidebar.selectbox("Color", list(_COLOR), key="filter_color")
    ratings = ["All", *[band for band in RATING_BANDS]]
    st.sidebar.selectbox(
        "Rating band",
        _keep(ratings, "filter_rating"),
        key="filter_rating",
        format_func=_rating_label,
    )
    families = ["All", *sorted(set(_values(connection, "opening_family")))]
    st.sidebar.selectbox("Opening family", _keep(families, "filter_family"), key="filter_family")
    chosen = _filters(date_bounds)
    st.sidebar.caption(active_filter_text(chosen))
    return chosen


def _reset() -> None:
    start, end = st.session_state.date_bounds
    st.session_state.filter_dates = (start, end)
    st.session_state.filter_time = "All"
    st.session_state.filter_color = "All"
    st.session_state.filter_rating = "All"
    st.session_state.filter_family = "All"
    st.session_state.drill = Drill()
    _bump()


def _filters(date_bounds: tuple[date, date]) -> Filters:
    raw = st.session_state.filter_dates
    if isinstance(raw, tuple) and len(raw) == 2 and all(isinstance(item, date) for item in raw):
        start, end = raw
        if start > end:
            start, end = end, start
    else:
        start, end = date_bounds
    family = st.session_state.filter_family
    rating = st.session_state.filter_rating
    control = st.session_state.filter_time
    return Filters(
        start,
        end,
        None if control == "All" else str(control),
        _COLOR.get(str(st.session_state.filter_color)),
        None if rating == "All" else str(rating),
        None if family == "All" else str(family),
    )


def _drill_for(filters: Filters) -> Drill:
    drill = st.session_state.drill
    if not isinstance(drill, Drill):
        drill = Drill()
    if filters.opening_family != drill.family:
        drill = select_family(Drill(clock_band=drill.clock_band), filters.opening_family)
    st.session_state.drill = drill
    return drill


def _openings(layout, charts, connection, filters: Filters, drill: Drill) -> None:
    st.subheader("Openings")
    _crumb(drill)
    cohort, covered = position_cohort(connection, filters)
    if cohort is None:
        st.caption("No published positions in the cube.")
        return
    if drill.family and drill.line and not drill.fen:
        _choose_fen(connection, filters, cohort, drill, dates=covered)
    elif drill.fen and drill.family and drill.line:
        _position(charts, connection, filters, cohort, drill, dates=covered)
    elif drill.family:
        _lines(layout, charts, connection, filters, cohort, drill, dates=covered)
    else:
        _families(charts, connection, filters, cohort, dates=covered)
    st.caption(_opening_caption(filters, cohort, covered))


def _opening_caption(filters: Filters, cohort: str, covered: bool) -> str:
    ignored = _ignored_position_filters(filters)
    if covered:
        pool = "Rated public" if cohort == "rated_public" else "Elite month"
        window = f"{pool}. Published positions only, not every game in the family."
    else:
        window = (
            "These positions use the full published window, which is wider than this date range."
        )
    if not ignored:
        return window
    split = "Positions are not split by " + _join_or(ignored) + "."
    if covered:
        return split
    return f"{window} {split}"


def _ignored_position_filters(filters: Filters) -> list[str]:
    ignored: list[str] = []
    if filters.color:
        ignored.append("color")
    if filters.time_control:
        ignored.append("time control")
    if filters.rating_band:
        ignored.append("rating")
    return ignored


def _families(charts, connection, filters: Filters, cohort: str, *, dates: bool) -> None:
    rows = opening_families(connection, filters, cohort, dates=dates)[:12]
    if not rows:
        return
    event = _draw(
        charts.selectable_bars(rows, name="family_pick", field="label", value_title="Games"),
        alt="Opening families by games. Select a bar to drill into lines.",
        key=_key("family_bars"),
    )
    _take(event, "family_pick", "label", None, _set_family)


def _lines(
    layout, charts, connection, filters: Filters, cohort: str, drill: Drill, *, dates: bool
) -> None:
    assert drill.family is not None
    rows = opening_lines(connection, filters, cohort, drill.family, dates=dates)
    if not rows:
        return
    plotted = [
        {
            "line": row["label"],
            "line_label": layout.san_text(str(row["label"])),
            "games": row["games"],
        }
        for row in rows[:12]
    ]
    event = _draw(
        charts.selectable_bars(
            plotted,
            name="line_pick",
            field="line",
            label_field="line_label",
            value_title="Games",
        ),
        alt="Opening lines by games. Select a bar to open the position.",
        key=_key("line_bars"),
    )
    st.table(
        [
            {"Line": layout.san_text(str(row["label"])), "Games": f"{_count(row['games']):,}"}
            for row in rows[:12]
        ],
        hide_index=True,
        height="content",
        alt="Opening lines and game counts. The full move order is the line.",
    )
    chosen = _selection(event, "line_pick", "line")
    if chosen and chosen != drill.line:
        match = next(row for row in rows if row["label"] == chosen)
        st.session_state.drill = select_line(drill, chosen, _texts(match.get("fens")))
        st.rerun()
    if st.button("Back"):
        _back(drill, filters)


def _position(
    charts, connection, filters: Filters, cohort: str, drill: Drill, *, dates: bool
) -> None:
    assert drill.family is not None and drill.fen is not None
    moves = continuations(connection, filters, cohort, drill.family, drill.fen, dates=dates)[:8]
    _board(drill.fen)
    if moves:
        _draw(
            charts.selectable_bars(moves, name="move_pick", field="label", value_title="Games"),
            alt="Continuation moves from the selected position.",
            key=_key("move_bars"),
        )
    if st.button("Back"):
        _back(drill, filters)


def _choose_fen(connection, filters: Filters, cohort: str, drill: Drill, *, dates: bool) -> None:
    assert drill.family is not None and drill.line is not None
    rows = opening_lines(connection, filters, cohort, drill.family, dates=dates)
    match = next((row for row in rows if row["label"] == drill.line), None)
    fens = _texts(None if match is None else match.get("fens"))
    if len(fens) == 1:
        st.session_state.drill = select_position(drill, str(fens[0]))
        st.rerun()
    if not fens:
        return
    choice = st.selectbox("Position", fens, key="fen_choice")
    if st.button("Open position"):
        st.session_state.drill = select_position(drill, str(choice))
        st.rerun()
    if st.button("Back"):
        _back(drill, filters)


def _clock(layout, charts, connection, filters: Filters, drill: Drill) -> None:
    st.subheader("Clock")
    bands, note, _tag = clock_display(connection, filters)
    if drill.clock_band:
        _games(layout, connection, filters, drill)
        return
    if bands:
        plotted = [
            {
                "label": _CLOCK.get(str(row["label"]), str(row["label"])),
                "band": row["label"],
                "games": row["games"],
            }
            for row in bands
        ]
        event = _draw(
            charts.selectable_bars(
                plotted,
                name="clock_pick",
                field="band",
                value_title="Evaluable moves",
                label_field="label",
                category_title="Time remaining",
                tooltip_field="label",
                tooltip_title="Time remaining",
                domain=charts.count_axis_domain([float(row["games"]) for row in plotted]),
            ),
            alt=(
                "Time remaining on the clock before the move, by evaluable moves. "
                "Select a band to list games with a move in that band."
            ),
            key=_key("clock_bars"),
        )
        _take(event, "clock_pick", "band", drill.clock_band, lambda value: _set_clock(drill, value))
    if note:
        st.caption(note)
    st.caption(
        "Each band is time remaining before the move. "
        "The length of a bar is evaluable moves, not games."
    )


def _games(layout, connection, filters: Filters, drill: Drill) -> None:
    assert drill.clock_band is not None
    label = _CLOCK.get(drill.clock_band, drill.clock_band)
    st.caption(f"{label} left on the clock")
    rows, _total, caption = clock_games(connection, filters, drill.clock_band)
    if rows:
        st.markdown(
            layout.clock_game_table(
                [
                    {
                        "white_rating": row["white_rating"],
                        "black_rating": row["black_rating"],
                        "time_control": row["time_control"],
                        "result": row["result"],
                        "opening": row["opening_line"],
                        "played_on": row["played_on"],
                        "lichess_id": row["lichess_id"],
                    }
                    for row in rows
                ]
            ),
            unsafe_allow_html=True,
        )
    st.caption(caption)
    if st.button("All bands"):
        st.session_state.drill = select_clock(drill, None)
        _bump()
        st.rerun()


def _months(charts, connection, filters: Filters) -> None:
    st.subheader("Periods")
    rows, note = month_display(connection, filters)
    if rows:
        _draw(
            charts.period_bars(rows),
            alt="Training games by published period.",
            key=None,
        )
    if note:
        st.caption(note)
    else:
        text = "Each bar is one published period."
        if _grain_present(connection, "game_cell"):
            text += " The Games card counts warehouse cells of at least 10 games."
        else:
            text += " The games delta uses the previous N periods."
        st.caption(text)


def _transpositions(layout, connection, filters: Filters) -> None:
    st.subheader("Most common transpositions")
    rows, note = transpositions(connection, filters)
    if rows:
        st.markdown(layout.transposition_cards(rows), unsafe_allow_html=True)
        _transposition_board(layout, rows)
    st.caption(note)


def _transposition_board(layout, rows: list[dict]) -> None:
    options = ["Top positions"] + [
        f"{index}. {layout.display_title(str(row['title']))} · {int(row['games']):,}"
        for index, row in enumerate(rows, start=1)
    ]
    if st.session_state.get("transpose_board") not in options:
        st.session_state["transpose_board"] = options[0]
    choice = st.selectbox("Board", options, key="transpose_board")
    if choice == "Top positions":
        return
    row = rows[options.index(str(choice)) - 1]
    _board(str(row["fen"]))
    st.table(
        [
            {"Move order": layout.san_text(str(san)), "Games": f"{games:,}"}
            for san, games in row["routes"]
        ],
        hide_index=True,
        height="content",
        alt="Top acyclic move orders for the selected position.",
    )


def _board(fen: str) -> None:
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parent / "board.py"
    spec = importlib.util.spec_from_file_location("hosted_board_draw", path)
    if spec is None or spec.loader is None:
        return
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        svg = module.fen_svg(fen)
    except ValueError:
        return
    st.markdown(svg, unsafe_allow_html=True)


def _crumb(drill: Drill) -> None:
    parts = ["Openings"]
    if drill.family:
        parts.append(drill.family)
    if drill.line:
        parts.append(_short(drill.line, 48))
    if drill.fen:
        parts.append("Position")
    st.markdown(
        '<div class="cal-crumb">' + " / ".join(parts) + "</div>",
        unsafe_allow_html=True,
    )


def _back(drill: Drill, filters: Filters) -> None:
    parent = select_family(Drill(clock_band=drill.clock_band), None)
    if drill.line or drill.fen:
        parent = select_family(Drill(clock_band=drill.clock_band), drill.family)
    st.session_state.drill = parent
    if parent.family is None:
        st.session_state.pending_family = "All"
    del filters
    _bump()
    st.rerun()


def _bump() -> None:
    st.session_state.chart_epoch = int(st.session_state.get("chart_epoch", 0)) + 1


def _key(name: str) -> str:
    return f"{name}_{st.session_state.get('chart_epoch', 0)}"


def _set_family(family: str) -> None:
    st.session_state.pending_family = family
    st.session_state.drill = select_family(st.session_state.drill, family)


def _set_clock(drill: Drill, band: str) -> None:
    if band in CLOCK_BANDS:
        st.session_state.drill = select_clock(drill, band)


def _take(event, name: str, field: str, current: str | None, apply) -> None:
    chosen = _selection(event, name, field)
    if not chosen or chosen == current:
        return
    apply(chosen)
    st.rerun()


def _draw(chart, *, alt: str, key: str | None):
    if key is None:
        return st.altair_chart(chart, width="stretch", theme=None, alt=alt)
    return st.altair_chart(
        chart,
        width="stretch",
        theme=None,
        alt=alt,
        on_select="rerun",
        key=key,
    )


def _selection(event, name: str, field: str) -> str | None:
    selection = getattr(event, "selection", None)
    if not selection:
        return None
    points = selection.get(name, []) if hasattr(selection, "get") else []
    if not points:
        return None
    first = points[0]
    if isinstance(first, dict) and first.get(field):
        return str(first[field])
    return None


def _time_sort_key(value: str) -> tuple[int, int, int, str]:
    """Sort ``base+increment`` numerically. Other labels follow, by text."""
    base, separator, increment = value.partition("+")
    if separator and base.isdigit() and increment.isdigit():
        return (0, int(base), int(increment), "")
    return (1, 0, 0, value)


def _ordered(connection, column: str) -> list[str]:
    values = _values(connection, column)
    if column == "time_control":
        return sorted(values, key=_time_sort_key)
    return sorted(values)


def _values(connection, column: str) -> list[str]:
    from chess_analytics.dashboard_cube import dimension_values

    return dimension_values(connection, column)


def _keep(options: list[str], key: str) -> list[str]:
    current = st.session_state.get(key)
    if current not in options:
        st.session_state[key] = options[0]
    return options


def _short(text: str, limit: int = 32) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _rating_label(item: object) -> str:
    text = str(item)
    return _BAND.get(text, text)


def _texts(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _count(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return 0
    return int(value)
