"""Independent Python/browser parity on authored PGNs; no account history or live calls."""

import hashlib
import io
import json
import shutil
import subprocess
from pathlib import Path

import chess
import chess.pgn
import pytest

from chess_analytics.game_import import normalize_game, provider_identity

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/imports/authored-games.pgn"
NODE = shutil.which("node")


def records(text):
    source = io.StringIO(text)
    result = []
    while game := chess.pgn.read_game(source):
        result.append(normalize_game(game))
    return result


def test_provider_neutral_reference_preserves_short_games_and_missing_ratings():
    normalized = records(FIXTURE.read_text())
    assert len(normalized) == 5
    assert [record["provider"] for record in normalized] == [
        "chesscom",
        "lichess",
        "chesscom",
        "lichess",
        "pgn",
    ]
    assert normalized[0]["visits"][0]["position_key"] == normalized[1]["visits"][0]["position_key"]
    assert normalized[2]["plies"] == 2 and normalized[2]["visits"] == []
    assert normalized[0]["rated"] is None and normalized[1]["rated"] is True
    assert normalized[4]["visits"][2]["route_has_repeat"]


@pytest.mark.skipif(
    NODE is None, reason="Browser parity requires Node; CI explicitly runs Node tests"
)
def test_browser_replay_and_python_normalization_agree_exactly():
    result = subprocess.run(
        [NODE, str(ROOT / "tests/js/import_parity.mjs"), str(FIXTURE)],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert json.loads(result.stdout) == records(FIXTURE.read_text())


@pytest.mark.skipif(NODE is None, reason="Node unit suite is a separate mandatory hosted CI step")
def test_browser_import_semantics_offline():
    result = subprocess.run(
        [NODE, "--test", str(ROOT / "tests/js/game_import.test.mjs")],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_annotation_only_imports_share_semantic_fingerprint():
    plain = records(FIXTURE.read_text())[0]
    annotated = records((FIXTURE.parent / "annotated-duplicate.pgn").read_text())[0]
    assert annotated == plain


@pytest.mark.parametrize("header", ['[Variant "Chess960"]', '[SetUp "1"]'])
def test_reference_rejects_unsupported_games(header):
    game = chess.pgn.read_game(io.StringIO(header + "\n" + FIXTURE.read_text()))
    with pytest.raises(ValueError, match="unsupported"):
        normalize_game(game)


def test_provider_headers_cannot_switch_namespaces_silently():
    headers = chess.pgn.Headers(
        {"Site": "https://lichess.org/fixture1", "Link": "https://www.chess.com/game/live/1"}
    )
    with pytest.raises(ValueError, match="conflicting_provider"):
        provider_identity(headers)


def test_vendored_dependency_is_hash_checked_and_keeps_its_license():
    root = ROOT / "site/assets/vendor"
    provenance = json.loads((root / "chess-js-provenance.json").read_text())
    for name, expected in provenance["files"].items():
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == expected
    assert provenance["version"] == "1.4.0" and provenance["license"] == "BSD-2-Clause"
    assert "Copyright" in (root / "LICENSE.chess-js.txt").read_text()


def test_import_runtime_has_no_network_or_persistence_operations():
    # Enforcement complements the import page's connect-src 'none' policy.
    for name in ("game-import-core.mjs", "game-import-worker.mjs", "game-import-ui.js"):
        text = (ROOT / "site/assets" / name).read_text()
        assert not any(
            token in text
            for token in (
                "fetch(",
                "XMLHttpRequest",
                "WebSocket",
                "sendBeacon",
                "localStorage",
                "indexedDB",
            )
        ), name
    assert "worker.terminate()" in (ROOT / "site/assets/game-import-ui.js").read_text()
