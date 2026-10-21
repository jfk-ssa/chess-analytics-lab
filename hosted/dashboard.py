"""Read-only hosted dashboard for the committed public aggregate extract.

Run from the repository root:

    streamlit run hosted/dashboard.py

Streamlit Community Cloud installs ``hosted/requirements.txt`` only. That file
pins Streamlit, Altair, narwhals, pandas, and protobuf. It does not install
this project. The page reads ``data/public/dashboard_extract.json`` and does
not open a warehouse.
"""

from __future__ import annotations

import hashlib
import importlib.util
import itertools
import json
import sys
from collections import defaultdict
from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import streamlit as st  # pyright: ignore[reportMissingImports]

_BUCKETS = ("under_10", "10_to_29", "30_to_59", "60_plus")
_BANDS = ("under_1200", "1200_1599", "1600_1999", "2000_plus")
_BAND_LABEL = {
    "under_1200": "Under 1200",
    "1200_1599": "1200–1599",
    "1600_1999": "1600–1999",
    "2000_plus": "2000+",
}
_PHASES = ("all", "early_ply", "middle_ply", "late_ply")
_PHASE_LABEL = {
    "all": "All phases",
    "early_ply": "Early ply",
    "middle_ply": "Middle ply",
    "late_ply": "Late ply",
}
_COHORT_LABEL = {
    "elite_reference": "Elite reference",
    "rated_public": "Rated public",
}
_CATEGORIES = (
    "boundary",
    "clarification",
    "clock",
    "clock_compare",
    "compare_openings",
    "coverage",
    "draw_rate",
    "opening_score",
    "opening_usage",
    "unsupported",
)
_FIGURE_TABLES = ("opening_family_share", "opening_score_cell", "clock_bucket")
_LENSES = ("d4-g3", "d4-g3-catalan", "d4-g3-kings-indian")


