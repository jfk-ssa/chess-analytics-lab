"""Altair charts for the hosted dashboard. No warehouse and no network."""

from __future__ import annotations

from typing import Any, cast

import altair as alt  # pyright: ignore[reportMissingImports]

# The offline job typechecks before the dashboard extra exists, so Altair's
# classes are not a type form in that environment. Chart and LayerChart both
# satisfy this alias once the extra is installed.
type _Drawn = Any

_INSTALLED = False
_SERIES = ("White, raw", "Black, raw", "Black, adjusted")
_SERIES_COLORS = ("#3d6b8c", "#203433", "#116559")
_ORANGE = "#a84a1f"
_TEAL = "#116559"
# Pinned to the full run label, including the repeat suffix. A set's chart
# shows the short label and passes these colors in explicitly.
_NAMED_RUN_COLORS = {
    "gpt-6-luna": _TEAL,
    "gpt-6-sol": _ORANGE,
    "grok-4.7 · low ×5": "#1d4ed8",
    "grok-4.7 · low ×1": "#7c3aed",
    "grok-4.7 · medium ×1": "#db2777",
    "grok-4.7 · high ×1": "#4d7c0f",
}
_RUN_COLOR_POOL = ("#1d4ed8", "#7c3aed", "#db2777", "#4d7c0f", "#0369a1")
# Space outside the axis so a full label is not flush with the chart edge.
_EDGE_PAD = {"left": 16, "right": 20, "top": 8, "bottom": 12}


def install_theme() -> None:
    """Point Altair at Inter and the page palette. Safe to call more than once."""
    global _INSTALLED
    if _INSTALLED:
        return

    @alt.theme.register("chesslab", enable=True)
    def _theme() -> alt.theme.ThemeConfig:
        return {
            "config": {
                "font": "Inter",
                "background": "transparent",
                "view": {"stroke": "transparent"},
                "axis": {
                    "labelFont": "Inter",
                    "titleFont": "Inter",
                    "labelColor": "#203433",
                    "titleColor": "#3d524c",
                    "labelFontSize": 12,
                    "titleFontSize": 12,
                    "gridColor": "#e3ebe4",
                    "domainColor": "#8aa399",
                    "tickColor": "#8aa399",
                },
                "legend": {
                    "labelFont": "Inter",
                    "titleFont": "Inter",
                    "labelColor": "#203433",
                    "titleColor": "#203433",
                    "labelFontSize": 12,
                    "titleFontSize": 12,
                },
                "range": {"category": ["#116559", "#a84a1f", "#3d6b8c", "#203433", "#6b4c7a"]},
                "bar": {"color": "#116559"},
            }
        }

    _INSTALLED = True


def _frame(
    chart: _Drawn,
    height: int,
    *,
    width: Any = "container",
    padding: dict[str, int] | None = None,
) -> _Drawn:
    if padding is None:
        return cast(_Drawn, chart.properties(height=height, width=width))
    return cast(_Drawn, chart.properties(height=height, width=width, padding=padding))


def pass_rate_domain(values: list[float]) -> list[float]:
    """Lower limit is 10 percentage points under the minimum, clamped at 0.

    The margin is 0.10 on the unit interval (10 percentage points), not 10
    percent of the minimum. Callers include interval lower bounds in
    ``values``. The upper limit stays 100 percent. ``nice`` stays off so the
    scale is not rounded back to zero.
    """
    finite = [float(value) for value in values if value is not None]
    if not finite:
        return [0.0, 1.0]
    return [max(0.0, min(finite) - 0.10), 1.0]


def _pass_axis(domain: list[float]) -> alt.Axis:
    """Whole-percent ticks. A tight window uses 5-point steps so labels stay readable."""
    span = domain[1] - domain[0]
    step = 0.05 if span <= 0.40 else 0.10
    return alt.Axis(format=".0%", tickMinStep=step, labelFlush=False, labelOverlap=False)


# Pixels of plot past the 100% position. A dot centered on that tick stays inside.
_MARK_INSET_PX = 12


def _pass_scale(domain: list[float]) -> alt.Scale:
    """Pass-rate scale. The domain still ends at 100 percent.

    The range stops ``_MARK_INSET_PX`` short of the plot edge, so a mark
    centered on the 100 percent tick is fully inside the frame. That tick
    stays the last labeled tick.
    """
    return alt.Scale(
        domain=domain,
        nice=False,
        zero=False,
        clamp=True,
        range=[0, {"expr": f"width - {_MARK_INSET_PX}"}],
    )


