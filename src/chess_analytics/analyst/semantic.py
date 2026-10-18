"""Governed metrics from the published mart's semantic manifest.

The analyst snapshot is the analytical warehouse. Semantic tables live on the
mart built from that snapshot's source. Any mismatch or query failure returns
None so the caller keeps the reviewed SQL. MetricFlow compiles in-process and
the compiled statement runs on a read-only connection.
"""

import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Protocol, cast

import duckdb

from chess_analytics.common import digest, read_json
from chess_analytics.corpus.metrics import opening_family_expr
from chess_analytics.corpus.publish import validate_analytical
from chess_analytics.marts.pipeline import checked_id, model_hash, validate_mart

logger = logging.getLogger(__name__)

GOVERNED_METRICS = frozenset({"game_draw_rate", "opening_usage", "opening_player_score"})
_TEXT = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 '-.")
_SCORE_FILTERS = (
    "family",
    "color",
    "rating_min",
    "rating_max_exclusive",
    "base_seconds",
    "increment_seconds",
)
_ENGINES: dict[str, Any] = {}
_EXPECTED_SEMANTIC: dict[str, str] = {}
_GROUPED_FAMILY_WHERE = (
    "{{ Dimension('game__opening_family') }} IS NOT NULL AND known_opening_games > 0"
)


class _SnapshotTools(Protocol):
    project: Path
    snapshot: Path
    dataset_id: str


def opening_family_sql(column: str = "source_opening") -> str:
    """The family expression shared with the reviewed SQL."""
    return opening_family_expr(column)


def _governed_call(metric_id: str, filters: dict, group_by: list[str]) -> bool:
    """True only for a filter shape this module can answer. Other shapes stay on SQL."""
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


def published_mart(project: Path, snapshot: Path) -> tuple[Path, Path] | None:
    """Warehouse and semantic manifest when the current mart matches this analytical source."""
    try:
        analytical = validate_analytical(snapshot)
        source_id = analytical["source_snapshot_id"]
        checked_id(source_id)
        source = read_json(project / "data" / "published" / source_id / "manifest.json")
        dataset = source["dataset"]
        if not isinstance(dataset, str) or dataset not in {"tiny", "foundation", "analytical"}:
            return None
        pointer = read_json(project / "data" / f"{dataset}-mart-current.json")
        directory = project / "data" / "marts" / "published" / checked_id(pointer["mart_id"])
        manifest = validate_mart(directory)
        project_hash = model_hash(project)
        if manifest.get("snapshot_id") != source_id or manifest.get("model_sha256") != project_hash:
            return None
        semantic_manifest = directory / "semantic_manifest.json"
        if digest(semantic_manifest) != _expected_semantic_digest(project):
            return None
    except (OSError, ValueError, RuntimeError, KeyError, duckdb.Error):
        return None
    return directory / "warehouse.duckdb", semantic_manifest


def resolve_governed(
    tools: _SnapshotTools, metric_id: str, filters: dict, group_by: list[str]
) -> dict | None:
    """Return the current tool shape, or None so the caller keeps its SQL path."""
    if not _governed_call(metric_id, filters, group_by):
        return None
    located = published_mart(tools.project, tools.snapshot)
    if located is None:
        return None
    warehouse, semantic = located
    try:
        if metric_id == "game_draw_rate":
            return _draw_rate(tools, warehouse, semantic)
        if metric_id == "opening_usage":
            return _opening_usage(tools, warehouse, semantic, filters, group_by)
        return _opening_player_score(tools, warehouse, semantic, filters)
    except (OSError, RuntimeError, ValueError, KeyError, ImportError, duckdb.Error):
        logger.warning("semantic query failed; using reviewed SQL")
        return None


def _expected_semantic_digest(project: Path) -> str:
    """Digest of the semantic manifest parsed from the current project models."""
    key = model_hash(project)
    cached = _EXPECTED_SEMANTIC.get(key)
    if cached is not None:
        return cached
    found = _parse_semantic_digest(project)
    _EXPECTED_SEMANTIC[key] = found
    return found


