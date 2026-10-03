import io
import json

import duckdb
import pytest

from chess_analytics.cli import fixture_plan, main
from chess_analytics.common import digest, read_json, writer_lock
from chess_analytics.ingest.acquire import acquire, bounded_copy
from chess_analytics.ingest.pgn import normalize, records
from chess_analytics.ingest.pipeline import ingest
from chess_analytics.metrics.draw_rate import draw_rate
from chess_analytics.warehouse.snapshots import build, current, report, validate_snapshot


def first_record(project):
    return next(records(project / "tests/fixtures/tiny.pgn", fixture_plan(project)))[1]


def run_fixture(project, root, source=None):
    source = source or project / "tests/fixtures/tiny.pgn"
    stage = ingest(project, root, "tiny", source, fixture_plan(project))
    return stage, build(project, root, "tiny")


def test_hand_checked_metric_and_repeat(project, tmp_path):
    stage, snapshot = run_fixture(project, tmp_path)
    result = report(project, snapshot)
    expected = read_json(project / "tests/fixtures/expected.json")
    assert result["counts"] == expected["counts"]
    for key, value in expected["metric"].items():
        assert result["metric"][key] == value
    assert result["coverage"]["missing"]["played_at"] == 22
    assert not any(validate_snapshot(snapshot).values())
    _, second = run_fixture(project, tmp_path)
    assert snapshot == second
    assert report(project, second)["metric"] == result["metric"]
    assert read_json(stage / "manifest.json")["counts"]["seen"] == 26


def test_identical_duplicate_does_not_inflate(project, tmp_path):
    source = tmp_path / "duplicate.pgn"
    source.write_text(first_record(project) * 2)
    stage, snapshot = run_fixture(project, tmp_path / "data", source)
    assert read_json(stage / "manifest.json")["counts"]["duplicate"] == 1
    with duckdb.connect(str(snapshot / "warehouse.duckdb"), read_only=True) as c:
        assert c.execute("select count(*) from fact_game").fetchone()[0] == 1
        assert c.execute("select count(*) from fact_player_game").fetchone()[0] == 2


def test_conflict_withholds_candidate_and_preserves_old(project, tmp_path):
    root = tmp_path / "data"
    _, previous = run_fixture(project, root)
    raw = first_record(project)
    source = tmp_path / "conflict.pgn"
    source.write_text(raw + raw.replace('"1500"', '"1600"'))
    with pytest.raises(ValueError, match="conflicting duplicate"):
        ingest(project, root, "tiny", source, fixture_plan(project))
    assert current(root, "tiny") == previous
    failures = [read_json(p) for p in (root / "staging").glob("*/manifest.json")]
    assert any(m["status"] == "failed" and m["counts"]["conflict"] == 1 for m in failures)
    validate_snapshot(previous)


def test_failure_before_publish_then_retry(project, tmp_path):
    root = tmp_path / "data"
    _, previous = run_fixture(project, root)
    source = tmp_path / "different.pgn"
    source.write_text(first_record(project))
    stage = ingest(project, root, "tiny", source, fixture_plan(project))
    with pytest.raises(RuntimeError, match="injected"):
        build(project, root, "tiny", fail_before_publish=True)
    assert current(root, "tiny") == previous
    assert any(read_json(p)["status"] == "failed" for p in stage.glob("build-*.json"))
    retried = build(project, root, "tiny")
    _, clean = run_fixture(project, tmp_path / "clean", source)
    assert report(project, retried)["metric"] == report(project, clean)["metric"]
    assert retried.name == clean.name


@pytest.mark.parametrize(
    "field,limit,message",
    [
        ("max_source_bytes", 1, "source byte"),
        ("max_decompressed_bytes", 1, "decompressed byte"),
        ("max_record_bytes", 20, "record exceeds"),
        ("max_games", 1, "game limit"),
        ("max_generated_bytes", 100, "allowance"),
        ("expected_records", 1, "record count"),
    ],
)
def test_resource_and_completeness_limits(project, tmp_path, field, limit, message):
    plan = {**fixture_plan(project), field: limit}
    with pytest.raises(ValueError, match=message):
        ingest(project, tmp_path, "tiny", project / "tests/fixtures/tiny.pgn", plan)
    assert not (tmp_path / "tiny-current.json").exists()
    assert any(read_json(p)["status"] == "failed" for p in tmp_path.glob("staging/*/manifest.json"))


