"""Offline Elite ingestion: restore Site from LichessURL, then reuse the pipeline."""

import importlib.util
import json
from pathlib import Path

import pytest

from chess_analytics.common import digest

ROOT = Path(__file__).resolve().parents[1]
GAME = """[Event "Rated Classical test"]
[LichessURL "https://lichess.org/abcd1234"]
[White "Alpha"]
[Black "Beta"]
[Result "1-0"]
[UTCDate "2025.11.01"]
[WhiteElo "2600"]
[BlackElo "2400"]
[TimeControl "180+0"]

1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 1-0
"""


def load_script():
    spec = importlib.util.spec_from_file_location("ingest_elite", ROOT / "scripts/ingest_elite.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def project(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config/opening-corpus.json").write_text(
        (ROOT / "config/opening-corpus.json").read_text()
    )
    (tmp_path / "src").symlink_to(ROOT / "src")
    (tmp_path / "contracts").symlink_to(ROOT / "contracts")
    (tmp_path / "uv.lock").write_bytes((ROOT / "uv.lock").read_bytes())
    (tmp_path / "reports").mkdir()
    source = tmp_path / "data/opening-sources/elite"
    source.mkdir(parents=True)
    return tmp_path, source


def write_source(source, text):
    path = source / "lichess_elite_2025-11.pgn"
    path.write_text(text)
    (source / "lichess_elite_2025-11.receipt.json").write_text(
        json.dumps({"pgn_file": path.name, "pgn_sha256": digest(path), "url": "offline-fixture"})
    )
    return path


def test_ingest_restores_site_and_does_not_download(tmp_path, monkeypatch, capsys):
    elite = load_script()
    root, source = project(tmp_path)
    original = write_source(source, GAME)
    published = (ROOT / "reports/elite-2025-11-ingestion.json").read_bytes()

    def refuse(*_args, **_kwargs):
        raise AssertionError("Elite ingestion downloaded a file")

    monkeypatch.setattr(elite, "PROJECT", root)
    monkeypatch.setattr("urllib.request.urlopen", refuse)
    elite.main()
    adapted = (root / "data/elite/elite-2025-11-compatible.pgn").read_text()
    assert '[Site "https://lichess.org/abcd1234"]' in adapted
    assert '[LichessURL "https://lichess.org/abcd1234"]' in adapted
    assert (
        digest(original)
        == json.loads((source / "lichess_elite_2025-11.receipt.json").read_text())["pgn_sha256"]
    )
    report = json.loads((root / "reports/elite-2025-11-ingestion.json").read_text())
    assert report["counts"]["accepted"] == 1
    assert report["counts"]["seen"] == 1
    assert report["adapter"]["games"] == 1
    assert (ROOT / "reports/elite-2025-11-ingestion.json").read_bytes() == published
    output = capsys.readouterr().out
    assert "snapshot" in output
    elite.main()
    again = json.loads((root / "reports/elite-2025-11-ingestion.json").read_text())
    assert again["adapter"]["source_sha256"] == report["adapter"]["source_sha256"]


def test_missing_lichess_url_fails_before_ingestion(tmp_path, monkeypatch):
    elite = load_script()
    root, source = project(tmp_path)
    write_source(source, GAME.replace("[LichessURL", "[WhiteURL"))
    monkeypatch.setattr(elite, "PROJECT", root)
    with pytest.raises(ValueError, match="no unambiguous LichessURL"):
        elite.main()
    assert not (root / "data/elite/elite-2025-11-compatible.pgn").exists()


def test_changed_source_is_rejected_before_adaptation(tmp_path, monkeypatch):
    elite = load_script()
    root, source = project(tmp_path)
    path = write_source(source, GAME)
    path.write_text(GAME + "\n")
    monkeypatch.setattr(elite, "PROJECT", root)
    with pytest.raises(ValueError, match="differs from its retained receipt"):
        elite.main()
