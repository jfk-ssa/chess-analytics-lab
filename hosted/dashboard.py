"""Hosted dashboard: a filterable cube, plus the committed live-eval extract.

Run from the repository root:

    streamlit run hosted/dashboard.py

Streamlit Community Cloud installs ``hosted/requirements.txt`` only. That file
pins Streamlit, Altair, DuckDB, narwhals, pandas, and protobuf. It does not
install this project. A push that leaves the requirements file unchanged
reruns this process without reinstalling. ``hosted/repo_import.py`` then
imports ``chess_analytics`` from ``src/`` again, before ``hosted/bi.py``
loads the cube. The page reads ``data/public/dashboard_cube.parquet`` and
``data/public/dashboard_extract.json``. It does not open a warehouse.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import NoReturn

import streamlit as st  # pyright: ignore[reportMissingImports]

_BUCKETS = ("under_10", "10_to_29", "30_to_59", "60_plus")
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


def _load_local(name: str):
    path = Path(__file__).resolve().parent / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"hosted_{name}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"hosted module is missing: {name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _pct(value: float, digits: int = 1) -> str:
    quantum = Decimal(1).scaleb(-digits)
    shown = (Decimal(repr(value)) * 100).quantize(quantum, rounding=ROUND_HALF_UP)
    return f"{shown}%"


def _usd(value: float) -> str:
    return f"${value:,.4f}"


def _usd_trim(value: float, digits: int = 6) -> str:
    """Six decimals, then drop trailing zeros. 0.222530 prints as $0.22253."""
    rendered = f"{value:,.{digits}f}".rstrip("0").rstrip(".")
    return f"${rendered}"


def _usd_3(value: float) -> str:
    """Three decimals on every sweep card. 0.22253 prints as $0.223."""
    return f"${value:,.3f}"


def _literal_currency(text: str) -> str:
    """Keep a currency amount literal. Streamlit treats ``$...$`` as LaTeX."""
    return text.replace("$", r"\$")


def _html_currency(text: str) -> str:
    """Escape a dollar inside HTML. A backslash would render inside the tag."""
    return text.replace("$", "&#36;")


def _caption(text: str) -> None:
    st.caption(_literal_currency(text))


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


def _run_label(row: dict, *, suffix: bool = False) -> str:
    """Title inside one set. The set heading already states the repeat count.

    ``suffix`` keeps ``×5`` or ``×1`` when one sentence names both low runs.
    Luna and Sol have no effort suffix. No run hash.
    """
    effort = str(row.get("effort") or "")
    model = str(row["model"])
    if effort in {"none", ""}:
        return model
    if "repeats" not in row:
        raise ValueError(f"live eval label needs a repeat count: {model} {effort}")
    label = f"{model} · {effort}"
    if suffix:
        return f"{label} ×{int(row['repeats'])}"
    return label


def _axis_run_label(row: dict) -> str:
    """Two horizontal lines. The repeat count stays in the set heading."""
    effort = str(row.get("effort") or "")
    model = str(row["model"])
    if effort in {"none", ""}:
        return model
    return f"{model}\n{effort}"


def _show(rows: list[dict], *, alt: str, height: int | None = None) -> None:
    if not rows or not 1 <= len(rows[0]) <= 3:
        raise ValueError("dashboard table must have 1 to 3 columns")
    if not alt.strip():
        raise ValueError("dashboard table needs alt text")
    st.table(rows, hide_index=True, height="content" if height is None else height, alt=alt)


def _chart(charts, chart, *, alt: str, key: str | None = None, content_width: bool = False):
    if not alt.strip():
        raise ValueError("dashboard chart needs alt text")
    del charts
    # ``content`` keeps a step width, so heatmap labels are not squeezed.
    width = "content" if content_width else "stretch"
    if key is None:
        return st.altair_chart(chart, width=width, theme=None, alt=alt)
    return st.altair_chart(
        chart,
        width=width,
        theme=None,
        alt=alt,
        on_select="rerun",
        key=key,
    )


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


def _live_eval_rate_id(run: dict, runs: list[dict]) -> str:
    """Match ``live_eval_rate_id``. Inlined: Community Cloud does not install the package."""
    model = str(run["model"])
    effort = str(run["effort"])
    repeats = int(run["repeats"])
    shared = sum(1 for other in runs if other["model"] == model and other["effort"] == effort) > 1
    subject = f"{model} {effort}"
    if shared and repeats != 5:
        subject = f"{subject} r{repeats}"
    return f"live_eval_pass_rate:{subject}"


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
            row
            for row in cases
            if row["model"] == run["model"]
            and row["effort"] == run["effort"]
            and row["repeats"] == run["repeats"]
        ]
        if not own:
            if run["headline"]:
                raise ValueError("live eval case passes do not match the run")
            continue
        if sum(row["passed"] for row in own) != run["passed"]:
            raise ValueError("live eval case passes do not match the run")
        receipt_id = _live_eval_rate_id(run, runs)
        receipt = _one(receipts, "receipt_id", receipt_id)
        if receipt["numerator"] != run["passed"] or receipt["denominator"] != run["trials"]:
            raise ValueError("live eval receipt does not match the run")


def _validate_lineage(extract: dict, rows) -> None:
    per_group = [{row["analytical_id"] for row in rows(extract, name)} for name in _FIGURE_TABLES]
    found = set().union(*per_group)
    if any(len(ids) != 1 for ids in per_group) or len(found) != 1:
        raise ValueError("public extract analytical ids differ")


def _plotted_row(row: dict, label: str) -> dict:
    return {
        "label": label,
        "pass_rate": row["pass_rate"],
        "wilson_low": row["wilson_low"],
        "wilson_high": row["wilson_high"],
        "gate": "Hard fail" if row["hard_fail"] else "Gate clear",
        "rate_label": f"{_pct(row['pass_rate'])} ({row['passed']:,} / {row['trials']:,})",
        "wilson_label": f"{_pct(row['wilson_low'])}–{_pct(row['wilson_high'])}",
        "cost_label": _usd(row["known_gross_cost_usd"]),
    }


def _wilson_rows(runs: list[dict]) -> list[dict]:
    """Keep the caller's order. Each set picks its own runs."""
    return [_plotted_row(row, _run_label(row)) for row in runs]


