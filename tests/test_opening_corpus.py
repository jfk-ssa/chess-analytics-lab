"""Offline opening-corpus checks. No archive download and no retained bulk source."""

import importlib.util
import json
from pathlib import Path

import duckdb
import pytest

from chess_analytics.common import digest, write_json

ROOT = Path(__file__).resolve().parents[1]


def load_script():
    spec = importlib.util.spec_from_file_location(
        "build_opening_corpus", ROOT / "scripts/build_opening_corpus.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def warehouse(path, rating):
    with duckdb.connect(str(path / "warehouse.duckdb")) as db:
        db.execute(
            """
            create table opening_game (
              provider varchar, game_id varchar, white_rating integer, black_rating integer,
              marked_bot boolean, result varchar, ply_count integer, source_period varchar
            )
            """
        )
        db.execute(
            """
            insert into opening_game
            values ('lichess', 'abcd1234', ?, 1500, false, '1-0', 30, '2025-11')
            """,
            [rating],
        )
    manifest = {
        "artifacts": {"warehouse.duckdb": digest(path / "warehouse.duckdb")},
        "policy": {"minimum_rating_both_players": 1000, "minimum_plies": 20},
        "counts": {"training_games": 1},
    }
    write_json(path / "manifest.json", manifest)


def test_publication_accepts_the_rating_floor_and_rejects_a_lower_game(tmp_path):
    corpus = load_script()
    good = tmp_path / "good"
    bad = tmp_path / "bad"
    good.mkdir()
    bad.mkdir()
    warehouse(good, 1000)
    warehouse(bad, 999)
    assert corpus.validate_publication(good)["counts"]["training_games"] == 1
    with pytest.raises(ValueError, match="does not reconcile"):
        corpus.validate_publication(bad)


def test_checked_source_rejects_a_changed_pgn(tmp_path, monkeypatch):
    corpus = load_script()
    monkeypatch.setattr(corpus, "PROJECT", tmp_path)
    monkeypatch.setattr(corpus, "validate_snapshot", lambda _snapshot: None)
    snapshot = tmp_path / "data/published/abc123"
    snapshot.mkdir(parents=True)
    source = tmp_path / "data/game.pgn"
    source.write_text("original\n")
    write_json(
        snapshot / "manifest.json",
        {
            "source_file": "game.pgn",
            "source_sha256": digest(source),
            "plan": {"period": "2025-11", "complete_archive": True},
            "counts": {"accepted": 1},
        },
    )
    found = corpus.checked_source(snapshot / "manifest.json")
    assert found["snapshot_id"] == "abc123"
    assert found["source_sha256"] == digest(source)
    source.write_text("changed\n")
    with pytest.raises(ValueError, match="missing or changed source"):
        corpus.checked_source(snapshot / "manifest.json")


def test_main_rejects_a_malformed_elite_snapshot_without_downloading(tmp_path, monkeypatch):
    corpus = load_script()
    (tmp_path / "config").mkdir()
    (tmp_path / "config/opening-corpus.json").write_text(
        (ROOT / "config/opening-corpus.json").read_text()
    )
    elite = tmp_path / "data/elite"
    elite.mkdir(parents=True)
    (elite / "elite-current.json").write_text(json.dumps({"snapshot_id": "not-a-snapshot"}))

    def refuse(*_args, **_kwargs):
        raise AssertionError("opening corpus build downloaded a file")

    monkeypatch.setattr(corpus, "PROJECT", tmp_path)
    monkeypatch.setattr("urllib.request.urlopen", refuse)
    with pytest.raises(ValueError, match="invalid Elite source snapshot identity"):
        corpus.main()
