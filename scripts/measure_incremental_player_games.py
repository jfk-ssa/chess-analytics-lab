"""Measure a from-scratch player_games rebuild against an incremental delta.

The facts are a deterministic stand-in for the published snapshot tables.
They reuse the column names and types in contracts/tables.json. They are not
a sample of the Lichess corpus, and they do not measure that distribution.

The published dbt project is not modified. Each run copies dbt/ into a
scratch directory and rewrites only the scratch player_games model.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import platform
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from functools import partial
from importlib.metadata import version
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
JOIN_ANCHOR = "    inner join {{ ref('int_game_eligibility') }} as g using (\"game_key\")\n)"
OPENING_SCORE_SQL = (
    'select sum("eligible_score"), sum("score_eligible"), sum("eligible_win") from player_games'
)
PLAYER_GAMES = "model.chess_analytics.player_games"
CONTENT_SHA256_METHOD = (
    "sha256 of repr(column names) plus repr of 8000-row chunks. "
    "Each column is cast to varchar in DuckDB before fetch."
)
QUERY_CONNECTION = (
    "read_only, DuckDB default memory_limit, one connection reused for every "
    "repeat, so the samples are warm buffer-pool times. Same default memory "
    "as the analyst. Not an adoption metric."
)


def log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def profile_settings() -> dict[str, str]:
    text = (ROOT / "dbt/profiles.yml").read_text()
    memory = "memory_limit: 256MB"
    spill = "max_temp_directory_size: 512MB"
    if memory not in text or spill not in text or "threads: 1" not in text:
        raise SystemExit("dbt/profiles.yml no longer matches the measured settings")
    return {
        "threads": "1",
        "memory_limit": "256MB",
        "max_temp_directory_size": "512MB",
    }


def apply_profile(connection: duckdb.DuckDBPyConnection) -> None:
    settings = profile_settings()
    connection.execute(f"set memory_limit = '{settings['memory_limit']}'")
    connection.execute(f"set max_temp_directory_size = '{settings['max_temp_directory_size']}'")


def remove_database(path: Path) -> None:
    for candidate in (path, Path(str(path) + ".wal")):
        if candidate.exists():
            candidate.unlink()


def create_schema(connection: duckdb.DuckDBPyConnection) -> None:
    schema = json.loads((ROOT / "contracts/tables.json").read_text())
    for table, columns in schema.items():
        if not isinstance(columns, dict):
            continue
        definitions = ", ".join(f'"{name}" {kind}' for name, kind in columns.items())
        connection.execute(f'create table "{table}" ({definitions})')


def seed_games(connection: duckdb.DuckDBPyConnection, start: int, count: int) -> None:
    """Insert games whose source ordinals are start+1 .. start+count."""
    if count < 1:
        raise ValueError("count must be positive")
    connection.execute(
        """
        insert into fact_game (
            "provider", "game_id", "source_ordinal", "result", "rated", "variant",
            "utc_date", "played_at", "timestamp_precision", "time_control",
            "base_seconds", "increment_seconds", "source_opening", "source_eco",
            "termination", "marked_bot", "ply_count", "headers_json", "record_fingerprint"
        )
        select
            'lichess',
            printf('%08x', i),
            i + 1,
            case i % 5
                when 0 then '1-0'
                when 1 then '0-1'
                when 2 then '1/2-1/2'
                when 3 then '*'
                else '1-0'
            end,
            true,
            'Standard',
            date '2013-01-01' + (i % 400) * interval 1 day,
            timestamptz '2013-01-01 12:00:00+00' + (i % 400) * interval 1 day,
            'second',
            case i % 3 when 0 then '300+0' when 1 then '600+2' else '180+0' end,
            case i % 3 when 0 then 300 when 1 then 600 else 180 end::bigint,
            case i % 3 when 1 then 2 else 0 end::bigint,
            case i % 5
                when 0 then 'Sicilian Defense: Najdorf'
                when 1 then 'French Defense: Advance Variation'
                when 2 then null
                when 3 then 'King''s Pawn Game'
                else 'Caro-Kann Defense: Classical'
            end,
            case when i % 11 = 0 then 'B90' else null end,
            'Normal',
            (i % 1000) = 0,
            (30 + (i % 50))::bigint,
            '{}',
            printf('fp-%08x', i)
        from range(?, ?) as t(i)
        """,
        [start, start + count],
    )
    connection.execute(
        """
        insert into fact_player_game (
            "provider", "game_id", "color", "player_key", "rating",
            "opponent_rating", "score"
        )
        select
            g."provider",
            g."game_id",
            c.color,
            'lichess:p' || printf(
                '%05d',
                case
                    when c.color = 'white' then g."source_ordinal" % 4000
                    else (g."source_ordinal" + 17) % 4000
                end
            ),
            case
                when c.color = 'white' then 1200 + (g."source_ordinal" % 800)
                else 1200 + ((g."source_ordinal" * 3) % 800)
            end::bigint,
            case
                when c.color = 'white' then 1200 + ((g."source_ordinal" * 3) % 800)
                else 1200 + (g."source_ordinal" % 800)
            end::bigint,
            case
                when g."result" = '*' then null
                when g."result" = '1/2-1/2' then 0.5
                when (g."result" = '1-0' and c.color = 'white')
                    or (g."result" = '0-1' and c.color = 'black') then 1.0
                else 0.0
            end
        from fact_game as g
        cross join (select unnest(['white', 'black']) as color) as c
        where g."source_ordinal" > ? and g."source_ordinal" <= ?
        """,
        [start, start + count],
    )


def _connect(path: Path) -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect(str(path))
    apply_profile(connection)
    return connection


def make_warehouse(path: Path, start: int, count: int) -> None:
    remove_database(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = _connect(path)
    try:
        create_schema(connection)
        seed_games(connection, start, count)
        connection.execute("checkpoint")
    finally:
        connection.close()


def append_games(path: Path, start: int, count: int) -> None:
    connection = _connect(path)
    try:
        seed_games(connection, start, count)
        connection.execute("checkpoint")
    finally:
        connection.close()


def content_sha256(path: Path, relation: str, order_by: str) -> tuple[str, int]:
    """Hash ordered rows as varchar so timestamptz does not need pytz."""
    digest = hashlib.sha256()
    seen = 0
    with duckdb.connect(str(path), read_only=True) as connection:
        described = connection.execute(f'describe "{relation}"').fetchall()
        columns = [row[0] for row in described]
        projection = ", ".join(f'cast("{name}" as varchar)' for name in columns)
        cursor = connection.execute(f'select {projection} from "{relation}" order by "{order_by}"')
        digest.update(repr(columns).encode())
        while True:
            rows = cursor.fetchmany(8000)
            if not rows:
                break
            digest.update(repr(rows).encode())
            seen += len(rows)
    return digest.hexdigest(), seen


def published_sql() -> str:
    return (ROOT / "dbt/models/marts/player_games.sql").read_text()


def _replace_config(sql: str, config: str) -> str:
    start = sql.index("{{ config(")
    end = sql.index("}}", start) + 2
    return sql[:start] + config + sql[end:]


def _inject_where(sql: str, predicate: str) -> str:
    if JOIN_ANCHOR not in sql:
        raise RuntimeError("player_games.sql join anchor was not found")
    where = "{% if is_incremental() %}\n" + predicate + "\n    {% endif %}"
    replacement = (
        "    inner join {{ ref('int_game_eligibility') }} as g using (\"game_key\")\n"
        + where
        + "\n)"
    )
    return sql.replace(JOIN_ANCHOR, replacement, 1)


def _new_games(games: int, ratio: float) -> int:
    return max(1, round(games * ratio))


def player_games_sql(kind: str, *, replay_after: int | None = None) -> str:
    """Return scratch player_games SQL for one measurement kind."""
    original = published_sql()
    if kind == "view":
        return original
    if kind == "table":
        return _replace_config(original, "{{ config(materialized='table') }}")
    if kind == "microbatch":
        # One batch. A begin date in 2013 would backfill every day through today.
        begin = datetime.now(UTC).date().isoformat()
        config = "\n".join(
            [
                "{{ config(",
                "    materialized='incremental',",
                "    incremental_strategy='microbatch',",
                "    unique_key='player_game_key',",
                "    event_time='utc_date',",
                f"    begin='{begin}',",
                "    batch_size='day',",
                "    on_schema_change='fail'",
                ") }}",
            ]
        )
        return _replace_config(original, config)
    unique_key = kind != "replay_without_key"
    strategy = "append" if kind == "append" else "merge" if kind == "merge" else "delete+insert"
    config_lines = [
        "{{ config(",
        "    materialized='incremental',",
        f"    incremental_strategy='{strategy}',",
    ]
    if unique_key:
        config_lines.append("    unique_key='player_game_key',")
    config_lines.extend(["    on_schema_change='fail'", ") }}"])
    configured = _replace_config(original, "\n".join(config_lines))
    if kind == "ordinal":
        predicate = '    where g."source_ordinal" > {{ var("loaded_through") }}'
    elif kind == "broken_filter":
        predicate = (
            '    where p."player_game_key" in (\n'
            '        select "player_game_key" from {{ this }}\n'
            "    )"
        )
    elif kind in {"replay", "replay_without_key"}:
        if replay_after is None:
            raise ValueError("replay SQL needs replay_after")
        predicate = f'    where g."source_ordinal" > {replay_after}'
    elif kind in {"anti_join", "append", "merge", "delete+insert"}:
        predicate = (
            '    where p."player_game_key" not in (\n'
            '        select "player_game_key" from {{ this }}\n'
            "    )"
        )
    else:
        raise ValueError(f"unknown player_games kind: {kind}")
    return _inject_where(configured, predicate)


def copy_project(dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(
        ROOT / "dbt",
        dest,
        ignore=shutil.ignore_patterns("target", "logs", "dbt_packages"),
    )


def set_player_games(project: Path, sql: str) -> None:
    (project / "models/marts/player_games.sql").write_text(sql)


def dbt_executable() -> Path:
    return Path(sys.executable).with_name("dbt")


_DBT_RUNNER = None


def _release_duckdb_environment() -> None:
    """Close the adapter's file so the next build, or a hash, can reopen it."""
    from dbt.adapters.duckdb.connections import DuckDBConnectionManager

    environment = DuckDBConnectionManager._ENV
    if environment is not None:
        environment.close()
        DuckDBConnectionManager._ENV = None


