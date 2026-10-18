"""Synthetic scale shape, and a small incremental equivalence proof.

The large timing run is scripts/measure_incremental_player_games.py. It is
not part of CI. These tests stay on a few dozen games.
"""

import importlib.util
import json
import os
import sys
from pathlib import Path

import duckdb
import pytest

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "measure_incremental_player_games",
    ROOT / "scripts/measure_incremental_player_games.py",
)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)

DBT = Path(sys.executable).with_name("dbt")


def _require_dbt() -> None:
    if DBT.is_file():
        return
    if os.environ.get("CHESSLAB_REQUIRE_DBT") == "1":
        pytest.fail("incremental equivalence needs the dbt extra in this job")
    pytest.skip("install the optional dbt extra")


def test_synthetic_facts_match_the_published_shape(tmp_path: Path) -> None:
    database = tmp_path / "warehouse.duckdb"
    _MODULE.make_warehouse(database, 0, 25)
    again = tmp_path / "again.duckdb"
    _MODULE.make_warehouse(again, 0, 25)
    schema = json.loads((ROOT / "contracts/tables.json").read_text())
    with duckdb.connect(str(database), read_only=True) as connection:
        for table, columns in schema.items():
            if not isinstance(columns, dict):
                continue
            described = connection.execute(f'describe "{table}"').fetchall()
            assert [row[0] for row in described] == list(columns)
        games = connection.execute("select count(*) from fact_game").fetchone()
        players = connection.execute("select count(*) from fact_player_game").fetchone()
        assert games is not None and players is not None
        assert games[0] == 25
        assert players[0] == 50
        broken = connection.execute(
            """
            select count(*) from (
                select "game_id"
                from fact_player_game
                group by "game_id"
                having count(*) != 2
                    or (
                        sum("score") is not null
                        and sum("score") != 1
                    )
            )
            """
        ).fetchone()
        lengths = connection.execute(
            'select count(*) from fact_game where length("game_id") != 8'
        ).fetchone()
    assert broken is not None and broken[0] == 0
    assert lengths is not None and lengths[0] == 0
    assert _MODULE.content_sha256(database, "fact_game", "game_id") == _MODULE.content_sha256(
        again, "fact_game", "game_id"
    )


def test_published_player_games_stays_a_view() -> None:
    sql = _MODULE.published_sql()
    assert "materialized='view'" in sql
    assert "is_incremental" not in sql
    assert "incremental_strategy" not in sql


def test_incremental_matches_full_refresh_until_the_key_or_filter_breaks(tmp_path: Path) -> None:
    _require_dbt()
    report = _MODULE.equivalence_report(tmp_path, games=40)
    assert report["rows"] == 80
    assert report["base_rows"] == 72
    assert report["incremental_match"] is True
    assert report["rerun_match"] is True
    assert report["replay_match"] is True
    assert report["broken_key_rows"] == 88
    assert report["broken_key_changed"] is True
    assert report["broken_filter_rows"] == 72