def _sweep_wilson_rows(runs: list[dict]) -> list[dict]:
    """Sweep bars run low, medium, high. The headline chart still uses gate order."""
    ordered = sorted(runs, key=lambda row: _EFFORT_ORDER.get(str(row["effort"]), 9))
    return [_plotted_row(row, str(row["effort"])) for row in ordered]


def _by_gate(runs: list[dict]) -> list[dict]:
    return sorted(runs, key=lambda row: (row["hard_fail"], row["github_run_id"]))


def _ranges_overlap(left: dict, right: dict) -> bool:
    return left["wilson_low"] <= right["wilson_high"] and right["wilson_low"] <= left["wilson_high"]


def _join_labels(labels: list[str]) -> str:
    if len(labels) == 1:
        return labels[0]
    if len(labels) == 2:
        return f"{labels[0]} and {labels[1]}"
    return ", ".join(labels[:-1]) + f", and {labels[-1]}"


def _interval_comparable(left: dict, right: dict) -> bool:
    """Wilson bars are compared only inside a like-for-like pair.

    Luna and Sol share frozen inputs. Their instruction hashes differ by the
    known dataset-id pair, so that pair stays comparable. Grok low ×5 does not
    share those frozen runner files. The 1-repeat grok runs share an instruction
    hash with each other. Low ×5 differs from them in the dataset snapshot id
    embedded in the instructions, and the repeat count differs too.
    """
    if "frozen_group" not in left or "frozen_group" not in right:
        return False
    if left["frozen_group"] != right["frozen_group"]:
        return False
    if int(left["repeats"]) != int(right["repeats"]):
        return False
    if left["instructions_sha256"] == right["instructions_sha256"]:
        return True
    return str(left["effort"]) == "none" and str(right["effort"]) == "none"


def _comparability_note(runs: list[dict]) -> str:
    """State the caveat that applies to the runs on this chart."""
    if any("frozen_group" not in row for row in runs):
        return ""
    parts: list[str] = []
    openai = [row for row in runs if str(row["effort"]) == "none"]
    grok_low_5 = [
        row
        for row in runs
        if row["model"] == "grok-4.7" and row["effort"] == "low" and int(row["repeats"]) == 5
    ]
    one_repeat = [row for row in runs if row["model"] == "grok-4.7" and int(row["repeats"]) == 1]
    if len(openai) >= 2 and len({row["frozen_group"] for row in openai}) == 1:
        names = _join_labels([_run_label(row) for row in openai])
        parts.append(f"{names} share frozen inputs.")
    if grok_low_5 and openai:
        label = _run_label(grok_low_5[0])
        parts.append(
            f"{label} does not: the frozen runner files changed, "
            "so its interval is not compared with theirs."
        )
    elif grok_low_5 and not openai:
        parts.append(f"{_run_label(grok_low_5[0])} is outside the 1-repeat comparison.")
    if len(one_repeat) >= 2:
        names = _join_labels([_run_label(row) for row in one_repeat])
        parts.append(f"{names} are like-for-like with each other.")
        if not grok_low_5:
            parts.append(
                "They are 48 trials each and use a different dataset snapshot "
                "from grok-4.7 · low ×5."
            )
    if grok_low_5 and one_repeat:
        parts.append(
            f"{_run_label(grok_low_5[0])} differs from them in the dataset snapshot id "
            "embedded in the instructions, so its interval is not compared with theirs."
        )
    if not parts:
        return "Intervals are compared only inside a shared frozen-input group."
    return " ".join(parts)