def _dbt_build_in_process(
    command: list[str],
    warehouse: Path,
    project: Path,
    expect_failure: bool,
) -> dict[str, object]:
    """One interpreter for the repeated equivalence builds.

    Each subprocess paid about three seconds of startup. The builds stay
    sequential and use the same flags, including ``--no-partial-parse``.
    The connection is closed before the caller opens the warehouse.
    """
    global _DBT_RUNNER
    from dbt.cli.main import dbtRunner

    keys = (
        "CHESSLAB_DBT_PATH",
        "DBT_PROFILES_DIR",
        "DBT_SEND_ANONYMOUS_USAGE_STATS",
        "DO_NOT_TRACK",
    )
    saved = {key: os.environ.get(key) for key in keys}
    os.environ["CHESSLAB_DBT_PATH"] = str(warehouse)
    os.environ["DBT_PROFILES_DIR"] = str(project)
    os.environ["DBT_SEND_ANONYMOUS_USAGE_STATS"] = "false"
    os.environ["DO_NOT_TRACK"] = "1"
    stdout, stderr = io.StringIO(), io.StringIO()
    started = time.perf_counter()
    try:
        if _DBT_RUNNER is None:
            _DBT_RUNNER = dbtRunner()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            # command[0] is the dbt executable. dbtRunner wants the subcommand.
            result = _DBT_RUNNER.invoke([*command[1:], "--quiet"])
    finally:
        _release_duckdb_environment()
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    failed = not bool(result.success)
    if failed != expect_failure:
        detail = f"{stdout.getvalue()}\n{stderr.getvalue()}\n{result.exception}"
        raise RuntimeError(detail[-4000:])
    return {
        "wall_seconds": time.perf_counter() - started,
        "returncode": 1 if failed else 0,
        "stdout": stdout.getvalue(),
        "stderr": stderr.getvalue(),
        "results": None,
    }


