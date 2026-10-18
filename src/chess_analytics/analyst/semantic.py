"""Governed metrics from the dbt semantic manifest, with the SQL path as fallback.

MetricFlow has no switch for its PyPI update check. Callers point HTTP proxies at a
closed local port so that check fails closed and the query still runs.
"""

import csv
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Protocol

import duckdb

from chess_analytics.common import digest

GOVERNED_METRICS = frozenset({"game_draw_rate", "opening_usage", "opening_player_score"})
_SEMANTIC_TABLES = frozenset({"games", "player_games", "metricflow_time_spine"})
_TEXT = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 '-.")
_SCORE_FILTERS = (
    "family",
    "color",
    "rating_min",
    "rating_max_exclusive",
    "base_seconds",
    "increment_seconds",
)


class _SnapshotTools(Protocol):
    project: Path
    snapshot: Path
    dataset_id: str


def manifest_path(project: Path) -> Path:
    return project / "dbt" / "target" / "semantic_manifest.json"


def semantic_ready(project: Path, warehouse: Path) -> bool:
    """True when parse artifacts, the mf binary, and the built tables are all present."""
    if not manifest_path(project).is_file() or not warehouse.is_file():
        return False
    if not Path(sys.executable).with_name("mf").is_file():
        return False
    try:
        with duckdb.connect(str(warehouse), read_only=True) as connection:
            found = {
                name
                for (name,) in connection.execute(
                    """select table_name from information_schema.tables
                    where table_schema = 'main'"""
                ).fetchall()
            }
    except duckdb.Error:
        return False
    return found >= _SEMANTIC_TABLES


def _governed_call(metric_id: str, filters: dict, group_by: list[str]) -> bool:
    """True only for a filter shape MetricFlow can answer. Other shapes stay on SQL."""
    if metric_id not in GOVERNED_METRICS or not isinstance(filters, dict):
        return False
    if group_by and filters:
        return False
    if metric_id == "game_draw_rate":
        return not filters and not group_by
    if metric_id == "opening_usage":
        if group_by == ["opening_family"] and not filters:
            return True
        family = filters.get("family")
        return (
            not group_by
            and set(filters) == {"family"}
            and isinstance(family, str)
            and 1 <= len(family) <= 80
            and _plain_text(family)
        )
    return not group_by and set(filters) == set(_SCORE_FILTERS) and _score_filters_valid(filters)


def resolve_governed(
    tools: _SnapshotTools, metric_id: str, filters: dict, group_by: list[str]
) -> dict | None:
    """Return the current tool shape, or None so the caller keeps its SQL path."""
    if not _governed_call(metric_id, filters, group_by):
        return None
    warehouse = tools.snapshot / "warehouse.duckdb"
    if not semantic_ready(tools.project, warehouse):
        return None
    if metric_id == "game_draw_rate":
        if filters or group_by:
            return None
        return _draw_rate(tools, warehouse)
    if metric_id == "opening_usage":
        return _opening_usage(tools, warehouse, filters, group_by)
    return _opening_player_score(tools, warehouse, filters, group_by)


def _draw_rate(tools: _SnapshotTools, warehouse: Path) -> dict:
    row = _one(tools.project, warehouse, ["drawn_games", "eligible_games", "game_draw_rate"])
    numerator = _as_int(row["drawn_games"])
    denominator = _as_int(row["eligible_games"])
    return {
        "metric_id": "game_draw_rate",
        "version": "1.0.0",
        "contract_sha256": digest(tools.project / "contracts/game_draw_rate.json"),
        "analytical_id": tools.dataset_id,
        "numerator": numerator,
        "denominator": denominator,
        "value": numerator / denominator if denominator else None,
    }


def _opening_usage(
    tools: _SnapshotTools, warehouse: Path, filters: dict, group_by: list[str]
) -> dict | None:
    if group_by == ["opening_family"] and not filters:
        return _opening_usage_grouped(tools, warehouse)
    if group_by or set(filters) != {"family"}:
        return None
    family = filters.get("family")
    if not isinstance(family, str) or not 1 <= len(family) <= 80 or not _plain_text(family):
        return None
    numerator = _as_int(
        _one(
            tools.project,
            warehouse,
            ["known_opening_games"],
            [_equals("game__opening_family", family)],
        )["known_opening_games"]
    )
    totals = _one(tools.project, warehouse, ["known_opening_games", "unknown_opening_games"])
    denominator = _as_int(totals["known_opening_games"])
    return {
        "metric_id": "opening_usage",
        "version": "1.0.0",
        "contract_sha256": digest(tools.project / "contracts/opening_usage.json"),
        "analytical_id": tools.dataset_id,
        "family": family,
        "numerator": numerator,
        "denominator": denominator,
        "unknown_opening_games": _as_int(totals["unknown_opening_games"]),
        "value": numerator / denominator if denominator else None,
        "scope": "observed bounded prefix only",
    }


def _opening_usage_grouped(tools: _SnapshotTools, warehouse: Path) -> dict:
    grouped = _rows(
        tools.project,
        warehouse,
        ["known_opening_games"],
        group_by=["game__opening_family"],
    )
    denominator = _as_int(
        _one(tools.project, warehouse, ["known_opening_games"])["known_opening_games"]
    )
    counted = sorted(
        (
            (row["game__opening_family"], _as_int(row["known_opening_games"]))
            for row in grouped
            if row.get("game__opening_family") not in {None, "", "None"}
            and _as_int(row["known_opening_games"])
        ),
        key=lambda item: (-item[1], item[0]),
    )
    return {
        "metric_id": "opening_usage",
        "analytical_id": tools.dataset_id,
        "group_by": ["opening_family"],
        "denominator": denominator,
        "rows": [
            {
                "family": family,
                "numerator": count,
                "value": count / denominator if denominator else None,
            }
            for family, count in counted[:500]
        ],
        "truncated": len(counted) > 500,
    }