def _wilson_caption(runs: list[dict]) -> str:
    ordered = list(runs)
    clear = [_run_label(row) for row in ordered if not row["hard_fail"]]
    failed = [_run_label(row) for row in ordered if row["hard_fail"]]
    if clear and failed:
        gate = f"{_join_labels(clear)} clear; {', '.join(failed)} hard-fails."
    elif failed:
        gate = f"{', '.join(failed)} hard-fails."
    elif clear:
        gate = f"{_join_labels(clear)} clear."
    else:
        gate = "Every shown run clears the gate."
    pairs = []
    for index, left in enumerate(ordered):
        for right in ordered[index + 1 :]:
            if not _interval_comparable(left, right):
                continue
            verb = "overlap" if _ranges_overlap(left, right) else "do not overlap"
            pairs.append(f"{_run_label(left)} and {_run_label(right)} {verb}")
    gap = (" ".join(pairs) + ".") if pairs else ""
    note = _comparability_note(ordered)
    priced = [f"{_run_label(row)} {_usd(row['known_gross_cost_usd'])}" for row in ordered]
    costs = ", ".join(priced)
    parts = [f"Gate first: {gate}"]
    if gap:
        parts.append(gap)
    if note:
        parts.append(note)
    parts.append(f"Known cost is {costs}.")
    parts.append("Reasoning tokens are listed with that cost.")
    if any(int(row["repeats"]) == 1 for row in ordered):
        parts.append(
            "A 1-repeat Wilson bar is the receipt interval on 48 trials. "
            "It is not redrawn as a 5-repeat rate, and this page does not recompute it."
        )
    return " ".join(parts)


def _over_abstention_phrase(count: int) -> str:
    noun = "over-abstention" if count == 1 else "over-abstentions"
    return f"{count} {noun}"


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
    abstentions = "; ".join(
        f"{_run_label(row)} has {_over_abstention_phrase(row['over_abstention'])}"
        for row in _by_gate(runs)
    )
    parts = [f"{abstentions}."]
    luna_rows = [
        row for row in categories if row["model"] == "gpt-6-luna" and row["category"] == "coverage"
    ]
    if len(luna_rows) == 1:
        luna = luna_rows[0]
        parts.append(f"Luna's coverage cases pass {luna['passed']} of {luna['trials']}.")
    sol_rows = [
        row for row in categories if row["model"] == "gpt-6-sol" and row["category"] == "boundary"
    ]
    if len(sol_rows) == 1:
        sol = sol_rows[0]
        budget = _boundary_case(cases, "gpt-6-sol")
        missed = f"{budget[0]['passed']} of {budget[0]['repeats']}" if budget else "unscored"
        parts.append(
            f"Sol's boundary cases pass {sol['passed']} of {sol['trials']}, "
            f"and boundary_budget passes {missed}."
        )
    return " ".join(parts)


def _case_rows(cases: list[dict], chosen: set[str]) -> list[dict]:
    return [row for row in cases if row["category"] in chosen]


def _boundary_case(cases: list[dict], model: str) -> list[dict]:
    return [row for row in cases if row["model"] == model and row["case_id"] == "boundary_budget"]


def _grid_caption(cases: list[dict], *, repeats: int | None = None) -> str:
    intro = (
        "Color is the pass fraction, passed divided by repeats. "
        "The cell prints passed/repeats, so 5/5 and 1/1 are both a full pass."
    )
    if repeats == 5:
        intro += " These columns are 5 repeats."
    elif repeats == 1:
        intro += " These columns are 1 repeat."
    budgets = [row for row in cases if row["case_id"] == "boundary_budget"]
    if not budgets:
        return intro
    parts = [f"{row['passed']}/{row['repeats']} for {_run_label(row)}" for row in budgets]
    return f"{intro} boundary_budget is {_join_labels(parts)}."


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


_GROK_LOW_INSTRUCTIONS = "622007a3deb785c204e58ba68419af0adbb0c0929d29dd97241038514d17181f"
_GROK_LATER_INSTRUCTIONS = "be294fd35f35327317ab64e58a202ef822347e9ac3451cda01bdc29ae15cc8d3"
_EFFORT_ORDER = {"none": 0, "low": 1, "medium": 2, "high": 3, "xhigh": 4}


def _token_count(value: float) -> str:
    if float(value).is_integer():
        return f"{value:,.0f}"
    return f"{value:,.1f}"


def _grok_one_repeat_arms(
    runs: list[dict],
) -> tuple[dict | None, dict, dict, dict | None] | None:
    """Medium and high at one repeat, plus a matching low when that receipt exists.

    The 5-repeat low run is the headline. It is not an arm of this comparison.
    """
    grok = [
        row
        for row in runs
        if row["model"] == "grok-4.7" and row["effort"] in {"low", "medium", "high"}
    ]
    mediums = [row for row in grok if row["effort"] == "medium"]
    highs = [row for row in grok if row["effort"] == "high"]
    if len(mediums) != 1 or len(highs) != 1:
        return None
    medium, high = mediums[0], highs[0]
    if medium["repeats"] != high["repeats"]:
        return None
    one = medium["repeats"]
    lows = [row for row in grok if row["effort"] == "low" and row["repeats"] == one]
    headlines = [row for row in grok if row["effort"] == "low" and row["repeats"] != one]
    if len(lows) > 1:
        return None
    low = lows[0] if lows else None
    headline_low = headlines[0] if len(headlines) == 1 else None
    return low, medium, high, headline_low