def dbt_build(
    project: Path,
    warehouse: Path,
    select: str | None,
    target: Path,
    logs: Path,
    *,
    exclude_tests: bool = True,
    variables: dict[str, int] | None = None,
    expect_failure: bool = False,
    verb: str = "build",
    in_process: bool = False,
) -> dict[str, object]:
    env = os.environ.copy()
    env.update(
        CHESSLAB_DBT_PATH=str(warehouse),
        DBT_SEND_ANONYMOUS_USAGE_STATS="false",
        DO_NOT_TRACK="1",
        DBT_PROFILES_DIR=str(project),
    )
    command = [
        str(dbt_executable()),
        verb,
        "--project-dir",
        str(project),
        "--profiles-dir",
        str(project),
        "--target-path",
        str(target),
        "--log-path",
        str(logs),
        "--no-partial-parse",
        "--no-use-colors",
    ]
    if select is not None:
        command.extend(["--select", select])
    if exclude_tests:
        command.extend(["--exclude", "resource_type:test resource_type:unit_test"])
    if variables is not None:
        command.extend(["--vars", json.dumps(variables)])
    if in_process:
        return _dbt_build_in_process(command, warehouse, project, expect_failure)
    started = time.perf_counter()
    completed = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    wall = time.perf_counter() - started
    results_path = target / "run_results.json"
    payload = json.loads(results_path.read_text()) if results_path.is_file() else None
    failed = completed.returncode != 0
    if failed != expect_failure:
        tail = (completed.stdout + "\n" + completed.stderr)[-4000:]
        raise RuntimeError(tail)
    return {
        "wall_seconds": wall,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "results": payload,
    }


def execution_time(payload: dict, unique_id: str) -> float:
    for row in payload["results"]:
        if row["unique_id"] == unique_id:
            return float(row["execution_time"])
    raise RuntimeError(f"{unique_id} was not in run_results")


def summarize(samples: list[float]) -> dict[str, float | list[float]]:
    if not samples:
        raise ValueError("no samples")
    return {
        "median": statistics.median(samples),
        "min": min(samples),
        "max": max(samples),
        "spread": max(samples) - min(samples),
        "samples": samples,
    }


