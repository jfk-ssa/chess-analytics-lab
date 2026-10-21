"""Read-only hosted dashboard for the committed public aggregate extract.

Run from the repository root:

    streamlit run hosted/dashboard.py

Streamlit Community Cloud installs ``hosted/requirements.txt`` only. That file
pins Streamlit plus the locked pandas and protobuf versions, and does not
install this project. The project package depends on DuckDB; this page never
opens a warehouse. ``_loader`` adds ``src/`` to the import path long enough to
import ``chess_analytics.public_extract``, which reads the JSON with the
standard library.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import streamlit as st  # pyright: ignore[reportMissingImports]

_BUCKETS = ("under_10", "10_to_29", "30_to_59", "60_plus")
_FOCAL = ("French Defense", "Sicilian Defense")
_COHORT = ("color", "rating_min", "rating_max_exclusive", "base_seconds", "increment_seconds")
_FIGURE_TABLES = ("opening_family_share", "opening_score_cell", "clock_bucket")


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


def _show(rows: list[dict], *, alt: str, height: int | None = None) -> None:
    if not rows or len(rows[0]) > 3:
        raise ValueError("dashboard table must have 1 to 3 columns")
    if not alt.strip():
        raise ValueError("dashboard table needs alt text")
    st.table(
        rows,
        hide_index=True,
        height="content" if height is None else height,
        alt=alt,
    )


def _pct(value: float) -> str:
    return f"{value:.1%}"


def _share(value: float, numerator: int) -> str:
    shown = f"{value:.1%}"
    if numerator > 0 and shown == "0.0%":
        return "<0.1%"
    return shown


def _ratio(numerator: int, denominator: int) -> str:
    return f"{numerator:,} / {denominator:,}"


def _blank(value: object) -> str:
    return "–" if value is None else str(value)


def _one(rows: list[dict], column: str, value: object) -> dict:
    matches = [row for row in rows if row[column] == value]
    if len(matches) != 1:
        raise ValueError(f"public extract {column} is missing: {value}")
    return matches[0]


def _origin(receipts: list[dict]) -> str:
    origins = {row["query_origin"] for row in receipts}
    if len(origins) != 1:
        raise ValueError("public extract figure has more than one query origin")
    return next(iter(origins))


def _close(stored: float | None, numerator: int, denominator: int) -> None:
    if stored is None or denominator == 0:
        raise ValueError("public extract rate is missing")
    if abs(stored - (numerator / denominator)) > 1e-9:
        raise ValueError("public extract rate does not match its numerator and denominator")


def _require_count(actual: object, expected: object, label: str) -> None:
    if actual != expected:
        raise ValueError(f"public extract {label} does not match")


def _build_rows(extract: dict, mart_id: object, digest: str) -> list[dict]:
    build = extract.get("build")
    if not isinstance(build, dict) or not isinstance(mart_id, str):
        raise ValueError("public extract build record is missing")
    fields = (
        ("Mart id", mart_id),
        ("Source snapshot", build.get("source_snapshot_id")),
        ("Model sha256", build.get("model_sha256")),
        ("Lock sha256", build.get("lock_sha256")),
        ("Semantic manifest sha256", build.get("semantic_manifest_sha256")),
        ("Extract sha256", digest),
    )
    if any(not isinstance(value, str) or not value for _, value in fields):
        raise ValueError("public extract build record is incomplete")
    return [{"Field": name, "Value": value} for name, value in fields]


def _figure_publication(extract: dict, *groups: list[dict]) -> dict:
    build = extract.get("build")
    snapshot = build.get("source_snapshot_id") if isinstance(build, dict) else None
    per_group = [{row["analytical_id"] for row in group} for group in groups]
    found = set().union(*per_group) if per_group else set()
    if (
        len(groups) != len(_FIGURE_TABLES)
        or any(len(ids) != 1 for ids in per_group)
        or len(found) != 1
        or not isinstance(snapshot, str)
        or not snapshot
    ):
        raise ValueError("public extract analytical ids differ")
    analytical_id = next(iter(found))
    names = ", ".join(_FIGURE_TABLES)
    if analytical_id == snapshot:
        relation = "It matches build.source_snapshot_id."
    else:
        relation = (
            "It is not build.source_snapshot_id. "
            "Those rows are a different publication from the build snapshot."
        )
    return {
        "rows": [{"Field": "analytical_id", "Value": analytical_id}],
        "caption": f"This analytical_id is on the committed rows of {names}. {relation}",
    }


def _families(receipts: list[dict], families: list[dict]) -> dict:
    usage = _one(receipts, "receipt_id", "opening_usage")
    reports = {row["source_report"] for row in families}
    if len(reports) != 1 or any(row["denominator"] != usage["denominator"] for row in families):
        raise ValueError("opening family rows do not share the opening_usage denominator")
    for row in families:
        _close(row["value"], row["numerator"], row["denominator"])
    focal = [_one(families, "family", name) for name in _FOCAL]

    def _usage_row(row: dict) -> dict:
        return {
            "Family": row["family"],
            "Games": f"{row['numerator']:,}",
            "Share": _share(row["value"], row["numerator"]),
        }

    return {
        "origin": _origin([usage]),
        "source": next(iter(reports)),
        "denominator": f"{usage['denominator']:,}",
        "chart": [{"Opening": row["family"], "Games": row["numerator"]} for row in focal],
        "focal": [_usage_row(row) for row in focal],
        "catalog": [_usage_row(row) for row in families],
    }


def _score_cells(receipts: list[dict], cells: list[dict]) -> tuple[dict, dict]:
    if {row["family"] for row in cells} != set(_FOCAL):
        raise ValueError("opening score cells are not French Defense and Sicilian Defense")
    cohort = tuple(cells[0][key] for key in _COHORT)
    if any(tuple(row[key] for key in _COHORT) != cohort for row in cells):
        raise ValueError("opening score cells do not share one cohort")
    player_receipts = []
    adjusted_receipts = []
    player_rows = []
    adjusted_rows = []
    details = []
    for name in _FOCAL:
        cell = _one(cells, "family", name)
        player = _one(receipts, "receipt_id", f"opening_player_score:{name}")
        adjusted = _one(receipts, "receipt_id", f"opening_adjusted_score:{name}")
        bootstrap = _one(receipts, "receipt_id", f"opening_adjusted_score_bootstrap:{name}")
        half = cell["wins"] + (cell["draws"] / 2)
        _require_count(half, player["numerator"], "opening player score numerator")
        _require_count(
            cell["eligible_player_games"], player["denominator"], "player-game denominator"
        )
        _close(cell["score_rate"], player["numerator"], player["denominator"])
        player_receipts.append(player)
        adjusted_receipts.extend((adjusted, bootstrap))
        score = _pct(cell["score_rate"])
        fraction = _ratio(player["numerator"], player["denominator"])
        record = f"{cell['wins']:,} wins, {cell['draws']:,} draws, {cell['losses']:,} losses"
        player_rows.append(
            {"Family": name, "Half-point score": f"{score} ({fraction})", "Record": record}
        )
        adjusted_rows.append(
            {
                "Family": name,
                "Adjusted score": _pct(cell["adjusted_score_rate"]),
                "Bootstrap interval": (
                    f"{_pct(cell['adjusted_interval_low'])}–{_pct(cell['adjusted_interval_high'])}"
                ),
            }
        )
        details.append(
            f"{name}: {cell['bootstrap_valid_repetitions']} bootstrap repetitions, "
            f"{cell['cluster_count']} clusters, low_support {str(cell['low_support']).lower()}"
        )
    color, rating_min, rating_max, base, increment = cohort
    return (
        {
            "origin": _origin(player_receipts),
            "cohort": (
                f"Both cells are {color}, rating_min {rating_min}, "
                f"rating_max_exclusive {rating_max}, time control {base}+{increment}."
            ),
            "rows": player_rows,
        },
        {
            "origin": _origin(adjusted_receipts),
            "detail": " ".join(details) + ".",
            "rows": adjusted_rows,
        },
    )


def _clock(receipts: list[dict], buckets: list[dict], strata: int) -> dict:
    if len(buckets) != len(_BUCKETS):
        raise ValueError("public extract clock buckets are not the four expected rows")
    rows = []
    used = []
    for name in _BUCKETS:
        row = _one(buckets, "bucket", name)
        receipt = _one(receipts, "receipt_id", f"clock_pressure_error_proxy:{name}")
        _require_count(row["proxy_errors"], receipt["numerator"], "clock proxy numerator")
        _require_count(row["evaluable_moves"], receipt["denominator"], "clock proxy denominator")
        _close(row["error_proxy_rate"], row["proxy_errors"], row["evaluable_moves"])
        _close(row["evaluation_coverage"], row["evaluable_moves"], row["eligible_moves"])
        used.append(receipt)
        rows.append(
            {
                "Bucket": name,
                "Error proxy": (
                    f"{_pct(row['error_proxy_rate'])} "
                    f"({_ratio(row['proxy_errors'], row['evaluable_moves'])})"
                ),
                "Evaluation coverage": (
                    f"{_pct(row['evaluation_coverage'])} "
                    f"({_ratio(row['evaluable_moves'], row['eligible_moves'])})"
                ),
            }
        )
    return {"origin": _origin(used), "rows": rows, "strata": strata}


def _lineage(receipts: list[dict], stages: list[dict], draw_denominator: object) -> dict:
    training = _one(receipts, "receipt_id", "opening_corpus_training_games")
    accepted = _one(receipts, "receipt_id", "m3_august_prefix_accepted")
    known = _one(receipts, "receipt_id", "known_opening_games")
    eligible = _one(stages, "stage_id", "m3_august_prefix:eligible_games")
    _require_count(
        _one(stages, "stage_id", "opening_corpus:training_games")["count"],
        training["numerator"],
        "opening corpus training games",
    )
    _require_count(
        _one(stages, "stage_id", "m3_august_prefix:accepted")["count"],
        accepted["numerator"],
        "August prefix accepted games",
    )
    _require_count(eligible["count"], draw_denominator, "draw-rate denominator")
    _require_count(
        _one(stages, "stage_id", "m3_august_prefix:known_opening_games")["count"],
        known["numerator"],
        "known opening games",
    )
    ordered = sorted(stages, key=lambda row: (row["lineage"], row["stage_order"]))
    corpus = [row for row in ordered if row["lineage"] == "opening_corpus"]
    august = [row for row in ordered if row["lineage"] == "m3_august_prefix"]
    notes: list[str] = []
    for row in corpus:
        if row["note"] not in notes:
            notes.append(row["note"])
    return {
        "origin": _origin([training, accepted, known]),
        "corpus_source": _one_source(corpus),
        "august_source": _one_source(august),
        "notes": notes,
        "corpus": [
            {
                "Period": _blank(row["period"]),
                "Cohort": _blank(row["cohort"]),
                "Games": f"{row['count']:,}",
            }
            for row in corpus
        ],
        "august": [
            {"Population": row["population"], "Games": f"{row['count']:,}", "Note": row["note"]}
            for row in august
        ],
    }


def _one_source(rows: list[dict]) -> str:
    reports = sorted({row["source_report"] for row in rows})
    if not reports:
        raise ValueError("public extract lineage is empty")
    return ", ".join(reports)


def _view(extract: dict, path: Path, table_rows) -> dict:
    receipts = table_rows(extract, "metric_receipt")
    families = table_rows(extract, "opening_family_share")
    cells = table_rows(extract, "opening_score_cell")
    buckets = table_rows(extract, "clock_bucket")
    draw = _one(receipts, "receipt_id", "game_draw_rate")
    if not draw["denominator"]:
        raise ValueError("game draw rate denominator is empty")
    player, adjusted = _score_cells(receipts, cells)
    return {
        "provenance": _build_rows(
            extract,
            draw["mart_id"],
            hashlib.sha256(path.read_bytes()).hexdigest(),
        ),
        "figures": _figure_publication(extract, families, cells, buckets),
        "draw": {
            "origin": _origin([draw]),
            "ratio": _ratio(draw["numerator"], draw["denominator"]),
            "rate": _pct(draw["numerator"] / draw["denominator"]),
        },
        "usage": _families(receipts, families),
        "player": player,
        "adjusted": adjusted,
        "clock": _clock(receipts, buckets, len(table_rows(extract, "clock_stratum"))),
        "lineage": _lineage(receipts, table_rows(extract, "lineage_stage"), draw["denominator"]),
    }


def _render(view: dict) -> None:
    st.title("Chess Analytics Lab")
    st.caption(
        "Read-only figures from data/public/dashboard_extract.json. "
        "No warehouse, no uploads, and no external calls."
    )
    st.header("Build provenance")
    st.caption(
        "Mart id is the game_draw_rate receipt. Source snapshot, model sha256, "
        "lock sha256, and semantic manifest sha256 are the extract build record. "
        "Extract sha256 is the hash of that file's bytes."
    )
    _show(
        view["provenance"],
        alt="Mart id, source snapshot, three build hashes, and extract sha256.",
    )
    figures = view["figures"]
    st.header("Figure analytical id")
    st.caption(figures["caption"])
    _show(
        figures["rows"],
        alt="analytical_id on opening_family_share, opening_score_cell, and clock_bucket.",
    )

    draw = view["draw"]
    st.header("Game draw rate")
    st.metric("Game draw rate", draw["ratio"])
    st.caption(
        f"Query origin: {draw['origin']}. Rate {draw['rate']}. "
        "The fraction is the game_draw_rate receipt. "
        "Its denominator matches m3_august_prefix:eligible_games."
    )

    usage = view["usage"]
    st.header("Opening usage")
    st.caption(
        f"Query origin: {usage['origin']}. Source report: {usage['source']}. "
        f"Each share uses the opening_usage denominator, {usage['denominator']}."
    )
    st.bar_chart(
        usage["chart"],
        x="Opening",
        y="Games",
        x_label="Opening",
        y_label="Games",
        horizontal=True,
        sort=False,
        height=220,
        alt="Game counts for French Defense and Sicilian Defense.",
    )
    _show(view["usage"]["focal"], alt="French Defense and Sicilian Defense games and shares.")
    st.caption(f"All {len(usage['catalog']):,} families in opening_family_share, in extract order.")
    _show(usage["catalog"], alt="Opening family game counts and shares.", height=420)

    player = view["player"]
    st.header("Opening player score")
    st.caption(
        f"Query origin: {player['origin']}. {player['cohort']} "
        "The half-point score is the receipt numerator: wins plus half the draws."
    )
    _show(player["rows"], alt="Half-point scores for French Defense and Sicilian Defense.")

    adjusted = view["adjusted"]
    st.header("Adjusted score and bootstrap")
    st.caption(
        f"Query origin: {adjusted['origin']}. "
        "The interval is adjusted_interval_low to adjusted_interval_high. "
        f"{adjusted['detail']}"
    )
    _show(adjusted["rows"], alt="Adjusted scores and bootstrap intervals.")

    clock = view["clock"]
    st.header("Clock buckets")
    st.caption(
        f"Query origin: {clock['origin']}. "
        "Error proxy is proxy_errors / evaluable_moves. "
        "Evaluation coverage is evaluable_moves / eligible_moves. "
        f"clock_stratum has {clock['strata']:,} rows and is not expanded."
    )
    _show(clock["rows"], alt="Clock-bucket error proxy and evaluation coverage.")

    lineage = view["lineage"]
    st.header("Lineage")
    st.caption(
        f"Query origin: {lineage['origin']}. "
        "The extract stores these lineages separately. This page does not add them."
    )
    st.subheader("Opening corpus")
    st.caption(f"Source report: {lineage['corpus_source']}. A dash is an empty period or cohort.")
    _show(lineage["corpus"], alt="Opening corpus game counts.")
    for note in lineage["notes"]:
        st.caption(note)
    st.subheader("August prefix")
    st.caption(f"Source reports: {lineage['august_source']}.")
    _show(lineage["august"], alt="August prefix game counts.")


def _fail(message: str) -> None:
    st.title("Chess Analytics Lab")
    st.error(message)
    st.stop()


def main() -> None:
    try:
        extract_path, load_extract, table_rows = _loader()
        path = extract_path()
        _render(_view(load_extract(path), path, table_rows))
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