def _matched_run(left: dict, right: dict) -> bool:
    return (
        left["instructions_sha256"] == right["instructions_sha256"]
        and left["frozen_group"] == right["frozen_group"]
        and left["repeats"] == right["repeats"]
    )


def _effort(row: dict) -> str:
    return str(row["effort"])


def _sweep_sign(left: dict, right: dict, effort_cases: list[dict], case_ids: list[str]) -> str:
    """Sign-test the shared case ids. A case missing from the effort table passed."""
    from chess_analytics.analyst.live_stats import exact_sign_test

    bits: dict[str, dict[str, list[bool]]] = {left["effort"]: {}, right["effort"]: {}}
    indexed = {
        (row["effort"], row["case_id"]): row
        for row in effort_cases
        if row["model"] == "grok-4.7" and row["effort"] in bits
    }
    for effort, owner in ((left["effort"], left), (right["effort"], right)):
        for case_id in case_ids:
            row = indexed.get((effort, case_id))
            if row is None:
                bits[effort][case_id] = [True] * int(owner["repeats"])
            else:
                bits[effort][case_id] = [True] * row["passed"] + [False] * (
                    row["repeats"] - row["passed"]
                )
    shared = set(bits[left["effort"]]) & set(bits[right["effort"]])
    result = exact_sign_test(
        {case_id: bits[left["effort"]][case_id] for case_id in shared},
        {case_id: bits[right["effort"]][case_id] for case_id in shared},
    )
    discordant = result["favor_left"] + result["favor_right"]
    noun = "repeat" if left["repeats"] == 1 else "repeats"
    return (
        f"{_effort(left)} vs {_effort(right)} share the instruction hash, "
        f"the frozen inputs, and {left['repeats']} {noun}. Of {len(shared)} cases, "
        f"{discordant} have different pass counts. {_effort(right)} is better on "
        f"{result['favor_right']}, {_effort(left)} on {result['favor_left']}. "
        f"Exact two-sided sign test, p = {result['p_value']:.4f}."
    )


def _grok_snapshot_explanation(headline_low: dict | None, medium: dict, low: dict | None) -> str:
    """The later snapshot is on every 1-repeat arm. low ×5 also differs in repeat count."""
    if headline_low is None:
        return ""
    hashes = {headline_low["instructions_sha256"], medium["instructions_sha256"]}
    if hashes != {_GROK_LOW_INSTRUCTIONS, _GROK_LATER_INSTRUCTIONS}:
        return ""
    text = (
        "instructions_sha256 is the SHA-256 of the literal instructions text in "
        "live_runner._quote. The system prompt is the same except the dataset snapshot "
        "id the model sees: 06bc03a3eabab5bbf3b958ec on low ×5 from e396cf4 and "
        "bea194558220eb669940d8f3 on all three 1-repeat runs from 15aaeb3. "
        "That id changed because eval_report.py and public_extract.py changed "
        "implementation_hash. The receipts do not record dataset_id. "
        "low ×5 is not strictly comparable with the 1-repeat runs."
    )
    if low is not None:
        text += (
            " low ×5 versus low ×1 is not comparable because the instruction hash "
            "and the repeat count both differ."
        )
    return text


def _sweep_caption(
    low: dict | None,
    medium: dict,
    high: dict,
    headline_low: dict | None,
) -> str:
    present = [row for row in (low, medium, high) if row is not None]
    costs = ", ".join(
        f"{_effort(row)} {_usd_trim(row['known_gross_cost_usd'] / row['repeats'])}"
        for row in present
    )
    if headline_low is None:
        lead = "The 5-repeat low run is outside this comparison"
    elif headline_low["instructions_sha256"] == medium["instructions_sha256"]:
        lead = (
            "The 5-repeat low run stays the headline and is outside this comparison "
            "because the repeat count differs"
        )
    else:
        lead = (
            "The 5-repeat low run uses a different instruction hash, stays the headline, "
            "and is outside this comparison"
        )
    return f"{lead} ({costs} per repeat)."


def _sweep_signs(
    low: dict | None,
    medium: dict,
    high: dict,
    effort_cases: list[dict],
    case_ids: list[str],
) -> list[str]:
    matched = _matched_run(medium, high)
    low_matched = low is not None and matched and _matched_run(low, medium)
    signs = []
    if low_matched and low is not None:
        signs.append(_sweep_sign(low, medium, effort_cases, case_ids))
        signs.append(_sweep_sign(low, high, effort_cases, case_ids))
    if matched:
        signs.append(_sweep_sign(medium, high, effort_cases, case_ids))
    else:
        signs.append("Medium versus high is not sign-tested.")
    if low is None:
        signs.append("The 1-repeat low run is not in this test.")
    signs.append("low ×5 is not in this test.")
    return signs