def copy_warehouse(source: Path, dest: Path) -> float:
    dest.parent.mkdir(parents=True, exist_ok=True)
    remove_database(dest)
    started = time.perf_counter()
    shutil.copy2(source, dest)
    return time.perf_counter() - started


def time_select(path: Path, sql: str, repeats: int) -> list[float]:
    """Repeat a query on one connection. Later samples are warm-cache times."""
    samples: list[float] = []
    with duckdb.connect(str(path), read_only=True) as connection:
        for _ in range(repeats):
            started = time.perf_counter()
            connection.execute(sql).fetchall()
            samples.append(time.perf_counter() - started)
    return samples


def compiled_batch_rows(warehouse: Path, target: Path) -> int:
    """Count rows the rendered incremental select would insert."""
    path = target / "compiled/chess_analytics/models/marts/player_games.sql"
    statement = path.read_text().strip().rstrip(";")
    with duckdb.connect(str(warehouse), read_only=True) as connection:
        row = connection.execute(f"select count(*) from ({statement})").fetchone()
    if row is None:
        raise RuntimeError("compiled player_games returned no count")
    return int(row[0])


def recorded_errors(node: object, path: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(node, dict):
        if "error" in node:
            found.append(path or "root")
        for key, value in node.items():
            if key == "error":
                continue
            child = f"{path}.{key}" if path else str(key)
            found.extend(recorded_errors(value, child))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            found.extend(recorded_errors(value, f"{path}[{index}]"))
    return found


def measurement_status(mismatches: list[str], scales: object) -> int:
    return 1 if mismatches or recorded_errors(scales) else 0


def node_map(payload: dict) -> dict[str, float]:
    return {row["unique_id"]: float(row["execution_time"]) for row in payload["results"]}


def fresh_dir(root: Path, name: str) -> Path:
    path = root / name
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)
    return path


def one_build(
    project: Path,
    template: Path,
    work: Path,
    label: str,
    select: str | None,
    *,
    exclude_tests: bool,
    variables: dict[str, int] | None = None,
) -> tuple[dict[str, object], Path]:
    directory = fresh_dir(work, label)
    warehouse = directory / "warehouse.duckdb"
    copy_warehouse(template, warehouse)
    result = dbt_build(
        project,
        warehouse,
        select,
        directory / "target",
        directory / "logs",
        exclude_tests=exclude_tests,
        variables=variables,
    )
    return result, warehouse


def repeated_model(
    project: Path,
    template: Path,
    work: Path,
    label: str,
    select: str,
    repeats: int,
    unique_id: str,
) -> dict[str, object]:
    walls: list[float] = []
    elapsed: list[float] = []
    execution: list[float] = []
    last = None
    for index in range(repeats):
        log(f"{label} {index + 1}/{repeats}")
        result, warehouse = one_build(
            project, template, work, f"{label}-{index}", select, exclude_tests=True
        )
        payload = result["results"]
        assert isinstance(payload, dict)
        walls.append(float(result["wall_seconds"]))
        elapsed.append(float(payload["elapsed_time"]))
        execution.append(execution_time(payload, unique_id))
        last = warehouse
        if index + 1 != repeats:
            shutil.rmtree(warehouse.parent)
    assert last is not None
    return {
        "wall_seconds": summarize(walls),
        "dbt_elapsed_seconds": summarize(elapsed),
        "execution_seconds": summarize(execution),
        "warehouse": last,
    }


def measure_incremental(
    project: Path,
    base_template: Path,
    work: Path,
    label: str,
    repeats: int,
    sql: str,
    new_start: int,
    new_count: int,
    *,
    variables_for: int | None = None,
) -> dict[str, object]:
    phases = ("initial", "delta", "rerun")
    store = {phase: {"wall": [], "elapsed": [], "execution": []} for phase in phases}
    last = None
    for index in range(repeats):
        log(f"{label} {index + 1}/{repeats}")
        set_player_games(project, sql)
        directory = fresh_dir(work, f"{label}-{index}")
        warehouse = directory / "warehouse.duckdb"
        copy_warehouse(base_template, warehouse)
        target = directory / "target"
        logs = directory / "logs"
        builds = []
        builds.append(
            (
                "initial",
                dbt_build(project, warehouse, "+player_games", target, logs, exclude_tests=True),
            )
        )
        append_games(warehouse, new_start, new_count)
        variables = None if variables_for is None else {"loaded_through": variables_for}
        builds.append(
            (
                "delta",
                dbt_build(
                    project,
                    warehouse,
                    "+player_games",
                    target,
                    logs,
                    exclude_tests=True,
                    variables=variables,
                ),
            )
        )
        builds.append(
            (
                "rerun",
                dbt_build(
                    project,
                    warehouse,
                    "+player_games",
                    target,
                    logs,
                    exclude_tests=True,
                    variables=variables,
                ),
            )
        )
        for phase, result in builds:
            payload = result["results"]
            assert isinstance(payload, dict)
            store[phase]["wall"].append(float(result["wall_seconds"]))
            store[phase]["elapsed"].append(float(payload["elapsed_time"]))
            store[phase]["execution"].append(execution_time(payload, PLAYER_GAMES))
        last = warehouse
        if index + 1 != repeats:
            shutil.rmtree(directory)
    assert last is not None
    return {
        phase: {
            "wall_seconds": summarize(values["wall"]),
            "dbt_elapsed_seconds": summarize(values["elapsed"]),
            "execution_seconds": summarize(values["execution"]),
        }
        for phase, values in store.items()
    } | {"warehouse": last}