_LABEL_FORMATS = {"count": ",", "rate": ".1%", "diff": "+,.1f"}
# Pixels kept clear of the plot edge so an outside label is not clipped.
_LABEL_GUTTER = 72
# A vertical count needs about this much plot width or the numbers collide.
_VERTICAL_LABEL_SLOT = 56
_LABEL_COLOR = "#203433"
_LABEL_ON_BAR = "#f7f4ea"
_MONTHS = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)


def value_label_format(kind: str) -> str:
    """Format for a bar-end label.

    Counts use thousands separators. Rates use one decimal percent.
    Diffs keep a sign and one decimal. No hosted bar plots a difference;
    the signed format is the one a diff bar would use.
    """
    try:
        return _LABEL_FORMATS[kind]
    except KeyError:
        raise ValueError(f"unknown label kind: {kind}") from None


def _numeric(rows: list[dict], field: str) -> list[float]:
    return [
        float(row[field])
        for row in rows
        if isinstance(row.get(field), (int, float)) and row[field] is not None
    ]


def _count_scale(rows: list[dict], field: str, passed: list[float] | None = None) -> alt.Scale:
    """Zero baseline for counts, with room past the longest bar for its label."""
    if passed is not None:
        low, high = float(passed[0]), float(passed[1])
        span = max(high - low, abs(high) * 0.02, 1.0)
        return alt.Scale(domain=[low, high + span * 0.22], nice=False, zero=low == 0)
    high = max(_numeric(rows, field), default=1.0)
    if high <= 0:
        high = 1.0
    return alt.Scale(domain=[0.0, high * 1.22], nice=False, zero=True)


def _rate_scale() -> alt.Scale:
    return alt.Scale(domain=[0, 1], nice=False, zero=True)


def compact_count(value: float) -> str:
    """Short count for a narrow slot, such as 240086 -> 240k and 90000 -> 90k."""
    number = float(value)
    sign = "-" if number < 0 else ""
    magnitude = abs(number)
    for unit, scale in (("M", 1_000_000), ("k", 1_000)):
        if magnitude < scale:
            continue
        scaled = magnitude / scale
        if scaled >= 10:
            return f"{sign}{scaled:.0f}{unit}"
        text = f"{scaled:.1f}".rstrip("0").rstrip(".")
        return f"{sign}{text}{unit}"
    return f"{sign}{magnitude:.0f}"


def _period_tick(label: object) -> str:
    """YYYY-MM becomes a horizontal tick such as Nov 25."""
    text = str(label)
    if len(text) < 7 or text[4] != "-" or not text[:4].isdigit() or not text[5:7].isdigit():
        return text
    month = int(text[5:7])
    if not 1 <= month <= 12:
        return text
    return f"{_MONTHS[month - 1]} {text[2:4]}"


def _nominal_axis(**extra: Any) -> alt.Axis:
    spec = {
        "labelAngle": 0,
        "labelFont": "Inter",
        "labelOverlap": False,
        "labelPadding": 4,
    }
    spec.update(extra)
    return alt.Axis(**spec)


def _join(*parts: Any) -> _Drawn:
    """One flat layer list. A nested layer would keep its axis out of the merge."""
    flat: list[Any] = []
    for part in parts:
        if part is None:
            continue
        if isinstance(part, list):
            flat.extend(item for item in part if item is not None)
        else:
            flat.append(part)
    drawn = alt.layer(*flat)
    return drawn.resolve_scale(x="shared", y="shared").resolve_axis(x="shared", y="shared")


def _with_labels(
    bars: _Drawn,
    labels: _Drawn,
    height: int,
    *,
    padding: dict[str, int] | None = None,
) -> _Drawn:
    # Shared axes: a null axis on the text layer would erase the bar's axis.
    return _frame(_join(bars, labels), height, padding=padding)


def _x_value(value: str, scale: alt.Scale, axis: alt.Axis | None, title: str | None) -> alt.X:
    if axis is None:
        return alt.X(f"{value}:Q", scale=scale, axis=None)
    return alt.X(f"{value}:Q", scale=scale, axis=axis, title=title)


def _y_value(value: str, scale: alt.Scale, axis: alt.Axis | None, title: str | None) -> alt.Y:
    if axis is None:
        return alt.Y(f"{value}:Q", scale=scale, axis=None)
    return alt.Y(f"{value}:Q", scale=scale, axis=axis, title=title)


def _label_texts(
    value: str,
    fmt: str,
    *,
    drop_below: int | None,
    compact_below: int | None,
    compact_field: str | None,
) -> list[Any]:
    if compact_below is not None:
        return [
            alt.condition(
                f"width >= {compact_below}",
                alt.Text(f"{value}:Q", format=fmt),
                alt.value(""),
            ),
            alt.condition(
                f"width < {compact_below}",
                alt.Text(f"{compact_field}:N"),
                alt.value(""),
            ),
        ]
    if drop_below is not None:
        return [
            alt.condition(
                f"width >= {drop_below}",
                alt.Text(f"{value}:Q", format=fmt),
                alt.value(""),
            )
        ]
    return [alt.Text(f"{value}:Q", format=fmt)]


