"""Read the committed public aggregate extract.

The hosted dashboard cannot run dbt or open the analytical warehouse.
It loads this JSON file with the standard library. ``connect`` registers
the same rows in an in-memory DuckDB database. Nothing here reads
credentials, downloads data, or labels a metric.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from chess_analytics.common import hash_json

EXTRACT_VERSION = "2"
EXTRACT_FILENAME = "dashboard_extract.json"
TABLES = (
    "lineage_stage",
    "opening_family_share",
    "opening_score_cell",
    "opening_color_score",
    "clock_bucket",
    "clock_stratum",
    "clock_pressure_band",
    "transposition_view",
    "transposition_compression",
    "transposition_coverage",
    "transposition_scope",
    "transposition_limitation",
    "live_eval_run",
    "live_eval_category",
    "live_eval_case",
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
METRICFLOW_METRICS = frozenset({"game_draw_rate", "opening_usage", "opening_player_score"})
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
_BUCKETS = frozenset({"under_10", "10_to_29", "30_to_59", "60_plus"})
_PHASES = frozenset({"early_ply", "middle_ply", "late_ply"})
_RATING_BANDS = frozenset({"under_1200", "1200_1599", "1600_1999", "2000_plus"})
_LINEAGES = frozenset({"opening_corpus", "m3_august_prefix"})
_COHORTS = frozenset({"elite_reference", "rated_public"})
_POPULATIONS = frozenset(
    {
        "accepted",
        "eligible_games",
        "excluded",
        "known_opening_games",
        "marked_bots",
        "seen",
        "training_games",
        "training_source_games",
        "unknown_results",
    }
)
_SOURCE_REPORTS = frozenset(
    {
        "M3-analytical-manifest.json",
        "M3-independent-reference.json",
        "M3-source-manifest.json",
        "M4-figures.json",
        "opening-corpus.json",
        "opening-positions-checkpoint.json",
        "opening-positions-dashboard.json",
    }
)
_METRICS = frozenset(
    {
        "clock_pressure_by_band",
        "clock_pressure_error_proxy",
        "game_draw_rate",
        "known_opening_games",
        "live_eval_pass_rate",
        "m3_august_prefix_accepted",
        "opening_adjusted_score",
        "opening_adjusted_score_bootstrap",
        "opening_color_score",
        "opening_corpus_training_games",
        "opening_player_score",
        "opening_usage",
        "transposition_visits",
    }
)
_SCORE_METRICS = frozenset(
    {
        "opening_adjusted_score",
        "opening_adjusted_score_bootstrap",
        "opening_player_score",
    }
)
_COLORS = frozenset({"white", "black"})
_FAMILY_EXTRA = set(" ',.-")
_PERIOD = re.compile(r"^\d{4}-\d{2}$")
_TIME_CONTROL = re.compile(r"^\d+\+\d+$")
_HEX_24 = re.compile(r"^[0-9a-f]{24}$")
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_CASE_ID = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_VIEW_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 '.\-]{0,79}$")
_LIVE_RECEIPT = re.compile(r"^live-eval-receipt-(?:\d+|[a-z0-9.]+(?:-[a-z0-9.]+)*-r\d+-\d+)\.json$")
_MODELS = frozenset({"gpt-6-luna", "gpt-6-sol", "grok-4.7"})
_EFFORTS = frozenset({"none", "low", "medium", "high", "xhigh"})
_CATEGORIES = frozenset(
    {
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
    }
)
_SEVERITIES = frozenset({"high", "normal"})
_COVERAGE_MODES = frozenset({"recurring", "transposing"})


def extract_path(project: Path | None = None) -> Path:
    """Path to the committed extract. An explicit project wins over the environment.

    A non-editable install does not contain ``data/``. Resolution is
    ``CHESSLAB_PUBLIC_EXTRACT`` when that path is a file, then the working
    directory, then a repository root found from the working directory.
    The installed package location is not used.
    """
    if project is not None:
        return Path(project) / "data" / "public" / EXTRACT_FILENAME
    for candidate in _extract_candidates():
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        "public extract not found; set CHESSLAB_PUBLIC_EXTRACT to the extract file"
    )


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
    _reject_metricflow_on_closed_metrics(tables["metric_receipt"])
    _check_build_record(payload)
    if identifier_issues(payload):
        raise ValueError("public extract failed the identifier check")
    return payload


def table_rows(extract: dict, name: str) -> list[dict]:
    if name not in TABLES:
        raise ValueError("unknown public extract table")
    return extract["tables"][name]


def identifier_issues(extract: dict) -> list[str]:
    """Column names, leaky strings, and categorical values outside the allowlists."""
    issues: list[str] = []
    for name in TABLES:
        rows = table_rows(extract, name)
        for column in rows[0]:
            lowered = column.lower()
            if any(part in lowered for part in FORBIDDEN_COLUMN_PARTS):
                issues.append(f"column {name}.{column}")
        for index, row in enumerate(rows):
            for column, value in row.items():
                leaked = isinstance(value, str) and _leaky_text(value)
                if leaked or not _allowed_value(name, column, row, value):
                    issues.append(f"value {name}[{index}].{column}")
    return issues


def connect(extract: dict):
    """Register each extract table in a new in-memory DuckDB connection."""
    import duckdb

    connection = duckdb.connect(":memory:")
    for name in TABLES:
        _register(connection, name, table_rows(extract, name))
    return connection


def _extract_candidates():
    override = os.environ.get("CHESSLAB_PUBLIC_EXTRACT")
    if override:
        yield Path(override)
    yield Path.cwd() / "data" / "public" / EXTRACT_FILENAME
    root = _repository_root(Path.cwd())
    if root is not None:
        yield root / "data" / "public" / EXTRACT_FILENAME


def _repository_root(start: Path) -> Path | None:
    for directory in (start, *start.parents):
        project = directory / "pyproject.toml"
        package = directory / "src" / "chess_analytics"
        if project.is_file() and package.is_dir():
            return directory
    return None


def _reject_metricflow_on_closed_metrics(rows: list[dict]) -> None:
    for row in rows:
        if row.get("query_origin") != "metricflow":
            continue
        metric = row.get("metric")
        if metric in NEVER_METRICFLOW:
            raise ValueError("clock and adjusted-score receipts cannot be metricflow")
        if metric not in METRICFLOW_METRICS:
            raise ValueError("metricflow is only allowed for governed metrics")


def derived_mart_id(snapshot_id: str, model_sha256: str, lock_sha256: str) -> str:
    """First 24 hex characters of the same hash ``mart_id`` uses."""
    return hash_json(
        {
            "snapshot_id": snapshot_id,
            "model_sha256": model_sha256,
            "lock_sha256": lock_sha256,
        }
    )[:24]


def _check_build_record(payload: dict) -> None:
    rows = payload["tables"]["metric_receipt"]
    metricflow = [row for row in rows if row.get("query_origin") == "metricflow"]
    build = payload.get("build")
    if not metricflow:
        if build is not None:
            raise ValueError("public extract build record requires a metricflow receipt")
        return
    if not isinstance(build, dict):
        raise ValueError("metricflow receipts require a build record")
    expected = {
        "lock_sha256",
        "model_sha256",
        "semantic_manifest_sha256",
        "source_snapshot_id",
    }
    if set(build) != expected:
        raise ValueError("public extract build record keys do not match")
    snapshot = build["source_snapshot_id"]
    model = build["model_sha256"]
    lock = build["lock_sha256"]
    semantic = build["semantic_manifest_sha256"]
    if not isinstance(snapshot, str) or _HEX_24.fullmatch(snapshot) is None:
        raise ValueError("public extract build snapshot is not 24 hex characters")
    for value in (model, lock, semantic):
        if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
            raise ValueError("public extract build hash is not 64 hex characters")
    derived = derived_mart_id(snapshot, model, lock)
    for row in payload["tables"]["metric_receipt"]:
        if row.get("query_origin") != "metricflow":
            continue
        if (
            row.get("mart_id") != derived
            or row.get("model_sha256") != model
            or row.get("semantic_manifest_sha256") != semantic
        ):
            raise ValueError("public extract mart_id does not match the build record")


def _allowed_value(table: str, column: str, row: dict, value: object) -> bool:
    if table == "lineage_stage" and column == "note":
        return isinstance(value, str)
    if table == "transposition_scope" and column == "scope":
        return isinstance(value, str) and bool(value.strip())
    if table == "transposition_limitation" and column == "text":
        return isinstance(value, str) and bool(value.strip())
    rule = _COLUMN_RULES.get(column)
    if rule is None:
        return not isinstance(value, str)
    return rule(row, value)


def _one_of(allowed: frozenset[str]):
    def check(_row: dict, value: object) -> bool:
        return isinstance(value, str) and value in allowed

    return check


def _optional_one_of(allowed: frozenset[str]):
    def check(_row: dict, value: object) -> bool:
        return value is None or (isinstance(value, str) and value in allowed)

    return check


def _hex(pattern: re.Pattern[str], *, optional: bool):
    def check(_row: dict, value: object) -> bool:
        if value is None:
            return optional
        return isinstance(value, str) and pattern.fullmatch(value) is not None

    return check


def _family_text(value: str) -> bool:
    if value == "?":
        return True
    if " " not in value or not 3 <= len(value) <= 80:
        return False
    return all(
        character.isalpha() or character.isdigit() or character in _FAMILY_EXTRA
        for character in value
    )


def _family(_row: dict, value: object) -> bool:
    return isinstance(value, str) and _family_text(value)


def _period(_row: dict, value: object) -> bool:
    if value is None:
        return True
    return isinstance(value, str) and _PERIOD.fullmatch(value) is not None


def _rolls_up(_row: dict, value: object) -> bool:
    return value is None or value == "opening_corpus:training_games"


def _time_control(_row: dict, value: object) -> bool:
    return isinstance(value, str) and _TIME_CONTROL.fullmatch(value) is not None


def _stage_id(row: dict, value: object) -> bool:
    if not isinstance(value, str):
        return False
    lineage = row.get("lineage")
    population = row.get("population")
    if population == "training_source_games":
        return value == f"{lineage}:{row.get('period')}:{row.get('cohort')}"
    return value == f"{lineage}:{population}"


def _receipt_id(row: dict, value: object) -> bool:
    metric = row.get("metric")
    subject = row.get("subject")
    if not isinstance(metric, str) or not isinstance(value, str):
        return False
    if subject is None:
        return value == metric
    return isinstance(subject, str) and value == f"{metric}:{subject}"


def _color_subject(value: object) -> bool:
    if not isinstance(value, str) or " " not in value:
        return False
    family, color = value.rsplit(" ", 1)
    return color in _COLORS and _family_text(family)


def _eval_subject(value: object) -> bool:
    if not isinstance(value, str) or " " not in value:
        return False
    model, effort = value.rsplit(" ", 1)
    return model in _MODELS and effort in _EFFORTS


def _subject(row: dict, value: object) -> bool:
    metric = row.get("metric")
    if metric in _SCORE_METRICS:
        return isinstance(value, str) and _family_text(value)
    if metric == "opening_color_score":
        return _color_subject(value)
    if metric == "live_eval_pass_rate":
        return _eval_subject(value)
    if metric == "clock_pressure_error_proxy":
        return isinstance(value, str) and value in _BUCKETS
    return value is None


def _source_report(_row: dict, value: object) -> bool:
    return isinstance(value, str) and (
        value in _SOURCE_REPORTS or _LIVE_RECEIPT.fullmatch(value) is not None
    )


def _optional_source(_row: dict, value: object) -> bool:
    return value is None or _source_report(_row, value)


def _view_name(_row: dict, value: object) -> bool:
    return isinstance(value, str) and _VIEW_NAME.fullmatch(value) is not None


def _case_id(_row: dict, value: object) -> bool:
    return isinstance(value, str) and _CASE_ID.fullmatch(value) is not None


_COLUMN_RULES = {
    "analytical_id": _hex(_HEX_24, optional=False),
    "bucket": _one_of(_BUCKETS),
    "case_id": _case_id,
    "category": _one_of(_CATEGORIES),
    "cohort": _optional_one_of(_COHORTS),
    "color": _one_of(_COLORS),
    "effort": _one_of(_EFFORTS),
    "family": _family,
    "interval_source_report": _optional_source,
    "lineage": _one_of(_LINEAGES),
    "mart_id": _hex(_HEX_24, optional=True),
    "metric": _one_of(_METRICS),
    "mode": _one_of(_COVERAGE_MODES),
    "model": _one_of(_MODELS),
    "model_sha256": _hex(_HEX_64, optional=True),
    "period": _period,
    "phase": _one_of(_PHASES),
    "population": _one_of(_POPULATIONS),
    "positions_sha256": _hex(_HEX_64, optional=False),
    "query_origin": _one_of(QUERY_ORIGINS),
    "rating_band": _one_of(_RATING_BANDS),
    "receipt_id": _receipt_id,
    "rolls_up_to": _rolls_up,
    "semantic_manifest_sha256": _hex(_HEX_64, optional=True),
    "severity": _one_of(_SEVERITIES),
    "source_report": _source_report,
    "stage_id": _stage_id,
    "subject": _subject,
    "time_control": _time_control,
    "unit": _one_of(frozenset({"games"})),
    "view": _view_name,
}


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