def test_bounded_download_without_content_length(tmp_path):
    target = tmp_path / "source.part"
    with pytest.raises(ValueError, match="byte limit"):
        bounded_copy(io.BytesIO(b"123456789"), target, 5, tmp_path, 10_000_000)
    assert target.stat().st_size <= 5


def test_cached_checksum_mismatch_never_downloads(project, tmp_path):
    plan = read_json(project / "config/datasets.json")["foundation"]
    raw = tmp_path / "raw"
    raw.mkdir()
    target = raw / plan["url"].rsplit("/", 1)[-1]
    target.write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="cached source"):
        acquire(tmp_path, plan)
    assert target.read_bytes() == b"corrupt"


def test_malformed_and_missing_fields(project):
    raw = first_record(project)
    assert normalize(raw.replace('"1500"', '"?"'), 1)[0] == "accepted"
    assert normalize(raw.replace('"1500"', '"oops"'), 1)[1] == "invalid_rating"
    assert normalize(raw.replace("1. e4", "1. Bh6"), 1)[1] == "illegal_or_malformed_moves"
    assert normalize(raw.rstrip().removesuffix("1-0"), 1)[1] == "missing_or_mismatched_termination"
    assert normalize(raw.replace('"1-0"', '"0-1"'), 1)[1] == "missing_or_mismatched_termination"
    assert (
        normalize(raw.replace('[WhiteElo "1500"]', "[WhiteElo 1500]"), 1)[1] == "malformed_header"
    )
    unknown = normalize(raw.replace('[UTCDate "2020.01.01"]\n', ""), 1)[2][0]
    assert unknown["played_at"] is None and unknown["utc_date"] is None


def test_missing_clock_and_mate_annotation_preserved(project):
    rows = list(records(project / "tests/fixtures/tiny.pgn", fixture_plan(project)))
    assert "[%eval #3]" in rows[1][1]
    assert normalize(rows[1][1], 2)[0] == "accepted"
    assert normalize(rows[2][1], 3)[0] == "accepted"  # no clock is not a zero clock


def test_empty_denominator_is_null(project, tmp_path):
    source = tmp_path / "unknown.pgn"
    source.write_text(first_record(project).replace("1-0", "*"))
    _, snapshot = run_fixture(project, tmp_path / "data", source)
    result = report(project, snapshot)["metric"]
    assert result["denominator"] == 0
    assert result["value"] is None
    assert result["unknown_results"] == 1


def test_artifact_tamper_blocks_publication(project, tmp_path):
    stage = ingest(
        project, tmp_path, "tiny", project / "tests/fixtures/tiny.pgn", fixture_plan(project)
    )
    with (stage / "games.jsonl").open("a") as out:
        out.write("{}\n")
    with pytest.raises(ValueError, match="checksum mismatch"):
        build(project, tmp_path, "tiny")


def test_read_only_snapshot_and_writer_lock(project, tmp_path):
    _, snapshot = run_fixture(project, tmp_path)
    with duckdb.connect(str(snapshot / "warehouse.duckdb"), read_only=True) as c:
        with pytest.raises(duckdb.Error):
            c.execute("delete from fact_game")
        assert draw_rate(c, project)["denominator"] == 20
    with writer_lock(tmp_path), pytest.raises(ValueError, match="another local writer"):
        with writer_lock(tmp_path):
            pass


def test_cli_offline_and_no_live_command(project, tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "DO-NOT-USE-WORKPLACE-KEY")
    assert main(["--project", str(project), "--data-dir", str(tmp_path), "demo"]) == 0
    assert json.loads(capsys.readouterr().out)["metric"]["value"] == 0.2
    with pytest.raises(SystemExit):
        main(["eval", "--mode", "live"])


def test_download_checksum_success_and_no_network_reuse(project, tmp_path, monkeypatch):
    class Response(io.BytesIO):
        status = 200
        headers = {}

    payload = b"bounded test archive"
    sample = tmp_path / "sample"
    sample.write_bytes(payload)
    plan = {**read_json(project / "config/datasets.json")["foundation"], "sha256": digest(sample)}
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: Response(payload))
    first = acquire(tmp_path, plan)
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: pytest.fail("downloaded twice"))
    assert acquire(tmp_path, plan) == first
    assert read_json(tmp_path / "raw/acquisition.json")["publisher_checksum_verified"]