def _bar_labels(
    rows: list[dict],
    *,
    category: str,
    value: str,
    kind: str,
    scale: alt.Scale,
    sort: Any,
    horizontal: bool,
    category_axis: alt.Axis,
    category_title: str | None,
    value_axis: alt.Axis | None = None,
    value_title: str | None = None,
    drop_below: int | None = None,
    compact_below: int | None = None,
    compact_field: str | None = None,
) -> _Drawn:
    """Text at the end of each bar.

    The category axis is the same one the bars use. Leaving it off, or setting
    it to None, makes Vega-Lite drop that shared axis. The value axis is hidden
    when ``value_axis`` is None; the scale is unchanged, so a count still
    starts at zero. A horizontal label that would cross the right edge moves
    inside the bar.
    """
    fmt = value_label_format(kind)
    texts = _label_texts(
        value,
        fmt,
        drop_below=drop_below,
        compact_below=compact_below,
        compact_field=compact_field,
    )
    layers: list[Any] = []
    for text in texts:
        if horizontal:
            fits = (
                f"scale('x', datum.{value}) > width - {_LABEL_GUTTER}"
                f" && scale('x', datum.{value}) > {_LABEL_GUTTER}"
            )
            marks = alt.Chart(alt.Data(values=rows)).mark_text(
                align={"expr": f"{fits} ? 'right' : 'left'"},
                dx={"expr": f"{fits} ? -5 : 6"},
                baseline="middle",
                color={"expr": f"{fits} ? '{_LABEL_ON_BAR}' : '{_LABEL_COLOR}'"},
                font="Inter",
                fontSize=12,
            )
            layers.append(
                marks.encode(
                    y=alt.Y(
                        f"{category}:N",
                        sort=sort,
                        axis=category_axis,
                        title=category_title,
                    ),
                    x=_x_value(value, scale, value_axis, value_title),
                    text=text,
                )
            )
            continue
        near_top = f"scale('y', datum.{value}) < 16"
        marks = alt.Chart(alt.Data(values=rows)).mark_text(
            align="center",
            baseline={"expr": f"{near_top} ? 'top' : 'bottom'"},
            dy={"expr": f"{near_top} ? 3 : -4"},
            color={"expr": f"{near_top} ? '{_LABEL_ON_BAR}' : '{_LABEL_COLOR}'"},
            font="Inter",
            fontSize=12,
        )
        layers.append(
            marks.encode(
                x=alt.X(f"{category}:N", sort=sort, axis=category_axis, title=category_title),
                y=_y_value(value, scale, value_axis, value_title),
                text=text,
            )
        )
    return layers


def funnel(rows: list[dict]) -> _Drawn:
    """Games removed. ``rows`` need stage, count, and order."""
    order = alt.EncodingSortField(field="order", order="ascending")
    scale = _count_scale(rows, "count")
    category_axis = _nominal_axis()
    bars = (
        alt.Chart(alt.Data(values=rows))
        .mark_bar(color=_TEAL, cornerRadius=2)
        .encode(
            y=alt.Y("stage:N", sort=order, title=None, axis=category_axis),
            x=alt.X("count:Q", scale=scale, axis=None),
            tooltip=[
                alt.Tooltip("stage:N", title="Removed"),
                alt.Tooltip("count:Q", title="Games", format=value_label_format("count")),
            ],
        )
    )
    labels = _bar_labels(
        rows,
        category="stage",
        value="count",
        kind="count",
        scale=scale,
        sort=order,
        horizontal=True,
        category_axis=category_axis,
        category_title=None,
    )
    return _with_labels(bars, labels, 168)


def horizontal_bars(rows: list[dict], *, x_title: str) -> _Drawn:
    """``rows`` need family and games. ``x_title`` is the tooltip name.

    The value axis is hidden; each bar prints its count.
    """
    height = max(180, 28 * len(rows) + 24)
    scale = _count_scale(rows, "games")
    category_axis = _nominal_axis()
    bars = (
        alt.Chart(alt.Data(values=rows))
        .mark_bar(color="#116559", cornerRadius=2)
        .encode(
            y=alt.Y("family:N", sort="-x", title=None, axis=category_axis),
            x=alt.X("games:Q", scale=scale, axis=None),
            tooltip=[
                alt.Tooltip("family:N", title="Family"),
                alt.Tooltip("games:Q", title=x_title, format=value_label_format("count")),
                alt.Tooltip("share_label:N", title="Share"),
            ],
        )
    )
    labels = _bar_labels(
        rows,
        category="family",
        value="games",
        kind="count",
        scale=scale,
        sort="-x",
        horizontal=True,
        category_axis=category_axis,
        category_title=None,
    )
    return _with_labels(bars, labels, height)


