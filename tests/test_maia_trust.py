"""Offline Maia comparison and repertoire view. No weight download."""

import math
from pathlib import Path

import pytest

from chess_analytics.analyst.maia_pins import CODE_COMMIT, CODE_REPO, PINS, RATING_SCALE
from chess_analytics.analyst.maia_trust import (
    INDEX_CAVEAT,
    PROBABILITY_TOLERANCE,
    calibration_report,
    d4_repertoire,
    holdout_inventory,
    lichess_blitz,
    probability_deltas,
    reliability,
    score_maia_v1,
    score_played,
    skip_reason,
)
from chess_analytics.analyst.tool_catalog import MAIA_CAVEATS
from chess_analytics.common import digest, read_json, write_json

ROOT = Path(__file__).resolve().parents[1]
DISTRIBUTION = ROOT / "tests/fixtures/maia/distribution.json"


def write_maia(project: Path, weights: Path) -> None:
    pin = PINS["23M"]
    write_json(
        project / "config/maia.json",
        {
            "version": "1",
            "default_alias": "23M",
            "models": {
                "23M": {
                    "alias": "23M",
                    "family": "maia3",
                    "weights_path": str(weights.resolve()),
                    "sha256": digest(weights),
                    "bytes": weights.stat().st_size,
                    "hf_repo": pin["hf_repo"],
                    "hf_revision": pin["hf_revision"],
                    "code_repo": CODE_REPO,
                    "code_commit": CODE_COMMIT,
                    "device": "cpu",
                    "dtype": "float32",
                    "threads": 1,
                    "rating_scale": RATING_SCALE,
                }
            },
        },
    )


PLAYED = [
    {"probability": 0.5, "rank": 1},
    {"probability": 0.25, "rank": 2},
    {"probability": 0.1, "rank": 4},
]
FREQUENCIES = [
    {"predicted": 0.49, "observed": 0.47, "count": 100},
    {"predicted": 0.12, "observed": 0.10, "count": 50},
]


def test_holdout_inventory_is_every_training_source_and_is_unmeasured():
    report = read_json(ROOT / "reports/opening-corpus.json")
    inventory = holdout_inventory(report)
    periods = [row["period"] for row in inventory["sources"]]
    assert periods == [
        "2025-11",
        "2025-12",
        "2026-01",
        "2026-02",
        "2026-03",
        "2026-04",
        "2026-05",
        "2026-06",
        "2026-07",
        "2026-08",
    ]
    assert "2013-01" not in periods
    assert all(period >= "2025-08" for period in periods)
    assert inventory["games"] == report["counts"]["training_games"] == 1_042_346
    assert inventory["sources"][0]["cohort"] == "elite_reference"
    assert inventory["sources"][0]["games"] == 240_086
    assert inventory["sources"][0]["first_date"] == "2025-11-01"
    assert inventory["sources"][0]["last_date"] == "2025-11-30"
    assert inventory["measured"] is False
    assert inventory["reason"] == "opening_index_absent"
    assert inventory["caveat"] == INDEX_CAVEAT
    assert not (ROOT / "data/openings").exists()


def test_played_move_scores_and_reliability_buckets():
    scored = score_played(PLAYED)
    expected_loss = (-math.log(0.5) - math.log(0.25) - math.log(0.1)) / 3
    assert scored["n"] == 3
    assert scored["log_loss"] == pytest.approx(expected_loss)
    assert scored["top1"] == pytest.approx(1 / 3)
    assert scored["top3"] == pytest.approx(2 / 3)
    assert score_played([]) == {"n": 0, "log_loss": None, "top1": None, "top3": None}
    buckets = {row["low"]: row for row in reliability(FREQUENCIES)}
    assert buckets[0.4]["count"] == 100
    assert buckets[0.4]["mean_predicted"] == pytest.approx(0.49)
    assert buckets[0.4]["mean_observed"] == pytest.approx(0.47)
    assert buckets[0.1]["count"] == 50
    assert buckets[0.0]["count"] == 0
    assert buckets[0.9]["high"] == 1.0
    report = read_json(ROOT / "reports/opening-corpus.json")
    measured = calibration_report(report, PLAYED, FREQUENCIES)
    assert measured["measured"] is True
    assert measured["reason"] is None
    assert measured["played"]["n"] == 3
    assert measured["games"] == 1_042_346
    assert measured["caveat"] == INDEX_CAVEAT
    assert calibration_report(report)["measured"] is False


