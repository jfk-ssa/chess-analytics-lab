import sys
from pathlib import Path

import pytest

from chess_analytics.cli import fixture_plan
from chess_analytics.common import read_json
from chess_analytics.ingest.pipeline import ingest
from chess_analytics.warehouse.snapshots import build, current
from platform_m2.pipeline import build_mart, operational_report, rollback_mart, validate_mart

DBT = Path(sys.executable).with_name("dbt")
pytestmark = pytest.mark.skipif(not DBT.exists(), reason="install the optional dbt extra")


def test_dbt_recovery_backfill_and_drift(project, tmp_path):
    root = tmp_path / "data"
    fixture = project / "tests/fixtures/tiny.pgn"
    ingest(project, root, "tiny", fixture, fixture_plan(project))
    first_snapshot = build(project, root, "tiny")
    first_mart = build_mart(project, root, "tiny", DBT)
    assert validate_mart(first_mart)["observed"]["drawn"] == 4

    # A changed but valid local source creates a new version. A failed candidate
    # must not replace the previous usable mart, and its attempt stays inspectable.
    source = tmp_path / "one-game.pgn"
    source.write_text(
        fixture.read_text().split('[Event "', 2)[0]
        + '[Event "'
        + fixture.read_text().split('[Event "', 2)[1]
    )
    ingest(project, root, "tiny", source, fixture_plan(project))
    second_snapshot = build(project, root, "tiny")
    assert first_snapshot != second_snapshot
    with pytest.raises(RuntimeError, match="injected failure"):
        build_mart(project, root, "tiny", DBT, fail_before_publish=True)
    assert read_json(root / "tiny-mart-current.json")["mart_id"] == first_mart.name
    failed = [read_json(p) for p in (root / "marts/attempts").glob("*/attempt.json")]
    assert any(p["status"] == "failed" for p in failed)

    second_mart = build_mart(project, root, "tiny", DBT)
    clean_root = tmp_path / "clean"
    ingest(project, clean_root, "tiny", source, fixture_plan(project))
    build(project, clean_root, "tiny")
    clean_mart = build_mart(project, clean_root, "tiny", DBT)
    assert second_mart.name == clean_mart.name
    assert validate_mart(second_mart)["observed"] == validate_mart(clean_mart)["observed"]

    # Historical backfill never changes the current pointer; rollback validates
    # and deliberately switches it to an earlier published mart.
    assert build_mart(project, root, "tiny", DBT, source_id=first_snapshot.name) == first_mart
    assert read_json(root / "tiny-mart-current.json")["mart_id"] == second_mart.name
    assert rollback_mart(root, "tiny", first_mart.name) == first_mart
    assert read_json(root / "tiny-mart-current.json")["mart_id"] == first_mart.name
    operations = operational_report(root, "tiny")
    assert operations["source_drift"][0]["severity"] == "warning"
    assert any(run["status"] == "failed" for run in operations["mart_attempts"])
    assert operations["peak_memory_bytes"] is None


def test_dbt_failure_preserves_current_and_logs(project, tmp_path):
    root = tmp_path / "data"
    ingest(project, root, "tiny", project / "tests/fixtures/tiny.pgn", fixture_plan(project))
    build(project, root, "tiny")
    with pytest.raises(ValueError, match="dbt build failed"):
        build_mart(project, root, "tiny", Path("/usr/bin/false"))
    assert not (root / "tiny-mart-current.json").exists()
    attempts = list((root / "marts/attempts").iterdir())
    assert len(attempts) == 1
    assert read_json(attempts[0] / "attempt.json")["status"] == "failed"
    assert (attempts[0] / "dbt-stderr.log").exists()
    assert current(root, "tiny").exists()
    with pytest.raises(ValueError, match="24-character"):
        build_mart(project, root, "tiny", DBT, source_id="../../outside")
    with pytest.raises(ValueError, match="24-character"):
        rollback_mart(root, "tiny", "../../outside")