def score_intervals(rows: list[dict]) -> _Drawn:
    """Grouped scores. Interval rows also carry low and high.

    A single series prints one-decimal percents. Two or three series omit
    the labels: the bars are 18 pixels wide and the text would overlap.
    """
    present = [name for name in _SERIES if any(row["series"] == name for row in rows)]
    offset = alt.Scale(domain=present)
    color = alt.Scale(domain=present, range=list(_SERIES_COLORS[: len(present)]))
    rate_scale = _rate_scale()
    category_axis = _nominal_axis()
    labeled = len(present) == 1
    # Grouped bars have no text, so they keep the Score axis. One series
    # prints the percent and hides that axis.
    value_axis = None if labeled else alt.Axis(format="%", labelAngle=0)
    base = alt.Chart(alt.Data(values=rows)).encode(
        x=alt.X("family:N", title=None, axis=category_axis),
        xOffset=alt.XOffset("series:N", scale=offset),
        color=alt.Color("series:N", scale=color, title=None),
        tooltip=[
            alt.Tooltip("family:N", title="Family"),
            alt.Tooltip("series:N", title="Series"),
            alt.Tooltip("rate_label:N", title="Score"),
            alt.Tooltip("interval_label:N", title="Interval"),
            alt.Tooltip("support_label:N", title="Low support"),
        ],
    )
    bars = base.mark_bar(size=18, cornerRadius=2).encode(
        y=alt.Y(
            "rate:Q",
            title=None if labeled else "Score",
            axis=value_axis,
            scale=rate_scale,
        )
    )
    # Three 18px series in one family leave no room for a percent label.
    labels = None
    if labeled:
        labels = _bar_labels(
            rows,
            category="family",
            value="rate",
            kind="rate",
            scale=rate_scale,
            sort=None,
            horizontal=False,
            category_axis=category_axis,
            category_title=None,
        )
    intervals = [row for row in rows if row["low"] is not None]
    if not intervals:
        return _frame(_join(bars, labels), 280)
    if labeled:
        error_y = alt.Y("low:Q", scale=rate_scale, axis=None)
    else:
        error_y = alt.Y("low:Q", scale=rate_scale)
    errors = (
        alt.Chart(alt.Data(values=intervals))
        .mark_errorbar(color=_ORANGE, ticks=True)
        .encode(
            x=alt.X("family:N", title=None, axis=category_axis),
            xOffset=alt.XOffset("series:N", scale=offset),
            y=error_y,
            y2="high:Q",
        )
    )
    return _frame(_join(bars, errors, labels), 300)


def _rate_domain(rows: list[dict]) -> list[float]:
    rates = [
        row["error_proxy_rate"]
        for row in rows
        if row.get("evaluable_moves") and row.get("error_proxy_rate") is not None
    ]
    if not rates:
        return [0, 1]
    low = min(rates)
    high = max(rates)
    if high <= low:
        low = max(0.0, low - 0.05)
        high = min(1.0, high + 0.05)
    return [low, high]


def heatmap(rows: list[dict], *, x_order: list[str], y_order: list[str]) -> _Drawn:
    """Rating band by time control. Blank cells have no evaluable moves."""
    chart = (
        alt.Chart(alt.Data(values=rows))
        .mark_rect()
        .encode(
            x=alt.X("time_control:N", sort=x_order, title="Time control"),
            y=alt.Y("rating_band:N", sort=y_order, title=None),
            color=alt.condition(
                alt.datum.evaluable_moves > 0,
                alt.Color(
                    "error_proxy_rate:Q",
                    title="Error proxy",
                    scale=alt.Scale(domain=_rate_domain(rows), scheme="goldgreen", reverse=True),
                    legend=alt.Legend(format=".0%"),
                ),
                alt.value("#e7e4da"),
            ),
            tooltip=[
                alt.Tooltip("rating_band:N", title="Rating"),
                alt.Tooltip("time_control:N", title="Time control"),
                alt.Tooltip("rate_label:N", title="Error proxy"),
                alt.Tooltip("evaluable_moves:Q", title="Evaluable moves", format=","),
                alt.Tooltip("coverage_label:N", title="Evaluation coverage"),
            ],
        )
    )
    return _frame(chart, 220)


