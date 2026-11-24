"""Mutate identity inputs in isolated, offline fixture publications."""

import hashlib
import json
import os
import runpy
import sys
from pathlib import Path

import duckdb
import pytest

from chess_analytics.analyst.live_runner import build_config
from chess_analytics.analyst.provider import quote_request
from chess_analytics.analyst.semantic import published_mart
from chess_analytics.analyst.tools import CheckedTools
from chess_analytics.common import digest, read_json, write_json, writer_lock
from chess_analytics.corpus.publish import analytics_hash, build_analytical, snapshot_identity
from chess_analytics.corpus.source import extracted_path
from chess_analytics.dashboard.analysis import current_snapshot
from chess_analytics.ingest.pipeline import implementation_hash, ingest
from chess_analytics.marts.pipeline import build_mart, mart_id, model_hash, validate_mart
from chess_analytics.portfolio_demo import QUESTIONS, _stage_project
from chess_analytics.warehouse.snapshots import build, report

PACKAGE = "src/chess_analytics"
DATASET = "analytical"
DBT = Path(sys.executable).with_name("dbt")


def _reingest(project):
    root = project / "data"
    plan = read_json(project / "config/datasets.json")[DATASET]
    with writer_lock(root):
        ingest(project, root, DATASET, extracted_path(root, plan), plan)
        return build(project, root, DATASET)


def _publish_moves(project):
    root = project / "data"
    with writer_lock(root):
        return build_analytical(project, root)


def _publish_mart(project, materialize=build_mart):
    root = project / "data"
    with writer_lock(root):
        return materialize(project, root, DATASET, DBT)


@pytest.fixture
def staged(project, tmp_path):
    dest = tmp_path / "project"
    _stage_project(project, dest)
    _reingest(dest)
    _publish_moves(dest)
    return dest


def _quote(project):
    config = build_config(model="gpt-6-luna", max_run_usd=1, acknowledged=True)
    return quote_request(project, QUESTIONS["opening"], config)


def _instructions_hash(project, dataset_id):
    instructions = json.loads(_quote(project)["body"])["instructions"]
    assert f"Dataset: {dataset_id}." in instructions
    return hashlib.sha256(instructions.encode()).hexdigest()


def _mutate(project, path, before, after):
    path = project / path
    source = path.read_text()
    assert before in source
    path.write_text(source.replace(before, after, 1))


@pytest.mark.parametrize(
    ("path", "before", "after"),
    [
        ("corpus/metrics.py", "numerator / denominator", "numerator / (denominator + 1)"),
        ("dashboard/analysis.py", "0.025 * (len(values)", "0.05 * (len(values)"),
        ("analyst/semantic.py", "return not filters and not group_by", "return False"),
    ],
)
def test_analytical_changes_invalidate_current_tools_and_quote(staged, path, before, after):
    old_id = CheckedTools(staged).dataset_id
    old_instructions = _instructions_hash(staged, old_id)
    manifest = read_json(current_snapshot(staged) / "manifest.json")
    implementation = implementation_hash(staged)
    _mutate(staged, f"{PACKAGE}/{path}", before, after)

    assert implementation_hash(staged) == implementation
    assert analytics_hash(staged) != manifest["analytics_implementation_sha256"]
    assert (
        snapshot_identity(staged, manifest["source_snapshot_id"], manifest["source_sha256"])
        != old_id
    )
    with pytest.raises(ValueError, match="analytical implementation differs"):
        CheckedTools(staged)
    with pytest.raises(ValueError, match="analytical implementation differs"):
        _quote(staged)

    assert _reingest(staged).name == manifest["source_snapshot_id"]
    rebuilt = _publish_moves(staged)
    assert rebuilt.name != old_id
    assert CheckedTools(staged).dataset_id == rebuilt.name
    assert _instructions_hash(staged, rebuilt.name) != old_instructions


def test_recursive_analyst_helper_is_hashed(staged):
    original = analytics_hash(staged)
    implementation = implementation_hash(staged)
    helper = staged / PACKAGE / "analyst/new/helper.py"
    helper.parent.mkdir()
    helper.write_text("def value():\n    return 1\n")
    assert analytics_hash(staged) != original
    assert implementation_hash(staged) == implementation


@pytest.mark.parametrize("identity", [None, 1, "0" * 23, "g" * 24])
def test_current_snapshot_rejects_invalid_pointer(staged, identity):
    pointer = staged / "data/analytical-moves-current.json"
    write_json(pointer, {} if identity is None else {"analytical_id": identity})
    with pytest.raises(ValueError, match="invalid analytical snapshot identity"):
        current_snapshot(staged)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("analytics_implementation_sha256", None, "analytical implementation differs"),
        ("source_snapshot_id", None, "analytical snapshot identity mismatch"),
        ("source_snapshot_id", "0" * 24, "analytical snapshot identity mismatch"),
        ("source_sha256", None, "analytical snapshot identity mismatch"),
        ("source_sha256", "0" * 64, "analytical snapshot identity mismatch"),
        ("analytical_id", None, "invalid analytical snapshot manifest"),
    ],
)
def test_current_snapshot_checks_manifest_identity(staged, field, value, message):
    path = current_snapshot(staged) / "manifest.json"
    manifest = read_json(path)
    if value is None:
        del manifest[field]
    else:
        manifest[field] = value
    write_json(path, manifest)
    for read in (current_snapshot, CheckedTools, _quote):
        with pytest.raises(ValueError, match=message):
            read(staged)


