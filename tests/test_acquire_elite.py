"""Offline Elite acquisition: a stand-in ZIP, then the cache, with no network."""

import importlib.util
import io
import json
import zipfile
from pathlib import Path

import pytest

from chess_analytics.common import digest

ROOT = Path(__file__).resolve().parents[1]


def load_script():
    spec = importlib.util.spec_from_file_location(
        "acquire_elite", ROOT / "scripts/acquire_elite.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Response(io.BytesIO):
    def __init__(self, payload, status=200):
        super().__init__(payload)
        self.status = status
        self.url = "https://database.nikonoel.fr/lichess_elite_2025-11.zip"
        self.headers = {"Content-Length": str(len(payload))}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def zip_bytes():
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr(
            "lichess_elite_2025-11.pgn",
            '[Event "Rated Blitz test"]\n\n1. e4 e5 1-0\n',
        )
    return payload.getvalue()


def prepare(tmp_path, monkeypatch, elite, payload):
    config = tmp_path / "config"
    config.mkdir()
    (config / "opening-corpus.json").write_text((ROOT / "config/opening-corpus.json").read_text())
    calls = []

    def urlopen(request, timeout=0):
        calls.append((request.full_url, timeout))
        return Response(payload)

    monkeypatch.setattr(elite, "PROJECT", tmp_path)
    monkeypatch.setattr(elite.urllib.request, "urlopen", urlopen)
    return calls


def test_import_does_not_download(monkeypatch):
    def refuse(*_args, **_kwargs):
        raise AssertionError("import downloaded an Elite archive")

    monkeypatch.setattr("urllib.request.urlopen", refuse)
    load_script()


def test_acquire_downloads_once_and_reuses_the_receipt(tmp_path, monkeypatch, capsys):
    elite = load_script()
    payload = zip_bytes()
    calls = prepare(tmp_path, monkeypatch, elite, payload)
    elite.main()
    first = json.loads(capsys.readouterr().out)
    assert calls == [("https://database.nikonoel.fr/lichess_elite_2025-11.zip", 60)]
    extracted = tmp_path / "data/opening-sources/elite/lichess_elite_2025-11.pgn"
    assert extracted.read_bytes().startswith(b'[Event "Rated Blitz test"]')
    downloaded = tmp_path / "data/opening-sources/elite/lichess_elite_2025-11.zip"
    assert first["download_sha256"] == digest(downloaded)
    assert first["pgn_sha256"] == digest(extracted)
    assert first["publisher_checksum_verified"] is False
    calls.clear()
    elite.main()
    second = json.loads(capsys.readouterr().out)
    assert calls == []
    assert second["pgn_sha256"] == first["pgn_sha256"]


def test_cached_zip_mismatch_does_not_download_again(tmp_path, monkeypatch):
    elite = load_script()
    calls = prepare(tmp_path, monkeypatch, elite, zip_bytes())
    elite.main()
    target = tmp_path / "data/opening-sources/elite/lichess_elite_2025-11.zip"
    target.write_bytes(target.read_bytes() + b"x")
    calls.clear()
    with pytest.raises(ValueError, match="differs from its acquisition receipt"):
        elite.main()
    assert calls == []


def test_http_failure_is_retained_without_a_published_zip(tmp_path, monkeypatch):
    elite = load_script()
    payload = zip_bytes()
    calls = prepare(tmp_path, monkeypatch, elite, payload)

    def refuse(request, timeout=0):
        calls.append(request.full_url)
        return Response(payload, status=404)

    monkeypatch.setattr(elite.urllib.request, "urlopen", refuse)
    with pytest.raises(ValueError, match="HTTP 200"):
        elite.main()
    root = tmp_path / "data/opening-sources/elite"
    assert not (root / "lichess_elite_2025-11.zip").exists()
    failure = json.loads((root / "acquisition-failure.json").read_text())
    assert failure["error"].startswith("ValueError:")


def test_low_disk_stops_after_a_verified_extract(tmp_path, monkeypatch):
    elite = load_script()
    prepare(tmp_path, monkeypatch, elite, zip_bytes())
    elite.main()
    monkeypatch.setattr(elite.shutil, "disk_usage", lambda _path: type("Usage", (), {"free": 1})())
    with pytest.raises(ValueError, match="less than 5 GB free"):
        elite.main()