def _sweep_table(effort_cases: list[dict]) -> list[dict]:
    rows = [row for row in effort_cases if row["model"] == "grok-4.7"]
    rows.sort(key=lambda row: (row["case_id"], _EFFORT_ORDER.get(row["effort"], 9)))
    table = []
    for row in rows:
        if row["failure_modes"] == "none":
            result = f"{row['passed']}/{row['repeats']} passed"
        else:
            modes = row["failure_modes"].replace(",", ", ")
            result = f"{row['passed']}/{row['repeats']}, {modes}"
        table.append({"Case": row["case_id"], "Effort": row["effort"], "Result": result})
    return table


def _sweep_card(row: dict) -> tuple[str, str, str]:
    """Detail breaks only at `` · ``, so a token count is not cut mid-value."""
    gate = "Hard fail" if row["hard_fail"] else "Gate clear"
    noun = "repeat" if row["repeats"] == 1 else "repeats"
    per = _usd_3(row["known_gross_cost_usd"] / row["repeats"])
    reasoning = _token_count(row["reasoning_tokens"] / row["repeats"])
    return (
        _run_label(row),
        f"{row['passed']}/{row['trials']}",
        f"{row['repeats']} {noun} · {gate} · {per} per repeat · {reasoning} reasoning tokens",
    )


def _grok_effort_sweep(
    layout, charts, runs: list[dict], effort_cases: list[dict], case_ids: list[str]
) -> None:
    arms = _grok_one_repeat_arms(runs)
    if arms is None:
        return
    low, medium, high, headline_low = arms
    present = [row for row in (low, medium, high) if row is not None]
    st.subheader(_SET_ONE)
    cards = []
    if low is None:
        cards.append(("grok-4.7 · low ×1", "—", "1 repeat · Receipt not in yet."))
    else:
        cards.append(_sweep_card(low))
    cards.extend(_sweep_card(row) for row in (medium, high))
    st.markdown(_html_currency(layout.equal_width_row(cards)), unsafe_allow_html=True)
    if low is None:
        sweep_alt = (
            "Grok reasoning-effort pass rates with Wilson 95 percent intervals. "
            "Medium and high are 1-repeat runs on the same instructions. "
            "The 1-repeat low run is not in this report."
        )
    else:
        sweep_alt = (
            "Grok reasoning-effort pass rates with Wilson 95 percent intervals. "
            "Low, medium, and high are 1-repeat runs on the same instructions."
        )
    _chart(charts, charts.wilson(_sweep_wilson_rows(present)), alt=sweep_alt)
    _caption(f"{_sweep_caption(low, medium, high, headline_low)} {_AXIS_RULE}")
    _caption(_wilson_caption(present))
    _show(
        _cost_token_table(present),
        alt="Known gross cost and reasoning tokens for the grok-4.7 one-repeat effort sweep.",
    )
    note = _grok_snapshot_explanation(headline_low, medium, low)
    signs = _sweep_signs(low, medium, high, effort_cases, case_ids)
    lines = [f"- {item}" for item in signs]
    if note:
        lines.append(note)
    st.markdown("\n".join(lines))
    _show(
        _sweep_table(effort_cases),
        alt="Pass counts for grok-4.7 cases that are not perfect on every reasoning effort.",
    )


_AXIS_RULE = (
    "On this chart, the axis starts 10 percentage points below the lowest pass rate "
    "or interval bound, clamped at 0, and ends at 100%."
)
_SET_FIVE = "Five repeats"
_SET_ONE = "Grok 4.7 effort sweep (one repeat)"


def _headline_runs(runs: list[dict]) -> list[dict]:
    return [row for row in runs if row["headline"]]


def _five_repeat_runs(runs: list[dict]) -> list[dict]:
    """Luna, grok low ×5, and Sol, with a hard fail last."""
    return _by_gate(_headline_runs(runs))


def _one_repeat_runs(runs: list[dict]) -> list[dict]:
    """Grok low, medium, and high at one repeat. Empty when that sweep is absent."""
    arms = _grok_one_repeat_arms(runs)
    if arms is None:
        return []
    low, medium, high, _headline_low = arms
    return [row for row in (low, medium, high) if row is not None]


def _matching_rows(runs: list[dict], rows: list[dict]) -> list[dict]:
    keys = {(row["model"], row["effort"], int(row["repeats"])) for row in runs}
    return [row for row in rows if (row["model"], row["effort"], int(row["repeats"])) in keys]


def _set_heading(title: str) -> None:
    st.markdown(f"##### {title}")


def _case_catalog(cases: list[dict]) -> list[dict]:
    seen: dict[str, dict] = {}
    for row in cases:
        seen.setdefault(str(row["case_id"]), row)
    return sorted(seen.values(), key=lambda row: int(row["case_order"]))