def bucket_bars(rows: list[dict]) -> _Drawn:
    """Error-proxy rates. The value axis stays, because a narrow plot drops the text."""
    scale = _rate_scale()
    order = [row["bucket"] for row in rows]
    category_axis = _nominal_axis()
    value_axis = alt.Axis(format="%", labelAngle=0, labelFont="Inter")
    bars = (
        alt.Chart(alt.Data(values=rows))
        .mark_bar(color="#116559", cornerRadius=2)
        .encode(
            x=alt.X("bucket:N", sort=order, title="Seconds left", axis=category_axis),
            y=alt.Y(
                "error_proxy_rate:Q",
                title="Error proxy",
                axis=value_axis,
                scale=scale,
            ),
            tooltip=[
                alt.Tooltip("bucket:N", title="Bucket"),
                alt.Tooltip("rate_label:N", title="Error proxy"),
                alt.Tooltip("coverage_label:N", title="Evaluation coverage"),
            ],
        )
    )
    labels = _bar_labels(
        rows,
        category="bucket",
        value="error_proxy_rate",
        kind="rate",
        scale=scale,
        sort=order,
        horizontal=False,
        category_axis=category_axis,
        category_title="Seconds left",
        value_axis=value_axis,
        value_title="Error proxy",
        drop_below=max(len(rows), 1) * _VERTICAL_LABEL_SLOT,
    )
    return _with_labels(bars, labels, 240)


def wilson(rows: list[dict]) -> _Drawn:
    """Pass rate with the receipt's Wilson interval as a horizontal bar.

    The domain is ``pass_rate_domain`` of the point and the interval's lower
    bound. A 1-repeat row uses the same encoding: the caller supplies that
    receipt's Wilson bounds, which are already on 48 trials.
    """
    order = [row["label"] for row in rows]
    domain = pass_rate_domain(
        [row["pass_rate"] for row in rows] + [row["wilson_low"] for row in rows]
    )
    scale = _pass_scale(domain)
    color = alt.Scale(domain=["Gate clear", "Hard fail"], range=[_TEAL, _ORANGE])
    y_axis = alt.Axis(
        labelAngle=0,
        labelLimit=0,
        labelFontSize=11,
        labelOverlap=False,
        labelPadding=6,
    )
    gate_legend = alt.Legend(orient="right", title=None, labelLimit=0, padding=4, offset=8)
    rules = (
        alt.Chart(alt.Data(values=rows))
        .mark_rule(strokeWidth=3)
        .encode(
            y=alt.Y("label:N", sort=order, title=None, axis=y_axis),
            x=alt.X(
                "wilson_low:Q",
                title="Pass rate",
                axis=_pass_axis(domain),
                scale=scale,
            ),
            x2="wilson_high:Q",
            color=alt.Color("gate:N", scale=color, title=None, legend=gate_legend),
        )
    )
    points = (
        alt.Chart(alt.Data(values=rows))
        .mark_point(filled=True, size=90)
        .encode(
            y=alt.Y("label:N", sort=order, axis=y_axis),
            x=alt.X("pass_rate:Q", scale=scale),
            color=alt.Color("gate:N", scale=color, title=None, legend=None),
            tooltip=[
                alt.Tooltip("label:N", title="Run"),
                alt.Tooltip("rate_label:N", title="Pass rate"),
                alt.Tooltip("wilson_label:N", title="Wilson 95%"),
                alt.Tooltip("cost_label:N", title="Known gross cost"),
                alt.Tooltip("gate:N", title="Gate"),
            ],
        )
    )
    height = max(160, 32 * len(rows) + 48)
    return _frame(rules + points, height, padding=_EDGE_PAD)


def _run_colors(models: list[str]) -> list[str]:
    pool = iter(_RUN_COLOR_POOL)
    colors: list[str] = []
    for model in models:
        named = _NAMED_RUN_COLORS.get(model)
        colors.append(named if named is not None else next(pool))
    return colors


def pinned_run_color(label: str) -> str:
    """Swatch for a full run label such as ``grok-4.7 · low ×5``."""
    named = _NAMED_RUN_COLORS.get(label)
    if named is not None:
        return named
    return _run_colors([label])[0]


def _series_colors(models: list[str], colors: dict[str, str] | None) -> list[str]:
    fallback = _run_colors(models)
    if colors is None:
        return fallback
    return [colors.get(name, fallback[index]) for index, name in enumerate(models)]


# One category row. Six 8px dots at 11px centers fit inside it, centered on the label.
_ROW_PX = 72
_DOT_PITCH_PX = 11
_DOT_SIZE = 64


