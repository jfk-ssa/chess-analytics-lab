"""Read-only, parameterized M3 metrics over a validated analytical snapshot."""

from pathlib import Path

import duckdb

from chess_analytics.common import digest
from chess_analytics.corpus.publish import validate_analytical

BUCKETS = {"under_10", "10_to_29", "30_to_59", "60_plus"}


def opening_usage(project: Path, snapshot: Path, family: str) -> dict:
    manifest = validate_analytical(snapshot)
    with duckdb.connect(str(snapshot / "warehouse.duckdb"), read_only=True) as con:
        numerator, denominator, unknown = con.execute(
            """
            select count(*) filter (where trim(split_part(source_opening, ':', 1)) = ?),
                   count(*) filter (where nullif(trim(source_opening), '') is not null),
                   count(*) filter (where nullif(trim(source_opening), '') is null)
            from fact_game
            where result in ('1-0','0-1','1/2-1/2') and not marked_bot
        """,
            [family],
        ).fetchone()
    return {
        "metric_id": "opening_usage",
        "version": "1.0.0",
        "contract_sha256": digest(project / "contracts/opening_usage.json"),
        "analytical_id": manifest["analytical_id"],
        "family": family,
        "numerator": numerator,
        "denominator": denominator,
        "unknown_opening_games": unknown,
        "value": numerator / denominator if denominator else None,
        "scope": "observed bounded prefix only",
    }


def opening_player_score(
    project: Path,
    snapshot: Path,
    *,
    family: str,
    color: str,
    rating_min: int,
    rating_max_exclusive: int,
    base_seconds: int,
    increment_seconds: int,
) -> dict:
    if color not in {"white", "black"} or rating_min >= rating_max_exclusive:
        raise ValueError("invalid color or half-open rating band")
    manifest = validate_analytical(snapshot)
    with duckdb.connect(str(snapshot / "warehouse.duckdb"), read_only=True) as con:
        wins, draws, losses, score = con.execute(
            """
            select count(*) filter (where p.score = 1),
                   count(*) filter (where p.score = 0.5),
                   count(*) filter (where p.score = 0),
                   sum(p.score)
            from fact_player_game p join fact_game g using (provider, game_id)
            where p.color = ? and p.rating >= ? and p.rating < ?
              and g.base_seconds = ? and g.increment_seconds = ?
              and trim(split_part(g.source_opening, ':', 1)) = ?
              and g.result in ('1-0','0-1','1/2-1/2') and not g.marked_bot
        """,
            [color, rating_min, rating_max_exclusive, base_seconds, increment_seconds, family],
        ).fetchone()
    total = wins + draws + losses
    return {
        "metric_id": "opening_player_score",
        "version": "1.0.0",
        "contract_sha256": digest(project / "contracts/opening_player_score.json"),
        "analytical_id": manifest["analytical_id"],
        "filters": {
            "family": family,
            "color": color,
            "rating_min": rating_min,
            "rating_max_exclusive": rating_max_exclusive,
            "base_seconds": base_seconds,
            "increment_seconds": increment_seconds,
        },
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "eligible_player_games": total,
        "win_rate": wins / total if total else None,
        "score_rate": score / total if total else None,
        "low_support": total < 100,
        "scope": "descriptive observed prefix; no causal claim",
    }


def clock_pressure(project: Path, snapshot: Path, bucket: str) -> dict:
    if bucket not in BUCKETS:
        raise ValueError("unsupported clock bucket")
    manifest = validate_analytical(snapshot)
    with duckdb.connect(str(snapshot / "warehouse.duckdb"), read_only=True) as con:
        eligible, evaluable, errors, mates = con.execute(
            """
            select count(*),
                   count(*) filter (where m.centipawn_deterioration is not null),
                   count(*) filter (where m.error_proxy),
                   count(*) filter (where m.eval_before_mate_white is not null
                                      or m.eval_after_mate_white is not null)
            from fact_move m join fact_game g using (provider, game_id)
            where m.clock_bucket = ? and g.increment_seconds = 0
              and g.result in ('1-0','0-1','1/2-1/2') and not g.marked_bot
        """,
            [bucket],
        ).fetchone()
    return {
        "metric_id": "clock_pressure_error_proxy",
        "version": "1.0.0",
        "contract_sha256": digest(project / "contracts/clock_pressure_error_proxy.json"),
        "coverage_contract_sha256": digest(project / "contracts/evaluation_coverage.json"),
        "analytical_id": manifest["analytical_id"],
        "bucket": bucket,
        "eligible_moves": eligible,
        "evaluable_moves": evaluable,
        "proxy_errors": errors,
        "mate_transition_moves": mates,
        "evaluation_coverage": evaluable / eligible if eligible else None,
        "error_proxy_rate": errors / evaluable if evaluable else None,
        "scope": "exploratory source-evaluation proxy in sampled games of observed prefix",
    }
