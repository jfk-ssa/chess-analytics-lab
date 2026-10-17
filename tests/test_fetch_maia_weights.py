"""Offline checks for the manual Maia download. The real host is never contacted."""

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from chess_analytics.analyst.maia_pins import PINS
from chess_analytics.analyst.tools import CheckedTools
from chess_analytics.common import write_json

ROOT = Path(__file__).resolve().parents[1]
DISTRIBUTION = (ROOT / "tests/fixtures/maia/distribution.json").read_bytes()


def _load():
    path = ROOT / "scripts/fetch_maia_weights.py"
    spec = importlib.util.spec_from_file_location("fetch_maia_weights", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Body:
    def __init__(self, data: bytes, status: int = 200):
        self.data = data
        self.status = status
        self.offset = 0

    def read(self, count=-1):
        if self.offset >= len(self.data):
            return b""
        if count is None or count < 0:
            count = len(self.data)
        chunk = self.data[self.offset : self.offset + count]
        self.offset += len(chunk)
        return chunk

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def _pin(data: bytes) -> dict:
    return {**PINS["23M"], "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


def test_importing_the_script_does_not_download():
    module = _load()
    assert "does not download" in (module.__doc__ or "")
    text = (ROOT / "scripts/fetch_maia_weights.py").read_text()
    assert "\nif __name__" in text


def test_matching_body_is_kept_and_printed_as_config(tmp_path):
    module = _load()
    seen = {}

    def opener(url):
        seen["url"] = url
        return _Body(DISTRIBUTION)

    document = module.fetch_weights("23M", tmp_path, opener, pins={"23M": _pin(DISTRIBUTION)})
    final = tmp_path / "maia3-23m.pt"
    assert final.read_bytes() == DISTRIBUTION
    assert not (tmp_path / ".maia3-23m.pt.partial").exists()
    assert PINS["23M"]["hf_repo"] in seen["url"]
    assert PINS["23M"]["hf_revision"] in seen["url"]
    assert document["models"]["23M"]["sha256"] == hashlib.sha256(DISTRIBUTION).hexdigest()
    assert document["models"]["23M"]["bytes"] == len(DISTRIBUTION)
    assert document["models"]["23M"]["weights_path"] == str(final.resolve())
    project = tmp_path / "project"
    write_json(project / "config/maia.json", document)
    tools = CheckedTools.__new__(CheckedTools)
    tools.project = project
    tools.dataset_id = "b" * 24
    result = tools.execute(
        "predict_human_moves",
        {"moves": ["d2d4"], "rating_self": 1500, "rating_opp": 1500},
    )
    assert result["moves"][0]["uci"] == "e7e5"
    assert result["reason"] is None


def test_hash_mismatch_and_http_error_delete_the_partial(tmp_path):
    module = _load()
    pin = _pin(b"good")

    def opener(_url):
        return _Body(b"bad!")

    with pytest.raises(ValueError, match="hash mismatch"):
        module.fetch_weights("23M", tmp_path, opener, pins={"23M": pin})
    assert list(tmp_path.iterdir()) == []

    def missing(_url):
        return _Body(b"good", status=404)

    with pytest.raises(ValueError, match="download failed"):
        module.fetch_weights("23M", tmp_path, missing, pins={"23M": pin})
    assert list(tmp_path.iterdir()) == []


def test_destination_must_be_gitignored_and_alias_can_come_from_config(tmp_path):
    module = _load()
    assert module.path_is_gitignored(ROOT, ROOT / "data/models/maia3-23m.pt")
    assert module.path_is_gitignored(ROOT, ROOT / "config/maia.json")
    assert not module.path_is_gitignored(ROOT, ROOT / "config/maia.example.json")
    config = tmp_path / "maia.json"
    config.write_text(json.dumps({"default_alias": "5M"}))
    assert module.alias_from_config(config) == "5M"

    def opener(_url):
        raise AssertionError("download started")

    code = module.main(
        ["--alias", "23M", "--dest", str(tmp_path), "--project", str(ROOT)],
        opener=opener,
    )
    assert code == 1
    assert module.INSTALL_LINE == "uv sync --locked --extra maia"
