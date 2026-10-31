"""Synthetic scale shape, and a small incremental equivalence proof.

The large timing run is scripts/measure_incremental_player_games.py. It is
not part of CI. These tests stay on a few dozen games.
"""

import importlib.util
import json
import os
import sys
import types
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


def test_happy_path_filter_is_the_anti_join() -> None:
    sql = _MODULE.player_games_sql("anti_join")
    assert 'where p."player_game_key" not in (' in sql
    assert 'select "player_game_key" from {{ this }}' in sql


def test_committed_receipt_names_the_hasher_that_produced_it() -> None:
    receipt = json.loads((ROOT / "reports/incremental-player-games.json").read_text())
    method = receipt["content_sha256_method"]
    assert "select *" in method
    assert "pytz" in method
    assert method != _MODULE.CONTENT_SHA256_METHOD
    assert "varchar" in _MODULE.CONTENT_SHA256_METHOD
    for scale in receipt["scales"]:
        assert "warm buffer-pool" in scale["query_connection"]


def test_a_recorded_build_error_fails_the_measurement() -> None:
    clean = [{"published_dbt_build": {"wall_seconds": {"median": 1}}}]
    failed = [{"published_dbt_build": {"error": "dbt failed"}}]
    assert _MODULE.measurement_status([], clean) == 0
    assert _MODULE.measurement_status([], failed) == 1
    assert _MODULE.measurement_status(["1000000 0.01"], clean) == 1


def _in_process_build_restores_the_environment(root: Path) -> None:
    """No env leak from load_dotenv or a close() error. Same collected test."""
    before = os.environ.copy()
    target = root / "stub-target"
    target.mkdir()
    state: dict[str, object] = {"success": True, "raise_close": True}

    class _Result:
        def __init__(self, success: object) -> None:
            self.success = success
            self.exception = None

    class _Runner:
        def invoke(self, args: list[str]) -> _Result:
            assert args[0] == "build"
            assert "--no-partial-parse" in args
            assert args[-1] == "--quiet"
            os.environ["CHESSLAB_FROM_INVOKE"] = "from-invoke"
            return _Result(state["success"])

    class _LeakModule(types.ModuleType):
        def __getattr__(self, name: str) -> type[_Runner]:
            if name != "dbtRunner":
                raise AttributeError(name)
            os.environ["CHESSLAB_FROM_DOTENV"] = "from-import"
            return _Runner

    command = [
        "dbt",
        "build",
        "--project-dir",
        str(root / "dbt"),
        "--profiles-dir",
        str(root / "dbt"),
        "--target-path",
        str(target),
        "--log-path",
        str(root / "logs"),
        "--no-partial-parse",
        "--no-use-colors",
    ]
    warehouse = root / "warehouse.duckdb"
    project = root / "dbt"

    def release() -> None:
        os.environ["CHESSLAB_DBT_PATH"] = "leaked-by-close"
        if state["raise_close"]:
            raise RuntimeError("close failed")

    with pytest.MonkeyPatch.context() as patch:
        patch.setitem(sys.modules, "dbt.cli.main", _LeakModule("dbt.cli.main"))
        patch.setattr(_MODULE, "_DBT_RUNNER", None)
        patch.setattr(_MODULE, "_release_duckdb_environment", release)
        with pytest.raises(RuntimeError, match="close failed"):
            _MODULE._dbt_build_in_process(command, warehouse, project, target, False)
        assert os.environ == before

        state["raise_close"] = False
        payload = {"results": [{"status": "success"}]}
        (target / "run_results.json").write_text(json.dumps(payload))
        built = _MODULE._dbt_build_in_process(command, warehouse, project, target, False)
        assert built["returncode"] == 0
        assert built["results"] == payload
        assert os.environ == before

        state["success"] = None
        with pytest.raises(RuntimeError, match="no success flag"):
            _MODULE._dbt_build_in_process(command, warehouse, project, target, False)
        assert os.environ == before

        state["success"] = False
        failed = _MODULE._dbt_build_in_process(command, warehouse, project, target, True)
        assert failed["returncode"] == 1
        assert failed["results"] == payload
        assert os.environ == before


@pytest.mark.dbt
def test_incremental_matches_full_refresh_until_the_key_or_filter_breaks(tmp_path: Path) -> None:
    _require_dbt()
    before = os.environ.copy()
    _in_process_build_restores_the_environment(tmp_path)
    assert os.environ == before
    sql = _MODULE.player_games_sql("anti_join")
    assert 'where p."player_game_key" not in (' in sql
    report = _MODULE.equivalence_report(tmp_path, games=40, in_process=True)
    assert os.environ == before
    assert report["rows"] == 80
    assert report["base_rows"] == 72
    assert report["incremental_match"] is True
    assert report["rerun_match"] is True
    assert report["replay_match"] is True
    assert report["delta_batch_rows"] == 8
    assert report["rerun_batch_rows"] == 0
    assert report["broken_key_rows"] == 88
    assert report["broken_key_changed"] is True
    assert report["broken_filter_rows"] == 72
