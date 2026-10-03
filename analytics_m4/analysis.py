"""Checked, parameterized analysis over a published M3 snapshot."""

import random
from collections import defaultdict
from pathlib import Path

import duckdb

from analytics_m3.metrics import clock_pressure, opening_player_score
from analytics_m3.publish import validate_analytical
from chess_analytics.common import digest

FAMILIES = ("Sicilian Defense", "French Defense")
BUCKETS = ("under_10", "10_to_29", "30_to_59", "60_plus")


def current_snapshot(project: Path) -> Path:
    from chess_analytics.common import read_json

    root = project / "data"
    identity = read_json(root / "analytical-moves-current.json")["analytical_id"]
    if len(identity) != 24 or any(c not in "0123456789abcdef" for c in identity):
        raise ValueError("invalid analytical snapshot identity")
    snapshot = root / "analytical/published" / identity
    validate_analytical(snapshot)
    return snapshot


def coverage(project: Path, snapshot: Path) -> dict:
    manifest = validate_analytical(snapshot)
    source = project / "data/published" / manifest["source_snapshot_id"] / "manifest.json"
    from chess_analytics.common import read_json

    source_manifest = read_json(source)
    return {
        "analytical_id": manifest["analytical_id"],
        "source_snapshot_id": manifest["source_snapshot_id"],
        "partial_archive": manifest["partial_archive"],
        "observed_dates": manifest["observed_date_coverage"],
        "source_counts": source_manifest["counts"],
        "opening_coverage": manifest["summary"]["opening_coverage"],
        "move_coverage": manifest["summary"]["move_coverage"],
        "selection": manifest["selection"],
    }


def _stratum(difference: int) -> str:
    if difference < -100:
        return "below_-100"
    if difference >= 100:
        return "100_plus"
    return "-100_to_99"


def _interval(values: list[float]) -> list[float] | None:
    if not values:
        return None
    values.sort()
    return [values[int(0.025 * (len(values) - 1))], values[int(0.975 * (len(values) - 1))]]


def opening_comparison(
    project: Path,
    snapshot: Path,
    *,
    color: str = "black",
    rating_min: int = 1400,
    rating_max_exclusive: int = 1600,
    base_seconds: int = 60,
    increment_seconds: int = 0,
    families: tuple[str, str] = FAMILIES,
    bootstrap_repetitions: int = 400,
) -> dict:
    if color not in {"white", "black"} or not 0 <= rating_min < rating_max_exclusive <= 4000:
        raise ValueError("invalid color or rating band")
    if (
        base_seconds < 0
        or increment_seconds < 0
        or len(families) != 2
        or families[0] == families[1]
        or any(not isinstance(family, str) or not 1 <= len(family) <= 80 for family in families)
    ):
        raise ValueError("invalid time control or families")
    validate_analytical(snapshot)
    with duckdb.connect(str(snapshot / "warehouse.duckdb"), read_only=True) as con:
        rows = con.execute(
            """
            select trim(split_part(g.source_opening, ':', 1)) as opening_family,
                   coalesce(p.player_key, g.game_id || ':' || p.color) as player_cluster,
                   p.score, p.rating - p.opponent_rating rating_difference
            from fact_player_game p join fact_game g using (provider, game_id)
            where p.color = ? and p.rating >= ? and p.rating < ?
              and g.base_seconds = ? and g.increment_seconds = ?
              and trim(split_part(g.source_opening, ':', 1)) in (?, ?)
              and p.opponent_rating is not null
              and g.result in ('1-0','0-1','1/2-1/2') and not g.marked_bot
            """,
            [color, rating_min, rating_max_exclusive, base_seconds, increment_seconds, *families],
        ).fetchall()
    grouped = {family: [] for family in families}
    for family, cluster, score, difference in rows:
        grouped[family].append((cluster, score, _stratum(difference)))
    counts = {family: defaultdict(int) for family in families}
    for family in families:
        for _, _, stratum in grouped[family]:
            counts[family][stratum] += 1
    common = [
        key
        for key in ("below_-100", "-100_to_99", "100_plus")
        if all(counts[f][key] for f in families)
    ]
    retained = sum(counts[family][key] for family in families for key in common)
    weights = (
        {key: sum(counts[family][key] for family in families) / retained for key in common}
        if retained
        else {}
    )

    def adjusted(records):
        by_stratum = defaultdict(list)
        for _, score, stratum in records:
            if stratum in weights:
                by_stratum[stratum].append(score)
        if any(not by_stratum[key] for key in weights):
            return None
        return sum(weights[key] * (sum(by_stratum[key]) / len(by_stratum[key])) for key in weights)

    result = {}
    for family in families:
        records = grouped[family]
        metric = opening_player_score(
            project,
            snapshot,
            family=family,
            color=color,
            rating_min=rating_min,
            rating_max_exclusive=rating_max_exclusive,
            base_seconds=base_seconds,
            increment_seconds=increment_seconds,
        )
        # The adjusted population requires both recorded player and opponent ratings.
        clusters = defaultdict(list)
        for record in records:
            clusters[record[0]].append(record)
        keys = sorted(clusters)
        rng = random.Random(20261003 + families.index(family))
        samples = []
        if keys and common:
            for _ in range(bootstrap_repetitions):
                resampled = [row for _ in keys for row in clusters[rng.choice(keys)]]
                value = adjusted(resampled)
                if value is not None:
                    samples.append(value)
        result[family] = {
            "raw": metric,
            "rating_difference_available_games": len(records),
            "cluster_count": len(keys),
            "adjusted_score_rate": adjusted(records) if common else None,
            "adjusted_95pct_cluster_bootstrap_interval": _interval(samples),
            "bootstrap_valid_repetitions": len(samples),
            "low_support": metric["eligible_player_games"] < 100,
        }
    return {
        "analytical_id": validate_analytical(snapshot)["analytical_id"],
        "metric_id": "opening_adjusted_score",
        "metric_version": "1.0.0",
        "contract_sha256": digest(project / "contracts/opening_adjusted_score.json"),
        "filters": {
            "color": color,
            "rating_min": rating_min,
            "rating_max_exclusive": rating_max_exclusive,
            "base_seconds": base_seconds,
            "increment_seconds": increment_seconds,
            "families": list(families),
        },
        "families": result,
        "common_rating_difference_weights": weights,
        "retained_player_games_with_opponent_rating": retained,
        "method": "common pooled rating-difference weights; seeded focal-player cluster bootstrap",
        "caveats": [
            "Observed ordered August 1 prefix only; opening choice is confounded.",
            "Bootstrap describes within-prefix clustering, not monthly uncertainty.",
            "Opponent dependence and missing/anonymous player identifiers remain limitations.",
        ],
    }


