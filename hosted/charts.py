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
# Luna stays teal and Sol stays orange. Later runs take the remaining swatches
# in the order the caller lists them.
_NAMED_RUN_COLORS = {"gpt-6-luna": _TEAL, "gpt-6-sol": _ORANGE}
_RUN_COLOR_POOL = ("#3d6b8c", "#6b4c7a", "#203433", "#8a6a2f", "#5c726b")


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


def _frame(chart: _Drawn, height: int, *, width: Any = "container") -> _Drawn:
    return cast(_Drawn, chart.properties(height=height, width=width))


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


def funnel(rows: list[dict]) -> _Drawn:
    """Games removed. ``rows`` need stage, count, and order."""
    order = alt.EncodingSortField(field="order", order="ascending")
    bars = (
        alt.Chart(alt.Data(values=rows))
        .mark_bar(color=_TEAL, cornerRadius=2)
        .encode(
            y=alt.Y("stage:N", sort=order, title=None),
            x=alt.X(
                "count:Q",
                title="Games removed",
                scale=alt.Scale(domainMin=0),
            ),
            tooltip=[
                alt.Tooltip("stage:N", title="Removed"),
                alt.Tooltip("count:Q", title="Games", format=","),
            ],
        )
    )
    labels = (
        alt.Chart(alt.Data(values=rows))
        .mark_text(align="left", dx=6, color="#203433", font="Inter", fontSize=12)
        .encode(
            y=alt.Y("stage:N", sort=order),
            x="count:Q",
            text=alt.Text("count:Q", format=","),
        )
    )
    return _frame(bars + labels, 168)


def horizontal_bars(rows: list[dict], *, x_title: str) -> _Drawn:
    """``rows`` need family and games."""
    height = max(180, 28 * len(rows) + 24)
    chart = (
        alt.Chart(alt.Data(values=rows))
        .mark_bar(color="#116559", cornerRadius=2)
        .encode(
            y=alt.Y("family:N", sort="-x", title=None),
            x=alt.X("games:Q", title=x_title),
            tooltip=[
                alt.Tooltip("family:N", title="Family"),
                alt.Tooltip("games:Q", title="Games", format=","),
                alt.Tooltip("share_label:N", title="Share"),
            ],
        )
    )
    return _frame(chart, height)