def category_dumbbell(
    rows: list[dict],
    *,
    category_order: list[str],
    model_order: list[str] | None = None,
    colors: dict[str, str] | None = None,
) -> _Drawn:
    """Pass rate by category. Each run is a dot centered on that row's label.

    Tied rates share an x position. Offsets are symmetric around the category
    index, and the row label is drawn at that same index, so the stack sits on
    the label. A faint band marks the row. The min-to-max line is not drawn.
    """
    models: list[str] = []
    for row in rows:
        if row["model"] not in models:
            models.append(row["model"])
    if model_order:
        rank = {name: index for index, name in enumerate(model_order)}
        models.sort(key=lambda name: rank.get(name, len(rank)))
    cat_index = {name: index for index, name in enumerate(category_order)}
    model_index = {name: index for index, name in enumerate(models)}
    count = len(models)
    step = 0.0 if count <= 1 else _DOT_PITCH_PX / _ROW_PX
    middle = (count - 1) / 2
    plotted = []
    for row in rows:
        if row["category"] not in cat_index or row["model"] not in model_index:
            continue
        shift = (model_index[row["model"]] - middle) * step
        plotted.append({**row, "y": cat_index[row["category"]] + shift})
    domain = pass_rate_domain([row["rate"] for row in rows])
    x_scale = _pass_scale(domain)
    n_rows = max(len(category_order), 1)
    y_domain = [-0.5, n_rows - 0.5]
    # Smaller category indexes stay at the top, matching category_order.
    y_scale = alt.Scale(domain=y_domain, nice=False, zero=False, reverse=True)
    bands = [
        {"y0": index - 0.5, "y1": index + 0.5, "shade": index % 2}
        for index in range(len(category_order))
    ]
    # A y2 rect suppresses the y axis on every layer, so the category name is a
    # text mark on the same scale. That keeps the label on the stack's center.
    labels = (
        alt.Chart(
            alt.Data(
                values=[{"y": index, "label": name} for index, name in enumerate(category_order)]
            )
        )
        .mark_text(
            align="right",
            baseline="middle",
            dx=-8,
            font="Inter",
            fontSize=11,
            color="#203433",
        )
        .encode(
            y=alt.Y("y:Q", scale=y_scale, axis=None),
            text="label:N",
            x=alt.value(0),
        )
    )
    # No x encoding on the band. A rect that ranges on both x and y drops the
    # axes for the whole layered chart. The rect spans the plot width.
    band_layer = (
        alt.Chart(alt.Data(values=bands))
        .mark_rect()
        .encode(
            y=alt.Y("y0:Q", scale=y_scale, axis=None),
            y2="y1:Q",
            color=alt.condition(
                alt.datum.shade == 0,
                alt.value("#e7eee9"),
                alt.value("#f7faf8"),
            ),
        )
    )
    points = (
        alt.Chart(alt.Data(values=plotted))
        .mark_point(filled=True, size=_DOT_SIZE, stroke="#faf9f5", strokeWidth=1)
        .encode(
            y=alt.Y("y:Q", scale=y_scale, axis=None),
            x=alt.X(
                "rate:Q",
                title="Pass rate",
                axis=_pass_axis(domain),
                scale=x_scale,
                stack=None,
            ),
            color=alt.Color(
                "model:N",
                title=None,
                sort=models,
                scale=alt.Scale(domain=models, range=_series_colors(models, colors)),
                legend=alt.Legend(orient="bottom", columns=1, labelLimit=0, labelFontSize=11),
            ),
            tooltip=[
                alt.Tooltip("model:N", title="Run"),
                alt.Tooltip("category:N", title="Category"),
                alt.Tooltip("passed_label:N", title="Passed"),
            ],
        )
    )
    # The legend and x-axis title sit inside this height, so the rows keep _ROW_PX.
    # Vega already insets the plot by the label width; the shared edge pad keeps
    # that label off the frame.
    return _frame(band_layer + labels + points, n_rows * _ROW_PX + 156, padding=_EDGE_PAD)


