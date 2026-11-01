"""Offline fixture behavior and a real dbt/MetricFlow query when the extra is installed."""

import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

import duckdb
import pytest

from chess_analytics.analyst.semantic import query_rows, validate_configs

ROOT = Path(__file__).resolve().parents[1]
DBT = Path(sys.executable).with_name("dbt")


@pytest.fixture
def move_warehouse(tmp_path: Path) -> Path:
    """Synthetic annotations: ordinary loss, clamp boundary, mate-only, missing, zero."""
    warehouse = tmp_path / "warehouse.duckdb"
    schema = json.loads((ROOT / "contracts/m3_tables.json").read_text())["fact_move"]
    with duckdb.connect(str(warehouse)) as con:
        columns = ", ".join(f'"{name}" {kind}' for name, kind in schema.items())
        con.execute(f"create table fact_move ({columns})")
        con.execute("""
            insert into fact_move
                (provider, game_id, ply, color, eval_before_cp_white, eval_after_cp_white,
                 eval_before_mate_white, eval_after_mate_white, centipawn_deterioration)
            values ('lichess', 'same-id', 1, 'white', 200, 100, null, null, 100),
                   ('lichess', 'same-id', 2, 'black', -100, 1500, null, null, 1600),
                   ('lichess', 'same-id', 3, 'white', 1500, null, null, -2, null),
                   ('lichess', 'same-id', 4, 'black', null, 0, -2, null, null),
                   ('lichess', 'same-id', 5, 'white', null, null, null, null, null),
                   ('lichess', 'same-id', 6, 'black', 0, -50, null, null, 0),
                   ('lichess', 'same-id', 7, 'white', 1000, 0, null, null, 1000),
                   ('lichess', 'mate-only', 1, 'white', 100, null, null, -2, null),
                   ('lichess', 'mate-only', 2, 'black', null, 0, -2, null, null)
        """)
        con.execute("""
            create table stg_games as
            select 'lichess' as provider, 'same-id' as game_id,
                   date '2026-10-01' as utc_date, 'Sicilian Defense' as opening_family
            union all select 'other', 'same-id', null, 'Other family'
            union all select 'lichess', 'mate-only', date '2026-10-01', 'Mate family'
        """)
        sql = (ROOT / "dbt/models/marts/move_evals.sql").read_text()
        sql = sql.replace("{{ config(materialized='view') }}", "")
        sql = sql.replace("{{ source('published', 'fact_move') }}", "fact_move")
        sql = sql.replace("{{ ref('stg_games') }}", "stg_games")
        con.execute(f"create view move_evals as {sql}")
    return warehouse


def test_clamp_mate_and_missing_exclusion(move_warehouse: Path) -> None:
    with duckdb.connect(str(move_warehouse)) as con:
        rows = con.execute("""
            select ply, evaluable, clamped_deterioration, game_key, utc_date, opening_family
            from move_evals where game_id = 'same-id' order by ply
        """).fetchall()
        assert [(row[0], row[1], row[2]) for row in rows] == [
            (1, True, 100),
            (2, True, 1000),
            (3, False, None),
            (4, False, None),
            (5, False, None),
            (6, True, 0),
            (7, True, 1000),
        ]
        assert all(
            row[3:] == ("lichess:same-id", date(2026, 10, 1), "Sicilian Defense") for row in rows
        )
        assert con.execute("""
            select sum(clamped_deterioration) / nullif(count(*) filter (where evaluable), 0)
            from move_evals
        """).fetchone() == (2100 / 4,)


@pytest.mark.dbt
def test_metricflow_mean_and_zero_denominator(move_warehouse: Path, tmp_path: Path) -> None:
    if not DBT.is_file():
        if os.environ.get("CHESSLAB_REQUIRE_DBT") == "1":
            pytest.fail("move metric tests need the dbt extra in this job")
        pytest.skip("install the optional dbt extra")
    env = {
        **os.environ,
        "CHESSLAB_DBT_PATH": str(move_warehouse),
        "DBT_SEND_ANONYMOUS_USAGE_STATS": "false",
    }
    built = subprocess.run(
        [
            str(DBT),
            "build",
            "--select",
            "move_evals",
            "--project-dir",
            str(ROOT / "dbt"),
            "--profiles-dir",
            str(ROOT / "dbt"),
            "--target-path",
            str(tmp_path / "target"),
            "--log-path",
            str(tmp_path / "logs"),
            "--no-partial-parse",
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert built.returncode == 0, (built.stdout + built.stderr)[-2000:]
    manifest = tmp_path / "target/semantic_manifest.json"
    assert validate_configs(manifest) == []
    metrics = ["clamped_centipawn_loss", "evaluable_moves", "mean_centipawn_loss"]
    row = query_rows(move_warehouse, manifest, metrics)[0]
    assert row == {
        "clamped_centipawn_loss": 2100,
        "evaluable_moves": 4,
        "mean_centipawn_loss": pytest.approx(2100 / 4),
    }
    with duckdb.connect(str(move_warehouse)) as con:
        con.execute(
            "delete from fact_move where eval_before_cp_white is not null "
            "and eval_after_cp_white is not null"
        )
    assert query_rows(move_warehouse, manifest, metrics)[0]["mean_centipawn_loss"] is None
    with duckdb.connect(str(move_warehouse)) as con:
        con.execute("delete from fact_move where game_id != 'mate-only'")
        assert con.execute(
            "select count(*), count(*) filter (where evaluable) from move_evals"
        ).fetchone() == (2, 0)
        assert con.execute("""
            select sum(clamped_deterioration) / nullif(count(*) filter (where evaluable), 0)
            from move_evals
        """).fetchone() == (None,)
    assert query_rows(move_warehouse, manifest, metrics)[0]["mean_centipawn_loss"] is None
    with duckdb.connect(str(move_warehouse)) as con:
        con.execute("delete from fact_move")
    assert query_rows(move_warehouse, manifest, metrics)[0]["mean_centipawn_loss"] is None
