import io
from pathlib import Path
from typing import ClassVar

import pytest
import zstandard

from chess_analytics.common import digest, read_json
from chess_analytics.corpus.moves import move_rows
from chess_analytics.corpus.source import acquire_prefix, extract_complete_games


def test_clock_proxy_uses_prior_same_side_and_mover_perspective():
    raw = """[Event "Rated Blitz test"]
[Site "https://lichess.org/abcdefgh"]
[Result "1-0"]
[TimeControl "60+0"]

1. e4 {[%clk 0:01:00] [%eval 0.00]} e5 {[%clk 0:01:00] [%eval 0.00]}
2. Nf3 {[%clk 0:00:05] [%eval 2.50]} Nc6 {[%clk 0:00:04] [%eval 5.00]}
3. Bb5 {[%clk 0:00:04] [%eval 2.50]} a6 {[%clk 0:00:03] [%eval #3]} 1-0
"""
    rows = move_rows(raw, "abcdefgh", 60, 0)
    assert rows[0]["clock_before_seconds"] is None
    assert rows[2]["clock_before_seconds"] == 60
    assert rows[2]["centipawn_deterioration"] == 0
    assert rows[3]["color"] == "black" and rows[3]["error_proxy"] is True
    assert rows[4]["clock_bucket"] == "under_10" and rows[4]["error_proxy"] is True
    assert rows[5]["eval_after_mate_white"] == 3
    assert rows[5]["error_proxy"] is None


def test_fixed_prefix_requires_range_and_discards_open_tail(tmp_path, monkeypatch):
    complete = """[Event "Rated Blitz test"]
[Site "https://lichess.org/abcdefgh"]
[Result "1-0"]

1. e4 e5 1-0

"""
    partial = """[Event "Rated Blitz test"]
[Site "https://lichess.org/ijklmnop"]
[Result "1-0"]

1. e4
"""
    payload = zstandard.ZstdCompressor().compress((complete * 2 + partial).encode())
    plan = {
        "url": "https://database.lichess.org/standard/fixed.pgn.zst",
        "period": "fixture",
        "range_start": 0,
        "range_end_inclusive": len(payload) - 1,
        "max_download_bytes": len(payload),
        "archive_listed_bytes": len(payload) + 100,
        "archive_listed_games": 1000,
        "compressed_prefix_sha256": digest_bytes(tmp_path, payload),
        "max_source_bytes": 1_000_000,
        "max_decompressed_bytes": 1_000_000,
        "max_generated_bytes": 1_000_000_000,
        "max_games": 10,
        "max_record_bytes": 10_000,
        "timeout_seconds": 1,
    }

    class Response(io.BytesIO):
        status = 206
        headers: ClassVar[dict] = {
            "Content-Range": f"bytes 0-{len(payload) - 1}/{len(payload) + 100}",
            "Content-Length": str(len(payload)),
        }

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.close()

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: Response(payload))
    source = acquire_prefix(tmp_path, plan)
    extracted, receipt = extract_complete_games(tmp_path, plan, source)
    assert receipt["complete_games"] == 2
    assert receipt["trailing_open_record_discarded"]
    assert extracted.read_text() == complete * 2
    assert (
        read_json(source.parent / "acquisition.json")["publisher_full_checksum_verified"] is False
    )

    source.unlink()

    class WrongResponse(Response):
        status = 200

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: WrongResponse(payload))
    with pytest.raises(ValueError, match="did not honor"):
        acquire_prefix(tmp_path, plan)


def digest_bytes(tmp_path: Path, payload: bytes) -> str:
    path = tmp_path / "checksum-source"
    path.write_bytes(payload)
    return digest(path)
