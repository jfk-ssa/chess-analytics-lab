"""Read the committed public aggregate extract.

The hosted dashboard cannot run dbt or open the analytical warehouse.
It loads this JSON file with the standard library. ``connect`` registers
the same rows in an in-memory DuckDB database. Nothing here reads
credentials, downloads data, or labels a metric.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

EXTRACT_VERSION = "1"
EXTRACT_FILENAME = "dashboard_extract.json"
TABLES = (
    "lineage_stage",
    "opening_family_share",
    "opening_score_cell",
    "clock_bucket",
    "clock_stratum",
    "metric_receipt",
)
QUERY_ORIGINS = frozenset({"metricflow", "reviewed_sql", "committed_report"})
# fact_move is not a dbt model. Adjusted score and its bootstrap sit outside
# MetricFlow. Those receipts must not be labeled metricflow.
NEVER_METRICFLOW = frozenset(
    {
        "clock_pressure_error_proxy",
        "opening_adjusted_score",
        "opening_adjusted_score_bootstrap",
    }
)
# GitHub rejects files over 100 MiB. The analytical warehouse is larger than
# that. This budget keeps the committed aggregate file small.
SIZE_BUDGET_BYTES = 262_144
FORBIDDEN_COLUMN_PARTS = (
    "player_key",
    "game_id",
    "headers_json",
    "fingerprint",
    "username",
    "absolute_path",
    "source_file",
)
_COLUMN_NAME = set("abcdefghijklmnopqrstuvwxyz0123456789_")


def extract_path(project: Path | None = None) -> Path:
    """Path to the committed extract. An explicit project wins over the environment.

    A non-editable install does not contain ``data/``. The current working
    directory is checked before the source-tree fallback so a hosted app
    started from the repository root still finds the file.
    """
    if project is not None:
        return Path(project) / "data" / "public" / EXTRACT_FILENAME
    override = os.environ.get("CHESSLAB_PUBLIC_EXTRACT")
    if override:
        return Path(override)
    candidate = Path.cwd() / "data" / "public" / EXTRACT_FILENAME
    if candidate.is_file():
        return candidate
    return Path(__file__).resolve().parents[2] / "data" / "public" / EXTRACT_FILENAME


def load_extract(path: Path | None = None) -> dict:
    """Load and check the extract shape. Does not open DuckDB."""
    source = Path(path) if path is not None else extract_path()
    payload = json.loads(source.read_text())
    if payload.get("extract_version") != EXTRACT_VERSION:
        raise ValueError("unsupported public extract version")
    tables = payload.get("tables")
    if not isinstance(tables, dict) or set(tables) != set(TABLES):
        raise ValueError("public extract tables do not match the reader")
    for name in TABLES:
        rows = tables[name]
        if not isinstance(rows, list) or not rows or any(not isinstance(row, dict) for row in rows):
            raise ValueError(f"public extract table is empty: {name}")
        keys = tuple(rows[0])
        if any(tuple(row) != keys for row in rows):
            raise ValueError(f"public extract rows differ: {name}")
        for column in keys:
            if not column or any(character not in _COLUMN_NAME for character in column):
                raise ValueError(f"public extract column name is not lowercase: {name}.{column}")
    if identifier_issues(payload):
        raise ValueError("public extract failed the identifier check")
    return payload


def table_rows(extract: dict, name: str) -> list[dict]:
    if name not in TABLES:
        raise ValueError("unknown public extract table")
    return extract["tables"][name]


def identifier_issues(extract: dict) -> list[str]:
    """Column names and string values that would leak a player, game, or path."""
    issues: list[str] = []
    for name in TABLES:
        rows = table_rows(extract, name)
        for column in rows[0]:
            lowered = column.lower()
            if any(part in lowered for part in FORBIDDEN_COLUMN_PARTS):
                issues.append(f"column {name}.{column}")
        for index, row in enumerate(rows):
            for column, value in row.items():
                if isinstance(value, str) and _leaky_text(value):
                    issues.append(f"value {name}[{index}].{column}")
    return issues


def connect(extract: dict):
    """Register each extract table in a new in-memory DuckDB connection."""
    import duckdb

    connection = duckdb.connect(":memory:")
    for name in TABLES:
        _register(connection, name, table_rows(extract, name))
    return connection


def _leaky_text(value: str) -> bool:
    lowered = value.lower()
    if any(
        part in lowered
        for part in ("player_key", "headers_json", "fingerprint", "username", "game_id")
    ):
        return True
    if "/" in value or "\\" in value or "@" in value or "://" in value:
        return True
    return ".pgn" in lowered or value.startswith("~")


def _register(connection, name: str, rows: list[dict]) -> None:
    columns = list(rows[0])
    definitions = ", ".join(f'"{column}" {_sql_type(rows, column)}' for column in columns)
    connection.execute(f'create table "{name}" ({definitions})')
    placeholders = ", ".join("?" for _ in columns)
    connection.executemany(
        f'insert into "{name}" values ({placeholders})',
        [tuple(row[column] for column in columns) for row in rows],
    )


def _sql_type(rows: list[dict], column: str) -> str:
    kinds = {type(row[column]) for row in rows if row[column] is not None}
    if not kinds or kinds <= {str}:
        return "varchar"
    if kinds == {bool}:
        return "boolean"
    if kinds <= {int}:
        return "bigint"
    if kinds <= {int, float}:
        return "double"
    raise ValueError(f"mixed public extract column: {column}")
