"""Build the committed public aggregate extract.

Rows come from committed reports. When the August analytical warehouse is
present, governed metrics can be relabeled metricflow and clock buckets
can be relabeled reviewed_sql, but only when the live counts match those
reports. Clock pressure, adjusted score, and the bootstrap are never
labeled metricflow. Missing local data is printed and does not invent rows.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from chess_analytics.common import write_json
from chess_analytics.public_extract import (
    EXTRACT_VERSION,
    NEVER_METRICFLOW,
    QUERY_ORIGINS,
    SIZE_BUDGET_BYTES,
    TABLES,
    extract_path,
    identifier_issues,
)

PROJECT = Path(__file__).resolve().parents[1]
BUCKET_ORDER = ("under_10", "10_to_29", "30_to_59", "60_plus")
GOVERNED_METRICS = ("game_draw_rate", "opening_usage", "opening_player_score")
NEVER_METRICFLOW_LINE = (
    "skipped: metricflow label for clock_pressure_error_proxy, "
    "opening_adjusted_score, and opening_adjusted_score_bootstrap (no governed source)"
)
BUILT_LINE = (
    "built: lineage_stage, opening_family_share, opening_score_cell, "
    "opening_color_score, clock_bucket, clock_stratum, clock_pressure_band, "
    "transposition_view, transposition_compression, transposition_coverage, "
    "transposition_scope, transposition_limitation, live_eval_run, "
    "live_eval_category, live_eval_case, metric_receipt from committed reports"
)
LOW_SUPPORT_PLAYER_GAMES = 100
_BAND_ORDER = ("under_1200", "1200_1599", "1600_1999", "2000_plus")
_COHORT_KEY = re.compile(
    r"^(?P<family>[^|]+)\|(?P<color>white|black)\|rating_(?P<low>\d+)_(?P<high>\d+)\|(?P<base>\d+)\+(?P<inc>\d+)$"
)
_RUN_ID = re.compile(r"^live-eval-receipt-(?:(\d+)|.+-r\d+-(\d+))\.json$")
MAC_NONE = "mac rebuild needed: none; every table was filled from committed reports"
MAC_OPTIONAL = (
    "mac rebuild optional: metric_receipt query_origin for game_draw_rate, "
    "opening_usage, and opening_player_score when the August warehouse and "
    "matching mart are present"
)
MAC_REBUILD = (
    "UV_PROJECT_ENVIRONMENT=$HOME/.venvs/chess-analytics-lab "
    "uv run --directory $HOME/Developer/chess-analytics-lab "
    "--locked --no-editable --extra dbt "
    "python scripts/build_public_extract.py"
)


def build_extract(project: Path) -> tuple[dict, list[str]]:
    sources = load_sources(project)
    check_sources(sources)
    live_runs, live_categories, live_cases = live_eval_tables(project)
    tables = {
        "lineage_stage": lineage_rows(sources),
        "opening_family_share": family_rows(sources),
        "opening_score_cell": score_rows(sources),
        "opening_color_score": color_score_rows(sources),
        "clock_bucket": clock_bucket_rows(sources),
        "clock_stratum": clock_stratum_rows(sources),
        "clock_pressure_band": clock_band_rows(sources),
        "transposition_view": transposition_view_rows(sources),
        "transposition_compression": transposition_compression_rows(sources),
        "transposition_coverage": transposition_coverage_rows(sources),
        "transposition_scope": transposition_scope_rows(sources),
        "transposition_limitation": transposition_limitation_rows(sources),
        "live_eval_run": live_runs,
        "live_eval_category": live_categories,
        "live_eval_case": live_cases,
    }
    tables["metric_receipt"] = receipt_rows(sources, tables)
    extract = {"extract_version": EXTRACT_VERSION, "tables": tables}
    check_extract(extract, sources)
    probe = collect_live_probe(project, extract)
    logs = upgrade_receipts(extract, probe)
    issues = identifier_issues(extract)
    if issues:
        raise ValueError("public extract failed the identifier check")
    encoded = json.dumps(extract, indent=2, sort_keys=True) + "\n"
    if len(encoded.encode()) > SIZE_BUDGET_BYTES:
        raise ValueError("public extract exceeds the size budget")
    return extract, logs


def load_sources(project: Path) -> dict:
    reports = project / "reports"
    return {
        "corpus": _read(reports / "opening-corpus.json"),
        "reference": _read(reports / "M3-independent-reference.json"),
        "source": _read(reports / "M3-source-manifest.json"),
        "analytical": _read(reports / "M3-analytical-manifest.json"),
        "figures": _read(reports / "M4-figures.json"),
        "checkpoint": _read(reports / "opening-positions-checkpoint.json"),
        "positions": _read(reports / "opening-positions-dashboard.json"),
    }


def check_sources(sources: dict) -> None:
    corpus = sources["corpus"]
    reference = sources["reference"]
    source = sources["source"]
    analytical = sources["analytical"]
    figures = sources["figures"]
    counts = corpus["counts"]
    training = [row["games"] for row in corpus["training_sources"]]
    if sum(training) != counts["training_games"]:
        raise ValueError("training sources do not sum to training games")
    if sum(corpus["rating_bands"].values()) != counts["training_games"]:
        raise ValueError("rating bands do not sum to training games")
    elite = [row for row in corpus["training_sources"] if row["cohort"] == "elite_reference"]
    if len(elite) != 1 or elite[0]["games"] != counts["elite_training_games"]:
        raise ValueError("elite training count differs from the corpus report")
    if source["counts"]["accepted"] != reference["accepted_games"]:
        raise ValueError("accepted counts differ")
    if figures["coverage"]["source_counts"]["accepted"] != reference["accepted_games"]:
        raise ValueError("figure accepted count differs")
    if source["reasons"].get("not_rated") != source["counts"]["excluded"]:
        raise ValueError("excluded games are not all unrated")
    if source["counts"]["seen"] != source["counts"]["accepted"] + source["counts"]["excluded"]:
        raise ValueError("seen games do not partition into accepted and excluded")
    coverage = analytical["summary"]["opening_coverage"]
    if coverage["known_opening_games"] != reference["known_opening_games"]:
        raise ValueError("known opening counts differ")
    if (
        figures["coverage"]["opening_coverage"]["known_opening_games"]
        != coverage["known_opening_games"]
    ):
        raise ValueError("figure known openings differ")
    if sum(reference["opening_families"].values()) != reference["known_opening_games"]:
        raise ValueError("opening families do not sum to known openings")
    if coverage["eligible_games"] != reference["eligible_games"]:
        raise ValueError("eligible counts differ")
    metric = source["metric"]
    if metric["metric_id"] != "game_draw_rate":
        raise ValueError("source manifest metric is not the draw rate")
    if metric["numerator"] != reference["drawn_eligible_games"]:
        raise ValueError("drawn games differ")
    if metric["denominator"] != reference["eligible_games"]:
        raise ValueError("draw-rate denominator differs")
    accepted = source["counts"]["accepted"]
    partitioned = metric["marked_bots"] + metric["unknown_results"] + metric["denominator"]
    if accepted != partitioned:
        raise ValueError("accepted games do not partition inside the August prefix")
    if figures["analytical_id"] != analytical["analytical_id"]:
        raise ValueError("analytical ids differ")
    _require_same_clocks(figures, analytical, reference)
    _require_same_families(analytical, reference)
    _require_same_scores(figures, reference)
    _require_positions_pin(sources)


def lineage_rows(sources: dict) -> list[dict]:
    corpus = sources["corpus"]
    source = sources["source"]
    analytical = sources["analytical"]
    metric = source["metric"]
    rows = [
        _stage(
            lineage="opening_corpus",
            stage_order=0,
            population="training_games",
            count=corpus["counts"]["training_games"],
            period=None,
            cohort=None,
            rolls_up_to=None,
            source_report="opening-corpus.json",
            note="Homepage pipeline count. Separate lineage from the August prefix dashboard.",
        )
    ]
    for index, item in enumerate(corpus["training_sources"], start=1):
        rows.append(
            _stage(
                lineage="opening_corpus",
                stage_order=index,
                population="training_source_games",
                count=item["games"],
                period=item["period"],
                cohort=item["cohort"],
                rolls_up_to="opening_corpus:training_games",
                source_report="opening-corpus.json",
                note=_corpus_note(item["cohort"]),
            )
        )
    coverage = analytical["summary"]["opening_coverage"]
    prefix = [
        ("seen", source["counts"]["seen"], "Games read from the ordered August prefix."),
        (
            "excluded",
            source["counts"]["excluded"],
            "Games dropped before acceptance because they were not rated.",
        ),
        (
            "accepted",
            source["counts"]["accepted"],
            "Accepted games in the August prefix. Not the opening-corpus training total.",
        ),
        (
            "marked_bots",
            metric["marked_bots"],
            "Source-marked bots inside the accepted August prefix.",
        ),
        (
            "unknown_results",
            metric["unknown_results"],
            "Accepted games with an unknown result, excluding source-marked bots.",
        ),
        (
            "eligible_games",
            coverage["eligible_games"],
            "Completed eligible games in the August prefix.",
        ),
        (
            "known_opening_games",
            coverage["known_opening_games"],
            "Eligible games with a source opening family. Same count as eligible in this prefix.",
        ),
    ]
    for index, (population, count, note) in enumerate(prefix):
        rows.append(
            _stage(
                lineage="m3_august_prefix",
                stage_order=index,
                population=population,
                count=count,
                period="2026-08",
                cohort=None,
                rolls_up_to=None,
                source_report=_prefix_report(population),
                note=note,
            )
        )
    return rows


def family_rows(sources: dict) -> list[dict]:
    reference = sources["reference"]
    analytical_id = sources["analytical"]["analytical_id"]
    denominator = reference["known_opening_games"]
    ranked = sorted(reference["opening_families"].items(), key=lambda item: (-item[1], item[0]))
    return [
        {
            "analytical_id": analytical_id,
            "denominator": denominator,
            "family": family,
            "numerator": numerator,
            "source_report": "M3-independent-reference.json",
            "value": numerator / denominator,
        }
        for family, numerator in ranked
    ]


def score_rows(sources: dict) -> list[dict]:
    opening = sources["figures"]["opening"]
    weights = opening["common_rating_difference_weights"]
    filters = opening["filters"]
    rows = []
    for family in sorted(opening["families"]):
        result = opening["families"][family]
        raw = result["raw"]
        interval = result["adjusted_95pct_cluster_bootstrap_interval"]
        rows.append(
            {
                "adjusted_interval_high": interval[1],
                "adjusted_interval_low": interval[0],
                "adjusted_score_rate": result["adjusted_score_rate"],
                "analytical_id": opening["analytical_id"],
                "base_seconds": filters["base_seconds"],
                "bootstrap_valid_repetitions": result["bootstrap_valid_repetitions"],
                "cluster_count": result["cluster_count"],
                "color": filters["color"],
                "draws": raw["draws"],
                "eligible_player_games": raw["eligible_player_games"],
                "family": family,
                "increment_seconds": filters["increment_seconds"],
                "losses": raw["losses"],
                "low_support": result["low_support"],
                "rating_difference_available_games": result["rating_difference_available_games"],
                "rating_max_exclusive": filters["rating_max_exclusive"],
                "rating_min": filters["rating_min"],
                "retained_player_games": opening["retained_player_games_with_opponent_rating"],
                "score_rate": raw["score_rate"],
                "source_report": "M4-figures.json",
                "weight_100_plus": weights["100_plus"],
                "weight_below_minus_100": weights["below_-100"],
                "weight_minus_100_to_99": weights["-100_to_99"],
                "win_rate": raw["win_rate"],
                "wins": raw["wins"],
            }
        )
    return rows


def clock_bucket_rows(sources: dict) -> list[dict]:
    figures = sources["figures"]
    by_bucket = {row["bucket"]: row for row in figures["clock"]["buckets"]}
    return [
        {
            "analytical_id": figures["clock"]["analytical_id"],
            "bucket": bucket,
            "eligible_moves": by_bucket[bucket]["eligible_moves"],
            "error_proxy_rate": by_bucket[bucket]["error_proxy_rate"],
            "evaluable_moves": by_bucket[bucket]["evaluable_moves"],
            "evaluation_coverage": by_bucket[bucket]["evaluation_coverage"],
            "mate_transition_moves": by_bucket[bucket]["mate_transition_moves"],
            "proxy_errors": by_bucket[bucket]["proxy_errors"],
            "source_report": "M4-figures.json",
        }
        for bucket in BUCKET_ORDER
    ]


def clock_stratum_rows(sources: dict) -> list[dict]:
    order = {bucket: index for index, bucket in enumerate(BUCKET_ORDER)}
    rows = [
        {
            "bucket": row["bucket"],
            "eligible_moves": row["eligible_moves"],
            "evaluable_moves": row["evaluable_moves"],
            "evaluation_coverage": row["evaluation_coverage"],
            "phase": row["phase"],
            "proxy_errors": row["proxy_errors"],
            "proxy_rate": row["proxy_rate"],
            "rating_band": row["rating_band"],
            "source_report": "M4-figures.json",
            "time_control": row["time_control"],
        }
        for row in sources["figures"]["clock"]["strata"]
    ]
    return sorted(
        rows,
        key=lambda row: (
            order[row["bucket"]],
            row["time_control"],
            row["phase"],
            row["rating_band"],
        ),
    )


def color_score_rows(sources: dict) -> list[dict]:
    opening = sources["figures"]["opening"]
    filters = opening["filters"]
    rows = []
    for key, raw in sources["reference"]["opening_player_cohorts"].items():
        parsed = _COHORT_KEY.fullmatch(key)
        if parsed is None:
            raise ValueError(f"opening cohort key is not understood: {key}")
        family = parsed.group("family")
        color = parsed.group("color")
        rating_min = int(parsed.group("low"))
        rating_max_exclusive = int(parsed.group("high")) + 1
        base_seconds = int(parsed.group("base"))
        increment_seconds = int(parsed.group("inc"))
        games = raw["games"]
        if games != raw["wins"] + raw["draws"] + raw["losses"]:
            raise ValueError(f"{key} games do not partition")
        published = (
            family in opening["families"]
            and color == filters["color"]
            and rating_min == filters["rating_min"]
            and rating_max_exclusive == filters["rating_max_exclusive"]
            and base_seconds == filters["base_seconds"]
            and increment_seconds == filters["increment_seconds"]
        )
        interval_low = None
        interval_high = None
        adjusted = None
        interval_source = None
        if published:
            result = opening["families"][family]
            figure = result["raw"]
            if (figure["wins"], figure["draws"], figure["losses"]) != (
                raw["wins"],
                raw["draws"],
                raw["losses"],
            ):
                raise ValueError(f"{family} color cell differs from M4")
            if figure["eligible_player_games"] != games:
                raise ValueError(f"{family} color cell games differ from M4")
            score_rate = (raw["wins"] + raw["draws"] / 2) / games
            if score_rate != figure["score_rate"] or raw["wins"] / games != figure["win_rate"]:
                raise ValueError(f"{family} color score differs from M4")
            interval = result["adjusted_95pct_cluster_bootstrap_interval"]
            interval_low, interval_high = interval
            adjusted = result["adjusted_score_rate"]
            interval_source = "M4-figures.json"
            if result["low_support"] != (games < LOW_SUPPORT_PLAYER_GAMES):
                raise ValueError(f"{family} low_support differs from the player-game threshold")
        rows.append(
            {
                "adjusted_interval_high": interval_high,
                "adjusted_interval_low": interval_low,
                "adjusted_score_rate": adjusted,
                "base_seconds": base_seconds,
                "color": color,
                "draws": raw["draws"],
                "family": family,
                "games": games,
                "increment_seconds": increment_seconds,
                "interval_source_report": interval_source,
                "losses": raw["losses"],
                "low_support": games < LOW_SUPPORT_PLAYER_GAMES,
                "rating_max_exclusive": rating_max_exclusive,
                "rating_min": rating_min,
                "score_rate": (raw["wins"] + raw["draws"] / 2) / games,
                "source_report": "M3-independent-reference.json",
                "win_rate": raw["wins"] / games,
                "wins": raw["wins"],
            }
        )
    if not rows:
        raise ValueError("opening color scores are empty")
    return sorted(rows, key=lambda row: (row["family"], row["color"]))


def clock_band_rows(sources: dict) -> list[dict]:
    totals: dict[tuple[str, str], list[int]] = {}
    for row in sources["figures"]["clock"]["strata"]:
        key = (row["rating_band"], row["time_control"])
        found = totals.setdefault(key, [0, 0, 0])
        found[0] += row["eligible_moves"]
        found[1] += row["evaluable_moves"]
        found[2] += row["proxy_errors"]
    rows = []
    for (band, control), (eligible, evaluable, errors) in totals.items():
        rows.append(
            {
                "eligible_moves": eligible,
                "error_proxy_rate": None if evaluable == 0 else errors / evaluable,
                "evaluable_moves": evaluable,
                "evaluation_coverage": None if eligible == 0 else evaluable / eligible,
                "proxy_errors": errors,
                "rating_band": band,
                "source_report": "M4-figures.json",
                "time_control": control,
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            _BAND_ORDER.index(row["rating_band"]),
            _control_order(row["time_control"]),
        ),
    )


def transposition_view_rows(sources: dict) -> list[dict]:
    return [
        {**row, "source_report": "opening-positions-dashboard.json"}
        for row in sources["positions"]["views"]
    ]


def transposition_compression_rows(sources: dict) -> list[dict]:
    return [
        {**row, "source_report": "opening-positions-dashboard.json"}
        for row in sources["positions"]["compression"]
    ]


def transposition_coverage_rows(sources: dict) -> list[dict]:
    return [
        {**row, "source_report": "opening-positions-dashboard.json"}
        for row in sources["positions"]["coverage"]
    ]


def transposition_scope_rows(sources: dict) -> list[dict]:
    checkpoint = sources["checkpoint"]
    summary = sources["positions"]
    return [
        {
            "games": checkpoint["games"],
            "ply_max": summary["plan_max_ply"],
            "ply_min": summary["plan_min_ply"],
            "positions_sha256": summary["source_sha256"],
            "scope": checkpoint["scope"],
            "source_report": "opening-positions-checkpoint.json",
            "visits": checkpoint["visits"],
        }
    ]


def transposition_limitation_rows(sources: dict) -> list[dict]:
    return [
        {"source_report": "opening-positions-dashboard.json", "text": text}
        for text in sources["positions"]["limitations"]
    ]


def receipt_rows(sources: dict, tables: dict) -> list[dict]:
    reference = sources["reference"]
    source = sources["source"]
    corpus = sources["corpus"]
    opening = sources["figures"]["opening"]
    rows = [
        _receipt(
            "opening_corpus_training_games",
            "opening_corpus_training_games",
            None,
            corpus["counts"]["training_games"],
            None,
        ),
        _receipt(
            "m3_august_prefix_accepted",
            "m3_august_prefix_accepted",
            None,
            source["counts"]["accepted"],
            None,
        ),
        _receipt(
            "known_opening_games",
            "known_opening_games",
            None,
            reference["known_opening_games"],
            reference["eligible_games"],
        ),
        _receipt(
            "game_draw_rate",
            "game_draw_rate",
            None,
            source["metric"]["numerator"],
            source["metric"]["denominator"],
        ),
        _receipt(
            "opening_usage",
            "opening_usage",
            None,
            reference["known_opening_games"],
            reference["known_opening_games"],
        ),
    ]
    for family in sorted(opening["families"]):
        result = opening["families"][family]
        raw = result["raw"]
        rows.append(
            _receipt(
                f"opening_player_score:{family}",
                "opening_player_score",
                family,
                _score_numerator(raw["wins"], raw["draws"]),
                raw["eligible_player_games"],
            )
        )
        rows.append(
            _receipt(
                f"opening_adjusted_score:{family}",
                "opening_adjusted_score",
                family,
                None,
                None,
            )
        )
        rows.append(
            _receipt(
                f"opening_adjusted_score_bootstrap:{family}",
                "opening_adjusted_score_bootstrap",
                family,
                None,
                None,
            )
        )
    for bucket in BUCKET_ORDER:
        row = next(
            item for item in sources["figures"]["clock"]["buckets"] if item["bucket"] == bucket
        )
        rows.append(
            _receipt(
                f"clock_pressure_error_proxy:{bucket}",
                "clock_pressure_error_proxy",
                bucket,
                row["proxy_errors"],
                row["evaluable_moves"],
            )
        )
    for cell in tables["opening_color_score"]:
        subject = f"{cell['family']} {cell['color']}"
        rows.append(
            _receipt(
                f"opening_color_score:{subject}",
                "opening_color_score",
                subject,
                _score_numerator(cell["wins"], cell["draws"]),
                cell["games"],
            )
        )
    bands = tables["clock_pressure_band"]
    rows.append(
        _receipt(
            "clock_pressure_by_band",
            "clock_pressure_by_band",
            None,
            sum(row["proxy_errors"] for row in bands),
            sum(row["evaluable_moves"] for row in bands),
        )
    )
    rows.append(
        _receipt(
            "transposition_visits",
            "transposition_visits",
            None,
            tables["transposition_scope"][0]["visits"],
            None,
        )
    )
    for run in tables["live_eval_run"]:
        subject = f"{run['model']} {run['effort']}"
        rows.append(
            _receipt(
                f"live_eval_pass_rate:{subject}",
                "live_eval_pass_rate",
                subject,
                run["passed"],
                run["trials"],
            )
        )
    return sorted(rows, key=lambda row: row["receipt_id"])


def collect_live_probe(project: Path, extract: dict) -> dict:
    """Query a local warehouse when it exists. Return {} when it does not."""
    if _snapshot_dir(project) is None:
        return {}
    try:
        from chess_analytics.analyst.semantic import published_mart, resolve_governed
        from chess_analytics.analyst.tools import CheckedTools
        from chess_analytics.common import read_json

        tools = CheckedTools(project)
        identity = _mart_identity(published_mart(tools.project, tools.snapshot), read_json)
    except Exception:
        return {"unusable": True}
    probe: dict[str, Any] = {"unusable": False}
    probe["game_draw_rate"] = _probe_draw(tools, resolve_governed, identity)
    probe["opening_usage"] = _probe_usage(tools, resolve_governed, identity)
    probe["opening_player_score"] = _probe_scores(tools, resolve_governed, identity, extract)
    probe["clock_pressure_error_proxy"] = _probe_clock(tools)
    return probe


def upgrade_receipts(extract: dict, probe: dict) -> list[str]:
    """Relabel receipts when a live query matches. Never invent aggregate rows."""
    before = {row["receipt_id"]: row["query_origin"] for row in extract["tables"]["metric_receipt"]}
    lines = _refresh_lines(extract, probe)
    lines.extend(_relabel_summary(extract, before, probe))
    return lines


def _refresh_lines(extract: dict, probe: dict) -> list[str]:
    if not probe or probe.get("unusable"):
        reason = _warehouse_reason(probe)
        return [
            f"skipped: metricflow refresh for {', '.join(GOVERNED_METRICS)} ({reason})",
            f"skipped: reviewed_sql refresh for {', '.join(GOVERNED_METRICS)} ({reason})",
            NEVER_METRICFLOW_LINE,
            BUILT_LINE,
            MAC_NONE,
            MAC_OPTIONAL,
        ]
    skipped = []
    refreshed = []
    for metric, updater in (
        ("game_draw_rate", _upgrade_draw),
        ("opening_usage", _upgrade_usage),
        ("opening_player_score", _upgrade_scores),
        ("clock_pressure_error_proxy", _upgrade_clock),
    ):
        outcome = updater(extract, probe.get(metric))
        if outcome == "refreshed":
            refreshed.append(metric)
        elif outcome:
            skipped.append(outcome)
    lines = list(skipped)
    lines.append(NEVER_METRICFLOW_LINE)
    if refreshed:
        joined = ", ".join(refreshed)
        lines.append(
            "refreshed: metric_receipt query_origin for "
            f"{joined} where live counts matched the committed reference"
        )
    else:
        lines.extend((BUILT_LINE, MAC_NONE, MAC_OPTIONAL))
    return lines


def _relabel_summary(extract: dict, before: dict, probe: dict) -> list[str]:
    rows = extract["tables"]["metric_receipt"]
    changed = [
        (
            f"relabeled: {row['receipt_id']} {before[row['receipt_id']]} -> "
            f"{row['query_origin']} (live counts matched the committed reference)"
        )
        for row in rows
        if before[row["receipt_id"]] != row["query_origin"]
    ]
    lines = changed or ["relabeled: none"]
    for row in rows:
        if before[row["receipt_id"]] != row["query_origin"]:
            continue
        reason = _not_relabeled_reason(row, probe)
        lines.append(f"not relabeled: {row['receipt_id']} stays {row['query_origin']} ({reason})")
    return lines


def _not_relabeled_reason(row: dict, probe: dict) -> str:
    metric = row["metric"]
    if metric in {"opening_adjusted_score", "opening_adjusted_score_bootstrap"}:
        return "outside MetricFlow"
    if metric not in {*GOVERNED_METRICS, "clock_pressure_error_proxy"}:
        return "committed report count, not a warehouse query"
    detail = _warehouse_reason(probe)
    if detail is None:
        live = probe.get(metric)
        detail = (
            "no live result" if not live else "live counts did not match the committed reference"
        )
    if metric == "clock_pressure_error_proxy":
        return f"{detail}; metricflow has no governed source"
    return detail


def _warehouse_reason(probe: dict) -> str | None:
    if not probe:
        return "analytical warehouse not found"
    if probe.get("unusable"):
        return "analytical warehouse present but not usable"
    return None


def check_extract(extract: dict, sources: dict) -> None:
    if set(extract["tables"]) != set(TABLES):
        raise ValueError("extract tables do not match the reader")
    lineage = extract["tables"]["lineage_stage"]
    _check_lineage(lineage, sources)
    families = extract["tables"]["opening_family_share"]
    known = sources["reference"]["known_opening_games"]
    if sum(row["numerator"] for row in families) != known:
        raise ValueError("extract families do not sum to known openings")
    if {row["query_origin"] for row in extract["tables"]["metric_receipt"]} - {"committed_report"}:
        raise ValueError("report-built receipts must start as committed_report")
    for row in extract["tables"]["metric_receipt"]:
        if row["metric"] in NEVER_METRICFLOW and row["query_origin"] == "metricflow":
            raise ValueError("clock and adjusted-score receipts cannot be metricflow")
        if row["query_origin"] not in QUERY_ORIGINS:
            raise ValueError("unsupported query origin")
    _check_color_scores(extract, sources)
    _check_clock_bands(extract, sources)
    _check_transpositions(extract, sources)
    _check_live_eval(extract)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the public aggregate extract",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Mac rebuild from ~/Developer/chess-analytics-lab. "
            "The dbt extra is required for MetricFlow. The dashboard extra is not.\n\n"
            + MAC_REBUILD
        ),
    )
    parser.add_argument("--project", type=Path, default=PROJECT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    project = args.project.resolve()
    output = args.output or extract_path(project)
    extract, logs = build_extract(project)
    for line in logs:
        print(line)
    write_json(output, extract)
    print(f"wrote {output.name} ({output.stat().st_size} bytes)")
    return 0


def _read(path: Path) -> dict:
    return json.loads(path.read_text())


def _control_order(value: str) -> tuple[int, int]:
    base, increment = value.split("+")
    return int(base), int(increment)


def _require_positions_pin(sources: dict) -> None:
    checkpoint = sources["checkpoint"]
    summary = sources["positions"]
    pinned = checkpoint["files"]["reports/opening-positions.json"]
    checked = checkpoint["independent_checks"]["report_sha256"]
    if summary.get("kind") != "opening_positions_dashboard_reduction":
        raise ValueError("opening position reduction kind differs")
    if summary.get("source_sha256") != pinned or pinned != checked:
        raise ValueError("opening position reduction pin differs from the checkpoint")
    if summary.get("source_version") != "1.1.0":
        raise ValueError("opening position reduction version differs")
    if summary.get("coverage_view") != "all":
        raise ValueError("opening position coverage view differs")
    if not summary.get("limitations"):
        raise ValueError("opening position limitations are empty")


def reduce_opening_positions(report: dict) -> dict:
    """Copy aggregate transposition rows. Position ids, moves, and labels stay out."""
    if report.get("kind") != "observed_white_opening_positions":
        raise ValueError("opening position report kind differs")
    if report.get("version") != "1.1.0":
        raise ValueError("opening position report version differs")
    plan = report["plan"]
    views = []
    compression = []
    coverage = []
    for cohort in sorted(report["cohorts"]):
        body = report["cohorts"][cohort]
        for row in body["compression_by_ply"]:
            compression.append(
                {
                    "cohort": cohort,
                    "distinct_positions": row["distinct_positions"],
                    "distinct_routes": row["distinct_routes"],
                    "endpoint_compression": row["endpoint_compression"],
                    "included_visits": row["included_visits"],
                    "ply": row["ply"],
                }
            )
        for view_name in sorted(body["views"]):
            view = body["views"][view_name]
            views.append(
                {
                    "cohort": cohort,
                    "denominator_games": view["denominator_games"],
                    "distinct_positions": view["distinct_positions"],
                    "recurring_positions": view["recurring_positions"],
                    "transposing_positions": view["transposing_positions"],
                    "view": view_name,
                }
            )
            if view_name != "all":
                continue
            rankings = view["rankings"]
            for mode in sorted(rankings):
                for point in rankings[mode]["coverage_curve"]:
                    coverage.append(
                        {
                            "additional_games": point["additional_games"],
                            "cohort": cohort,
                            "games": point["games"],
                            "mode": mode,
                            "n": point["n"],
                            "share": point["share"],
                            "view": "all",
                        }
                    )
    return {
        "compression": sorted(compression, key=lambda row: (row["cohort"], row["ply"])),
        "coverage": sorted(coverage, key=lambda row: (row["cohort"], row["mode"], row["n"])),
        "coverage_view": "all",
        "kind": "opening_positions_dashboard_reduction",
        "limitations": list(report["limitations"]),
        "plan_max_ply": plan["max_ply"],
        "plan_min_ply": plan["min_ply"],
        "source_report": "opening-positions.json",
        "source_version": report["version"],
        "views": views,
    }


def live_eval_tables(project: Path) -> tuple[list[dict], list[dict], list[dict]]:
    from chess_analytics.eval_report import discover_receipts, load_cases, load_receipts, verify

    case_path = project / "evals" / "cases" / "analyst_live_v1.json"
    cases = load_cases(case_path)
    listed = json.loads(case_path.read_text())
    order = {item["id"]: index for index, item in enumerate(listed)}
    if set(order) != set(cases) or len(order) != len(listed):
        raise ValueError("live eval case ids differ")
    paths = discover_receipts(project / "reports")
    if not paths:
        raise ValueError("live eval receipts are missing")
    receipts = load_receipts(paths)
    integrity = verify(receipts, cases)
    failed = [f"{label} {detail}".strip() for label, ok, detail in integrity.checks if not ok]
    if failed:
        raise ValueError("live eval receipt failed integrity: " + "; ".join(failed[:4]))
    runs = []
    categories = []
    case_rows = []
    for receipt in receipts:
        if receipt.raw.get("complete") is not True:
            raise ValueError(f"{receipt.path.name} is not a complete live-eval receipt")
        match = _RUN_ID.fullmatch(receipt.path.name)
        if match is None:
            raise ValueError(f"{receipt.path.name} has no GitHub run id")
        run_id = int(match.group(1) or match.group(2))
        wilson_low, wilson_high = receipt.wilson
        bootstrap_low, bootstrap_high = receipt.bootstrap
        runs.append(
            {
                "bootstrap_high": bootstrap_high,
                "bootstrap_low": bootstrap_low,
                "cases": int(receipt.raw["cases"]),
                "effort": receipt.effort,
                "github_run_id": run_id,
                "hard_fail": receipt.hard_fail,
                "headline": receipt.repeats == 5,
                "high_severity_misses": int(receipt.raw["high_severity_misses"]),
                "known_gross_cost_usd": receipt.cost,
                "max_run_usd": float(receipt.raw["max_run_usd"]),
                "model": receipt.model,
                "over_abstention": int(receipt.raw["over_abstention"]),
                "pass_rate": receipt.rate,
                "passed": receipt.passed,
                "repeats": receipt.repeats,
                "source_report": receipt.path.name,
                "trials": receipt.n,
                "unsafe_answer": int(receipt.raw["unsafe_answer"]),
                "wilson_high": wilson_high,
                "wilson_low": wilson_low,
            }
        )
        passes = receipt.passes_by_case()
        totals: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for case_id, case in cases.items():
            passed = passes[case_id]
            totals[case.category][0] += passed
            totals[case.category][1] += receipt.repeats
            case_rows.append(
                {
                    "case_id": case_id,
                    "case_order": order[case_id],
                    "category": case.category,
                    "effort": receipt.effort,
                    "model": receipt.model,
                    "passed": passed,
                    "repeats": receipt.repeats,
                    "severity": case.severity,
                }
            )
        for category, (passed, trials) in sorted(totals.items()):
            categories.append(
                {
                    "category": category,
                    "effort": receipt.effort,
                    "model": receipt.model,
                    "passed": passed,
                    "trials": trials,
                }
            )
    runs.sort(key=lambda row: row["github_run_id"])
    categories.sort(key=lambda row: (row["model"], row["effort"], row["category"]))
    case_rows.sort(key=lambda row: (row["model"], row["effort"], row["case_order"]))
    return runs, categories, case_rows


def _check_color_scores(extract: dict, sources: dict) -> None:
    cells = extract["tables"]["opening_color_score"]
    published = sources["figures"]["opening"]["families"]
    matched = [row for row in cells if row["interval_source_report"] == "M4-figures.json"]
    if {row["family"] for row in matched} != set(published):
        raise ValueError("adjusted intervals are not the published opening families")
    for row in matched:
        if row["adjusted_interval_low"] is None or row["adjusted_interval_high"] is None:
            raise ValueError(f"{row['family']} adjusted interval is missing")
        if row["color"] != sources["figures"]["opening"]["filters"]["color"]:
            raise ValueError("adjusted interval color differs from the published cohort")
    for row in cells:
        if row["interval_source_report"] is None and row["adjusted_score_rate"] is not None:
            raise ValueError("unpublished color cell has an adjusted score")
        half = row["wins"] + row["draws"] / 2
        if abs(row["score_rate"] - (half / row["games"])) > 1e-12:
            raise ValueError("color score rate does not match wins and draws")


def _check_clock_bands(extract: dict, sources: dict) -> None:
    bands = extract["tables"]["clock_pressure_band"]
    keys = {(row["rating_band"], row["time_control"]) for row in bands}
    if len(keys) != len(bands):
        raise ValueError("clock pressure bands are not unique")
    eligible = sum(row["eligible_moves"] for row in bands)
    evaluable = sum(row["evaluable_moves"] for row in bands)
    errors = sum(row["proxy_errors"] for row in bands)
    buckets = sources["figures"]["clock"]["buckets"]
    if eligible != sum(row["eligible_moves"] for row in buckets):
        raise ValueError("clock bands do not sum to the bucket eligible moves")
    if evaluable != sum(row["evaluable_moves"] for row in buckets):
        raise ValueError("clock bands do not sum to the bucket evaluable moves")
    if errors != sum(row["proxy_errors"] for row in buckets):
        raise ValueError("clock bands do not sum to the bucket proxy errors")


def _without_source(rows: list[dict]) -> list[dict]:
    return [{key: value for key, value in row.items() if key != "source_report"} for row in rows]


def _check_transpositions(extract: dict, sources: dict) -> None:
    summary = sources["positions"]
    checkpoint = sources["checkpoint"]
    views = extract["tables"]["transposition_view"]
    if _without_source(views) != summary["views"]:
        raise ValueError("transposition views differ from the reduction")
    if _without_source(extract["tables"]["transposition_compression"]) != summary["compression"]:
        raise ValueError("transposition compression differs from the reduction")
    if _without_source(extract["tables"]["transposition_coverage"]) != summary["coverage"]:
        raise ValueError("transposition coverage differs from the reduction")
    scope = extract["tables"]["transposition_scope"]
    if len(scope) != 1:
        raise ValueError("transposition scope is not one row")
    row = scope[0]
    if row["games"] != checkpoint["games"] or row["visits"] != checkpoint["visits"]:
        raise ValueError("transposition scope differs from the checkpoint")
    if row["scope"] != checkpoint["scope"]:
        raise ValueError("transposition scope text differs from the checkpoint")
    if str(row["ply_min"]) not in row["scope"] or str(row["ply_max"]) not in row["scope"]:
        raise ValueError("transposition ply window is not in the scope text")
    denominators = [item["denominator_games"] for item in views if item["view"] == "all"]
    training = sources["corpus"]["counts"]["training_games"]
    if sum(denominators) != training or row["games"] != training:
        raise ValueError("transposition denominators differ from the opening corpus")
    lenses = checkpoint["independent_checks"]["checks"]["lenses"]
    for key, games in lenses.items():
        cohort, view = key.split("/", 1)
        found = [
            item["denominator_games"]
            for item in views
            if item["cohort"] == cohort and item["view"] == view
        ]
        if found != [games]:
            raise ValueError(f"transposition lens {key} differs from the checkpoint")
    limitations = [item["text"] for item in extract["tables"]["transposition_limitation"]]
    if limitations != summary["limitations"]:
        raise ValueError("transposition limitations differ from the reduction")


def _check_live_eval(extract: dict) -> None:
    runs = extract["tables"]["live_eval_run"]
    cases = extract["tables"]["live_eval_case"]
    categories = extract["tables"]["live_eval_category"]
    if not any(row["headline"] for row in runs):
        raise ValueError("live eval extract has no 5-repeat headline run")
    for run in runs:
        if run["passed"] > run["trials"] or run["trials"] != run["cases"] * run["repeats"]:
            raise ValueError(f"{run['model']} live eval trials do not match")
        own = [
            row for row in cases if row["model"] == run["model"] and row["effort"] == run["effort"]
        ]
        if sum(row["passed"] for row in own) != run["passed"]:
            raise ValueError(f"{run['model']} case passes do not match the run")
        grouped: dict[str, int] = defaultdict(int)
        for row in own:
            grouped[row["category"]] += row["passed"]
        for category, passed in grouped.items():
            found = [
                item["passed"]
                for item in categories
                if item["model"] == run["model"]
                and item["effort"] == run["effort"]
                and item["category"] == category
            ]
            if found != [passed]:
                raise ValueError(f"{run['model']} {category} passes differ")


def _stage(
    *,
    lineage: str,
    stage_order: int,
    population: str,
    count: int,
    period: str | None,
    cohort: str | None,
    rolls_up_to: str | None,
    source_report: str,
    note: str,
) -> dict:
    stage_id = f"{lineage}:{population}"
    if period is not None and population == "training_source_games":
        stage_id = f"{lineage}:{period}:{cohort}"
    return {
        "cohort": cohort,
        "count": count,
        "lineage": lineage,
        "note": note,
        "period": period,
        "population": population,
        "rolls_up_to": rolls_up_to,
        "source_report": source_report,
        "stage_id": stage_id,
        "stage_order": stage_order,
        "unit": "games",
    }


def _corpus_note(cohort: str) -> str:
    if cohort == "elite_reference":
        return (
            "Curated elite month published by nikonoel. "
            "Inside the opening corpus, not the August prefix."
        )
    return "Opening-corpus training slice for this period. Not the August prefix accepted count."


def _prefix_report(population: str) -> str:
    if population in {"eligible_games", "known_opening_games"}:
        return "M3-analytical-manifest.json"
    return "M3-source-manifest.json"


def _receipt(receipt_id: str, metric: str, subject: str | None, numerator, denominator) -> dict:
    return {
        "denominator": denominator,
        "mart_id": None,
        "metric": metric,
        "model_sha256": None,
        "numerator": numerator,
        "query_origin": "committed_report",
        "receipt_id": receipt_id,
        "semantic_manifest_sha256": None,
        "subject": subject,
    }


def _score_numerator(wins: int, draws: int):
    score = wins + draws * 0.5
    if float(score).is_integer():
        return int(score)
    return score


def _require_same_clocks(figures: dict, analytical: dict, reference: dict) -> None:
    by_bucket = {row["bucket"]: row for row in figures["clock"]["buckets"]}
    manifest_rows = {row["bucket"]: row for row in analytical["summary"]["clock_buckets"]}
    if set(by_bucket) != set(BUCKET_ORDER) or set(manifest_rows) != set(BUCKET_ORDER):
        raise ValueError("clock bucket sets differ")
    if set(reference["clock_buckets"]) != set(BUCKET_ORDER):
        raise ValueError("reference clock bucket sets differ")
    keys = (
        "eligible_moves",
        "evaluable_moves",
        "proxy_errors",
        "mate_transition_moves",
        "evaluation_coverage",
        "error_proxy_rate",
    )
    for bucket, row in by_bucket.items():
        other = manifest_rows[bucket]
        if any(row[key] != other[key] for key in keys):
            raise ValueError(f"clock bucket {bucket} differs from the analytical manifest")
        ref = reference["clock_buckets"][bucket]
        observed = (
            row["eligible_moves"],
            row["evaluable_moves"],
            row["proxy_errors"],
            row["mate_transition_moves"],
        )
        expected = (ref["eligible"], ref["evaluable"], ref["errors"], ref["mate"])
        if observed != expected:
            raise ValueError(f"clock bucket {bucket} differs from the independent reference")


def _require_same_families(analytical: dict, reference: dict) -> None:
    families = reference["opening_families"]
    for item in analytical["summary"]["top_opening_families"]:
        if families.get(item["family"]) != item["eligible_games"]:
            raise ValueError("top opening family differs from the independent reference")


def _require_same_scores(figures: dict, reference: dict) -> None:
    opening = figures["opening"]
    filters = opening["filters"]
    expected = {
        "color": "black",
        "rating_min": 1400,
        "rating_max_exclusive": 1600,
        "base_seconds": 60,
        "increment_seconds": 0,
        "families": ["Sicilian Defense", "French Defense"],
    }
    if filters != expected:
        raise ValueError("opening figure filters differ from the published cohort")
    if set(opening["families"]) != set(expected["families"]):
        raise ValueError("opening figure families differ from the published cohort")
    for family, result in opening["families"].items():
        cohort = reference["opening_player_cohorts"][f"{family}|black|rating_1400_1599|60+0"]
        raw = result["raw"]
        if (raw["wins"], raw["draws"], raw["losses"]) != (
            cohort["wins"],
            cohort["draws"],
            cohort["losses"],
        ):
            raise ValueError(f"{family} score cell differs from the independent reference")
        if raw["eligible_player_games"] != cohort["games"]:
            raise ValueError(f"{family} game count differs from the independent reference")
        interval = result["adjusted_95pct_cluster_bootstrap_interval"]
        if not isinstance(interval, list) or len(interval) != 2:
            raise ValueError(f"{family} adjusted interval is missing")
        if result["bootstrap_valid_repetitions"] != 400:
            raise ValueError(f"{family} bootstrap repetition count differs")


def _check_lineage(lineage: list[dict], sources: dict) -> None:
    parent_id = "opening_corpus:training_games"
    parent = next(row for row in lineage if row["stage_id"] == parent_id)
    children = [row for row in lineage if row["rolls_up_to"] == parent_id]
    if sum(row["count"] for row in children) != parent["count"]:
        raise ValueError("opening corpus sources do not sum to training games")
    if parent["count"] != sources["corpus"]["counts"]["training_games"]:
        raise ValueError("training games differ from the corpus report")
    prefix = [row for row in lineage if row["lineage"] == "m3_august_prefix"]
    if any(row["rolls_up_to"] for row in prefix):
        raise ValueError("August prefix stages must not roll up into another lineage")
    counts = {row["population"]: row["count"] for row in prefix}
    august_slice = next(row["count"] for row in children if row["period"] == "2026-08")
    if august_slice == counts["accepted"]:
        raise ValueError("August corpus slice and prefix accepted count must stay distinct")
    if (
        counts["accepted"]
        != counts["marked_bots"] + counts["unknown_results"] + counts["eligible_games"]
    ):
        raise ValueError("August prefix populations do not partition accepted games")


def _snapshot_dir(project: Path) -> Path | None:
    pointer = project / "data" / "analytical-moves-current.json"
    if not pointer.is_file():
        return None
    try:
        identity = json.loads(pointer.read_text())["analytical_id"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if not isinstance(identity, str) or len(identity) != 24:
        return None
    if any(character not in "0123456789abcdef" for character in identity):
        return None
    directory = project / "data" / "analytical" / "published" / identity
    if not (directory / "warehouse.duckdb").is_file():
        return None
    return directory


def _mart_identity(located, read_json) -> dict | None:
    if located is None:
        return None
    manifest = read_json(located[0].parent / "manifest.json")
    identity = {
        "mart_id": manifest.get("mart_id"),
        "model_sha256": manifest.get("model_sha256"),
        "semantic_manifest_sha256": manifest.get("semantic_manifest_sha256"),
    }
    if not _identity_ok(identity):
        return None
    return identity


def _identity_ok(identity: dict) -> bool:
    mart_id = identity.get("mart_id")
    model = identity.get("model_sha256")
    semantic = identity.get("semantic_manifest_sha256")
    return (
        isinstance(mart_id, str)
        and len(mart_id) == 24
        and _hex(mart_id)
        and isinstance(model, str)
        and len(model) == 64
        and _hex(model)
        and isinstance(semantic, str)
        and len(semantic) == 64
        and _hex(semantic)
    )


def _hex(value: str) -> bool:
    return all(character in "0123456789abcdef" for character in value)


def _blank_identity() -> dict:
    return {"mart_id": None, "model_sha256": None, "semantic_manifest_sha256": None}


def _probe_draw(tools, resolve_governed, identity) -> dict | None:
    try:
        governed = resolve_governed(tools, "game_draw_rate", {}, [])
        if governed is not None and identity is not None:
            return {
                "origin": "metricflow",
                "numerator": governed["numerator"],
                "denominator": governed["denominator"],
                **identity,
            }
        reviewed = tools._query_metric_sql("game_draw_rate", {}, [])
    except Exception:
        return None
    return {
        "origin": "reviewed_sql",
        "numerator": reviewed["numerator"],
        "denominator": reviewed["denominator"],
        **_blank_identity(),
    }


def _probe_usage(tools, resolve_governed, identity) -> dict | None:
    try:
        governed = resolve_governed(tools, "opening_usage", {}, ["opening_family"])
        if governed is not None and identity is not None:
            return {
                "origin": "metricflow",
                "denominator": governed["denominator"],
                "families": {row["family"]: row["numerator"] for row in governed["rows"]},
                "truncated": governed["truncated"],
                **identity,
            }
        reviewed = tools._query_metric_sql("opening_usage", {}, ["opening_family"])
    except Exception:
        return None
    return {
        "origin": "reviewed_sql",
        "denominator": reviewed["denominator"],
        "families": {row["family"]: row["numerator"] for row in reviewed["rows"]},
        "truncated": reviewed["truncated"],
        **_blank_identity(),
    }


def _probe_scores(tools, resolve_governed, identity, extract: dict) -> dict | None:
    cells = extract["tables"]["opening_score_cell"]
    shared = {
        "color": cells[0]["color"],
        "rating_min": cells[0]["rating_min"],
        "rating_max_exclusive": cells[0]["rating_max_exclusive"],
        "base_seconds": cells[0]["base_seconds"],
        "increment_seconds": cells[0]["increment_seconds"],
    }
    found = {}
    origins = set()
    try:
        for cell in cells:
            filters = {**shared, "family": cell["family"]}
            governed = resolve_governed(tools, "opening_player_score", filters, [])
            if governed is not None and identity is not None:
                found[cell["family"]] = governed
                origins.add("metricflow")
                continue
            found[cell["family"]] = tools._query_metric_sql("opening_player_score", filters, [])
            origins.add("reviewed_sql")
    except Exception:
        return None
    if len(origins) != 1:
        return None
    origin = origins.pop()
    payload = {"origin": origin, "cells": found, **_blank_identity()}
    if origin == "metricflow":
        if identity is None:
            return None
        payload.update(identity)
    return payload


def _probe_clock(tools) -> dict | None:
    try:
        from chess_analytics.corpus.metrics import clock_pressure

        buckets = {
            bucket: clock_pressure(tools.project, tools.snapshot, bucket) for bucket in BUCKET_ORDER
        }
    except Exception:
        return None
    return {"origin": "reviewed_sql", "buckets": buckets, **_blank_identity()}


def _upgrade_draw(extract: dict, live: dict | None) -> str | None:
    if live is None:
        return "skipped: live refresh for game_draw_rate (no live result)"
    row = _find_receipt(extract, "game_draw_rate")
    if live["numerator"] != row["numerator"] or live["denominator"] != row["denominator"]:
        return (
            "skipped: live refresh for game_draw_rate (counts differ from the committed reference)"
        )
    _set_origin(row, live)
    return "refreshed"


def _upgrade_usage(extract: dict, live: dict | None) -> str | None:
    if live is None:
        return "skipped: live refresh for opening_usage (no live result)"
    if live.get("truncated"):
        return "skipped: live refresh for opening_usage (grouped result was truncated)"
    families = {
        row["family"]: row["numerator"] for row in extract["tables"]["opening_family_share"]
    }
    denominator = extract["tables"]["opening_family_share"][0]["denominator"]
    if live["families"] != families or live["denominator"] != denominator:
        return (
            "skipped: live refresh for opening_usage (counts differ from the committed reference)"
        )
    _set_origin(_find_receipt(extract, "opening_usage"), live)
    return "refreshed"


def _upgrade_scores(extract: dict, live: dict | None) -> str | None:
    if live is None:
        return "skipped: live refresh for opening_player_score (no live result)"
    cells = extract["tables"]["opening_score_cell"]
    for cell in cells:
        found = live["cells"].get(cell["family"])
        if found is None or not _same_score(cell, found):
            return (
                "skipped: live refresh for opening_player_score "
                "(counts differ from the committed reference)"
            )
    for cell in cells:
        _set_origin(_find_receipt(extract, f"opening_player_score:{cell['family']}"), live)
    return "refreshed"


def _upgrade_clock(extract: dict, live: dict | None) -> str | None:
    if live is None:
        return "skipped: live refresh for clock_pressure_error_proxy (no live result)"
    if live.get("origin") == "metricflow":
        raise ValueError("clock and adjusted-score receipts cannot be metricflow")
    for row in extract["tables"]["clock_bucket"]:
        found = live["buckets"].get(row["bucket"])
        if found is None or not _same_clock(row, found):
            return (
                "skipped: live refresh for clock_pressure_error_proxy "
                "(counts differ from the committed reference)"
            )
    for row in extract["tables"]["metric_receipt"]:
        if row["metric"] == "clock_pressure_error_proxy":
            _set_origin(row, live)
    return "refreshed"


def _same_score(cell: dict, live: dict) -> bool:
    return (
        live["wins"] == cell["wins"]
        and live["draws"] == cell["draws"]
        and live["losses"] == cell["losses"]
        and live["eligible_player_games"] == cell["eligible_player_games"]
        and live["score_rate"] == cell["score_rate"]
    )


def _same_clock(row: dict, live: dict) -> bool:
    return (
        live["eligible_moves"] == row["eligible_moves"]
        and live["evaluable_moves"] == row["evaluable_moves"]
        and live["proxy_errors"] == row["proxy_errors"]
        and live["mate_transition_moves"] == row["mate_transition_moves"]
        and live["evaluation_coverage"] == row["evaluation_coverage"]
        and live["error_proxy_rate"] == row["error_proxy_rate"]
    )


def _find_receipt(extract: dict, receipt_id: str) -> dict:
    for row in extract["tables"]["metric_receipt"]:
        if row["receipt_id"] == receipt_id:
            return row
    raise ValueError(f"missing receipt: {receipt_id}")


def _set_origin(row: dict, live: dict) -> None:
    origin = live["origin"]
    if origin not in QUERY_ORIGINS:
        raise ValueError("unsupported query origin")
    if origin == "metricflow" and row["metric"] in NEVER_METRICFLOW:
        raise ValueError("clock and adjusted-score receipts cannot be metricflow")
    if origin == "metricflow" and not _identity_ok(live):
        raise ValueError("metricflow receipt is missing mart identity")
    row["query_origin"] = origin
    if origin == "metricflow":
        row["mart_id"] = live["mart_id"]
        row["model_sha256"] = live["model_sha256"]
        row["semantic_manifest_sha256"] = live["semantic_manifest_sha256"]
        return
    row["mart_id"] = None
    row["model_sha256"] = None
    row["semantic_manifest_sha256"] = None


if __name__ == "__main__":
    raise SystemExit(main())