def _one_repeat_cases(run: dict, catalog: list[dict], effort_cases: list[dict]) -> list[dict]:
    """Fill a 1-repeat grid from the miss table. A missing case passed.

    The extract stores only the 1-repeat cases that miss at least once. The
    pass total is checked against the run row, which matches the receipt.
    """
    indexed = {
        row["case_id"]: row
        for row in effort_cases
        if row["model"] == run["model"]
        and row["effort"] == run["effort"]
        and int(row["repeats"]) == int(run["repeats"])
    }
    built: list[dict] = []
    for case in catalog:
        hit = indexed.get(case["case_id"])
        if hit is None:
            passed = int(run["repeats"])
            modes = "none"
        else:
            passed = int(hit["passed"])
            modes = str(hit["failure_modes"])
        built.append(
            {
                "case_id": case["case_id"],
                "case_order": case["case_order"],
                "category": case["category"],
                "effort": run["effort"],
                "model": run["model"],
                "passed": passed,
                "repeats": int(run["repeats"]),
                "severity": case["severity"],
                "failure_modes": modes,
            }
        )
    if sum(int(row["passed"]) for row in built) != int(run["passed"]):
        raise ValueError(f"{_run_label(run)} case grid does not match the run")
    if len(built) * int(run["repeats"]) != int(run["trials"]):
        raise ValueError(f"{_run_label(run)} case grid does not match the run")
    return built


def _categories_from_cases(run: dict, case_rows: list[dict]) -> list[dict]:
    totals: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for row in case_rows:
        totals[str(row["category"])][0] += int(row["passed"])
        totals[str(row["category"])][1] += int(row["repeats"])
    return [
        {
            "category": category,
            "effort": run["effort"],
            "model": run["model"],
            "passed": passed,
            "repeats": int(run["repeats"]),
            "trials": trials,
        }
        for category, (passed, trials) in sorted(totals.items())
    ]


def _stamp_headline_categories(categories: list[dict], runs: list[dict]) -> list[dict]:
    stamped = []
    for row in categories:
        matches = [
            run
            for run in runs
            if run["headline"] and run["model"] == row["model"] and run["effort"] == row["effort"]
        ]
        if len(matches) != 1:
            raise ValueError(f"live eval category is missing a headline run: {row['model']}")
        stamped.append({**row, "repeats": matches[0]["repeats"]})
    return stamped


def _cost_token_table(runs: list[dict]) -> list[dict]:
    return [
        {
            "Run": _run_label(row),
            "Known cost": _usd_3(float(row["known_gross_cost_usd"])),
            "Reasoning tokens": _token_count(float(row["reasoning_tokens"])),
        }
        for row in runs
    ]


def _miss_result(row: dict) -> str:
    """Score on the first line. Each failure mode is its own following line."""
    score = f"{int(row['passed'])}/{int(row['repeats'])}"
    modes = row.get("failure_modes")
    if not isinstance(modes, str) or modes in {"", "none"}:
        return score
    reasons = [part.strip() for part in modes.split(",") if part.strip()]
    return "\n\n".join([score, *reasons])


def _miss_table(case_rows: list[dict]) -> list[dict]:
    table = []
    for row in case_rows:
        if int(row["passed"]) >= int(row["repeats"]):
            continue
        table.append({"Run": _run_label(row), "Case": row["case_id"], "Result": _miss_result(row)})
    return table


def _eval_cards(layout, runs: list[dict]) -> None:
    pairs: list[tuple[tuple[str, str, str], tuple[str, str, str]]] = []
    for row in _by_gate(_headline_runs(runs)):
        gate = "Hard fail" if row["hard_fail"] else "Gate clear"
        pairs.append(
            (
                (
                    _run_label(row),
                    _pct(row["pass_rate"]),
                    f"{row['passed']:,} of {row['trials']:,} · {gate}",
                ),
                (
                    f"{_run_label(row)} cost",
                    _usd(row["known_gross_cost_usd"]),
                    (
                        f"Cap {_usd(row['max_run_usd'])} · "
                        f"{_token_count(float(row['reasoning_tokens']))} reasoning tokens"
                    ),
                ),
            )
        )
    st.markdown(
        _html_currency(layout.model_columns(pairs)),
        unsafe_allow_html=True,
    )


def _case_order(catalog: list[dict], chosen: set[str]) -> list[str]:
    seen: list[str] = []
    ordered = sorted(catalog, key=lambda item: int(item["case_order"]))
    for row in ordered:
        if row["category"] not in chosen:
            continue
        case_id = str(row["case_id"])
        if case_id not in seen:
            seen.append(case_id)
    return seen


def _render_category_chart(
    charts,
    categories: list[dict],
    cases: list[dict],
    runs: list[dict],
    chosen: set[str],
    *,
    alt: str,
) -> None:
    visible = _category_rows(categories, chosen)
    if visible:
        order = [name for name in _CATEGORIES if name in chosen]
        _chart(
            charts,
            charts.category_dumbbell(
                visible,
                category_order=order,
                model_order=[_run_label(row) for row in runs],
                colors={
                    _run_label(row): charts.pinned_run_color(_run_label(row, suffix=True))
                    for row in runs
                },
            ),
            alt=alt,
        )
        _caption(_AXIS_RULE)
    _caption(_category_caption(categories, cases, runs, chosen))