@pytest.mark.parametrize(
    "path", [f"{PACKAGE}/marts/pipeline.py", "dbt/models/marts/move_evals.sql"]
)
def test_mart_changes_invalidate_current_tools_and_quote(staged, path):
    implementation = implementation_hash(staged)
    analytical = analytics_hash(staged)
    model = model_hash(staged)
    with (staged / path).open("a") as file:
        file.write("\n")

    assert implementation_hash(staged) == implementation
    assert analytics_hash(staged) != analytical
    assert model_hash(staged) != model
    for read in (CheckedTools, _quote):
        with pytest.raises(ValueError, match="analytical implementation differs"):
            read(staged)


@pytest.mark.dbt
@pytest.mark.parametrize(
    ("path", "before", "after"),
    [
        (
            f"{PACKAGE}/marts/pipeline.py",
            ').create("fact_move")',
            ').filter("ply > 1").create("fact_move")',
        ),
        ("dbt/models/marts/move_evals.sql", "materialized='view'", "materialized='table'"),
    ],
)
def test_mart_changes_publish_new_model_and_preserve_previous_bytes(staged, path, before, after):
    if not DBT.is_file():
        if os.environ.get("CHESSLAB_REQUIRE_DBT") == "1":
            pytest.fail("mart mutation tests need the dbt extra")
        pytest.skip("install the optional dbt extra")

    old_moves = current_snapshot(staged)
    old_analytical = read_json(old_moves / "manifest.json")
    implementation = implementation_hash(staged)
    old_mart = _publish_mart(staged)
    old_manifest = validate_mart(old_mart)
    old_bytes = {file.name: digest(file) for file in old_mart.iterdir()}
    assert published_mart(staged, old_moves) is not None
    _mutate(staged, path, before, after)
    assert implementation_hash(staged) == implementation
    assert analytics_hash(staged) != old_analytical["analytics_implementation_sha256"]
    assert model_hash(staged) != old_manifest["model_sha256"]
    assert mart_id(staged, old_manifest["snapshot_id"]) != old_mart.name
    assert published_mart(staged, old_moves) is None  # Same source, stale model hash.

    source = _reingest(staged)
    assert source.name == old_manifest["snapshot_id"]
    assert _publish_moves(staged) != old_moves
    if path.endswith(".py"):
        rebuilt = _publish_mart(staged, runpy.run_path(str(staged / path))["build_mart"])
        with duckdb.connect(str(rebuilt / "warehouse.duckdb"), read_only=True) as con:
            assert con.execute("select min(ply) from fact_move").fetchone() == (2,)
    else:
        rebuilt = _publish_mart(staged)
    assert rebuilt.name == mart_id(staged, source.name) != old_mart.name
    assert validate_mart(rebuilt)["model_sha256"] == model_hash(staged)
    assert (rebuilt / "model_hash.txt").read_text().strip() == model_hash(staged)
    assert {file.name: digest(file) for file in old_mart.iterdir()} == old_bytes
    assert published_mart(staged, current_snapshot(staged)) == (
        rebuilt / "warehouse.duckdb",
        rebuilt / "semantic_manifest.json",
    )


def test_generated_dbt_files_leave_identities_unchanged(staged):
    implementation = implementation_hash(staged)
    analytical = analytics_hash(staged)
    model = model_hash(staged)
    moves = current_snapshot(staged)
    source_id = read_json(moves / "manifest.json")["source_snapshot_id"]
    mart = mart_id(staged, source_id)
    for name in ("target", "logs", "dbt_packages"):
        directory = staged / "dbt" / name
        directory.mkdir()
        (directory / "generated.sql").write_text("select 1\n")
        (directory / "generated.yml").write_text("version: 2\n")

    assert implementation_hash(staged) == implementation
    assert analytics_hash(staged) == analytical
    assert model_hash(staged) == model
    assert _reingest(staged).name == source_id
    assert _publish_moves(staged) == moves
    assert mart_id(staged, source_id) == mart


@pytest.mark.parametrize(
    "path", ["eval_report.py", "public_extract.py", "dashboard_cube.py", "dashboard/dashboard.py"]
)
def test_presentation_changes_preserve_snapshot_ids_and_quote(staged, path):
    moves = current_snapshot(staged)
    manifest = read_json(moves / "manifest.json")
    implementation = implementation_hash(staged)
    instructions = _instructions_hash(staged, moves.name)
    with (staged / PACKAGE / path).open("a") as file:
        file.write("\n# Fixture presentation edit.\n")

    assert implementation_hash(staged) == implementation
    assert analytics_hash(staged) == manifest["analytics_implementation_sha256"]
    assert _reingest(staged).name == manifest["source_snapshot_id"]
    assert _publish_moves(staged) == moves
    assert _instructions_hash(staged, moves.name) == instructions


@pytest.mark.parametrize(
    "path",
    [
        f"{PACKAGE}/ingest/pgn.py",
        f"{PACKAGE}/warehouse/snapshots.py",
        f"{PACKAGE}/metrics/draw_rate.sql",
        f"{PACKAGE}/common.py",
        "contracts/tables.json",
    ],
)
def test_ingest_changes_require_fresh_snapshot(staged, path):
    root = staged / "data"
    manifest = read_json(current_snapshot(staged) / "manifest.json")
    old_source = root / "published" / manifest["source_snapshot_id"]
    implementation = implementation_hash(staged)
    with (staged / path).open("a") as file:
        file.write("\n")

    assert implementation_hash(staged) != implementation
    with pytest.raises(ValueError, match="implementation changed after ingest"):
        build(staged, root, DATASET)
    with pytest.raises(ValueError, match="snapshot implementation differs"):
        report(staged, old_source)
    assert _reingest(staged) != old_source
