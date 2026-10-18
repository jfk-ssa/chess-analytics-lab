"""MetricFlow parity for the governed metrics. Requires the optional dbt extra."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import duckdb
import pytest

from chess_analytics.analyst.core import replay
from chess_analytics.analyst.tool_catalog import TOOLS
from chess_analytics.analyst.tools import CheckedTools
from chess_analytics.cli import fixture_plan
from chess_analytics.common import read_json, writer_lock
from chess_analytics.dashboard.analysis import current_snapshot
from chess_analytics.ingest.pipeline import ingest
from chess_analytics.marts.pipeline import build_mart
from chess_analytics.portfolio_demo import run
from chess_analytics.warehouse.snapshots import build

PROJECT = Path(__file__).resolve().parents[1]
DBT = Path(sys.executable).with_name("dbt")
MF = Path(sys.executable).with_name("mf")
pytestmark = pytest.mark.skipif(
    not DBT.is_file() or not MF.is_file(), reason="install the optional dbt extra"
)
ALLOWLIST = [
    "list_metrics",
    "get_metric_definition",
    "get_dataset_coverage",
    "query_metric",
    "compare_openings",
    "analyze_clock_pressure",
    "compare_clock_buckets",
    "evaluate_position",
    "position_continuations",
    "compare_candidate_moves",
    "predict_human_moves",
]
DRAW_KEYS = {
    "metric_id",
    "version",
    "contract_sha256",
    "analytical_id",
    "numerator",
    "denominator",
    "value",
}
USAGE_KEYS = DRAW_KEYS | {"family", "unknown_opening_games", "scope"}
SCORE_KEYS = {
    "metric_id",
    "version",
    "contract_sha256",
    "analytical_id",
    "filters",
    "wins",
    "draws",
    "losses",
    "eligible_player_games",
    "win_rate",
    "score_rate",
    "low_support",
    "scope",
}
SCORE_FILTERS = {
    "family": "Sicilian Defense",
    "color": "white",
    "rating_min": 1400,
    "rating_max_exclusive": 1600,
    "base_seconds": 60,
    "increment_seconds": 0,
}


def _env(warehouse: Path, log_path: Path, *, block_network: bool) -> dict[str, str]:
    log_path.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(
        CHESSLAB_DBT_PATH=str(warehouse),
        DBT_PROFILES_DIR=str(PROJECT / "dbt"),
        DBT_PROJECT_DIR=str(PROJECT / "dbt"),
        DBT_TARGET="local",
        DBT_SEND_ANONYMOUS_USAGE_STATS="false",
        DO_NOT_TRACK="1",
        DBT_LOG_PATH=str(log_path),
    )
    if block_network:
        env.update(
            https_proxy="http://127.0.0.1:9",
            http_proxy="http://127.0.0.1:9",
            HTTPS_PROXY="http://127.0.0.1:9",
            HTTP_PROXY="http://127.0.0.1:9",
            no_proxy="",
            NO_PROXY="",
        )
    return env


def _run(
    command: list[str], warehouse: Path, *, block_network: bool
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        cwd=PROJECT,
        env=_env(warehouse, warehouse.parent / "dbt-logs", block_network=block_network),
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, (completed.stderr or completed.stdout)[-1500:]
    return completed


def _parse(warehouse: Path) -> None:
    _run(
        [
            str(DBT),
            "parse",
            "--project-dir",
            str(PROJECT / "dbt"),
            "--profiles-dir",
            str(PROJECT / "dbt"),
            "--no-use-colors",
        ],
        warehouse,
        block_network=False,
    )


def _publish_tiny(root: Path, source: Path) -> tuple[Path, Path]:
    plan = fixture_plan(PROJECT)
    plan["url"] = f"local:{source.relative_to(PROJECT)}"
    with writer_lock(root):
        ingest(PROJECT, root, "tiny", source, plan)
        snapshot = build(PROJECT, root, "tiny")
        mart = build_mart(PROJECT, root, "tiny", DBT)
    _parse(mart / "warehouse.duckdb")
    return snapshot, mart


def _tools(project: Path, snapshot: Path, dataset_id: str) -> CheckedTools:
    tools = CheckedTools.__new__(CheckedTools)
    tools.project = project
    tools.snapshot = snapshot
    tools.dataset_id = dataset_id
    return tools


def test_allowlist_is_unchanged():
    assert [spec.name for spec in TOOLS] == ALLOWLIST


def test_parse_validate_and_tiny_draw_rate(project, tmp_path):
    snapshot, mart = _publish_tiny(tmp_path / "data", project / "tests/fixtures/tiny.pgn")
    warehouse = mart / "warehouse.duckdb"
    _run([str(MF), "validate-configs", "--skip-dw"], warehouse, block_network=True)
    explained = _run(
        [str(MF), "query", "--quiet", "--explain", "--metrics", "game_draw_rate"],
        warehouse,
        block_network=True,
    )
    assert "SUM(eligible_game)" in explained.stdout
    assert "utc_date" not in explained.stdout

    sql_tools = _tools(project, snapshot, snapshot.name)
    semantic_tools = _tools(project, mart, snapshot.name)
    sql_result = sql_tools.query_metric("game_draw_rate", {})
    semantic_result = semantic_tools.query_metric("game_draw_rate", {})
    assert sql_result == semantic_result
    assert set(sql_result) == DRAW_KEYS
    assert (sql_result["numerator"], sql_result["denominator"], sql_result["value"]) == (4, 20, 0.2)

    manifest = project / "dbt" / "target" / "semantic_manifest.json"
    hidden = manifest.with_suffix(".hidden")
    manifest.rename(hidden)
    try:
        fallback = semantic_tools.query_metric("game_draw_rate", {})
    finally:
        hidden.rename(manifest)
    assert fallback == sql_result

    nulled = tmp_path / "nulled"
    nulled.mkdir()
    shutil.copy2(warehouse, nulled / "warehouse.duckdb")
    with duckdb.connect(str(nulled / "warehouse.duckdb")) as connection:
        connection.execute(
            """update games set utc_date = null
            where game_key = (select min(game_key) from games where eligible_game = 1)"""
        )
    nulled_result = _tools(project, nulled, snapshot.name).query_metric("game_draw_rate", {})
    assert (nulled_result["numerator"], nulled_result["denominator"]) == (4, 20)


def test_demo_fixture_metric_parity(project, tmp_path):
    run(project, tmp_path / "workspace")
    demo = tmp_path / "workspace" / "project"
    (demo / "dbt").symlink_to(project / "dbt")
    snapshot = current_snapshot(demo)
    copy = tmp_path / "semantic"
    copy.mkdir()
    shutil.copy2(snapshot / "warehouse.duckdb", copy / "warehouse.duckdb")
    _run(
        [
            str(DBT),
            "build",
            "--project-dir",
            str(PROJECT / "dbt"),
            "--profiles-dir",
            str(PROJECT / "dbt"),
            "--no-use-colors",
        ],
        copy / "warehouse.duckdb",
        block_network=False,
    )
    _parse(copy / "warehouse.duckdb")
    expected = read_json(project / "tests/fixtures/portfolio_expected.json")
    sql_tools = CheckedTools(demo)
    semantic_tools = _tools(demo, copy, sql_tools.dataset_id)
    draw = sql_tools.query_metric("game_draw_rate", {})
    assert draw == semantic_tools.query_metric("game_draw_rate", {})
    assert (draw["numerator"], draw["denominator"]) == (
        expected["draws"],
        expected["eligible_games"],
    )

    for family, games, score in (
        ("Sicilian Defense", expected["sicilian_games"], expected["sicilian_white_score"]),
        ("French Defense", expected["french_games"], expected["french_white_score"]),
    ):
        filters = {**SCORE_FILTERS, "family": family}
        usage = sql_tools.query_metric("opening_usage", {"family": family})
        player = sql_tools.query_metric("opening_player_score", filters)
        assert usage == semantic_tools.query_metric("opening_usage", {"family": family})
        assert player == semantic_tools.query_metric("opening_player_score", filters)
        assert set(usage) == USAGE_KEYS
        assert set(player) == SCORE_KEYS
        assert (usage["numerator"], usage["denominator"], usage["value"]) == (
            games,
            expected["opening_known_games"],
            games / expected["opening_known_games"],
        )
        assert player["score_rate"] == score
        assert player["low_support"] is True

    grouped = sql_tools.query_metric("opening_usage", {}, ["opening_family"])
    assert grouped == semantic_tools.query_metric("opening_usage", {}, ["opening_family"])
    assert grouped["denominator"] == expected["opening_known_games"]
    assert [(row["family"], row["numerator"]) for row in grouped["rows"]] == [
        ("French Defense", expected["french_games"]),
        ("Sicilian Defense", expected["sicilian_games"]),
    ]
    assert grouped["truncated"] is False

    plan = project / "evals/replay_plans/governed_draw_rate.json"
    record = json.loads(plan.read_text())
    answer = replay(demo, record["question"], plan)
    assert answer["status"] == "answered"
    assert answer["result"]["numerator"] == expected["draws"]
    assert answer["result"]["denominator"] == expected["eligible_games"]
