"""Only reviewed, read-only metric operations are exposed to the analyst."""

import json
from pathlib import Path

import duckdb

from analytics_m3.metrics import BUCKETS, clock_pressure, opening_player_score, opening_usage
from analytics_m4.analysis import coverage, current_snapshot, opening_comparison
from chess_analytics.common import digest

CONTRACTS = {
    "game_draw_rate": "game_draw_rate.json",
    "opening_adjusted_score": "opening_adjusted_score.json",
    "opening_usage": "opening_usage.json",
    "opening_player_score": "opening_player_score.json",
    "clock_pressure_error_proxy": "clock_pressure_error_proxy.json",
    "evaluation_coverage": "evaluation_coverage.json",
}
ALLOWED_GROUP_BY = {"opening_family", "clock_bucket"}


def _exact_keys(value: dict, allowed: set[str]):
    if not isinstance(value, dict) or set(value) - allowed:
        raise ValueError("unknown or malformed filter")


class CheckedTools:
    def __init__(self, project: Path):
        self.project = project
        self.snapshot = current_snapshot(project)
        self.dataset_id = self.snapshot.name

    def list_metrics(self) -> dict:
        return {"dataset_id": self.dataset_id, "metric_ids": sorted(CONTRACTS)}

    def get_metric_definition(self, metric_id: str) -> dict:
        if metric_id not in CONTRACTS:
            raise ValueError("unsupported metric")
        path = self.project / "contracts" / CONTRACTS[metric_id]
        return {
            "dataset_id": self.dataset_id,
            "contract_sha256": digest(path),
            "definition": json.loads(path.read_text()),
        }

    def get_dataset_coverage(self) -> dict:
        return coverage(self.project, self.snapshot)

    def query_metric(
        self, metric_id: str, filters: dict, group_by: list[str] | None = None
    ) -> dict:
        group_by = group_by or []
        if (
            not isinstance(group_by, list)
            or len(group_by) > 1
            or any(item not in ALLOWED_GROUP_BY for item in group_by)
        ):
            raise ValueError("unsupported grouping")
        if group_by:
            if filters:
                raise ValueError("grouped metrics do not accept additional filters")
            if metric_id == "opening_usage" and group_by == ["opening_family"]:
                with duckdb.connect(str(self.snapshot / "warehouse.duckdb"), read_only=True) as con:
                    rows = con.execute(
                        """select trim(split_part(source_opening, ':', 1)) opening_family,
                                  count(*) games
                        from fact_game where result in ('1-0','0-1','1/2-1/2')
                          and not marked_bot and nullif(trim(source_opening), '') is not null
                        group by 1 order by games desc, opening_family limit 501"""
                    ).fetchall()
                    denominator = con.execute(
                        """select count(*) from fact_game
                        where result in ('1-0','0-1','1/2-1/2') and not marked_bot
                          and nullif(trim(source_opening), '') is not null"""
                    ).fetchone()[0]
                return {
                    "metric_id": metric_id,
                    "analytical_id": self.dataset_id,
                    "group_by": group_by,
                    "denominator": denominator,
                    "rows": [
                        {
                            "family": family,
                            "numerator": count,
                            "value": count / denominator if denominator else None,
                        }
                        for family, count in rows[:500]
                    ],
                    "truncated": len(rows) > 500,
                }
            if metric_id in {"clock_pressure_error_proxy", "evaluation_coverage"} and group_by == [
                "clock_bucket"
            ]:
                return {
                    "metric_id": metric_id,
                    "analytical_id": self.dataset_id,
                    "group_by": group_by,
                    "rows": [
                        clock_pressure(self.project, self.snapshot, bucket)
                        for bucket in sorted(BUCKETS)
                    ],
                    "truncated": False,
                }
            raise ValueError("unsupported metric grouping")
        if metric_id == "game_draw_rate":
            if filters or group_by:
                raise ValueError("draw rate takes no filters")
            with duckdb.connect(str(self.snapshot / "warehouse.duckdb"), read_only=True) as con:
                numerator, denominator = con.execute(
                    """select count(*) filter (where result = '1/2-1/2'), count(*)
                    from fact_game where result in ('1-0','0-1','1/2-1/2')
                    and not marked_bot"""
                ).fetchone()
            return {
                "metric_id": metric_id,
                "version": "1.0.0",
                "contract_sha256": digest(self.project / "contracts/game_draw_rate.json"),
                "analytical_id": self.dataset_id,
                "numerator": numerator,
                "denominator": denominator,
                "value": numerator / denominator if denominator else None,
            }
        if metric_id == "opening_adjusted_score":
            required = {
                "families",
                "color",
                "rating_min",
                "rating_max_exclusive",
                "base_seconds",
                "increment_seconds",
            }
            _exact_keys(filters, required)
            if set(filters) != required or group_by:
                raise ValueError("exact adjusted opening filters required")
            if not isinstance(filters["families"], list) or len(filters["families"]) != 2:
                raise ValueError("two opening families required")
            return opening_comparison(
                self.project, self.snapshot, **{**filters, "families": tuple(filters["families"])}
            )
        if metric_id == "opening_usage":
            _exact_keys(filters, {"family"})
            if group_by and group_by != ["opening_family"]:
                raise ValueError("unsupported opening grouping")
            family = filters.get("family")
            if not isinstance(family, str) or not 1 <= len(family) <= 80:
                raise ValueError("opening family required")
            return opening_usage(self.project, self.snapshot, family)
        if metric_id == "opening_player_score":
            required = {
                "family",
                "color",
                "rating_min",
                "rating_max_exclusive",
                "base_seconds",
                "increment_seconds",
            }
            _exact_keys(filters, required)
            if set(filters) != required or group_by:
                raise ValueError("exact player score filters required")
            if any(
                type(filters[key]) is not int
                for key in (
                    "rating_min",
                    "rating_max_exclusive",
                    "base_seconds",
                    "increment_seconds",
                )
            ):
                raise ValueError("integer filters required")
            if not 0 <= filters["rating_min"] < filters["rating_max_exclusive"] <= 4000:
                raise ValueError("invalid rating range")
            if filters["base_seconds"] < 0 or filters["increment_seconds"] < 0:
                raise ValueError("invalid time control")
            return opening_player_score(self.project, self.snapshot, **filters)
        if metric_id in {"clock_pressure_error_proxy", "evaluation_coverage"}:
            _exact_keys(filters, {"bucket"})
            if group_by and group_by != ["clock_bucket"]:
                raise ValueError("unsupported clock grouping")
            if filters.get("bucket") not in BUCKETS:
                raise ValueError("clock bucket required")
            return clock_pressure(self.project, self.snapshot, filters["bucket"])
        raise ValueError("unsupported metric")

    def compare_openings(self, filters: dict) -> dict:
        required = {
            "families",
            "color",
            "rating_min",
            "rating_max_exclusive",
            "base_seconds",
            "increment_seconds",
        }
        _exact_keys(filters, required)
        if (
            set(filters) != required
            or not isinstance(filters["families"], list)
            or len(filters["families"]) != 2
        ):
            raise ValueError("two families and exact cohort filters required")
        if any(not isinstance(f, str) or len(f) > 80 for f in filters["families"]):
            raise ValueError("invalid family")
        common = {key: value for key, value in filters.items() if key != "families"}
        rows = [
            self.query_metric("opening_player_score", {**common, "family": family})
            for family in filters["families"]
        ]
        a, b = rows
        delta = (
            None
            if a["score_rate"] is None or b["score_rate"] is None
            else a["score_rate"] - b["score_rate"]
        )
        return {
            "dataset_id": self.dataset_id,
            "families": rows,
            "score_rate_difference_first_minus_second": delta,
            "win_rate_difference_first_minus_second": (
                None
                if a["win_rate"] is None or b["win_rate"] is None
                else a["win_rate"] - b["win_rate"]
            ),
            "caveats": ["observed_prefix_only", "association_not_causation"],
        }

    def analyze_clock_pressure(self, bucket: str) -> dict:
        return self.query_metric("clock_pressure_error_proxy", {"bucket": bucket})

    def compare_clock_buckets(self, first: str, second: str) -> dict:
        if first == second:
            raise ValueError("two distinct clock buckets required")
        a, b = self.analyze_clock_pressure(first), self.analyze_clock_pressure(second)
        delta = (
            None
            if a["error_proxy_rate"] is None or b["error_proxy_rate"] is None
            else a["error_proxy_rate"] - b["error_proxy_rate"]
        )
        return {
            "dataset_id": self.dataset_id,
            "buckets": [a, b],
            "error_proxy_rate_difference_first_minus_second": delta,
            "evaluation_coverage_difference_first_minus_second": (
                None
                if a["evaluation_coverage"] is None or b["evaluation_coverage"] is None
                else a["evaluation_coverage"] - b["evaluation_coverage"]
            ),
            "caveats": ["source_evaluation_selection", "exploratory_proxy"],
        }

    def execute(self, name: str, args: dict) -> dict:
        if not isinstance(args, dict):
            raise ValueError("tool arguments must be an object")
        if name == "list_metrics" and not args:
            return self.list_metrics()
        if name == "get_metric_definition" and set(args) == {"metric_id"}:
            return self.get_metric_definition(args["metric_id"])
        if name == "get_dataset_coverage" and not args:
            return self.get_dataset_coverage()
        if name == "query_metric" and set(args) <= {"metric_id", "filters", "group_by"}:
            return self.query_metric(**args)
        if name == "compare_openings" and set(args) == {"filters"}:
            return self.compare_openings(args["filters"])
        if name == "analyze_clock_pressure" and set(args) == {"bucket"}:
            return self.analyze_clock_pressure(args["bucket"])
        if name == "compare_clock_buckets" and set(args) == {"first", "second"}:
            return self.compare_clock_buckets(args["first"], args["second"])
        raise ValueError("unsupported tool or arguments")