def _opening_player_score(
    tools: _SnapshotTools, warehouse: Path, filters: dict, group_by: list[str]
) -> dict | None:
    if group_by or set(filters) != set(_SCORE_FILTERS):
        return None
    if not _score_filters_valid(filters):
        return None
    family = filters["family"]
    row = _one(
        tools.project,
        warehouse,
        [
            "opening_wins",
            "opening_draws",
            "opening_losses",
            "opening_score_games",
            "opening_score_total",
            "opening_player_score",
            "win_rate",
        ],
        [
            _equals("player_game__color", filters["color"]),
            _equals("player_game__opening_family", family),
            _compare("player_game__base_seconds", "=", filters["base_seconds"]),
            _compare("player_game__increment_seconds", "=", filters["increment_seconds"]),
            _compare("player_game__rating", ">=", filters["rating_min"]),
            _compare("player_game__rating", "<", filters["rating_max_exclusive"]),
        ],
    )
    wins = _as_int(row["opening_wins"])
    draws = _as_int(row["opening_draws"])
    losses = _as_int(row["opening_losses"])
    total = _as_int(row["opening_score_games"])
    score = _as_float(row["opening_score_total"])
    return {
        "metric_id": "opening_player_score",
        "version": "1.0.0",
        "contract_sha256": digest(tools.project / "contracts/opening_player_score.json"),
        "analytical_id": tools.dataset_id,
        "filters": {
            "family": family,
            "color": filters["color"],
            "rating_min": filters["rating_min"],
            "rating_max_exclusive": filters["rating_max_exclusive"],
            "base_seconds": filters["base_seconds"],
            "increment_seconds": filters["increment_seconds"],
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


def _score_filters_valid(filters: dict) -> bool:
    family = filters["family"]
    if not isinstance(family, str) or not _plain_text(family):
        return False
    if filters["color"] not in {"white", "black"}:
        return False
    integer_keys = (
        "rating_min",
        "rating_max_exclusive",
        "base_seconds",
        "increment_seconds",
    )
    if any(type(filters[key]) is not int for key in integer_keys):
        return False
    if not 0 <= filters["rating_min"] < filters["rating_max_exclusive"] <= 4000:
        return False
    return filters["base_seconds"] >= 0 and filters["increment_seconds"] >= 0


def _plain_text(value: str) -> bool:
    return bool(value) and set(value) <= _TEXT


def _equals(dimension: str, value: str) -> str:
    escaped = value.replace("'", "''")
    return "{{ Dimension('" + dimension + "') }} = '" + escaped + "'"


def _compare(dimension: str, operator: str, value: int) -> str:
    return "{{ Dimension('" + dimension + "') }} " + operator + " " + str(value)


def _one(
    project: Path, warehouse: Path, metrics: list[str], where: list[str] | None = None
) -> dict:
    rows = _rows(project, warehouse, metrics, where=where)
    if len(rows) != 1:
        raise RuntimeError("metricflow query returned an unexpected row count")
    return rows[0]


def _rows(
    project: Path,
    warehouse: Path,
    metrics: list[str],
    where: list[str] | None = None,
    group_by: list[str] | None = None,
) -> list[dict]:
    executable = Path(sys.executable).with_name("mf")
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        output = root / "result.csv"
        command = [
            str(executable),
            "query",
            "--quiet",
            "--metrics",
            ",".join(metrics),
            "--csv",
            str(output),
        ]
        if group_by:
            command.extend(["--group-by", ",".join(group_by)])
        for clause in where or []:
            command.extend(["--where", clause])
        completed = subprocess.run(
            command,
            cwd=root,
            env=_mf_env(project, warehouse, root / "logs"),
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode or not output.is_file():
            detail = (completed.stderr or completed.stdout).strip()
            raise RuntimeError(f"metricflow query failed ({completed.returncode}): {detail[-500:]}")
        with output.open(newline="") as handle:
            return list(csv.DictReader(handle))


def _mf_env(project: Path, warehouse: Path, log_path: Path) -> dict[str, str]:
    log_path.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(
        {
            "CHESSLAB_DBT_PATH": str(warehouse),
            "DBT_PROFILES_DIR": str(project / "dbt"),
            "DBT_PROJECT_DIR": str(project / "dbt"),
            "DBT_TARGET": "local",
            "DBT_SEND_ANONYMOUS_USAGE_STATS": "false",
            "DO_NOT_TRACK": "1",
            "DBT_LOG_PATH": str(log_path),
            # update-checker has no disable flag. A closed proxy makes the PyPI
            # request fail immediately; MetricFlow then continues.
            "https_proxy": "http://127.0.0.1:9",
            "http_proxy": "http://127.0.0.1:9",
            "HTTPS_PROXY": "http://127.0.0.1:9",
            "HTTP_PROXY": "http://127.0.0.1:9",
            "no_proxy": "",
            "NO_PROXY": "",
        }
    )
    return env


def _as_int(value: str) -> int:
    if value in {"", "None", "null", "nan", "NaN"}:
        return 0
    number = float(value)
    if not number.is_integer():
        raise RuntimeError(f"expected an integer metric value, got {value}")
    return int(number)


def _as_float(value: str) -> float:
    if value in {"", "None", "null", "nan", "NaN"}:
        return 0.0
    return float(value)