def clock_analysis(project: Path, snapshot: Path) -> dict:
    manifest = validate_analytical(snapshot)
    buckets = [clock_pressure(project, snapshot, bucket) for bucket in BUCKETS]
    with duckdb.connect(str(snapshot / "warehouse.duckdb"), read_only=True) as con:
        strata = con.execute(
            """
            select m.clock_bucket, g.time_control, m.phase_proxy,
                   case when p.rating < 1200 then 'under_1200'
                        when p.rating < 1600 then '1200_1599'
                        when p.rating < 2000 then '1600_1999'
                        else '2000_plus' end rating_band,
                   count(*) eligible,
                   count(*) filter (where m.centipawn_deterioration is not null) evaluable,
                   count(*) filter (where m.error_proxy) proxy_errors
            from fact_move m join fact_game g using (provider, game_id)
              join fact_player_game p on p.provider=m.provider and p.game_id=m.game_id
                and p.color=m.color
            where m.clock_bucket is not null and g.increment_seconds=0
              and g.result in ('1-0','0-1','1/2-1/2') and not g.marked_bot
              and p.rating is not null
            group by all order by 1,2,3,4
            """
        ).fetchall()
    return {
        "analytical_id": manifest["analytical_id"],
        "buckets": buckets,
        "strata": [
            {
                "bucket": b,
                "time_control": t,
                "phase": p,
                "rating_band": r,
                "eligible_moves": e,
                "evaluable_moves": v,
                "proxy_errors": x,
                "evaluation_coverage": v / e if e else None,
                "proxy_rate": x / v if v else None,
            }
            for b, t, p, r, e, v, x in strata
        ],
        "caveats": [
            "Source evaluation availability is selected and sparse; no causal inference.",
            "Moves within a game/player are dependent; no independent-move interval is claimed.",
            "Only zero-increment games and previous same-player clocks are eligible.",
        ],
    }


def opening_catalog(project: Path, snapshot: Path) -> list[dict]:
    manifest = validate_analytical(snapshot)
    denominator = manifest["summary"]["opening_coverage"]["known_opening_games"]
    return [
        {
            "family": item["family"],
            "numerator": item["eligible_games"],
            "denominator": denominator,
            "value": item["eligible_games"] / denominator,
        }
        for item in manifest["summary"]["top_opening_families"]
    ]