def _render_case_grid(
    charts,
    cases: list[dict],
    runs: list[dict],
    catalog: list[dict],
    chosen: set[str],
    *,
    alt: str,
    repeats: int,
) -> None:
    visible = _case_rows(cases, chosen)
    seen = _case_order(catalog, chosen)
    if visible and seen:
        by_key = {
            (row["model"], row["effort"], int(row["repeats"]), row["case_id"]): row
            for row in visible
        }
        plotted = []
        for run in runs:
            for case_id in seen:
                row = by_key.get((run["model"], run["effort"], int(run["repeats"]), case_id))
                if row is None:
                    continue
                plotted.append({**row, "model": _axis_run_label(run), "run": _run_label(run)})
        if plotted:
            _chart(
                charts,
                charts.case_grid(
                    plotted,
                    case_order=seen,
                    model_order=[_axis_run_label(row) for row in runs],
                ),
                alt=alt,
                content_width=True,
            )
    ordered = [
        row
        for run in runs
        for row in visible
        if row["model"] == run["model"]
        and row["effort"] == run["effort"]
        and int(row["repeats"]) == int(run["repeats"])
    ]
    _caption(_grid_caption(ordered, repeats=repeats))


def _render_misses(cases: list[dict], *, alt: str) -> None:
    misses = _miss_table(cases)
    if misses:
        _show(misses, alt=alt, height=360)


def _eval_tab(layout, charts, extract: dict, rows) -> None:
    runs = rows(extract, "live_eval_run")
    cases = rows(extract, "live_eval_case")
    categories = rows(extract, "live_eval_category")
    effort_cases = rows(extract, "live_eval_effort_case")
    five = _five_repeat_runs(runs)
    one = _one_repeat_runs(runs)
    catalog = _case_catalog(cases)
    one_cases: list[dict] = []
    one_categories: list[dict] = []
    for run in one:
        built = _one_repeat_cases(run, catalog, effort_cases)
        one_cases.extend(built)
        one_categories.extend(_categories_from_cases(run, built))
    headline_categories = _stamp_headline_categories(categories, runs)
    five_categories = _matching_rows(five, headline_categories)
    five_cases = [{**row, "failure_modes": "none"} for row in _matching_rows(five, cases)]
    _eval_cards(layout, runs)
    _caption(
        "Published live-eval report: "
        "[live-eval.html](https://jfk-ssa.github.io/chess-analytics-lab/live-eval.html)."
    )
    st.subheader("Pass rate")
    _set_heading(_SET_FIVE)
    _chart(
        charts,
        charts.wilson(_wilson_rows(five)),
        alt=(
            "Pass rate for the five-repeat runs with Wilson 95 percent intervals. "
            "gpt-6-luna, grok-4.7 low times five, and gpt-6-sol."
        ),
    )
    _caption(_wilson_caption(five))
    _caption(
        "Query origin: committed_report. The bar is the receipt Wilson 95 percent interval. "
        f"{_AXIS_RULE}"
    )
    _show(
        _cost_token_table(five),
        alt="Known gross cost and reasoning tokens for the five-repeat runs.",
    )
    chosen: set[str] = {
        str(name)
        for name in st.multiselect(
            "Category",
            list(_CATEGORIES),
            default=list(_CATEGORIES),
            key="eval_category",
        )
    }
    _set_heading(_SET_FIVE)
    _render_category_chart(
        charts,
        five_categories,
        five_cases,
        five,
        chosen,
        alt=("Dumbbell of pass rate by category for the five-repeat runs. Each point is one run."),
    )
    if one:
        _set_heading(_SET_ONE)
        _render_category_chart(
            charts,
            one_categories,
            one_cases,
            one,
            chosen,
            alt=(
                "Dumbbell of pass rate by category for the grok-4.7 one-repeat effort sweep. "
                "Each point is one run."
            ),
        )
    _set_heading(_SET_FIVE)
    _render_case_grid(
        charts,
        five_cases,
        five,
        catalog,
        chosen,
        alt=(
            "Grid of cases for the five-repeat runs, colored by pass fraction. "
            "Each cell prints passed/repeats. Column labels are horizontal."
        ),
        repeats=5,
    )
    _render_misses(
        five_cases,
        alt="Cases that missed at least one repeat, for the five-repeat runs.",
    )
    if one:
        _set_heading(_SET_ONE)
        _render_case_grid(
            charts,
            one_cases,
            one,
            catalog,
            chosen,
            alt=(
                "Grid of cases for the grok-4.7 one-repeat effort sweep, "
                "colored by pass fraction. Each cell prints passed/repeats. "
                "Column labels are horizontal."
            ),
            repeats=1,
        )
        _render_misses(
            one_cases,
            alt=(
                "Cases that missed at least one repeat, for the grok-4.7 one-repeat effort sweep."
            ),
        )
    _grok_effort_sweep(layout, charts, runs, effort_cases, [row["case_id"] for row in catalog])


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
        try:
            body = rows(extract, name)
        except ValueError as exc:
            if "unknown public extract table" not in str(exc):
                raise
            continue
        sources = sorted({row["source_report"] for row in body if row.get("source_report")})
        if sources:
            source = ", ".join(sources)
        elif name in {"live_eval_case", "live_eval_category", "live_eval_effort_case"}:
            run_rows = rows(extract, "live_eval_run")
            run_sources = sorted(
                {row["source_report"] for row in run_rows if row.get("source_report")}
            )
            source = ", ".join(run_sources) if run_sources else "live_eval_run"
        else:
            source = "metric_receipt"
        table.append({"Table": name, "Rows": f"{len(body):,}", "Source": source})
    return table