def case_grid(rows: list[dict], *, case_order: list[str], model_order: list[str]) -> _Drawn:
    """Teal ramp on the pass fraction. The cell prints passed/repeats.

    Column labels stay horizontal. ``width`` is one step per run so a label
    such as ``grok-4.7`` / ``medium ×1`` fits at 10px without rotation or
    ellipsis. A narrow viewport scrolls the chart instead of squeezing it.
    """
    plotted: list[dict] = []
    for row in rows:
        repeats = int(row["repeats"])
        passed = int(row["passed"])
        fraction = passed / repeats if repeats else 0.0
        plotted.append(
            {
                **row,
                "fraction": fraction,
                "cell_label": f"{passed}/{repeats}",
                "run": row.get("run") or str(row.get("model", "")).replace("\n", " "),
            }
        )
    height = max(220, 22 * len(case_order) + 56)
    x_axis = alt.Axis(
        labelAngle=0,
        labelAlign="center",
        labelBaseline="top",
        labelFontSize=10,
        labelLimit=0,
        labelOverlap=False,
        labelPadding=8,
    )
    base = alt.Chart(alt.Data(values=plotted)).encode(
        x=alt.X("model:N", sort=model_order, title=None, axis=x_axis),
        y=alt.Y(
            "case_id:N",
            sort=case_order,
            title=None,
            axis=alt.Axis(
                labelLimit=0, labelFontSize=11, labelAngle=0, labelOverlap=False, labelPadding=6
            ),
        ),
    )
    rects = base.mark_rect(stroke="#faf9f5", strokeWidth=1).encode(
        color=alt.Color(
            "fraction:Q",
            title="Pass fraction",
            scale=alt.Scale(domain=[0, 1], range=["#e7f3ef", "#116559"], clamp=True),
            legend=alt.Legend(format=".0%", orient="bottom", direction="horizontal"),
        ),
        tooltip=[
            alt.Tooltip("case_id:N", title="Case"),
            alt.Tooltip("category:N", title="Category"),
            alt.Tooltip("run:N", title="Run"),
            alt.Tooltip("cell_label:N", title="Passed / repeats"),
            alt.Tooltip("severity:N", title="Severity"),
        ],
    )
    counts = base.mark_text(font="Inter", fontSize=10).encode(
        text="cell_label:N",
        color=alt.condition(alt.datum.fraction >= 0.5, alt.value("#faf9f5"), alt.value("#203433")),
    )
    # 112px per column leaves a 10px label, two lines, inside the band.
    return _frame(rects + counts, height, width=alt.Step(112), padding=_EDGE_PAD)


def compression(rows: list[dict]) -> _Drawn:
    chart = (
        alt.Chart(alt.Data(values=rows))
        .mark_line(point=True)
        .encode(
            x=alt.X("ply:O", title="Ply"),
            y=alt.Y(
                "endpoint_compression:Q",
                title="Endpoint compression",
                axis=alt.Axis(format="%"),
            ),
            color=alt.Color(
                "cohort:N",
                title=None,
                scale=alt.Scale(range=["#116559", "#a84a1f"]),
            ),
            tooltip=[
                alt.Tooltip("cohort:N", title="Cohort"),
                alt.Tooltip("ply:O", title="Ply"),
                alt.Tooltip("compression_label:N", title="Endpoint compression"),
                alt.Tooltip("distinct_positions:Q", title="Distinct positions", format=","),
                alt.Tooltip("distinct_routes:Q", title="Distinct routes", format=","),
            ],
        )
    )
    return _frame(chart, 260)


def coverage(rows: list[dict]) -> _Drawn:
    chart = (
        alt.Chart(alt.Data(values=rows))
        .mark_line(point=True)
        .encode(
            x=alt.X("n:O", title="Top positions"),
            y=alt.Y("share:Q", title="Games covered", axis=alt.Axis(format="%")),
            color=alt.Color(
                "cohort:N",
                title=None,
                scale=alt.Scale(range=["#116559", "#a84a1f"]),
            ),
            tooltip=[
                alt.Tooltip("cohort:N", title="Cohort"),
                alt.Tooltip("n:O", title="N"),
                alt.Tooltip("share_label:N", title="Share of games"),
                alt.Tooltip("games:Q", title="Games", format=","),
            ],
        )
    )
    return _frame(chart, 260)


def count_axis_domain(values: list[float]) -> list[float] | None:
    """Ten percent under the minimum when every value sits in a tight band.

    A spread of 25 percent or more, or a non-positive minimum, keeps the
    automatic scale so a count of moves or games still starts at zero. The
    upper end sits two percent above the maximum so the longest bar is not
    flush with the plot edge.
    """
    finite = [float(value) for value in values if value is not None]
    if len(finite) < 2:
        return None
    low = min(finite)
    high = max(finite)
    if low <= 0 or high >= low * 1.25:
        return None
    floor = low * 0.9
    span = max(high - floor, low * 0.02)
    return [floor, high + span * 0.02]


