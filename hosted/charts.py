"""Altair charts for the hosted dashboard. No warehouse and no network."""

from __future__ import annotations

from typing import cast

import altair as alt  # pyright: ignore[reportMissingImports]

_Drawn = alt.Chart | alt.LayerChart

_INSTALLED = False
_SERIES = ("White, raw", "Black, raw", "Black, adjusted")
_SERIES_COLORS = ("#3d6b8c", "#203433", "#116559")


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
                "range": {"category": ["#116559", "#c4552a", "#3d6b8c", "#b0892e", "#6b4c7a"]},
                "bar": {"color": "#116559"},
            }
        }

    _INSTALLED = True


def _frame(chart: _Drawn, height: int) -> _Drawn:
    return cast(_Drawn, chart.properties(height=height, width="container"))


def funnel(rows: list[dict]) -> _Drawn:
    """Centered bars. ``rows`` need stage, count, and order."""
    plotted = [{**row, "left": -row["count"] / 2, "right": row["count"] / 2} for row in rows]
    bars = (
        alt.Chart(alt.Data(values=plotted))
        .mark_bar(color="#116559", cornerRadius=3)
        .encode(
            y=alt.Y(
                "stage:N",
                sort=alt.EncodingSortField(field="order", order="ascending"),
                title=None,
            ),
            x=alt.X(
                "left:Q",
                title=None,
                axis=alt.Axis(labels=False, ticks=False, grid=False, domain=False),
            ),
            x2="right:Q",
            tooltip=[
                alt.Tooltip("stage:N", title="Stage"),
                alt.Tooltip("count:Q", title="Games", format=","),
            ],
        )
    )
    labels = (
        alt.Chart(alt.Data(values=plotted))
        .mark_text(align="left", dx=8, color="#203433", font="Inter", fontSize=12)
        .encode(
            y=alt.Y("stage:N", sort=alt.EncodingSortField(field="order", order="ascending")),
            x="right:Q",
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
            scale=alt.Scale(domain=[0.35, 0.62]),
        )
    )
    intervals = [row for row in rows if row["low"] is not None]
    if not intervals:
        return _frame(bars, 280)
    errors = (
        alt.Chart(alt.Data(values=intervals))
        .mark_errorbar(color="#c4552a", ticks=True)
        .encode(
            x=alt.X("family:N"),
            xOffset=alt.XOffset("series:N", scale=offset),
            y=alt.Y("low:Q"),
            y2="high:Q",
        )
    )
    return _frame(bars + errors, 300)


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
                    scale=alt.Scale(domain=[0.04, 0.20], scheme="goldgreen", reverse=True),
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
    """Pass rate with the receipt's Wilson interval as a horizontal bar."""
    order = [row["label"] for row in rows]
    color = alt.Scale(domain=["Gate clear", "Hard fail"], range=["#116559", "#c4552a"])
    rules = (
        alt.Chart(alt.Data(values=rows))
        .mark_rule(strokeWidth=3)
        .encode(
            y=alt.Y("label:N", sort=order, title=None),
            x=alt.X(
                "wilson_low:Q",
                title="Pass rate",
                axis=alt.Axis(format="%"),
                scale=alt.Scale(domain=[0.75, 1]),
            ),
            x2="wilson_high:Q",
            color=alt.Color("gate:N", scale=color, title=None),
        )
    )
    points = (
        alt.Chart(alt.Data(values=rows))
        .mark_point(filled=True, size=90)
        .encode(
            y=alt.Y("label:N", sort=order),
            x="pass_rate:Q",
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
    return _frame(rules + points, 160)


def category_bars(rows: list[dict], *, category_order: list[str]) -> _Drawn:
    chart = (
        alt.Chart(alt.Data(values=rows))
        .mark_bar(cornerRadius=2)
        .encode(
            y=alt.Y("category:N", sort=category_order, title=None),
            x=alt.X("rate:Q", title="Pass rate", axis=alt.Axis(format="%")),
            color=alt.Color(
                "model:N",
                title=None,
                scale=alt.Scale(range=["#116559", "#c4552a", "#3d6b8c", "#b0892e"]),
            ),
            xOffset="model:N",
            tooltip=[
                alt.Tooltip("model:N", title="Model"),
                alt.Tooltip("category:N", title="Category"),
                alt.Tooltip("passed_label:N", title="Passed"),
            ],
        )
    )
    return _frame(chart, max(220, 36 * len(category_order) + 24))


def case_grid(rows: list[dict], *, case_order: list[str], model_order: list[str]) -> _Drawn:
    """Color is the number of repeats passed, on a fixed 0–5 scale."""
    height = max(180, 16 * len(case_order) + 36)
    chart = (
        alt.Chart(alt.Data(values=rows))
        .mark_rect(stroke="#faf9f5", strokeWidth=1)
        .encode(
            x=alt.X("model:N", sort=model_order, title=None),
            y=alt.Y(
                "case_id:N",
                sort=case_order,
                title=None,
                axis=alt.Axis(labelLimit=220, labelFontSize=11),
            ),
            color=alt.Color(
                "passed:O",
                title="Repeats passed",
                scale=alt.Scale(
                    domain=[0, 1, 2, 3, 4, 5],
                    range=["#f4d6c6", "#f6e7c1", "#e4efd4", "#b7d4c4", "#6eae9a", "#116559"],
                ),
            ),
            tooltip=[
                alt.Tooltip("case_id:N", title="Case"),
                alt.Tooltip("category:N", title="Category"),
                alt.Tooltip("model:N", title="Model"),
                alt.Tooltip("passed:Q", title="Repeats passed"),
                alt.Tooltip("repeats:Q", title="Repeats"),
                alt.Tooltip("severity:N", title="Severity"),
            ],
        )
    )
    return _frame(chart, height)


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
                scale=alt.Scale(range=["#116559", "#c4552a"]),
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
                scale=alt.Scale(range=["#116559", "#c4552a"]),
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