def _render(
    layout,
    charts,
    bi,
    extract: dict,
    path: Path,
    rows,
    connection,
    cube_bounds,
    extract_error: str | None = None,
) -> None:
    charts.install_theme()
    stylesheet = Path(__file__).resolve().parent / "static" / "dashboard.css"
    if stylesheet.is_file():
        st.html("<style>" + stylesheet.read_text() + "</style>")
    st.title("Chess Analytics Lab")
    bi.render(layout, charts, connection, cube_bounds)
    st.subheader("Live eval")
    if extract_error is not None:
        st.error(extract_error)
        return
    _eval_tab(layout, charts, extract, rows)
    with st.expander("Provenance"):
        _about(extract, path, rows)


def _duckdb_error(exc: BaseException) -> bool:
    """True for ``duckdb.Error``, including the ``_duckdb`` implementation class."""
    module = type(exc).__module__.split(".")[0]
    if module in {"duckdb", "_duckdb"}:
        return True
    try:
        import duckdb
    except ModuleNotFoundError:
        return False
    return isinstance(exc, duckdb.Error)


def _show_build_label() -> None:
    """Footer caption from the package just reloaded for this rerun.

    Attribute access on the module. A ``from chess_analytics.build_info
    import BUILD_LABEL`` bound before ``importlib.reload`` would keep the
    previous string, so a code-only push would not show up. ADR 0107.
    """
    import chess_analytics.build_info as build_info

    _caption(f"build: {build_info.BUILD_LABEL}")


def _fail(message: str) -> NoReturn:
    st.title("Chess Analytics Lab")
    st.error(message)
    st.stop()
    raise RuntimeError(message)


def _import_repository_package():
    repo_import = _load_local("repo_import")
    try:
        return repo_import.import_repository_package()
    except repo_import.RepositoryImportError as exc:
        _fail(str(exc))


def _cube_name_message(exc: BaseException) -> str:
    module = sys.modules.get("chess_analytics.dashboard_cube")
    location = getattr(module, "__file__", None) or "the cached module"
    return (
        "hosted/bi.py imports names from chess_analytics.dashboard_cube, "
        f"and the copy loaded from {location} does not provide them. "
        "The page reloads src/chess_analytics before that import. "
        f"The checkout itself is inconsistent: {exc}"
    )


def main() -> None:
    extract_error: str | None = None
    layout = None
    charts = None
    extract = None
    path = None
    table_rows = None
    bounds = None
    connect = None
    cube_path = None
    try:
        layout = _load_local("layout")
        charts = _load_local("charts")
        (
            extract_path,
            load_extract,
            table_rows,
            bounds,
            connect,
            cube_path,
        ) = _import_repository_package()
        path = extract_path()
        extract = load_extract(path)
        _validate(extract, table_rows)
    except json.JSONDecodeError as exc:
        extract_error = f"Public extract is not valid JSON: {exc}"
    except ValueError as exc:
        extract_error = f"Public extract failed validation: {exc}"
    except OSError as exc:
        extract_error = f"Public extract unavailable: {exc}"
    except ModuleNotFoundError as exc:
        extract_error = f"Public extract reader could not be imported: {exc}"
    if (
        layout is None
        or charts is None
        or bounds is None
        or connect is None
        or cube_path is None
        or table_rows is None
    ):
        _fail(extract_error or "Dashboard view could not be imported")
    try:
        source = cube_path()
        connection = connect(source)
        cube_bounds = bounds(connection)
        bi = _load_local("bi")
    except FileNotFoundError as exc:
        if extract_error is not None:
            _fail(extract_error)
        _fail(f"Dashboard cube unavailable: {exc}")
    except ModuleNotFoundError as exc:
        _fail(f"Dashboard cube could not be imported: {exc}")
    except ImportError as exc:
        _fail(_cube_name_message(exc))
    except Exception as exc:
        if _duckdb_error(exc):
            _fail(f"Dashboard cube unavailable: {exc}")
        raise
    try:
        if extract_error is not None or extract is None or path is None or table_rows is None:
            _render(
                layout,
                charts,
                bi,
                {},
                Path(),
                table_rows if table_rows is not None else (lambda *_args: []),
                connection,
                cube_bounds,
                extract_error or "Public extract unavailable",
            )
        else:
            _render(layout, charts, bi, extract, path, table_rows, connection, cube_bounds)
        _show_build_label()
    except ImportError as exc:
        _fail(_cube_name_message(exc))


st.set_page_config(page_title="Chess Analytics Lab", layout="wide")
main()
