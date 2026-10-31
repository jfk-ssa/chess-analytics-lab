"""An enforced mart contract fails the build when a column disappears."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import duckdb
import pytest

ROOT = Path(__file__).resolve().parents[1]
DBT = Path(sys.executable).with_name("dbt")


def _require_dbt():
    if DBT.is_file():
        return
    if os.environ.get("CHESSLAB_REQUIRE_DBT") == "1":
        pytest.fail("contract tests need the dbt extra in this job")
    pytest.skip("install the optional dbt extra")


def _empty_sources(warehouse: Path) -> None:
    schema = json.loads((ROOT / "contracts/tables.json").read_text())
    with duckdb.connect(str(warehouse)) as connection:
        for table, columns in schema.items():
            if not isinstance(columns, dict):
                continue
            definitions = ", ".join(f'"{name}" {kind}' for name, kind in columns.items())
            connection.execute(f'create table "{table}" ({definitions})')


@pytest.mark.dbt
def test_enforced_contract_rejects_a_dropped_column(tmp_path):
    _require_dbt()
    warehouse = tmp_path / "warehouse.duckdb"
    _empty_sources(warehouse)
    project = tmp_path / "dbt"
    shutil.copytree(
        ROOT / "dbt",
        project,
        ignore=shutil.ignore_patterns("target", "logs", "dbt_packages"),
    )
    sql_path = project / "models/marts/mart_game_outcomes.sql"
    sql = sql_path.read_text()
    removed = "    count(*) filter (where metric_eligible and drawn) as drawn_games,\n"
    assert removed in sql
    sql_path.write_text(sql.replace(removed, "", 1))
    env = os.environ.copy()
    env.update(
        CHESSLAB_DBT_PATH=str(warehouse),
        DBT_SEND_ANONYMOUS_USAGE_STATS="false",
        DO_NOT_TRACK="1",
        DBT_PROFILES_DIR=str(project),
    )
    completed = subprocess.run(
        [
            str(DBT),
            "build",
            "--select",
            "+mart_game_outcomes",
            "--project-dir",
            str(project),
            "--profiles-dir",
            str(project),
            "--target-path",
            str(tmp_path / "target"),
            "--log-path",
            str(tmp_path / "logs"),
            "--no-use-colors",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    output = completed.stdout + completed.stderr
    assert completed.returncode != 0, output[-2000:]
    assert "contract" in output.lower()
    assert "drawn_games" in output