def _parse_semantic_digest(project: Path) -> str:
    dbt = Path(sys.executable).with_name("dbt")
    if not dbt.is_file():
        raise RuntimeError("semantic manifest check failed")
    try:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            warehouse = root / "warehouse.duckdb"
            duckdb.connect(str(warehouse)).close()
            env = os.environ.copy()
            env["CHESSLAB_DBT_PATH"] = str(warehouse)
            env["DBT_PROFILES_DIR"] = str(project / "dbt")
            env["DBT_SEND_ANONYMOUS_USAGE_STATS"] = "false"
            completed = subprocess.run(
                [
                    str(dbt),
                    "parse",
                    "--project-dir",
                    str(project / "dbt"),
                    "--profiles-dir",
                    str(project / "dbt"),
                    "--target-path",
                    str(root / "target"),
                    "--log-path",
                    str(root / "log"),
                    "--no-use-colors",
                ],
                cwd=project,
                env=env,
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            parsed = root / "target" / "semantic_manifest.json"
            if completed.returncode or not parsed.is_file():
                raise RuntimeError("semantic manifest check failed")
            return digest(parsed)
    except (OSError, subprocess.SubprocessError, duckdb.Error) as error:
        raise RuntimeError("semantic manifest check failed") from error


def _draw_rate(tools: _SnapshotTools, warehouse: Path, semantic: Path) -> dict:
    row = _one(warehouse, semantic, ["drawn_games", "eligible_games", "game_draw_rate"])
    numerator = _as_int(row["drawn_games"])
    denominator = _as_int(row["eligible_games"])
    ratio = _optional_float(row["game_draw_rate"])
    if denominator == 0:
        ratio = None
    elif ratio is None:
        raise RuntimeError("draw rate ratio missing")
    return {
        "metric_id": "game_draw_rate",
        "version": "1.0.0",
        "contract_sha256": digest(tools.project / "contracts/game_draw_rate.json"),
        "analytical_id": tools.dataset_id,
        "numerator": numerator,
        "denominator": denominator,
        "value": ratio,
    }


def _opening_usage(
    tools: _SnapshotTools,
    warehouse: Path,
    semantic: Path,
    filters: dict,
    group_by: list[str],
) -> dict:
    if group_by == ["opening_family"]:
        return _opening_usage_grouped(tools, warehouse, semantic)
    family = filters["family"]
    numerator = _as_int(
        _one(
            warehouse,
            semantic,
            ["known_opening_games"],
            where=[_equals("game__opening_family", family)],
        )["known_opening_games"]
    )
    totals = _one(warehouse, semantic, ["known_opening_games", "unknown_opening_games"])
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


def _opening_usage_grouped(tools: _SnapshotTools, warehouse: Path, semantic: Path) -> dict:
    grouped = query_rows(
        warehouse,
        semantic,
        ["known_opening_games"],
        where=[_GROUPED_FAMILY_WHERE],
        group_by=["game__opening_family"],
        limit=501,
    )
    denominator = _as_int(_one(warehouse, semantic, ["known_opening_games"])["known_opening_games"])
    counted = sorted(
        (
            (str(row["game__opening_family"]), _as_int(row["known_opening_games"]))
            for row in grouped
            if row.get("game__opening_family") not in {None, ""}
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
    tools: _SnapshotTools, warehouse: Path, semantic: Path, filters: dict
) -> dict:
    family = filters["family"]
    row = _one(
        warehouse,
        semantic,
        [
            "opening_wins",
            "opening_draws",
            "opening_losses",
            "opening_score_games",
            "opening_score_total",
            "opening_player_score",
            "win_rate",
        ],
        where=[
            _equals("player_game__color", filters["color"]),
            _equals("player_game__opening_family", family),
            _compare("player_game__base_seconds", "=", filters["base_seconds"]),
            _compare("player_game__increment_seconds", "=", filters["increment_seconds"]),
            _compare("player_game__rating", ">=", filters["rating_min"]),
            _compare("player_game__rating", "<", filters["rating_max_exclusive"]),
        ],
    )
    total = _as_int(row["opening_score_games"])
    score_rate = _optional_float(row["opening_player_score"])
    win_rate = _optional_float(row["win_rate"])
    if total == 0:
        score_rate = None
        win_rate = None
    elif score_rate is None or win_rate is None:
        raise RuntimeError("score ratio missing")
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
        "wins": _as_int(row["opening_wins"]),
        "draws": _as_int(row["opening_draws"]),
        "losses": _as_int(row["opening_losses"]),
        "eligible_player_games": total,
        "win_rate": win_rate,
        "score_rate": score_rate,
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
    warehouse: Path,
    semantic: Path,
    metrics: list[str],
    where: list[str] | None = None,
) -> dict[str, object]:
    rows = query_rows(warehouse, semantic, metrics, where=where)
    if len(rows) != 1:
        raise RuntimeError("semantic query returned an unexpected row count")
    return rows[0]


def query_rows(
    warehouse: Path,
    semantic_manifest: Path,
    metrics: list[str],
    *,
    where: list[str] | None = None,
    group_by: list[str] | None = None,
    limit: int | None = None,
) -> list[dict[str, object]]:
    """Compile one MetricFlow query and run it against a read-only warehouse."""
    sql = _compile_sql(semantic_manifest, metrics, where=where, group_by=group_by, limit=limit)
    with duckdb.connect(str(warehouse), read_only=True) as connection:
        cursor = connection.execute(sql)
        names = [str(item[0]) for item in cursor.description]
        return [
            {name: value for name, value in zip(names, row, strict=True)}
            for row in cursor.fetchall()
        ]


def _compile_sql(
    semantic_manifest: Path,
    metrics: list[str],
    *,
    where: list[str] | None = None,
    group_by: list[str] | None = None,
    limit: int | None = None,
) -> str:
    from chess_analytics.analyst.metricflow_imports import query_request

    order = None
    if group_by:
        order = [f"-{metrics[0]}", *group_by]
    request = query_request().create(
        metric_names=metrics,
        group_by_names=group_by,
        where_constraints=where,
        limit=limit,
        order_by_names=order,
    )
    explained = _engine(semantic_manifest).explain(mf_request=request)
    return explained.sql_statement.without_descriptions.sql


def _engine(semantic_manifest: Path):
    key = digest(semantic_manifest)
    cached = _ENGINES.get(key)
    if cached is not None:
        return cached
    from chess_analytics.analyst.metricflow_imports import (
        manifest_lookup,
        metricflow_engine,
        parse_dbt_manifest,
    )

    parsed = parse_dbt_manifest()(semantic_manifest.read_text())
    engine = metricflow_engine()(
        semantic_manifest_lookup=manifest_lookup()(parsed),
        sql_client=cast(Any, _DuckDbExplainClient()),
    )
    _ENGINES[key] = engine
    return engine


class _DuckDbExplainClient:
    """Renderer-only client. explain() must not open the mart."""

    def __init__(self) -> None:
        from chess_analytics.analyst.metricflow_imports import duckdb_renderer, sql_engine

        self.sql_engine_type = sql_engine().DUCKDB
        self.sql_plan_renderer = duckdb_renderer()()

    def query(self, stmt: str, sql_bind_parameter_set: object = None) -> object:
        raise RuntimeError("semantic explain must not query")

    def execute(self, stmt: str, sql_bind_parameter_set: object = None) -> None:
        raise RuntimeError("semantic explain must not execute")

    def dry_run(self, stmt: str, sql_bind_parameter_set: object = None) -> None:
        return None

    def close(self) -> None:
        return None

    def render_bind_parameter_key(self, bind_parameter_key: str) -> str:
        return "?"


def validate_configs(path: Path) -> list[str]:
    """Return blocking semantic-manifest errors. This is the in-process validate-configs check."""
    from chess_analytics.analyst.metricflow_imports import manifest_validator, parse_dbt_manifest

    parsed = parse_dbt_manifest()(path.read_text())
    result = manifest_validator()().validate_semantic_manifest(
        cast(Any, parsed), multi_process=False
    )
    return [issue.message for issue in (*result.errors, *result.future_errors)]


def smoke_draw_rate(warehouse: Path, semantic_manifest: Path) -> None:
    """Read-only tiny-mart check. Exits nonzero when the rate or the digest changes."""
    before = digest(warehouse)
    rows = query_rows(
        warehouse, semantic_manifest, ["drawn_games", "eligible_games", "game_draw_rate"]
    )
    if digest(warehouse) != before or len(rows) != 1:
        raise RuntimeError("semantic smoke check failed")
    row = rows[0]
    observed = (
        _as_int(row["drawn_games"]),
        _as_int(row["eligible_games"]),
        _optional_float(row["game_draw_rate"]),
    )
    if observed != (4, 20, 0.2):
        raise RuntimeError("semantic smoke check failed")


def _as_int(value: object) -> int:
    if value is None or value in {"", "None", "null", "nan", "NaN"}:
        return 0
    number = float(value)  # type: ignore[arg-type]
    if not number.is_integer():
        raise RuntimeError("expected an integer metric value")
    return int(number)


def _optional_float(value: object) -> float | None:
    if value is None or value in {"", "None", "null", "nan", "NaN"}:
        return None
    number = float(value)  # type: ignore[arg-type]
    if number != number:
        return None
    return number


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        if args and args[0] == "validate-configs" and len(args) in {1, 2}:
            manifest = Path(args[1] if len(args) == 2 else "dbt/target/semantic_manifest.json")
            messages = validate_configs(manifest)
            if messages:
                print(f"semantic validation failed ({len(messages)})", file=sys.stderr)
                return 1
            print("ERRORS: 0")
            return 0
        if len(args) == 3 and args[0] == "smoke-draw-rate":
            smoke_draw_rate(Path(args[1]), Path(args[2]))
            print("4,20,0.2")
            return 0
    except (OSError, RuntimeError, ValueError, ImportError):
        print("semantic command failed", file=sys.stderr)
        return 1
    print("usage: validate-configs | smoke-draw-rate WAREHOUSE MANIFEST", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
