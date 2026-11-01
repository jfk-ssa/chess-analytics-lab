"""Closed payload facade; a future backend may adapt CheckedTools.

Recorded values are flat numeric cells, not a warehouse result envelope.
No SQL is generated here. Opening families remain literal ADR 0085 families;
a future SQL backend must use corpus.metrics.opening_family_expr.
"""

import json
import math
import re
from copy import deepcopy
from typing import Protocol

METRIC_IDS = frozenset(
    {
        "opening_player_score",
        "game_draw_rate",
        "opening_usage",
        "clock_pressure_error_proxy",
        "mean_centipawn_loss",
    }
)
_BUCKETS = {"under_10", "10_to_29", "30_to_59", "60_plus"}
_COHORT = {"color", "rating_min", "rating_max_exclusive", "base_seconds", "increment_seconds"}
EVIDENCE_ID = re.compile(r"[a-z][a-z0-9_-]*")


def numeric_fields(value: object) -> bool:
    return (
        isinstance(value, dict)
        and bool(value)
        and all(
            isinstance(key, str)
            and (number is None or (type(number) in (int, float) and math.isfinite(number)))
            for key, number in value.items()
        )
    )


def validate_call(name: str, args: dict) -> None:
    """Reject unknown operations and malformed filters before backend dispatch."""
    if not isinstance(args, dict):
        raise ValueError("tool arguments must be an object")
    if name == "query_metric" and set(args) == {"metric_id", "filters"}:
        metric = args["metric_id"]
        if not isinstance(metric, str) or metric not in METRIC_IDS:
            raise ValueError("unsupported coach metric")
        filters = args["filters"]
        keys = {
            "opening_usage": {"family"},
            "opening_player_score": _COHORT | {"family"},
            "clock_pressure_error_proxy": {"bucket"},
        }.get(metric, set())
    elif name == "compare_openings" and set(args) == {"filters"}:
        filters, keys = args["filters"], _COHORT | {"families"}
    elif name == "analyze_clock_pressure" and set(args) == {"bucket"}:
        filters, keys = args, {"bucket"}
    else:
        raise ValueError("unsupported coach tool or arguments")
    if not isinstance(filters, dict) or set(filters) != keys:
        raise ValueError("exact coach filters required")
    families = filters.get("families", [filters["family"]] if "family" in filters else [])
    if not isinstance(families, list) or ("families" in filters and len(families) != 2):
        raise ValueError("two opening families required")
    if any(not isinstance(f, str) or not f.strip() or len(f) > 80 for f in families):
        raise ValueError("invalid opening family")
    if "bucket" in filters and (
        not isinstance(filters["bucket"], str) or filters["bucket"] not in _BUCKETS
    ):
        raise ValueError("unsupported clock bucket")
    if "color" in filters:
        integers = _COHORT - {"color"}
        if (
            filters["color"] not in ("white", "black")
            or any(type(filters[k]) is not int or filters[k] < 0 for k in integers)
            or not filters["rating_min"] < filters["rating_max_exclusive"] <= 4000
        ):
            raise ValueError("invalid opening cohort")


class PayloadBackend(Protocol):
    def execute(self, name: str, args: dict) -> dict: ...


def _key(name: str, args: dict) -> str:
    return json.dumps([name, args], sort_keys=True, allow_nan=False)


class RecordedToolBackend:
    """Exact tool+argument lookup only; missing recordings fail closed."""

    def __init__(self, recordings: list[dict]):
        self._payloads: dict[str, dict] = {}
        for recording in recordings:
            key = _key(recording["tool"], recording["args"])
            if key in self._payloads:
                raise ValueError("duplicate tool recording")
            self._payloads[key] = deepcopy(recording["result"])

    def execute(self, name: str, args: dict) -> dict:
        try:
            return deepcopy(self._payloads[_key(name, args)])
        except KeyError as exc:
            raise ValueError("no recorded tool payload") from exc


class CoachTools:
    def __init__(self, backend: PayloadBackend):
        self._backend = backend

    def execute(self, name: str, args: dict) -> dict:
        validate_call(name, args)
        result = self._backend.execute(name, deepcopy(args))
        evidence_id = result.get("evidence_id")
        if (
            not isinstance(evidence_id, str)
            or not EVIDENCE_ID.fullmatch(evidence_id)
            or not numeric_fields(result.get("values"))
        ):
            raise ValueError("tool payload requires evidence id and finite numeric cells")
        return {**result, "tool": name, "args": deepcopy(args)}