def selectable_bars(
    rows: list[dict],
    *,
    name: str,
    field: str,
    value_title: str,
    label_field: str | None = None,
    category_title: str | None = None,
    tooltip_field: str | None = None,
    tooltip_title: str | None = None,
    domain: list[float] | None = None,
    horizontal_category_title: bool = False,
) -> _Drawn:
    """Horizontal bars with a point selection named ``name`` on ``field``.

    ``horizontal_category_title`` draws the y-axis title left to right above
    the labels. Counts omit ``domain`` so the scale keeps its zero baseline.
    The value axis is hidden: each bar prints its count, with headroom so the
    text is not cut off. A label that would cross the right edge moves inside.
    """
    shown = label_field or field
    height = max(180, 28 * max(len(rows), 1) + 24)
    pick = alt.selection_point(name=name, fields=[field])
    tip_field = tooltip_field or field
    tip_title = tooltip_title or ("Line" if field == "line" else shown)
    x_scale = _count_scale(rows, "games", domain)
    y_axis = {
        "labelLimit": 480,
        "labelFont": "Inter",
        "labelOverlap": False,
        "labelAngle": 0,
        "labelPadding": 4,
    }
    frame_padding = None
    if horizontal_category_title:
        # Anchor at the start so the horizontal title sits above the labels.
        # "end" lands on the last category and covers that label.
        y_axis.update(
            titleAngle=0,
            titleAnchor="start",
            titleAlign="left",
            titleBaseline="bottom",
            titleLimit=160,
            titlePadding=8,
        )
        frame_padding = {"left": 4, "right": 18, "top": 28, "bottom": 4}
    category_axis = alt.Axis(**y_axis)
    chart = (
        alt.Chart(alt.Data(values=rows))
        .mark_bar(color=_TEAL, cornerRadius=2, cursor="pointer")
        .encode(
            y=alt.Y(
                f"{shown}:N",
                sort="-x",
                title=category_title,
                axis=category_axis,
            ),
            x=alt.X("games:Q", stack=None, scale=x_scale, axis=None),
            opacity=alt.condition(pick, alt.value(1), alt.value(0.4)),
            tooltip=[
                alt.Tooltip(f"{tip_field}:N", title=tip_title),
                alt.Tooltip("games:Q", title=value_title, format=value_label_format("count")),
            ],
        )
        .add_params(pick)
    )
    labels = _bar_labels(
        rows,
        category=shown,
        value="games",
        kind="count",
        scale=x_scale,
        sort="-x",
        horizontal=True,
        category_axis=category_axis,
        category_title=category_title,
    )
    return _with_labels(chart, labels, height, padding=frame_padding)


def period_bars(rows: list[dict]) -> _Drawn:
    """Training games by published period. No selection.

    Month ticks are horizontal, shortened from ``2025-11`` to ``Nov 25``.
    The full period stays in the tooltip. The value axis is hidden and the
    scale still starts at zero. A wide plot prints the full count above each
    bar. Below 56 pixels per month the count shortens (``240k``) and every
    other month is labeled so the ticks do not collide.
    """
    plotted = []
    for index, row in enumerate(rows):
        # The flag is ours: datum.index on an axis tick is not the month index.
        flag = "0" if index % 2 == 0 else "1"
        plotted.append(
            {
                **row,
                "tick": f"{flag}|{_period_tick(row.get('label'))}",
                "compact": compact_count(float(row["games"])),
            }
        )
    scale = _count_scale(plotted, "games")
    slot = max(len(plotted), 1) * _VERTICAL_LABEL_SLOT
    category_axis = _nominal_axis(
        labelFlush=True,
        labelExpr=(
            f"width < {slot} && split(datum.label, '|')[0] == '1' ? null "
            f": split(datum.label, '|')[1]"
        ),
    )
    chart = (
        alt.Chart(alt.Data(values=plotted))
        .mark_bar(color=_TEAL, cornerRadius=2)
        .encode(
            x=alt.X("tick:N", sort=None, title=None, axis=category_axis),
            y=alt.Y("games:Q", scale=scale, axis=None),
            tooltip=[
                alt.Tooltip("label:N", title="Period"),
                alt.Tooltip("games:Q", title="Games", format=value_label_format("count")),
            ],
        )
    )
    labels = _bar_labels(
        plotted,
        category="tick",
        value="games",
        kind="count",
        scale=scale,
        sort=None,
        horizontal=False,
        category_axis=category_axis,
        category_title=None,
        compact_below=slot,
        compact_field="compact",
    )
    return _with_labels(chart, labels, 240, padding={"left": 8, "right": 8, "top": 16, "bottom": 4})


def transposition_bars(rows: list[dict]) -> _Drawn:
    height = max(180, 26 * len(rows) + 24)
    scale = _rate_scale()
    category_axis = _nominal_axis()
    bars = (
        alt.Chart(alt.Data(values=rows))
        .mark_bar(color="#3d6b8c", cornerRadius=2)
        .encode(
            y=alt.Y("view:N", sort="-x", title=None, axis=category_axis),
            x=alt.X("share:Q", scale=scale, axis=None),
            tooltip=[
                alt.Tooltip("view:N", title="Opening"),
                alt.Tooltip("share_label:N", title="Transposing share"),
                alt.Tooltip(
                    "denominator_games:Q",
                    title="Games",
                    format=value_label_format("count"),
                ),
            ],
        )
    )
    labels = _bar_labels(
        rows,
        category="view",
        value="share",
        kind="rate",
        scale=scale,
        sort="-x",
        horizontal=True,
        category_axis=category_axis,
        category_title=None,
    )
    return _with_labels(bars, labels, height)