def _load_local(name: str):
    path = Path(__file__).resolve().parent / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"hosted_{name}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"hosted module is missing: {name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _loader():
    src = str(Path(__file__).resolve().parents[1] / "src")
    inserted = src not in sys.path
    if inserted:
        sys.path.insert(0, src)
    try:
        from chess_analytics.public_extract import extract_path, load_extract, table_rows

        return extract_path, load_extract, table_rows
    finally:
        if inserted:
            sys.path.remove(src)


def _pct(value: float, digits: int = 1) -> str:
    quantum = Decimal(1).scaleb(-digits)
    shown = (Decimal(repr(value)) * 100).quantize(quantum, rounding=ROUND_HALF_UP)
    return f"{shown}%"


def _usd(value: float) -> str:
    return f"${value:,.4f}"


def _literal_currency(text: str) -> str:
    """Keep a currency amount literal. Streamlit treats ``$...$`` as LaTeX."""
    return text.replace("$", r"\$")


def _html_currency(text: str) -> str:
    """Escape a dollar inside HTML. A backslash would render inside the tag."""
    return text.replace("$", "&#36;")


def _caption(text: str) -> None:
    st.caption(_literal_currency(text))


def _share(value: float, numerator: int) -> str:
    shown = _pct(value)
    if numerator > 0 and shown == "0.0%":
        return "<0.1%"
    return shown


def _one(rows: list[dict], column: str, value: object) -> dict:
    matches = [row for row in rows if row[column] == value]
    if len(matches) != 1:
        raise ValueError(f"public extract {column} is missing: {value}")
    return matches[0]


def _half(wins: int, draws: int) -> int | float:
    score = wins + draws * 0.5
    if float(score).is_integer():
        return int(score)
    return score


def _close(stored: float | None, numerator: int | float, denominator: int) -> None:
    if stored is None or denominator == 0:
        raise ValueError("public extract rate is missing")
    if abs(stored - (numerator / denominator)) > 1e-9:
        raise ValueError("public extract rate does not match its numerator and denominator")


def _control_order(value: str) -> tuple[int, int]:
    base, increment = value.split("+")
    return int(base), int(increment)


def _run_label(row: dict) -> str:
    if row["effort"] in {"none", ""}:
        return row["model"]
    return f"{row['model']} · {row['effort']}"


def _show(rows: list[dict], *, alt: str, height: int | None = None) -> None:
    if not rows or not 1 <= len(rows[0]) <= 3:
        raise ValueError("dashboard table must have 1 to 3 columns")
    if not alt.strip():
        raise ValueError("dashboard table needs alt text")
    st.table(rows, hide_index=True, height="content" if height is None else height, alt=alt)


def _chart(charts, chart, *, alt: str) -> None:
    if not alt.strip():
        raise ValueError("dashboard chart needs alt text")
    st.altair_chart(chart, width="stretch", theme=None, alt=alt)
    del charts


def _validate(extract: dict, rows) -> None:
    _validate_draw(extract, rows)
    _validate_openings(extract, rows)
    _validate_clock(extract, rows)
    _validate_transposition(extract, rows)
    _validate_eval(extract, rows)
    _validate_lineage(extract, rows)


def _validate_draw(extract: dict, rows) -> None:
    build = extract.get("build")
    if not isinstance(build, dict) or not build.get("source_snapshot_id"):
        raise ValueError("public extract build record is missing")
    draw = _one(rows(extract, "metric_receipt"), "receipt_id", "game_draw_rate")
    eligible = _one(rows(extract, "lineage_stage"), "stage_id", "m3_august_prefix:eligible_games")
    if draw["denominator"] != eligible["count"] or not draw["denominator"]:
        raise ValueError("game draw rate denominator does not match eligible games")
    _close(draw["numerator"] / draw["denominator"], draw["numerator"], draw["denominator"])


def _validate_openings(extract: dict, rows) -> None:
    receipts = rows(extract, "metric_receipt")
    families = rows(extract, "opening_family_share")
    usage = _one(receipts, "receipt_id", "opening_usage")
    if sum(row["numerator"] for row in families) != usage["denominator"]:
        raise ValueError("opening families do not sum to the opening_usage denominator")
    for cell in rows(extract, "opening_color_score"):
        _close(cell["score_rate"], _half(cell["wins"], cell["draws"]), cell["games"])
        if cell["low_support"] != (cell["games"] < 100):
            raise ValueError("opening color low_support does not use the 100-game rule")
        if cell["color"] != "black":
            if cell["adjusted_score_rate"] is not None:
                raise ValueError("white opening cell has an adjusted score")
            continue
        receipt = _one(receipts, "receipt_id", f"opening_player_score:{cell['family']}")
        if _half(cell["wins"], cell["draws"]) != receipt["numerator"]:
            raise ValueError("black opening score does not match its receipt")
        if cell["games"] != receipt["denominator"]:
            raise ValueError("black opening games do not match the receipt")
        if cell["adjusted_interval_low"] is None or cell["adjusted_interval_high"] is None:
            raise ValueError("black opening cell is missing its interval")


def _validate_clock(extract: dict, rows) -> None:
    buckets = rows(extract, "clock_bucket")
    bands = rows(extract, "clock_pressure_band")
    receipts = rows(extract, "metric_receipt")
    for name in _BUCKETS:
        row = _one(buckets, "bucket", name)
        receipt = _one(receipts, "receipt_id", f"clock_pressure_error_proxy:{name}")
        _close(row["error_proxy_rate"], row["proxy_errors"], row["evaluable_moves"])
        if row["proxy_errors"] != receipt["numerator"]:
            raise ValueError("clock bucket does not match its receipt")
    band_errors = sum(row["proxy_errors"] for row in bands)
    bucket_errors = sum(row["proxy_errors"] for row in buckets)
    if band_errors != bucket_errors:
        raise ValueError("clock bands do not sum to the buckets")
    band_moves = sum(row["evaluable_moves"] for row in bands)
    bucket_moves = sum(row["evaluable_moves"] for row in buckets)
    if band_moves != bucket_moves:
        raise ValueError("clock band evaluable moves do not sum to the buckets")


def _validate_transposition(extract: dict, rows) -> None:
    scope = rows(extract, "transposition_scope")
    if len(scope) != 1:
        raise ValueError("transposition scope is not one row")
    views = [row for row in rows(extract, "transposition_view") if row["view"] == "all"]
    training = _one(rows(extract, "metric_receipt"), "receipt_id", "opening_corpus_training_games")
    if sum(row["denominator_games"] for row in views) != training["numerator"]:
        raise ValueError("transposition games do not match the opening corpus")
    if scope[0]["games"] != training["numerator"]:
        raise ValueError("transposition scope games do not match the opening corpus")
    visits = _one(rows(extract, "metric_receipt"), "receipt_id", "transposition_visits")
    if visits["numerator"] != scope[0]["visits"]:
        raise ValueError("transposition visits do not match the scope row")


def _validate_eval(extract: dict, rows) -> None:
    runs = rows(extract, "live_eval_run")
    cases = rows(extract, "live_eval_case")
    receipts = rows(extract, "metric_receipt")
    if not any(row["headline"] for row in runs):
        raise ValueError("live eval extract has no 5-repeat run")
    for run in runs:
        _close(run["pass_rate"], run["passed"], run["trials"])
        if run["wilson_low"] > run["pass_rate"] or run["pass_rate"] > run["wilson_high"]:
            raise ValueError("live eval pass rate is outside its Wilson interval")
        own = [
            row for row in cases if row["model"] == run["model"] and row["effort"] == run["effort"]
        ]
        if sum(row["passed"] for row in own) != run["passed"]:
            raise ValueError("live eval case passes do not match the run")
        receipt_id = f"live_eval_pass_rate:{run['model']} {run['effort']}"
        receipt = _one(receipts, "receipt_id", receipt_id)
        if receipt["numerator"] != run["passed"] or receipt["denominator"] != run["trials"]:
            raise ValueError("live eval receipt does not match the run")


def _validate_lineage(extract: dict, rows) -> None:
    per_group = [{row["analytical_id"] for row in rows(extract, name)} for name in _FIGURE_TABLES]
    found = set().union(*per_group)
    if any(len(ids) != 1 for ids in per_group) or len(found) != 1:
        raise ValueError("public extract analytical ids differ")


def _family_rows(families: list[dict], names: set[str] | None = None) -> list[dict]:
    chosen = families if names is None else [row for row in families if row["family"] in names]
    return [
        {
            "family": row["family"],
            "games": row["numerator"],
            "share_label": _share(row["value"], row["numerator"]),
        }
        for row in chosen
    ]


def _catalog(families: list[dict]) -> list[dict]:
    return [
        {
            "Family": row["family"],
            "Games": f"{row['numerator']:,}",
            "Share": _share(row["value"], row["numerator"]),
        }
        for row in families
    ]


def _august(stages: list[dict], population: str) -> int:
    match = [
        row
        for row in stages
        if row["lineage"] == "m3_august_prefix" and row["population"] == population
    ]
    if len(match) != 1:
        raise ValueError(f"August lineage stage is missing: {population}")
    return match[0]["count"]


def _funnel(stages: list[dict]) -> list[dict]:
    """Games removed from the August prefix, not the near-equal population counts."""
    labels = (
        ("excluded", "Unrated"),
        ("marked_bots", "Marked bots"),
        ("unknown_results", "Unknown results"),
    )
    return [
        {"stage": label, "count": _august(stages, population), "order": order}
        for order, (population, label) in enumerate(labels)
    ]


def _score_rows(cells: list[dict], *, color: str, families: set[str]) -> list[dict]:
    plotted = []
    for cell in cells:
        if color != "all" and cell["color"] != color:
            continue
        if cell["family"] not in families:
            continue
        side = "White" if cell["color"] == "white" else "Black"
        plotted.append(
            {
                "family": cell["family"],
                "series": f"{side}, raw",
                "rate": cell["score_rate"],
                "low": None,
                "high": None,
                "rate_label": _pct(cell["score_rate"]),
                "interval_label": "not published",
                "support_label": "yes" if cell["low_support"] else "no",
            }
        )
        if cell["adjusted_score_rate"] is None:
            continue
        plotted.append(
            {
                "family": cell["family"],
                "series": "Black, adjusted",
                "rate": cell["adjusted_score_rate"],
                "low": cell["adjusted_interval_low"],
                "high": cell["adjusted_interval_high"],
                "rate_label": _pct(cell["adjusted_score_rate"]),
                "interval_label": (
                    f"{_pct(cell['adjusted_interval_low'])}–{_pct(cell['adjusted_interval_high'])}"
                ),
                "support_label": "yes" if cell["low_support"] else "no",
            }
        )
    return plotted


def _score_caption(cells: list[dict]) -> str:
    sentences = []
    families = []
    for cell in cells:
        if cell["family"] not in families:
            families.append(cell["family"])
    for family in families:
        white = [row for row in cells if row["family"] == family and row["color"] == "white"]
        black = [row for row in cells if row["family"] == family and row["color"] == "black"]
        if not white or not black or black[0]["adjusted_interval_low"] is None:
            continue
        rate = white[0]["score_rate"]
        low = black[0]["adjusted_interval_low"]
        high = black[0]["adjusted_interval_high"]
        if rate < low:
            place = "below"
        elif rate > high:
            place = "above"
        else:
            place = "inside"
        short = family.removesuffix(" Defense")
        interval = f"{_pct(low)}–{_pct(high)}"
        sentences.append(
            f"{short} White is {_pct(rate)} ({_half_points(white[0])}), "
            f"{place} the Black interval {interval}."
        )
    if sentences:
        return " ".join(sentences)
    return (
        "These are raw half-point scores for the selected families. "
        "The adjusted interval was published for Black only."
    )


def _share_caption(selected: list[dict], denominator: int) -> str:
    if not selected or not denominator:
        return "Select a family to see its share of known-opening games."
    games = sum(row["games"] for row in selected)
    return (
        f"The selected families are {_pct(games / denominator)} "
        f"of {denominator:,} known-opening games."
    )


def _heatmap_rows(
    strata: list[dict],
    bands: Sequence[str],
    controls: Sequence[str],
    phase: str,
) -> list[dict]:
    totals = {(band, control): [0, 0, 0] for band in bands for control in controls}
    for row in strata:
        key = (row["rating_band"], row["time_control"])
        if key not in totals:
            continue
        if phase != "all" and row["phase"] != phase:
            continue
        found = totals[key]
        found[0] += row["eligible_moves"]
        found[1] += row["evaluable_moves"]
        found[2] += row["proxy_errors"]
    plotted = []
    for band in bands:
        for control in controls:
            eligible, evaluable, errors = totals[(band, control)]
            rate = None if evaluable == 0 else errors / evaluable
            coverage = None if eligible == 0 else evaluable / eligible
            plotted.append(
                {
                    "rating_band": _BAND_LABEL[band],
                    "time_control": control,
                    "rating_code": band,
                    "error_proxy_rate": rate,
                    "evaluable_moves": evaluable,
                    "rate_label": "no evaluable moves" if rate is None else _pct(rate),
                    "coverage_label": "none" if coverage is None else _pct(coverage),
                }
            )
    return plotted


def _falling_controls(rows: list[dict]) -> tuple[list[str], list[str]]:
    by_control: dict[str, dict[str, float]] = defaultdict(dict)
    for row in rows:
        rate = row["error_proxy_rate"]
        if row["evaluable_moves"] <= 0 or rate is None:
            continue
        by_control[row["time_control"]][row["rating_code"]] = rate
    falling = []
    other = []
    for control, rates in by_control.items():
        ordered = [rates[band] for band in _BANDS if band in rates]
        monotone = len(ordered) >= 3 and all(
            left + 1e-12 >= right for left, right in itertools.pairwise(ordered)
        )
        if monotone:
            falling.append(control)
        else:
            other.append(control)
    falling.sort(key=_control_order)
    other.sort(key=_control_order)
    return falling, other


def _heatmap_caption(rows: list[dict]) -> str:
    falling, other = _falling_controls(rows)
    if not falling and not other:
        return "This filter has no evaluable moves, so the error proxy is blank."
    if falling and not other:
        joined = ", ".join(falling)
        return f"On {joined} the error proxy falls as the rating band rises."
    if falling:
        return (
            f"On {', '.join(falling)} the error proxy falls as the rating band rises. "
            f"{', '.join(other)} is not monotone in this filter."
        )
    return "In this filter the error proxy does not fall steadily with rating."


def _bucket_rows(buckets: list[dict]) -> list[dict]:
    plotted = []
    for name in _BUCKETS:
        row = _one(buckets, "bucket", name)
        plotted.append(
            {
                "bucket": name,
                "error_proxy_rate": row["error_proxy_rate"],
                "rate_label": _pct(row["error_proxy_rate"]),
                "coverage_label": _pct(row["evaluation_coverage"]),
            }
        )
    return plotted


def _bucket_table(buckets: list[dict]) -> list[dict]:
    table = []
    for name in _BUCKETS:
        row = _one(buckets, "bucket", name)
        proxy = (
            f"{_pct(row['error_proxy_rate'])} "
            f"({row['proxy_errors']:,} / {row['evaluable_moves']:,})"
        )
        table.append(
            {
                "Bucket": name,
                "Error proxy": proxy,
                "Coverage": _pct(row["evaluation_coverage"]),
            }
        )
    return table


def _bucket_caption(buckets: list[dict]) -> str:
    under = _one(buckets, "bucket", "under_10")
    slow = _one(buckets, "bucket", "60_plus")
    mid = _one(buckets, "bucket", "30_to_59")
    relation = "above" if slow["error_proxy_rate"] > mid["error_proxy_rate"] else "below"
    return (
        f"Under 10 seconds has the highest error proxy, {_pct(under['error_proxy_rate'])}, "
        f"and the thinnest coverage, {_pct(under['evaluation_coverage'])}. "
        f"60+ seconds ({_pct(slow['error_proxy_rate'])}) is slightly {relation} "
        f"30–59 seconds ({_pct(mid['error_proxy_rate'])})."
    )


def _compression_rows(rows: list[dict]) -> list[dict]:
    return [
        {
            "cohort": _COHORT_LABEL[row["cohort"]],
            "ply": row["ply"],
            "endpoint_compression": row["endpoint_compression"],
            "compression_label": _pct(row["endpoint_compression"]),
            "distinct_positions": row["distinct_positions"],
            "distinct_routes": row["distinct_routes"],
        }
        for row in rows
    ]


def _compression_caption(rows: list[dict]) -> str:
    ends = {(row["cohort"], row["ply"]): row["endpoint_compression"] for row in rows}
    elite = ends[("elite_reference", 20)]
    public = ends[("rated_public", 20)]
    return (
        "Endpoint compression falls from ply 6 to ply 20 in both cohorts. "
        f"At ply 20 the elite month is {_pct(elite)} and the public prefixes are {_pct(public)}."
    )


def _coverage_rows(rows: list[dict]) -> list[dict]:
    plotted = []
    for row in rows:
        if row["view"] != "all" or row["mode"] != "recurring":
            continue
        plotted.append(
            {
                "cohort": _COHORT_LABEL[row["cohort"]],
                "n": row["n"],
                "share": row["share"],
                "share_label": _pct(row["share"]),
                "games": row["games"],
            }
        )
    return plotted


def _coverage_caption(rows: list[dict]) -> str:
    top = [row for row in rows if row["n"] == 20]
    if len(top) != 2:
        return "Union coverage of the top positions, for the all-positions view."
    by_cohort = {row["cohort"]: row["share"] for row in top}
    return (
        "The 20 most frequent positions cover "
        f"{_pct(by_cohort['elite_reference'])} of elite games and "
        f"{_pct(by_cohort['rated_public'])} of public games. Coverage is a union."
    )


def _transposing_rows(views: list[dict], cohort: str) -> list[dict]:
    plotted = []
    for row in views:
        if row["cohort"] != cohort or row["view"] == "all" or row["view"].startswith("d4-"):
            continue
        share = row["transposing_positions"] / row["distinct_positions"]
        plotted.append(
            {
                "view": row["view"],
                "share": share,
                "share_label": _pct(share),
                "denominator_games": row["denominator_games"],
            }
        )
    return plotted


def _lens_table(views: list[dict]) -> list[dict]:
    table = []
    for lens in _LENSES:
        elite = _view_games(views, "elite_reference", lens)
        public = _view_games(views, "rated_public", lens)
        table.append({"Lens": lens, "Elite games": f"{elite:,}", "Public games": f"{public:,}"})
    return table


def _view_games(views: list[dict], cohort: str, view: str) -> int:
    matches = [row for row in views if row["cohort"] == cohort and row["view"] == view]
    if len(matches) != 1:
        raise ValueError(f"transposition view is missing: {cohort} {view}")
    return matches[0]["denominator_games"]


def _wilson_rows(runs: list[dict]) -> list[dict]:
    plotted = []
    for row in _by_gate(runs):
        plotted.append(
            {
                "label": _run_label(row),
                "pass_rate": row["pass_rate"],
                "wilson_low": row["wilson_low"],
                "wilson_high": row["wilson_high"],
                "gate": "Hard fail" if row["hard_fail"] else "Gate clear",
                "rate_label": f"{_pct(row['pass_rate'])} ({row['passed']:,} / {row['trials']:,})",
                "wilson_label": f"{_pct(row['wilson_low'])}–{_pct(row['wilson_high'])}",
                "cost_label": _usd(row["known_gross_cost_usd"]),
            }
        )
    return plotted


def _by_gate(runs: list[dict]) -> list[dict]:
    return sorted(runs, key=lambda row: (row["hard_fail"], row["github_run_id"]))


def _short_model(model: str) -> str:
    if model.startswith("gpt-6-"):
        return model.removeprefix("gpt-6-").title()
    return model


def _ranges_overlap(left: dict, right: dict) -> bool:
    return left["wilson_low"] <= right["wilson_high"] and right["wilson_low"] <= left["wilson_high"]


def _join_labels(labels: list[str]) -> str:
    if len(labels) == 1:
        return labels[0]
    if len(labels) == 2:
        return f"{labels[0]} and {labels[1]}"
    return ", ".join(labels[:-1]) + f", and {labels[-1]}"


def _wilson_caption(runs: list[dict]) -> str:
    ordered = _by_gate(runs)
    clear = [_run_label(row) for row in ordered if not row["hard_fail"]]
    failed = [_run_label(row) for row in ordered if row["hard_fail"]]
    if clear and failed:
        gate = f"{_join_labels(clear)} clear; {', '.join(failed)} hard-fails."
    elif failed:
        gate = f"{', '.join(failed)} hard-fails."
    else:
        gate = "Every headline run clears the gate."
    pairs = []
    for index, left in enumerate(ordered):
        for right in ordered[index + 1 :]:
            verb = "overlap" if _ranges_overlap(left, right) else "do not overlap"
            pairs.append(f"{_run_label(left)} and {_run_label(right)} {verb}")
    gap = (" ".join(pairs) + ".") if pairs else ""
    priced = [f"{_run_label(row)} {_usd(row['known_gross_cost_usd'])}" for row in ordered]
    costs = ", ".join(priced)
    return f"Gate first: {gate} {gap} Known cost is {costs}."


def _category_rows(categories: list[dict], chosen: set[str]) -> list[dict]:
    plotted = []
    for row in categories:
        if row["category"] not in chosen:
            continue
        plotted.append(
            {
                "category": row["category"],
                "model": _run_label(row),
                "rate": row["passed"] / row["trials"],
                "passed_label": f"{row['passed']:,} / {row['trials']:,}",
            }
        )
    return plotted


def _category_caption(
    categories: list[dict],
    cases: list[dict],
    runs: list[dict],
    chosen: set[str],
) -> str:
    visible = [row for row in categories if row["category"] in chosen]
    if not visible:
        return "Select a category to compare pass rates."
    if set(chosen) != set(_CATEGORIES):
        worst = min(visible, key=lambda row: (row["passed"] / row["trials"], row["model"]))
        return (
            f"Lowest in this filter: {_run_label(worst)} {worst['category']}, "
            f"{worst['passed']} of {worst['trials']}."
        )
    luna = _one_category(categories, "gpt-6-luna", "coverage")
    sol = _one_category(categories, "gpt-6-sol", "boundary")
    budget = _boundary_case(cases, "gpt-6-sol")
    missed = f"{budget[0]['passed']} of {budget[0]['repeats']}" if budget else "unscored"
    abstentions = "; ".join(
        f"{_run_label(row)} has {row['over_abstention']} over-abstentions" for row in _by_gate(runs)
    )
    return (
        f"{abstentions}. "
        f"Luna's coverage cases pass {luna['passed']} of {luna['trials']}. "
        f"Sol's boundary cases pass {sol['passed']} of {sol['trials']}, "
        f"and boundary_budget passes {missed}."
    )


def _one_category(rows: list[dict], model: str, category: str) -> dict:
    matches = [row for row in rows if row["model"] == model and row["category"] == category]
    if len(matches) != 1:
        raise ValueError(f"live eval category is missing: {model} {category}")
    return matches[0]


def _case_rows(cases: list[dict], chosen: set[str]) -> list[dict]:
    return [row for row in cases if row["category"] in chosen]


def _boundary_case(cases: list[dict], model: str) -> list[dict]:
    return [row for row in cases if row["model"] == model and row["case_id"] == "boundary_budget"]


def _grid_caption(cases: list[dict]) -> str:
    sol = _boundary_case(cases, "gpt-6-sol")
    luna = _boundary_case(cases, "gpt-6-luna")
    if not sol or not luna:
        return (
            "Color and the printed count are repeats passed. A pale cell is a miss on every repeat."
        )
    text = (
        "Color and the printed count are repeats passed. boundary_budget is "
        f"{sol[0]['passed']} of {sol[0]['repeats']} for gpt-6-sol and "
        f"{luna[0]['passed']} of {luna[0]['repeats']} for gpt-6-luna"
    )
    grok = _boundary_case(cases, "grok-4.7")
    if grok:
        text += f", and {grok[0]['passed']} of {grok[0]['repeats']} for grok-4.7"
    return text + "."


def _build_rows(extract: dict, digest: str, rows) -> list[dict]:
    draw = _one(rows(extract, "metric_receipt"), "receipt_id", "game_draw_rate")
    build = extract["build"]
    fields = (
        ("Mart id", draw["mart_id"]),
        ("Source snapshot", build.get("source_snapshot_id")),
        ("Model sha256", build.get("model_sha256")),
        ("Lock sha256", build.get("lock_sha256")),
        ("Semantic manifest sha256", build.get("semantic_manifest_sha256")),
        ("Extract sha256", digest),
    )
    if any(not isinstance(value, str) or not value for _, value in fields):
        raise ValueError("public extract build record is incomplete")
    return [{"Field": name, "Value": value} for name, value in fields]


def _figure_caption(extract: dict, rows) -> tuple[list[dict], str]:
    build = extract["build"]
    snapshot = build.get("source_snapshot_id")
    per_group = [{row["analytical_id"] for row in rows(extract, name)} for name in _FIGURE_TABLES]
    analytical_id = next(iter(set().union(*per_group)))
    names = ", ".join(_FIGURE_TABLES)
    if analytical_id == snapshot:
        relation = "It matches build.source_snapshot_id."
    else:
        relation = (
            "It is not build.source_snapshot_id. "
            "Those rows are a different publication from the build snapshot."
        )
    return (
        [{"Field": "analytical_id", "Value": analytical_id}],
        f"This analytical_id is on the committed rows of {names}. {relation}",
    )


def _gate_name(row: dict) -> str:
    name = _short_model(row["model"])
    if row["effort"] not in {"none", ""}:
        return f"{name} {row['effort']}"
    return name


def _gate_card(runs: list[dict], cases: list[dict]) -> tuple[str, str, str]:
    ordered = _by_gate([row for row in runs if row["headline"]])
    clear = [row for row in ordered if not row["hard_fail"]]
    failed = [row for row in ordered if row["hard_fail"]]
    if not clear or not failed:
        return ("Analyst gate", "No split gate", "This extract has one gate outcome.")
    clear_names = ", ".join(_gate_name(row) for row in clear)
    fail_names = ", ".join(_gate_name(row) for row in failed)
    value = f"{clear_names} clear; {fail_names} fail"
    parts = []
    for row in clear:
        parts.append(f"{_gate_name(row)} {_pct(row['pass_rate'])} clears")
    for row in failed:
        budget = _boundary_case(cases, row["model"])
        miss = f"{budget[0]['passed']}/{budget[0]['repeats']}" if budget else "unscored"
        parts.append(
            f"{_gate_name(row)} {_pct(row['pass_rate'])} but misses boundary_budget {miss}"
        )
    return ("Analyst gate", value, "; ".join(parts))


def _hero(layout, extract: dict, rows) -> None:
    receipts = rows(extract, "metric_receipt")
    draw = _one(receipts, "receipt_id", "game_draw_rate")
    training = _one(receipts, "receipt_id", "opening_corpus_training_games")
    runs = rows(extract, "live_eval_run")
    cards = [
        (
            "Opening corpus",
            f"{training['numerator']:,}",
            "Training games. A separate lineage from the August prefix.",
        ),
        (
            "Draw rate",
            _pct(draw["numerator"] / draw["denominator"]),
            f"{draw['numerator']:,} / {draw['denominator']:,} eligible games",
        ),
        _gate_card(runs, rows(extract, "live_eval_case")),
    ]
    st.markdown(
        _html_currency(layout.equal_width_row(cards)),
        unsafe_allow_html=True,
    )


def _eval_cards(layout, runs: list[dict]) -> None:
    cards: list[tuple[str, str, str]] = []
    for row in _by_gate(runs):
        gate = "Hard fail" if row["hard_fail"] else "Gate clear"
        cards.append(
            (
                _run_label(row),
                _pct(row["pass_rate"]),
                f"{row['passed']:,} of {row['trials']:,}. {gate}",
            )
        )
        cards.append(
            (
                f"{_run_label(row)} cost",
                _usd(row["known_gross_cost_usd"]),
                f"Cap {_usd(row['max_run_usd'])}",
            )
        )
    st.markdown(
        _html_currency(layout.equal_width_row(cards)),
        unsafe_allow_html=True,
    )


def _overview(charts, extract: dict, rows) -> None:
    stages = rows(extract, "lineage_stage")
    families = rows(extract, "opening_family_share")
    denominator = families[0]["denominator"]
    funnel_rows = _funnel(stages)
    seen = _august(stages, "seen")
    accepted = _august(stages, "accepted")
    eligible = _august(stages, "eligible_games")
    removed = sum(row["count"] for row in funnel_rows)
    st.subheader("August prefix")
    _chart(
        charts,
        charts.funnel(funnel_rows),
        alt="Games removed from the August prefix: unrated, marked bots, and unknown results.",
    )
    _caption(
        f"Of {seen:,} games read, {accepted:,} are accepted and {eligible:,} are eligible. "
        f"{removed:,} games are removed: "
        + ", ".join(f"{row['count']:,} {row['stage'].lower()}" for row in funnel_rows)
        + ". The opening corpus is not added to this funnel."
    )
    _caption(
        "Query origin: metricflow. The draw-rate denominator matches "
        "m3_august_prefix:eligible_games."
    )
    st.subheader("Opening families")
    top = _family_rows(families)[:12]
    _chart(
        charts,
        charts.horizontal_bars(top, x_title="Games"),
        alt="Twelve largest opening families by games.",
    )
    _caption(_share_caption(top, denominator).replace("selected", "twelve largest"))
    _caption(
        f"Query origin: metricflow. Each share uses the opening_usage denominator, {denominator:,}."
    )


def _openings(charts, extract: dict, rows) -> None:
    families = rows(extract, "opening_family_share")
    names = [row["family"] for row in families]
    default = names[:8]
    chosen = st.multiselect("Family", names, default=default, key="opening_family")
    color = st.selectbox(
        "Color",
        ("all", "white", "black"),
        format_func=_color_label,
        key="opening_color",
    )
    selected = _family_rows(families, set(chosen))
    denominator = families[0]["denominator"]
    st.subheader("Share of known openings")
    if selected:
        _chart(
            charts,
            charts.horizontal_bars(selected, x_title="Games"),
            alt="Opening family game counts for the families selected above.",
        )
    _caption(_share_caption(selected, denominator))
    st.subheader("Score and adjusted interval")
    plotted = _score_rows(rows(extract, "opening_color_score"), color=color, families=set(chosen))
    if plotted:
        _chart(
            charts,
            charts.score_intervals(plotted),
            alt="Raw score by color and the Black adjusted score with its bootstrap interval.",
        )
    shown_cells = [
        cell
        for cell in rows(extract, "opening_color_score")
        if cell["family"] in set(chosen) and (color == "all" or cell["color"] == color)
    ]
    _caption(_score_caption(shown_cells))
    _caption("Query origin: metricflow. The raw half-point score is wins plus half the draws.")
    _score_table(rows(extract, "opening_color_score"))
    st.subheader("Transpositions")
    _transpositions(charts, extract, rows)
    _caption(f"All {len(families):,} families in opening_family_share, in extract order.")
    _show(_catalog(families), alt="Opening family game counts and shares.", height=420)


def _color_label(item: str) -> str:
    if item == "all":
        return "Both colors"
    return item.title()


def _half_points(cell: dict) -> str:
    points = cell["wins"] + cell["draws"] / 2
    shown = f"{int(points):,}" if points == int(points) else f"{points:,.1f}"
    return f"{shown} / {cell['games']:,}"


def _score_table(cells: list[dict]) -> None:
    table = []
    for cell in cells:
        score = f"{_pct(cell['score_rate'])} ({_half_points(cell)})"
        if cell["adjusted_score_rate"] is None:
            interval = "not published"
        else:
            low = _pct(cell["adjusted_interval_low"])
            high = _pct(cell["adjusted_interval_high"])
            interval = f"{_pct(cell['adjusted_score_rate'])} ({low}–{high})"
        table.append(
            {
                "Family": cell["family"],
                "Color": cell["color"],
                "Raw / adjusted": f"{score} / {interval}",
            }
        )
    _show(table, alt="Raw scores and, for Black, adjusted scores with bootstrap intervals.")
    _caption(
        "Query origin: committed_report. The interval is adjusted_interval_low to "
        "adjusted_interval_high. Low support is under 100 games; these four cells are not flagged."
    )


def _transpositions(charts, extract: dict, rows) -> None:
    scope = rows(extract, "transposition_scope")[0]
    _caption(f"{scope['scope']} {scope['visits']:,} position visits from {scope['games']:,} games.")
    compression = rows(extract, "transposition_compression")
    _chart(
        charts,
        charts.compression(_compression_rows(compression)),
        alt="Endpoint compression by ply for the elite month and the rated public prefixes.",
    )
    _caption(_compression_caption(compression))
    coverage = _coverage_rows(rows(extract, "transposition_coverage"))
    _chart(
        charts,
        charts.coverage(coverage),
        alt="Share of games covered by the top N recurring positions.",
    )
    _caption(_coverage_caption(rows(extract, "transposition_coverage")))
    views = rows(extract, "transposition_view")
    cohort = st.selectbox(
        "Cohort",
        ("elite_reference", "rated_public"),
        format_func=lambda item: _COHORT_LABEL[item],
        key="transposition_cohort",
    )
    bars = _transposing_rows(views, cohort)
    _chart(
        charts,
        charts.transposition_bars(bars),
        alt="Share of distinct positions that can be reached by more than one route.",
    )
    _caption(
        "A higher bar means more of that opening's positions are true transpositions. "
        "Frequency is not move quality."
    )
    _show(
        _lens_table(views),
        alt="Game counts for the three d4 and g3 fianchetto lenses.",
    )
    _caption(
        "Inside d4-g3, the elite month has more Catalan and King's Indian games "
        "than the public prefixes."
    )
    _caption("Query origin: committed_report. The reduction has no position ids.")


def _clock(charts, extract: dict, rows) -> None:
    bands = rows(extract, "clock_pressure_band")
    by_control: dict[str, int] = defaultdict(int)
    for row in bands:
        by_control[row["time_control"]] += row["evaluable_moves"]
    options = sorted(by_control, key=_control_order)
    default = [control for control in options if by_control[control] >= 100]
    chosen_bands = st.multiselect(
        "Rating band",
        list(_BANDS),
        default=list(_BANDS),
        format_func=lambda item: _BAND_LABEL[item],
        key="clock_band",
    )
    chosen_controls = st.multiselect("Time control", options, default=default, key="clock_control")
    phase = st.selectbox(
        "Phase",
        _PHASES,
        format_func=lambda item: _PHASE_LABEL[item],
        key="clock_phase",
    )
    st.subheader("Error proxy by rating and time control")
    if chosen_bands and chosen_controls:
        plotted = _heatmap_rows(
            rows(extract, "clock_stratum"),
            chosen_bands,
            chosen_controls,
            phase,
        )
        _chart(
            charts,
            charts.heatmap(
                plotted,
                x_order=sorted(chosen_controls, key=_control_order),
                y_order=[_BAND_LABEL[band] for band in _BANDS if band in chosen_bands],
            ),
            alt="Heatmap of the clock-pressure error proxy by rating band and time control.",
        )
        _caption(_heatmap_caption(plotted))
    else:
        _caption("Select a rating band and a time control.")
    _caption(
        "Query origin: committed_report. The heatmap pools clock_stratum "
        "from the same M4 publication as the four buckets. "
        "Gray cells have no evaluable moves. No independent-move interval is claimed."
    )
    st.subheader("Four clock buckets")
    buckets = rows(extract, "clock_bucket")
    _chart(
        charts,
        charts.bucket_bars(_bucket_rows(buckets)),
        alt="Error proxy for the four clock buckets.",
    )
    _caption(_bucket_caption(buckets))
    _caption("Query origin: reviewed_sql. Error proxy is proxy_errors / evaluable_moves.")
    _show(_bucket_table(buckets), alt="Clock-bucket error proxy and evaluation coverage.")


def _eval_tab(layout, charts, extract: dict, rows) -> None:
    runs = rows(extract, "live_eval_run")
    cases = rows(extract, "live_eval_case")
    categories = rows(extract, "live_eval_category")
    _eval_cards(layout, runs)
    _caption(
        "Published live-eval report: "
        "[live-eval.html](https://jfk-ssa.github.io/chess-analytics-lab/live-eval.html)."
    )
    st.subheader("Pass rate")
    _chart(
        charts,
        charts.wilson(_wilson_rows(_by_gate(runs))),
        alt="Headline pass rate for each model with its Wilson 95 percent interval.",
    )
    _caption(_wilson_caption(runs))
    _caption(
        "Query origin: committed_report. The bar is the receipt Wilson 95 percent interval. "
        "A 1-repeat run would not be drawn as a 5-repeat rate."
    )
    chosen = st.multiselect(
        "Category",
        list(_CATEGORIES),
        default=list(_CATEGORIES),
        key="eval_category",
    )
    visible_categories = _category_rows(categories, set(chosen))
    if visible_categories:
        order = [name for name in _CATEGORIES if name in chosen]
        _chart(
            charts,
            charts.category_dumbbell(visible_categories, category_order=order),
            alt="Dumbbell of pass rate by category. Each point is one model.",
        )
    _caption(_category_caption(categories, cases, runs, set(chosen)))
    visible_cases = _case_rows(cases, set(chosen))
    if visible_cases:
        case_order = [
            row["case_id"]
            for row in sorted(visible_cases, key=lambda item: item["case_order"])
            if row["model"] == visible_cases[0]["model"]
        ]
        # unique while keeping order
        seen: list[str] = []
        for case_id in case_order:
            if case_id not in seen:
                seen.append(case_id)
        model_order = [_run_label(row) for row in _by_gate(runs)]
        plotted = [{**row, "model": _run_label(row)} for row in visible_cases]
        _chart(
            charts,
            charts.case_grid(plotted, case_order=seen, model_order=model_order),
            alt="Grid of cases by model, colored by how many repeats passed.",
        )
    _caption(_grid_caption(visible_cases))


def _about(extract: dict, path: Path, rows) -> None:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    st.subheader("Build provenance")
    _caption(
        "Mart id is the game_draw_rate receipt. Source snapshot, model sha256, "
        "lock sha256, and semantic manifest sha256 are the extract build record. "
        "Extract sha256 is the hash of that file's bytes."
    )
    _show(
        _build_rows(extract, digest, rows),
        alt="Mart id, source snapshot, three build hashes, and extract sha256.",
    )
    figure_rows, figure_caption = _figure_caption(extract, rows)
    st.subheader("Figure analytical id")
    _caption(figure_caption)
    _show(
        figure_rows,
        alt="analytical_id on opening_family_share, opening_score_cell, and clock_bucket.",
    )
    st.subheader("Where the figures come from")
    _origin_captions(rows(extract, "metric_receipt"))
    st.subheader("Lineage")
    _caption(
        "Query origin: committed_report. The extract stores these lineages separately. "
        "This page does not add them."
    )
    _lineage_tables(rows(extract, "lineage_stage"))
    scope = rows(extract, "transposition_scope")[0]
    st.subheader("Transposition pin")
    _show(
        [
            {"Field": "Positions sha256", "Value": scope["positions_sha256"]},
            {"Field": "Games", "Value": f"{scope['games']:,}"},
            {"Field": "Visits", "Value": f"{scope['visits']:,}"},
        ],
        alt="Pinned opening-positions report hash, games, and position visits.",
    )
    _caption(scope["scope"])
    for limitation in rows(extract, "transposition_limitation"):
        _caption(limitation["text"])
    st.subheader("Tables in this extract")
    _show(
        _table_index(extract, rows),
        alt="Extract table names, row counts, and source reports.",
        height=420,
    )


def _origin_captions(receipts: list[dict]) -> None:
    grouped: dict[str, set[str]] = defaultdict(set)
    for row in receipts:
        grouped[row["query_origin"]].add(row["metric"])
    for origin in ("metricflow", "reviewed_sql", "committed_report"):
        metrics = ", ".join(sorted(grouped[origin]))
        _caption(f"Query origin: {origin}. Metrics: {metrics}.")


def _lineage_tables(stages: list[dict]) -> None:
    ordered = sorted(stages, key=lambda row: (row["lineage"], row["stage_order"]))
    corpus = [row for row in ordered if row["lineage"] == "opening_corpus"]
    august = [row for row in ordered if row["lineage"] == "m3_august_prefix"]
    _caption("Opening corpus. A dash is an empty period or cohort.")
    _show(
        [
            {
                "Period": "–" if row["period"] is None else row["period"],
                "Cohort": "–" if row["cohort"] is None else row["cohort"],
                "Games": f"{row['count']:,}",
            }
            for row in corpus
        ],
        alt="Opening corpus game counts.",
    )
    notes: list[str] = []
    for row in corpus:
        if row["note"] not in notes:
            notes.append(row["note"])
    for note in notes:
        _caption(note)
    _caption("August prefix.")
    _show(
        [
            {"Population": row["population"], "Games": f"{row['count']:,}", "Note": row["note"]}
            for row in august
        ],
        alt="August prefix game counts.",
    )


def _table_index(extract: dict, rows) -> list[dict]:
    table = []
    for name in extract["tables"]:
        body = rows(extract, name)
        sources = sorted({row["source_report"] for row in body if row.get("source_report")})
        if sources:
            source = ", ".join(sources)
        elif name in {"live_eval_case", "live_eval_category"}:
            run_rows = rows(extract, "live_eval_run")
            run_sources = sorted(
                {row["source_report"] for row in run_rows if row.get("source_report")}
            )
            source = ", ".join(run_sources) if run_sources else "live_eval_run"
        else:
            source = "metric_receipt"
        table.append({"Table": name, "Rows": f"{len(body):,}", "Source": source})
    return table


def _render(layout, charts, extract: dict, path: Path, rows) -> None:
    charts.install_theme()
    stylesheet = Path(__file__).resolve().parent / "static" / "dashboard.css"
    if stylesheet.is_file():
        st.html(stylesheet)
    st.title("Chess Analytics Lab")
    _caption(
        "Read-only figures from data/public/dashboard_extract.json. "
        "No warehouse, no uploads, and no external calls."
    )
    _hero(layout, extract, rows)
    overview, openings, clock, analyst, about = st.tabs(
        ["Overview", "Openings", "Clock pressure", "AI analyst eval", "About the data"]
    )
    with overview:
        _overview(charts, extract, rows)
    with openings:
        _openings(charts, extract, rows)
    with clock:
        _clock(charts, extract, rows)
    with analyst:
        _eval_tab(layout, charts, extract, rows)
    with about:
        _about(extract, path, rows)


def _fail(message: str) -> None:
    st.title("Chess Analytics Lab")
    st.error(message)
    st.stop()


def main() -> None:
    try:
        layout = _load_local("layout")
        charts = _load_local("charts")
        extract_path, load_extract, table_rows = _loader()
        path = extract_path()
        extract = load_extract(path)
        _validate(extract, table_rows)
        _render(layout, charts, extract, path, table_rows)
    except json.JSONDecodeError as exc:
        _fail(f"Public extract is not valid JSON: {exc}")
    except ValueError as exc:
        _fail(f"Public extract failed validation: {exc}")
    except OSError as exc:
        _fail(f"Public extract unavailable: {exc}")
    except ModuleNotFoundError as exc:
        _fail(f"Public extract reader could not be imported: {exc}")


st.set_page_config(page_title="Chess Analytics Lab", layout="wide")
main()