def score_intervals(rows: list[dict]) -> _Drawn:
    """Grouped scores. Interval rows also carry low and high."""
    present = [name for name in _SERIES if any(row["series"] == name for row in rows)]
    offset = alt.Scale(domain=present)
    color = alt.Scale(domain=present, range=list(_SERIES_COLORS[: len(present)]))
    base = alt.Chart(alt.Data(values=rows)).encode(
        x=alt.X("family:N", title=None),
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
            title="Score",
            axis=alt.Axis(format="%"),
            scale=alt.Scale(domain=[0, 1]),
        )
    )
    intervals = [row for row in rows if row["low"] is not None]
    if not intervals:
        return _frame(bars, 280)
    errors = (
        alt.Chart(alt.Data(values=intervals))
        .mark_errorbar(color=_ORANGE, ticks=True)
        .encode(
            x=alt.X("family:N"),
            xOffset=alt.XOffset("series:N", scale=offset),
            y=alt.Y("low:Q", scale=alt.Scale(domain=[0, 1])),
            y2="high:Q",
        )
    )
    return _frame(bars + errors, 300)


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
    chart = (
        alt.Chart(alt.Data(values=rows))
        .mark_bar(color="#116559", cornerRadius=2)
        .encode(
            x=alt.X("bucket:N", sort=[row["bucket"] for row in rows], title="Seconds left"),
            y=alt.Y("error_proxy_rate:Q", title="Error proxy", axis=alt.Axis(format="%")),
            tooltip=[
                alt.Tooltip("bucket:N", title="Bucket"),
                alt.Tooltip("rate_label:N", title="Error proxy"),
                alt.Tooltip("coverage_label:N", title="Evaluation coverage"),
            ],
        )
    )
    return _frame(chart, 240)


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
    scale = {"domain": domain, "nice": False, "zero": False, "clamp": True}
    color = alt.Scale(domain=["Gate clear", "Hard fail"], range=[_TEAL, _ORANGE])
    y_axis = alt.Axis(labelAngle=0, labelLimit=0, labelFontSize=11, labelOverlap=False)
    rules = (
        alt.Chart(alt.Data(values=rows))
        .mark_rule(strokeWidth=3)
        .encode(
            y=alt.Y("label:N", sort=order, title=None, axis=y_axis),
            x=alt.X(
                "wilson_low:Q",
                title="Pass rate",
                axis=_pass_axis(domain),
                scale=alt.Scale(**scale),
            ),
            x2="wilson_high:Q",
            color=alt.Color("gate:N", scale=color, title=None),
        )
    )
    points = (
        alt.Chart(alt.Data(values=rows))
        .mark_point(filled=True, size=90)
        .encode(
            y=alt.Y("label:N", sort=order, axis=y_axis),
            x=alt.X("pass_rate:Q", scale=alt.Scale(**scale)),
            color=alt.Color("gate:N", scale=color, title=None),
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
    return _frame(rules + points, height)


def _run_colors(models: list[str]) -> list[str]:
    pool = iter(_RUN_COLOR_POOL)
    colors: list[str] = []
    for model in models:
        named = _NAMED_RUN_COLORS.get(model)
        colors.append(named if named is not None else next(pool))
    return colors


def category_dumbbell(
    rows: list[dict], *, category_order: list[str], model_order: list[str] | None = None
) -> _Drawn:
    """Pass rate by category. Points are runs; the rule joins one category."""
    models: list[str] = []
    grouped: dict[str, list[float]] = {}
    for row in rows:
        if row["model"] not in models:
            models.append(row["model"])
        grouped.setdefault(row["category"], []).append(row["rate"])
    if model_order:
        rank = {name: index for index, name in enumerate(model_order)}
        models.sort(key=lambda name: rank.get(name, len(rank)))
    spans = [
        {"category": category, "low": min(rates), "high": max(rates)}
        for category, rates in grouped.items()
    ]
    domain = pass_rate_domain([row["rate"] for row in rows])
    scale = {"domain": domain, "nice": False, "zero": False, "clamp": True}
    rules = (
        alt.Chart(alt.Data(values=spans))
        .mark_rule(color="#8aa399", strokeWidth=2)
        .encode(
            y=alt.Y("category:N", sort=category_order, title=None),
            x=alt.X(
                "low:Q",
                title="Pass rate",
                axis=_pass_axis(domain),
                scale=alt.Scale(**scale),
                stack=None,
            ),
            x2="high:Q",
        )
    )
    points = (
        alt.Chart(alt.Data(values=rows))
        .mark_point(filled=True, size=110)
        .encode(
            y=alt.Y("category:N", sort=category_order, title=None),
            x=alt.X("rate:Q", scale=alt.Scale(**scale), stack=None),
            color=alt.Color(
                "model:N",
                title=None,
                sort=models,
                scale=alt.Scale(domain=models, range=_run_colors(models)),
                legend=alt.Legend(orient="bottom", columns=1, labelLimit=0, labelFontSize=11),
            ),
            tooltip=[
                alt.Tooltip("model:N", title="Run"),
                alt.Tooltip("category:N", title="Category"),
                alt.Tooltip("passed_label:N", title="Passed"),
            ],
        )
    )
    return _frame(rules + points, max(220, 32 * len(category_order) + 36))


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
            axis=alt.Axis(labelLimit=220, labelFontSize=11, labelAngle=0),
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
    return _frame(rects + counts, height, width=alt.Step(112))


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


def selectable_bars(
    rows: list[dict],
    *,
    name: str,
    field: str,
    value_title: str,
    label_field: str | None = None,
) -> _Drawn:
    """Horizontal bars with a point selection named ``name`` on ``field``."""
    shown = label_field or field
    height = max(180, 28 * max(len(rows), 1) + 24)
    pick = alt.selection_point(name=name, fields=[field])
    chart = (
        alt.Chart(alt.Data(values=rows))
        .mark_bar(color=_TEAL, cornerRadius=2, cursor="pointer")
        .encode(
            y=alt.Y(
                f"{shown}:N",
                sort="-x",
                title=None,
                axis=alt.Axis(labelLimit=480, labelFont="Inter", labelOverlap=False),
            ),
            x=alt.X(
                "games:Q",
                title=value_title,
                stack=None,
                axis=alt.Axis(labelFont="Inter"),
            ),
            opacity=alt.condition(pick, alt.value(1), alt.value(0.4)),
            tooltip=[
                alt.Tooltip(f"{field}:N", title="Line" if field == "line" else shown),
                alt.Tooltip("games:Q", title=value_title, format=","),
            ],
        )
        .add_params(pick)
    )
    return _frame(chart, height)


def period_bars(rows: list[dict]) -> _Drawn:
    """Training games by published period. No selection."""
    chart = (
        alt.Chart(alt.Data(values=rows))
        .mark_bar(color=_TEAL, cornerRadius=2)
        .encode(
            x=alt.X(
                "label:N",
                sort=None,
                title=None,
                axis=alt.Axis(labelAngle=-40, labelFont="Inter"),
            ),
            y=alt.Y("games:Q", title="Games"),
            tooltip=[
                alt.Tooltip("label:N", title="Period"),
                alt.Tooltip("games:Q", title="Games", format=","),
            ],
        )
    )
    return _frame(chart, 240)


def transposition_bars(rows: list[dict]) -> _Drawn:
    height = max(180, 26 * len(rows) + 24)
    chart = (
        alt.Chart(alt.Data(values=rows))
        .mark_bar(color="#3d6b8c", cornerRadius=2)
        .encode(
            y=alt.Y("view:N", sort="-x", title=None),
            x=alt.X(
                "share:Q",
                title="Transposing positions / distinct positions",
                axis=alt.Axis(format="%"),
            ),
            tooltip=[
                alt.Tooltip("view:N", title="Opening"),
                alt.Tooltip("share_label:N", title="Transposing share"),
                alt.Tooltip("denominator_games:Q", title="Games", format=","),
            ],
        )
    )
    return _frame(chart, height)