def test_tolerance_accepts_thread_noise_and_rejects_a_tenth():
    actual = [{"uci": "d7d5", "probability": 0.491}]
    assert probability_deltas(actual, {"d7d5": 0.491 + 1e-6}, PROBABILITY_TOLERANCE) == []
    assert probability_deltas(actual, {"d7d5": 0.491}, 1e-4) == []
    misses = probability_deltas(actual, {"d7d5": 0.391}, PROBABILITY_TOLERANCE)
    assert misses == [{"uci": "d7d5", "expected": 0.391, "actual": 0.491}]
    missing = probability_deltas(actual, {"g8f6": 0.14}, PROBABILITY_TOLERANCE)
    assert missing[0]["actual"] is None


def test_lichess_blitz_window_and_skip_reasons():
    assert lichess_blitz(180, 0)
    assert lichess_blitz(180, 2)
    assert lichess_blitz(300, 3)
    assert not lichess_blitz(60, 0)
    assert not lichess_blitz(300, 5)
    assert not lichess_blitz(600, 0)
    assert not lichess_blitz(None, 0)
    assert skip_reason(False, False, "linux-x86_64", "linux-x86_64") == "maia_not_configured"
    assert skip_reason(True, False, "linux-x86_64", "linux-x86_64") == "maia_unavailable"
    assert skip_reason(True, True, "darwin-arm64", "linux-x86_64") == "platform_unmeasured"
    assert skip_reason(True, True, "linux-x86_64", "linux-x86_64") is None


def test_d4_view_uses_the_checked_tool_and_keeps_the_caveats(tmp_path):
    weights = tmp_path / "weights.json"
    weights.write_text(DISTRIBUTION.read_text())
    write_maia(tmp_path, weights)
    view = d4_repertoire(tmp_path)
    assert view["opening"] == "1.d4"
    assert view["moves"] == ["d2d4"]
    assert view["side_to_move"] == "black"
    assert view["caveats"] == list(MAIA_CAVEATS)
    assert [level["rating_self"] for level in view["levels"]] == [1200, 1500, 1800]
    for level in view["levels"]:
        assert level["rating_opp"] == level["rating_self"]
        assert level["reason"] is None
        assert level["moves"] == [{"uci": "e7e5", "san": "e5", "probability": 1.0}]
        assert level["caveats"] == list(MAIA_CAVEATS)


def test_maia_v1_skips_before_any_worker_and_pins_the_frozen_file(tmp_path, monkeypatch):
    def explode(*_args, **_kwargs):
        raise AssertionError("worker started")

    monkeypatch.setattr("chess_analytics.analyst.maia_trust.predict_human_moves", explode)
    skipped = score_maia_v1(tmp_path)
    assert skipped["skipped"] is True
    assert skipped["reason"] == "maia_not_configured"
    assert skipped["failures"] == []
    weights = tmp_path / "weights.json"
    weights.write_text(DISTRIBUTION.read_text())
    write_maia(tmp_path, weights)
    unavailable = score_maia_v1(tmp_path)
    assert unavailable["skipped"] is True
    assert unavailable["reason"] == "maia_unavailable"
    cases = read_json(ROOT / "evals/cases/maia_v1.json")
    reference = read_json(ROOT / "evals/references/maia_v1.json")
    assert [case["id"] for case in cases] == ["start_1500", "d4_1200", "d4_1500", "d4_1800"]
    assert reference["probability_tolerance"] == PROBABILITY_TOLERANCE == 1e-4
    assert reference["platform"] == "linux-x86_64"
    assert cases[2]["probabilities"]["d7d5"] == 0.491
    assert cases[2]["top_move"] == "d7d5"


def test_repertoire_script_does_not_download():
    source = (ROOT / "scripts/maia_d4_repertoire.py").read_text()
    assert "urlopen" not in source
    assert "if __name__" in source
