"""Governed semantic metrics. Unit tests run without dbt; parity tests build a real mart."""

import json
import logging
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import duckdb
import pytest

from chess_analytics.analyst import semantic
from chess_analytics.analyst.core import replay
from chess_analytics.analyst.tool_catalog import TOOLS
from chess_analytics.analyst.tools import CheckedTools
from chess_analytics.cli import fixture_plan
from chess_analytics.common import digest, read_json, write_json, writer_lock
from chess_analytics.corpus.metrics import opening_family_expr
from chess_analytics.corpus.publish import build_analytical
from chess_analytics.corpus.source import extracted_path
from chess_analytics.ingest.pipeline import ingest
from chess_analytics.marts.pipeline import model_hash
from chess_analytics.portfolio_demo import run
from chess_analytics.warehouse.snapshots import build

PROJECT = Path(__file__).resolve().parents[1]
DBT = Path(sys.executable).with_name("dbt")
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


def _require_dbt():
    if DBT.is_file():
        return
    if os.environ.get("CHESSLAB_REQUIRE_DBT") == "1":
        pytest.fail("semantic tests need the dbt extra in this job")
    pytest.skip("install the optional dbt extra")


def _transform(project: Path, root: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "chess_analytics.marts",
            "--project",
            str(project),
            "--data-dir",
            str(root),
            "transform",
            "--dataset",
            "analytical",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, (completed.stderr or completed.stdout)[-1500:]


def _edged_tiny_pgn(directory: Path) -> Path:
    """Keep the tiny counts, force one sampled game, and add the family edge cases."""
    text = (PROJECT / "tests/fixtures/tiny.pgn").read_text()
    text = text.replace("https://lichess.org/test0001", "https://lichess.org/00000013", 1)
    text = text.replace(
        '[Site "https://lichess.org/00000013"]\n',
        '[Site "https://lichess.org/00000013"]\n[Opening ": Foo"]\n',
        1,
    )
    text = text.replace(
        '[Site "https://lichess.org/test0002"]\n',
        '[Site "https://lichess.org/test0002"]\n[Opening "None: Example"]\n',
        1,
    )
    path = directory / "tiny-edges.pgn"
    path.write_text(text)
    return path


def _stage_product(dest: Path, pgn: Path, period: str) -> Path:
    """Analytical snapshot plus the mart transform, the configuration CheckedTools can use."""
    for name in ("src", "contracts"):
        shutil.copytree(PROJECT / name, dest / name)
    shutil.copytree(
        PROJECT / "dbt",
        dest / "dbt",
        ignore=shutil.ignore_patterns("target", "logs", "dbt_packages"),
    )
    shutil.copy2(PROJECT / "uv.lock", dest / "uv.lock")
    plan = {
        **fixture_plan(PROJECT),
        "url": f"local:{pgn.name}",
        "period": period,
        "source_kind": "synthetic_test_fixture",
        "max_games": 100,
    }
    write_json(dest / "config/datasets.json", {"analytical": plan})
    root = dest / "data"
    source = extracted_path(root, plan)
    source.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(pgn, source)
    write_json(
        source.with_suffix(".receipt.json"),
        {
            "source_sha256": digest(source),
            "partial_archive": True,
            "compressed_prefix_sha256": None,
            "source_kind": "synthetic_test_fixture",
        },
    )
    with writer_lock(root):
        ingest(dest, root, "analytical", source, plan)
        build(dest, root, "analytical")
        build_analytical(dest, root)
    _transform(dest, root)
    return dest


def _mart(project: Path) -> Path:
    pointer = read_json(project / "data/analytical-mart-current.json")
    return project / "data/marts/published" / pointer["mart_id"]


def _spy(monkeypatch):
    calls = []
    real = semantic.query_rows

    def wrapped(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(semantic, "query_rows", wrapped)
    return calls


def _sql_draw(tools: CheckedTools) -> dict:
    pointer = tools.project / "data/analytical-mart-current.json"
    saved = pointer.read_text()
    pointer.unlink()
    try:
        return tools.query_metric("game_draw_rate", {})
    finally:
        pointer.write_text(saved)


def _copy_mart(project: Path, name: str) -> Path:
    dest = project / "data/marts/published" / name
    shutil.copytree(_mart(project), dest)
    return dest


def _publish_copy(project: Path, directory: Path) -> None:
    manifest = read_json(directory / "manifest.json")
    manifest["mart_id"] = directory.name
    manifest["warehouse_sha256"] = digest(directory / "warehouse.duckdb")
    write_json(directory / "manifest.json", manifest)
    write_json(project / "data/analytical-mart-current.json", {"mart_id": directory.name})


@pytest.fixture(scope="module")
def tiny_product(tmp_path_factory):
    _require_dbt()
    directory = tmp_path_factory.mktemp("semantic-tiny")
    return _stage_product(directory / "project", _edged_tiny_pgn(directory), "semantic-tiny")


@pytest.fixture(scope="module")
def portfolio_product(tmp_path_factory):
    _require_dbt()
    workspace = tmp_path_factory.mktemp("semantic-portfolio")
    run(PROJECT, workspace)
    demo = workspace / "project"
    shutil.copytree(
        PROJECT / "dbt",
        demo / "dbt",
        ignore=shutil.ignore_patterns("target", "logs", "dbt_packages"),
    )
    _transform(demo, demo / "data")
    return demo


def test_allowlist_is_unchanged():
    assert [spec.name for spec in TOOLS] == ALLOWLIST


def test_model_hash_skips_only_the_top_level_generated_directory(tmp_path):
    project = tmp_path / "project"
    nested = project / "dbt/models/target"
    nested.mkdir(parents=True)
    (nested / "keep.sql").write_text("select 1\n")
    generated = project / "dbt/target"
    generated.mkdir()
    (generated / "skip.sql").write_text("select 2\n")
    (generated / "_semantic.yml").mkdir()
    first = model_hash(project)
    (generated / "skip.sql").write_text("select 9\n")
    assert model_hash(project) == first
    (nested / "keep.sql").write_text("select 8\n")
    assert model_hash(project) != first


def test_opening_family_expression_matches_sql_and_the_model():
    expr = opening_family_expr()
    assert expr == "nullif(trim(split_part(source_opening, ':', 1)), '')"
    quoted = "nullif(trim(split_part(\"source_opening\", ':', 1)), '')"
    assert quoted in (PROJECT / "dbt/models/staging/stg_games.sql").read_text()
    with duckdb.connect() as connection:
        rows = connection.execute(
            f"""select source_opening, {expr}
            from (values (': Foo'), ('Sicilian Defense: Najdorf'), (''),
                         (NULL), ('None'), ('  French Defense  ')) t(source_opening)"""
        ).fetchall()
    assert rows == [
        (": Foo", None),
        ("Sicilian Defense: Najdorf", "Sicilian Defense"),
        ("", None),
        (None, None),
        ("None", "None"),
        ("  French Defense  ", "French Defense"),
    ]


def test_governed_call_accepts_only_the_reviewed_shapes():
    assert semantic._governed_call("game_draw_rate", {}, [])
    assert not semantic._governed_call("game_draw_rate", {"family": "Sicilian Defense"}, [])
    assert semantic._governed_call("opening_usage", {"family": "King's Pawn Game"}, [])
    assert semantic._governed_call("opening_usage", {}, ["opening_family"])
    assert not semantic._governed_call(
        "opening_usage", {"family": "Sicilian Defense"}, ["opening_family"]
    )
    assert not semantic._governed_call("opening_usage", {"family": "Réti Opening"}, [])
    assert not semantic._governed_call("opening_usage", {"family": "A" * 81}, [])
    assert not semantic._governed_call("opening_usage", {"family": ""}, [])
    bad = {**SCORE_FILTERS, "rating_min": True}
    assert not semantic._governed_call("opening_player_score", bad, [])
    bad_text = {**SCORE_FILTERS, "rating_min": "1400"}
    assert not semantic._governed_call("opening_player_score", bad_text, [])
    assert semantic._governed_call("opening_player_score", SCORE_FILTERS, [])
    assert "name: opening_usage" not in (PROJECT / "dbt/models/marts/_semantic.yml").read_text()
    assert semantic._equals("game__opening_family", "King's Pawn") == (
        "{{ Dimension('game__opening_family') }} = 'King''s Pawn'"
    )


def test_grouped_truncation_drops_null_and_zero_before_the_limit(monkeypatch):
    """500 real families plus a null group and a zero group are not truncated."""

    def rows(_warehouse, _semantic, metrics, where=None, group_by=None, limit=None):
        if not group_by:
            assert metrics == ["known_opening_games"]
            return [{"known_opening_games": 500}]
        assert where is not None
        assert any("IS NOT NULL" in clause for clause in where)
        assert any("known_opening_games > 0" in clause for clause in where)
        raw = [
            {"game__opening_family": f"Family {index:03d}", "known_opening_games": 1}
            for index in range(500)
        ]
        raw.append({"game__opening_family": None, "known_opening_games": 4})
        raw.append({"game__opening_family": "Zero", "known_opening_games": 0})
        chosen = raw
        if any("IS NOT NULL" in clause for clause in where):
            chosen = [row for row in chosen if row["game__opening_family"] not in {None, ""}]
        if any("known_opening_games > 0" in clause for clause in where):
            chosen = [row for row in chosen if row["known_opening_games"]]
        if limit is not None:
            chosen = chosen[:limit]
        return chosen

    monkeypatch.setattr(semantic, "query_rows", rows)
    grouped_tools = type("T", (), {"dataset_id": "a" * 24})()
    grouped = semantic._opening_usage_grouped(grouped_tools, Path("w"), Path("m"))
    assert len(grouped["rows"]) == 500
    assert grouped["truncated"] is False
    assert all(row["numerator"] for row in grouped["rows"])


def test_grouped_usage_keeps_a_family_named_none(monkeypatch):
    def rows(_warehouse, _semantic, metrics, where=None, group_by=None, limit=None):
        assert limit in {None, 501}
        if group_by:
            return [
                {"game__opening_family": "None", "known_opening_games": 3},
                {"game__opening_family": None, "known_opening_games": 1},
                {"game__opening_family": "", "known_opening_games": 2},
            ]
        assert metrics == ["known_opening_games"]
        return [{"known_opening_games": 3}]

    monkeypatch.setattr(semantic, "query_rows", rows)
    grouped_tools = type("T", (), {"dataset_id": "a" * 24})()
    grouped = semantic._opening_usage_grouped(grouped_tools, Path("w"), Path("m"))
    assert [row["family"] for row in grouped["rows"]] == ["None"]
    assert grouped["truncated"] is False


def test_zero_denominator_and_supported_score(monkeypatch):
    def rows(_warehouse, _semantic, metrics, where=None, group_by=None, limit=None):
        if "game_draw_rate" in metrics:
            return [{"drawn_games": 0, "eligible_games": 0, "game_draw_rate": None}]
        return [
            {
                "opening_wins": 60,
                "opening_draws": 20,
                "opening_losses": 20,
                "opening_score_games": 100,
                "opening_score_total": 70,
                "opening_player_score": 0.7,
                "win_rate": 0.6,
            }
        ]

    monkeypatch.setattr(semantic, "query_rows", rows)
    tools = type("T", (), {"project": PROJECT, "dataset_id": "a" * 24})()
    draw = semantic._draw_rate(tools, Path("w"), Path("m"))
    assert draw["value"] is None
    assert (draw["numerator"], draw["denominator"]) == (0, 0)
    score = semantic._opening_player_score(tools, Path("w"), Path("m"), SCORE_FILTERS)
    assert score["low_support"] is False
    assert score["score_rate"] == 0.7
    assert score["win_rate"] == 0.6


def test_missing_metricflow_import_falls_back(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def blocked(name, *args, **kwargs):
        if name == "metricflow" or name.startswith(("metricflow.", "metricflow_")):
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked)
    semantic._ENGINES.clear()

    def located(_project, _snapshot):
        return Path("warehouse.duckdb"), Path("semantic_manifest.json")

    monkeypatch.setattr(semantic, "published_mart", located)
    tools = type(
        "T",
        (),
        {"project": Path(), "snapshot": Path("s"), "dataset_id": "c" * 24},
    )()
    assert semantic.resolve_governed(tools, "game_draw_rate", {}, []) is None


def test_semantic_failures_fall_back(tmp_path, monkeypatch):
    tools = type(
        "T",
        (),
        {"project": tmp_path, "snapshot": tmp_path / "missing", "dataset_id": "b" * 24},
    )()
    assert semantic.published_mart(tmp_path, tmp_path / "missing") is None
    assert semantic.resolve_governed(tools, "game_draw_rate", {}, []) is None

    def located(_project, _snapshot):
        return Path("w"), Path("m")

    monkeypatch.setattr(semantic, "published_mart", located)

    def explode(*_args, **_kwargs):
        raise ImportError("metricflow missing")

    monkeypatch.setattr(semantic, "query_rows", explode)
    assert semantic.resolve_governed(tools, "game_draw_rate", {}, []) is None

    def missing_table(*_args, **_kwargs):
        raise RuntimeError("semantic query failed")

    monkeypatch.setattr(semantic, "query_rows", missing_table)
    assert semantic.resolve_governed(tools, "game_draw_rate", {}, []) is None


def test_tiny_product_draw_rate_uses_the_mart_and_a_poisoned_copy_diverges(
    tiny_product, monkeypatch
):
    tools = CheckedTools(tiny_product)
    mart = _mart(tiny_product)
    warehouse = mart / "warehouse.duckdb"
    analytical = tools.snapshot / "warehouse.duckdb"
    before = digest(warehouse)
    analytical_before = digest(analytical)
    calls = _spy(monkeypatch)
    sql_result = _sql_draw(tools)
    assert calls == []
    started = time.perf_counter()
    semantic_result = tools.query_metric("game_draw_rate", {})
    elapsed = time.perf_counter() - started
    assert calls
    assert semantic_result == sql_result
    assert set(semantic_result) == DRAW_KEYS
    assert semantic_result["numerator"] == 4
    assert semantic_result["denominator"] == 20
    assert semantic_result["value"] == 0.2
    pointer = tiny_product / "data/analytical-mart-current.json"
    saved_pointer = pointer.read_text()
    pointer.unlink()
    try:
        sql_usage = tools.query_metric("opening_usage", {"family": "None"})
        sql_grouped = tools.query_metric("opening_usage", {}, ["opening_family"])
    finally:
        pointer.write_text(saved_pointer)
    usage = tools.query_metric("opening_usage", {"family": "None"})
    grouped = tools.query_metric("opening_usage", {}, ["opening_family"])
    assert usage == sql_usage
    assert grouped == sql_grouped
    assert usage["numerator"] == 1
    assert usage["unknown_opening_games"] == 19
    assert usage["family"] == "None"
    assert [row["family"] for row in grouped["rows"]] == ["None"]
    assert digest(warehouse) == before
    assert digest(analytical) == analytical_before
    semantic.smoke_draw_rate(warehouse, mart / "semantic_manifest.json")
    errors = semantic.validate_configs(mart / "semantic_manifest.json")
    assert errors == []
    compiled = semantic._compile_sql(
        mart / "semantic_manifest.json", ["drawn_games", "eligible_games", "game_draw_rate"]
    )
    assert "utc_date" not in compiled
    manifest = read_json(mart / "manifest.json")
    source_id = read_json(tools.snapshot / "manifest.json")["source_snapshot_id"]
    assert manifest["snapshot_id"] == source_id
    assert manifest["model_sha256"] == model_hash(tiny_product)
    assert (mart / "model_hash.txt").read_text().strip() == manifest["model_sha256"]

    nulled = _copy_mart(tiny_product, "cd" * 12)
    with duckdb.connect(str(nulled / "warehouse.duckdb")) as connection:
        connection.execute(
            """update fact_game set utc_date = null
            where game_id = (
                select game_id from fact_game
                where result in ('1-0','0-1','1/2-1/2') and not marked_bot
                order by game_id limit 1)"""
        )
    _publish_copy(tiny_product, nulled)
    try:
        nulled_result = tools.query_metric("game_draw_rate", {})
    finally:
        write_json(tiny_product / "data/analytical-mart-current.json", {"mart_id": mart.name})
    assert nulled_result["numerator"] == 4
    assert nulled_result["denominator"] == 20
    assert nulled_result["value"] == 0.2
    assert digest(warehouse) == before

    poisoned = _copy_mart(tiny_product, "ab" * 12)
    with duckdb.connect(str(poisoned / "warehouse.duckdb")) as connection:
        connection.execute("update fact_game set result = '1-0' where result = '1/2-1/2'")
    _publish_copy(tiny_product, poisoned)
    try:
        poisoned_result = tools.query_metric("game_draw_rate", {})
    finally:
        write_json(tiny_product / "data/analytical-mart-current.json", {"mart_id": mart.name})
    assert poisoned_result["numerator"] != sql_result["numerator"]
    assert digest(analytical) == analytical_before
    assert digest(warehouse) == before

    hidden = mart / "manifest.json"
    saved = hidden.read_text()
    body = json.loads(saved)
    body["model_sha256"] = "0" * 64
    hidden.write_text(json.dumps(body))
    before_calls = len(calls)
    try:
        fallback = tools.query_metric("game_draw_rate", {})
    finally:
        hidden.write_text(saved)
    assert len(calls) == before_calls
    assert fallback == sql_result

    write_json(Path("/tmp/semantic-timings.json"), {"tiny_draw_rate_seconds": round(elapsed, 3)})


def test_missing_games_view_falls_back_without_leaking_sql(tiny_product, caplog):
    tools = CheckedTools(tiny_product)
    sql_result = _sql_draw(tools)
    pointer = tiny_product / "data/analytical-mart-current.json"
    saved = pointer.read_text()
    broken = _copy_mart(tiny_product, "12" * 12)
    with duckdb.connect(str(broken / "warehouse.duckdb")) as connection:
        connection.execute("drop view games")
    _publish_copy(tiny_product, broken)
    caplog.set_level(logging.WARNING)
    try:
        result = tools.query_metric("game_draw_rate", {})
    finally:
        pointer.write_text(saved)
    assert result == sql_result
    messages = [
        record.message
        for record in caplog.records
        if record.name == "chess_analytics.analyst.semantic"
    ]
    assert messages == ["semantic query failed; using reviewed SQL"]


def test_rewritten_semantic_manifest_falls_back_to_sql(tiny_product, monkeypatch):
    tools = CheckedTools(tiny_product)
    sql_result = _sql_draw(tools)
    calls = _spy(monkeypatch)
    rewritten = _copy_mart(tiny_product, "ef" * 12)
    semantic_path = rewritten / "semantic_manifest.json"
    original = semantic_path.read_text()
    assert original.count('"drawn_game"') == 1
    semantic_path.write_text(original.replace('"drawn_game"', '"eligible_game"', 1))
    manifest = read_json(rewritten / "manifest.json")
    manifest["mart_id"] = rewritten.name
    manifest["warehouse_sha256"] = digest(rewritten / "warehouse.duckdb")
    manifest["semantic_manifest_sha256"] = digest(semantic_path)
    write_json(rewritten / "manifest.json", manifest)
    pointer = tiny_product / "data/analytical-mart-current.json"
    saved = pointer.read_text()
    write_json(pointer, {"mart_id": rewritten.name})
    before_calls = len(calls)
    try:
        result = tools.query_metric("game_draw_rate", {})
    finally:
        pointer.write_text(saved)
    assert len(calls) == before_calls
    assert (result["numerator"], result["denominator"], result["value"]) == (
        sql_result["numerator"],
        sql_result["denominator"],
        sql_result["value"],
    )


def test_portfolio_product_metric_parity(portfolio_product, monkeypatch):
    tools = CheckedTools(portfolio_product)
    expected = read_json(PROJECT / "tests/fixtures/portfolio_expected.json")
    calls = _spy(monkeypatch)
    pointer = portfolio_product / "data/analytical-mart-current.json"
    saved = pointer.read_text()
    pointer.unlink()
    try:
        sql_draw = tools.query_metric("game_draw_rate", {})
    finally:
        pointer.write_text(saved)
    assert calls == []
    timings = {}
    started = time.perf_counter()
    draw = tools.query_metric("game_draw_rate", {})
    timings["draw_rate_seconds"] = round(time.perf_counter() - started, 3)
    assert calls
    assert draw == sql_draw
    assert draw["numerator"] == expected["draws"]
    assert draw["denominator"] == expected["eligible_games"]
    warehouse = _mart(portfolio_product) / "warehouse.duckdb"
    before = digest(warehouse)

    for family, games, score in (
        ("Sicilian Defense", expected["sicilian_games"], expected["sicilian_white_score"]),
        ("French Defense", expected["french_games"], expected["french_white_score"]),
    ):
        filters = {**SCORE_FILTERS, "family": family}
        pointer.unlink()
        try:
            sql_usage = tools.query_metric("opening_usage", {"family": family})
            sql_player = tools.query_metric("opening_player_score", filters)
        finally:
            pointer.write_text(saved)
        before_calls = len(calls)
        started = time.perf_counter()
        usage = tools.query_metric("opening_usage", {"family": family})
        timings[f"{family}_usage_seconds"] = round(time.perf_counter() - started, 3)
        started = time.perf_counter()
        player = tools.query_metric("opening_player_score", filters)
        timings[f"{family}_score_seconds"] = round(time.perf_counter() - started, 3)
        assert len(calls) > before_calls
        assert usage == sql_usage
        assert player == sql_player
        assert set(usage) == USAGE_KEYS
        assert set(player) == SCORE_KEYS
        assert (usage["numerator"], usage["denominator"], usage["value"]) == (
            games,
            expected["opening_known_games"],
            games / expected["opening_known_games"],
        )
        assert player["score_rate"] == score
        assert player["win_rate"] == player["wins"] / player["eligible_player_games"]
        assert player["low_support"] is True

    pointer.unlink()
    try:
        sql_grouped = tools.query_metric("opening_usage", {}, ["opening_family"])
    finally:
        pointer.write_text(saved)
    grouped = tools.query_metric("opening_usage", {}, ["opening_family"])
    assert grouped == sql_grouped
    assert grouped["denominator"] == expected["opening_known_games"]
    assert [(row["family"], row["numerator"]) for row in grouped["rows"]] == [
        ("French Defense", expected["french_games"]),
        ("Sicilian Defense", expected["sicilian_games"]),
    ]
    assert grouped["truncated"] is False
    compare_filters = {
        "families": ["Sicilian Defense", "French Defense"],
        "color": "white",
        "rating_min": 1400,
        "rating_max_exclusive": 1600,
        "base_seconds": 60,
        "increment_seconds": 0,
    }
    before_calls = len(calls)
    started = time.perf_counter()
    compared = tools.compare_openings(compare_filters)
    timings["compare_openings_seconds"] = round(time.perf_counter() - started, 3)
    assert len(calls) > before_calls
    assert compared["families"][0]["score_rate"] == expected["sicilian_white_score"]
    assert digest(warehouse) == before

    plan = PROJECT / "evals/replay_plans/governed_draw_rate.json"
    record = json.loads(plan.read_text())
    before_calls = len(calls)
    answer = replay(portfolio_product, record["question"], plan)
    assert len(calls) > before_calls
    assert answer["status"] == "answered"
    assert answer["result"]["numerator"] == expected["draws"]
    assert answer["result"]["denominator"] == expected["eligible_games"]
    existing = {}
    timing_path = Path("/tmp/semantic-timings.json")
    if timing_path.exists():
        existing = read_json(timing_path)
    write_json(timing_path, {**existing, **timings})