def hash_player_games(path: Path) -> dict[str, object]:
    started = time.perf_counter()
    digest, rows = content_sha256(path, "player_games", "player_game_key")
    return {
        "sha256": digest,
        "rows": rows,
        "hash_seconds": time.perf_counter() - started,
    }


def microbatch_error(project: Path, work: Path) -> str:
    warehouse = work / "micro" / "warehouse.duckdb"
    make_warehouse(warehouse, 0, 20)
    set_player_games(project, player_games_sql("microbatch"))
    target = work / "micro-target"
    logs = work / "micro-logs"
    dbt_build(project, warehouse, "+player_games", target, logs, exclude_tests=True)
    failed = dbt_build(
        project,
        warehouse,
        "+player_games",
        target,
        logs,
        exclude_tests=True,
        expect_failure=True,
    )
    text = str(failed["stdout"]) + "\n" + str(failed["stderr"])
    for line in text.splitlines():
        stripped = line.strip()
        if "does not support 'unique_key'" in stripped:
            return stripped
    lines = [
        line
        for line in text.splitlines()
        if "microbatch" in line.lower() or "unique_key" in line or "Error" in line
    ]
    return "\n".join(lines[-12:]) or text[-1500:]


def machine_facts() -> dict[str, object]:
    page = os.sysconf("SC_PAGE_SIZE")
    pages = os.sysconf("SC_PHYS_PAGES")
    with duckdb.connect() as connection:
        threads = connection.execute("select current_setting('threads')").fetchone()
        memory = connection.execute("select current_setting('memory_limit')").fetchone()
    return {
        "platform": platform.platform(),
        "system": platform.system(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "cpu_count": os.cpu_count(),
        "mem_total_bytes": int(page * pages),
        "duckdb": duckdb.__version__,
        "duckdb_default_threads": None if threads is None else threads[0],
        "duckdb_default_memory_limit": None if memory is None else memory[0],
        "dbt_core": version("dbt-core"),
        "dbt_duckdb": version("dbt-duckdb"),
    }


def full_build_summary(
    project: Path,
    template: Path,
    work: Path,
    repeats: int,
) -> dict[str, object]:
    set_player_games(project, player_games_sql("view"))
    walls: list[float] = []
    elapsed: list[float] = []
    by_node: dict[str, list[float]] = {}
    for index in range(repeats):
        log(f"published dbt build {index + 1}/{repeats}")
        result, warehouse = one_build(
            project,
            template,
            work,
            f"published-{index}",
            None,
            exclude_tests=False,
        )
        payload = result["results"]
        assert isinstance(payload, dict)
        walls.append(float(result["wall_seconds"]))
        elapsed.append(float(payload["elapsed_time"]))
        for unique_id, seconds in node_map(payload).items():
            by_node.setdefault(unique_id, []).append(seconds)
        shutil.rmtree(warehouse.parent)
    ranked = sorted(
        ({"unique_id": unique_id, **summarize(samples)} for unique_id, samples in by_node.items()),
        key=lambda item: float(item["median"]),
        reverse=True,
    )
    return {
        "wall_seconds": summarize(walls),
        "dbt_elapsed_seconds": summarize(elapsed),
        "nodes_by_median_execution": ranked,
    }


def measure_scale(
    games: int,
    ratios: list[float],
    repeats: int,
    project: Path,
    work: Path,
) -> dict[str, object]:
    scale_dir = fresh_dir(work, f"scale-{games}")
    full_template = scale_dir / "template-full" / "warehouse.duckdb"
    log(f"seed {games} games")
    started = time.perf_counter()
    make_warehouse(full_template, 0, games)
    seed_seconds = time.perf_counter() - started
    facts_bytes = full_template.stat().st_size
    copies = [
        copy_warehouse(full_template, scale_dir / f"copy-{i}" / "warehouse.duckdb")
        for i in range(repeats)
    ]
    for path in (scale_dir / f"copy-{i}" for i in range(repeats)):
        shutil.rmtree(path)

    set_player_games(project, player_games_sql("table"))
    table = repeated_model(
        project, full_template, scale_dir, "table", "+player_games", repeats, PLAYER_GAMES
    )
    table_warehouse = table.pop("warehouse")
    table_query = time_select(table_warehouse, OPENING_SCORE_SQL, repeats)
    table_bytes = table_warehouse.stat().st_size
    full_hash = hash_player_games(table_warehouse)

    set_player_games(project, player_games_sql("view"))
    view = repeated_model(
        project, full_template, scale_dir, "view", "+player_games", repeats, PLAYER_GAMES
    )
    view_warehouse = view.pop("warehouse")
    view_query = time_select(view_warehouse, OPENING_SCORE_SQL, repeats)
    view_bytes = view_warehouse.stat().st_size

    deltas: dict[str, object] = {}
    for ratio in ratios:
        new_count = _new_games(games, ratio)
        base = games - new_count
        base_template = scale_dir / f"template-{ratio}" / "warehouse.duckdb"
        make_warehouse(base_template, 0, base)
        kind = "anti_join"
        measured = measure_incremental(
            project,
            base_template,
            scale_dir,
            f"delete-insert-{ratio}",
            repeats,
            player_games_sql(kind),
            base,
            new_count,
        )
        warehouse = measured.pop("warehouse")
        digest = hash_player_games(warehouse)
        set_player_games(project, player_games_sql("replay", replay_after=base))
        replay_dir = fresh_dir(scale_dir, f"replay-{ratio}")
        replay_db = replay_dir / "warehouse.duckdb"
        shutil.copy2(warehouse, replay_db)
        replay = dbt_build(
            project,
            replay_db,
            "player_games",
            replay_dir / "target",
            replay_dir / "logs",
            exclude_tests=True,
        )
        replay_hash = hash_player_games(replay_db)
        payload = replay["results"]
        assert isinstance(payload, dict)
        deltas[str(ratio)] = {
            "new_games": new_count,
            "base_games": base,
            "strategy": "delete+insert",
            "filter": "player_game_key not in target",
            **measured,
            "warehouse_bytes": warehouse.stat().st_size,
            "equivalence": {
                "full_refresh": full_hash,
                "after_rerun": digest,
                "match": digest["sha256"] == full_hash["sha256"]
                and digest["rows"] == full_hash["rows"],
            },
            "replay": {
                "execution_seconds": execution_time(payload, PLAYER_GAMES),
                "wall_seconds": replay["wall_seconds"],
                "rows": replay_hash["rows"],
                "sha256": replay_hash["sha256"],
                "match": replay_hash["sha256"] == full_hash["sha256"]
                and replay_hash["rows"] == full_hash["rows"],
            },
        }
        shutil.rmtree(warehouse.parent)

    ordinal_ratio = 0.01
    ordinal_new = _new_games(games, ordinal_ratio)
    ordinal_base = games - ordinal_new
    ordinal_template = scale_dir / "template-ordinal" / "warehouse.duckdb"
    make_warehouse(ordinal_template, 0, ordinal_base)
    ordinal = measure_incremental(
        project,
        ordinal_template,
        scale_dir,
        "ordinal",
        repeats,
        player_games_sql("ordinal"),
        ordinal_base,
        ordinal_new,
        variables_for=ordinal_base,
    )
    ordinal_warehouse = ordinal.pop("warehouse")
    ordinal_hash = hash_player_games(ordinal_warehouse)
    ordinal_result = {
        "new_games": ordinal_new,
        "base_games": ordinal_base,
        "filter": "source_ordinal > loaded_through var",
        **ordinal,
        "equivalence": {
            "match": ordinal_hash["sha256"] == full_hash["sha256"]
            and ordinal_hash["rows"] == full_hash["rows"],
            "rows": ordinal_hash["rows"],
            "sha256": ordinal_hash["sha256"],
        },
    }
    shutil.rmtree(ordinal_warehouse.parent)

    strategies: dict[str, object] = {}
    strategy_new = _new_games(games, 0.01)
    strategy_base = games - strategy_new
    strategy_template = scale_dir / "template-strategy" / "warehouse.duckdb"
    make_warehouse(strategy_template, 0, strategy_base)
    names = ["append", "delete+insert", "merge"]
    buckets = {name: {"wall": [], "elapsed": [], "execution": []} for name in names}
    for index in range(repeats):
        order = names[index % len(names) :] + names[: index % len(names)]
        for name in order:
            kind = "append" if name == "append" else "merge" if name == "merge" else "anti_join"
            log(f"strategy {name} {games} {index + 1}/{repeats}")
            set_player_games(project, player_games_sql(kind))
            directory = fresh_dir(scale_dir, f"strategy-{name}-{index}")
            warehouse = directory / "warehouse.duckdb"
            copy_warehouse(strategy_template, warehouse)
            target = directory / "target"
            logs = directory / "logs"
            dbt_build(project, warehouse, "+player_games", target, logs, exclude_tests=True)
            append_games(warehouse, strategy_base, strategy_new)
            delta = dbt_build(project, warehouse, "+player_games", target, logs, exclude_tests=True)
            payload = delta["results"]
            assert isinstance(payload, dict)
            buckets[name]["wall"].append(float(delta["wall_seconds"]))
            buckets[name]["elapsed"].append(float(payload["elapsed_time"]))
            buckets[name]["execution"].append(execution_time(payload, PLAYER_GAMES))
            shutil.rmtree(directory)
    for name, values in buckets.items():
        strategies[name] = {
            "wall_seconds": summarize(values["wall"]),
            "dbt_elapsed_seconds": summarize(values["elapsed"]),
            "execution_seconds": summarize(values["execution"]),
        }

    set_player_games(project, player_games_sql("view"))
    downstream_nodes = [
        "model.chess_analytics.mart_player_outcomes",
        "model.chess_analytics.games",
        "model.chess_analytics.player_games",
        "model.chess_analytics.metricflow_time_spine",
    ]
    downstream_store = {unique_id: [] for unique_id in downstream_nodes}
    downstream_wall: list[float] = []
    downstream_elapsed: list[float] = []
    for index in range(repeats):
        log(f"downstream {games} {index + 1}/{repeats}")
        result, warehouse = one_build(
            project,
            full_template,
            scale_dir,
            f"downstream-{index}",
            "+mart_player_outcomes +games +player_games +metricflow_time_spine",
            exclude_tests=True,
        )
        payload = result["results"]
        assert isinstance(payload, dict)
        downstream_wall.append(float(result["wall_seconds"]))
        downstream_elapsed.append(float(payload["elapsed_time"]))
        mapped = node_map(payload)
        for unique_id in downstream_nodes:
            downstream_store[unique_id].append(mapped[unique_id])
        shutil.rmtree(warehouse.parent)

    try:
        published = full_build_summary(project, full_template, scale_dir, min(3, repeats))
    except RuntimeError as exc:
        published = {"error": str(exc)[-4000:]}
    return {
        "games": games,
        "player_game_rows": games * 2,
        "seed_seconds": seed_seconds,
        "facts_bytes": facts_bytes,
        "copy_seconds": summarize(copies),
        "full_refresh_table": table,
        "table_bytes": table_bytes,
        "table_query_seconds": summarize(table_query),
        "view_build": view,
        "view_bytes": view_bytes,
        "view_query_seconds": summarize(view_query),
        "query_sql": OPENING_SCORE_SQL,
        "query_connection": QUERY_CONNECTION,
        "deltas": deltas,
        "ordinal_predicate_1pct": ordinal_result,
        "strategy_1pct_delta": strategies,
        "downstream": {
            "wall_seconds": summarize(downstream_wall),
            "dbt_elapsed_seconds": summarize(downstream_elapsed),
            "execution_seconds": {
                unique_id: summarize(samples) for unique_id, samples in downstream_store.items()
            },
        },
        "published_dbt_build": published,
    }


def equivalence_report(
    root: Path, games: int = 40, *, in_process: bool = False
) -> dict[str, object]:
    """Small proof used by tests. Same SQL generator as the measurement.

    ``in_process`` repeats the builds in one interpreter. The timing study
    keeps the default and still pays a process start per build.
    """
    profile_settings()
    new_count = 4
    base = games - new_count
    project = root / "dbt"
    copy_project(project)
    build = partial(dbt_build, in_process=in_process)
    full = root / "full" / "warehouse.duckdb"
    make_warehouse(full, 0, games)
    set_player_games(project, player_games_sql("table"))
    build(project, full, "+player_games", root / "t-full", root / "l-full", exclude_tests=True)
    full_hash, full_rows = content_sha256(full, "player_games", "player_game_key")

    incremental = root / "inc" / "warehouse.duckdb"
    make_warehouse(incremental, 0, base)
    set_player_games(project, player_games_sql("anti_join"))
    build(project, incremental, "+player_games", root / "t-inc", root / "l-inc", exclude_tests=True)
    append_games(incremental, base, new_count)
    build(
        project,
        incremental,
        "player_games",
        root / "t-inc",
        root / "l-inc",
        exclude_tests=True,
        verb="compile",
    )
    delta_batch_rows = compiled_batch_rows(incremental, root / "t-inc")
    build(project, incremental, "+player_games", root / "t-inc", root / "l-inc", exclude_tests=True)
    delta_hash, delta_rows = content_sha256(incremental, "player_games", "player_game_key")
    build(
        project,
        incremental,
        "player_games",
        root / "t-inc",
        root / "l-inc",
        exclude_tests=True,
        verb="compile",
    )
    rerun_batch_rows = compiled_batch_rows(incremental, root / "t-inc")
    build(project, incremental, "+player_games", root / "t-inc", root / "l-inc", exclude_tests=True)
    rerun_hash, rerun_rows = content_sha256(incremental, "player_games", "player_game_key")
    set_player_games(project, player_games_sql("replay", replay_after=base))
    build(project, incremental, "player_games", root / "t-inc", root / "l-inc", exclude_tests=True)
    replay_hash, replay_rows = content_sha256(incremental, "player_games", "player_game_key")

    broken_key = root / "key" / "warehouse.duckdb"
    make_warehouse(broken_key, 0, games)
    set_player_games(project, player_games_sql("replay_without_key", replay_after=base))
    build(project, broken_key, "+player_games", root / "t-key", root / "l-key", exclude_tests=True)
    before_key, _ = content_sha256(broken_key, "player_games", "player_game_key")
    build(project, broken_key, "player_games", root / "t-key", root / "l-key", exclude_tests=True)
    _, broken_key_rows = content_sha256(broken_key, "player_games", "player_game_key")

    broken_filter = root / "filter" / "warehouse.duckdb"
    make_warehouse(broken_filter, 0, base)
    set_player_games(project, player_games_sql("broken_filter"))
    build(
        project,
        broken_filter,
        "+player_games",
        root / "t-filter",
        root / "l-filter",
        exclude_tests=True,
    )
    append_games(broken_filter, base, new_count)
    build(
        project,
        broken_filter,
        "+player_games",
        root / "t-filter",
        root / "l-filter",
        exclude_tests=True,
    )
    _, broken_filter_rows = content_sha256(broken_filter, "player_games", "player_game_key")
    return {
        "rows": full_rows,
        "base_rows": base * 2,
        "incremental_match": delta_hash == full_hash and delta_rows == full_rows,
        "delta_batch_rows": delta_batch_rows,
        "rerun_match": rerun_hash == full_hash and rerun_rows == full_rows,
        "rerun_batch_rows": rerun_batch_rows,
        "replay_match": replay_hash == full_hash and replay_rows == full_rows,
        "broken_key_rows": broken_key_rows,
        "broken_key_changed": before_key != full_hash or broken_key_rows != full_rows,
        "broken_filter_rows": broken_filter_rows,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", default="100000,1000000")
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--deltas", default="0.01,0.10")
    parser.add_argument("--output", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.repeats < 3:
        raise SystemExit("repeats must be at least 3 so a median is meaningful")
    games = [int(item) for item in args.games.split(",") if item]
    ratios = [float(item) for item in args.deltas.split(",") if item]
    settings = profile_settings()
    if dbt_executable().is_file() is False:
        raise SystemExit("dbt is not installed; sync the dbt extra")
    started = time.perf_counter()
    with_temp = Path(tempfile.mkdtemp(prefix="chesslab-incremental-"))
    try:
        project = with_temp / "dbt"
        copy_project(project)
        probe = microbatch_error(project, with_temp)
        log("microbatch probe captured")
        scales = [measure_scale(count, ratios, args.repeats, project, with_temp) for count in games]
        mismatches = []
        for scale in scales:
            deltas = scale["deltas"]
            assert isinstance(deltas, dict)
            for ratio, item in deltas.items():
                assert isinstance(item, dict)
                equivalence = item["equivalence"]
                replay = item["replay"]
                assert isinstance(equivalence, dict)
                assert isinstance(replay, dict)
                if not equivalence["match"] or not replay["match"]:
                    mismatches.append(f"{scale['games']} {ratio}")
            ordinal = scale["ordinal_predicate_1pct"]
            assert isinstance(ordinal, dict)
            ordinal_equivalence = ordinal["equivalence"]
            assert isinstance(ordinal_equivalence, dict)
            if not ordinal_equivalence["match"]:
                mismatches.append(f"{scale['games']} ordinal")
            for item in recorded_errors(scale):
                mismatches.append(f"{scale['games']} {item}")
        report = {
            "generated_at": datetime.now(UTC).isoformat(),
            "synthetic": {
                "description": (
                    "Deterministic fact_game and fact_player_game rows from a range index. "
                    "Same columns as the published snapshot. Not the Lichess distribution."
                ),
                "games": games,
                "player_games_per_game": 2,
            },
            "content_sha256_method": CONTENT_SHA256_METHOD,
            "profile": settings,
            "machine": machine_facts(),
            "strategy": {
                "supported": ["append", "delete+insert", "merge", "microbatch"],
                "chosen": "delete+insert",
                "unique_key": "player_game_key",
                "microbatch_with_unique_key": probe,
            },
            "scales": scales,
            "elapsed_seconds": time.perf_counter() - started,
            "mismatches": mismatches,
        }
    finally:
        shutil.rmtree(with_temp, ignore_errors=True)
    text = json.dumps(report, indent=2) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text)
        log(f"wrote {args.output}")
    else:
        sys.stdout.write(text)
    for item in mismatches:
        log(f"measurement failed: {item}")
    return measurement_status(mismatches, report["scales"])


if __name__ == "__main__":
    raise SystemExit(main())
