"""Offline corpus extractor. The fake distribution stands in for Maia weights."""

import json
import math
import random
from pathlib import Path

import pytest

from chess_analytics.analyst.maia_corpus import SEED, calibrate, render_markdown, select_games
from chess_analytics.analyst.maia_pins import CODE_COMMIT, CODE_REPO, PINS, RATING_SCALE
from chess_analytics.common import digest, write_json

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "tests/fixtures/maia/corpus.pgn"
DISTRIBUTION = ROOT / "tests/fixtures/maia/distribution.json"
PUBLIC_IDS = [1, 6, 7, 8]
ELITE_IDS = [1, 2, 3, 6, 7, 8]


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


def reservoir(ids: list[int], size: int, seed: int) -> list[int]:
    rng = random.Random(seed)
    chosen: list[int] = []
    for seen, item in enumerate(ids, start=1):
        if len(chosen) < size:
            chosen.append(item)
        else:
            slot = rng.randrange(seen)
            if slot < size:
                chosen[slot] = item
    return chosen


def test_public_sample_is_blitz_only_and_elite_keeps_the_curated_month():
    public, public_stats = select_games(
        CORPUS, blitz_only=True, sample_size=20, seed=SEED, plies=12
    )
    elite, elite_stats = select_games(CORPUS, blitz_only=False, sample_size=20, seed=SEED, plies=12)
    assert [game["ordinal"] for game in public] == PUBLIC_IDS
    assert [game["ordinal"] for game in elite] == ELITE_IDS
    assert public_stats["games_seen"] == 8
    assert public_stats["games_eligible"] == 4
    assert public_stats["games_passing_blitz"] == 4
    assert elite_stats["games_eligible"] == 6
    assert elite_stats["games_passing_blitz"] == 4
    assert elite_stats["sample_blitz_games"] == 4
    assert public_stats["sample_target_met"] is False
    drawn = select_games(CORPUS, blitz_only=True, sample_size=2, seed=SEED, plies=12)
    again = select_games(CORPUS, blitz_only=True, sample_size=2, seed=SEED, plies=12)
    ordinals = [game["ordinal"] for game in drawn[0]]
    assert ordinals == [game["ordinal"] for game in again[0]]
    assert ordinals == reservoir(PUBLIC_IDS, 2, SEED)
    assert len(public[0]["moves"]) == 12


def test_fake_distribution_scores_one_population(tmp_path):
    weights = _traced_weights(tmp_path)
    write_maia(tmp_path, weights)
    report = calibrate(
        tmp_path,
        CORPUS,
        "public",
        sample_size=20,
        seed=SEED,
        plies=12,
        batch_size=1,
        bootstrap=400,
    )
    pop = report["population"]
    assert report["measured"] is True
    assert report["reason"] is None
    assert "populations" not in report
    assert pop["id"] == "public_2026_08_blitz"
    assert pop["blitz_filter"] is True
    assert pop["n_positions"] == 7
    assert pop["excluded_zero_probability"] == 10
    assert pop["top1"] == pytest.approx(6 / 7)
    assert pop["top3"] == pytest.approx(1)
    opening = -math.log(0.625)
    queen = -math.log(0.375)
    assert pop["log_loss"] == pytest.approx((3 * opening + queen) / 7)
    low, high = pop["log_loss_interval"]
    assert low <= high
    bands = {row["band"]: row["n_positions"] for row in pop["by_rating_band"]}
    assert bands["below-1000"] == 1
    assert bands["1000–1599"] == 2
    assert bands["1600–1999"] == 1
    assert bands["2000–2299"] == 1
    assert bands["2300+"] == 2
    assert pop["by_ply"][0]["n_positions"] == 4
    assert pop["by_ply"][1]["n_positions"] == 3
    assert all(row["n_positions"] == 0 for row in pop["by_ply"] if row["ply"] > 2)
    pids = (tmp_path / "pid.txt").read_text().split()
    assert len(pids) > 1
    assert len(set(pids)) == 1
    traced = [json.loads(line) for line in (tmp_path / "echo.jsonl").read_text().splitlines()]
    assert [row["boards"] for row in traced[:12]] == [1, 2, 3, 4, 5, 6, 7, 8, 8, 8, 8, 8]
    assert traced[-1]["rating_self"] == 5000
    assert traced[-1]["rating_opp"] == 1500
    e4_bin = next(row for row in pop["reliability"] if math.isclose(row["low"], 0.6))
    assert e4_bin["count"] == 4
    assert e4_bin["mean_predicted"] == pytest.approx(0.625)
    assert e4_bin["mean_observed"] == pytest.approx(0.75)
    text = render_markdown(report)
    assert "not pooled" in text
    assert "public_2026_08_blitz" in text
    assert "elite_2025_11" not in text
    elite = calibrate(
        tmp_path, CORPUS, "elite", sample_size=20, seed=SEED, plies=12, batch_size=8, bootstrap=5
    )
    assert elite["population"]["blitz_filter"] is False
    assert elite["population"]["sample_games"] == 6
    assert "labeled subset" in render_markdown(elite)


def test_missing_config_skips_without_a_worker(tmp_path):
    with pytest.raises(ValueError, match="maia_not_configured"):
        calibrate(tmp_path, CORPUS, "elite", sample_size=2, bootstrap=1)


def _traced_weights(project: Path) -> Path:
    payload = json.loads(DISTRIBUTION.read_text())
    payload["pid_file"] = str(project / "pid.txt")
    payload["echo_request"] = str(project / "echo.jsonl")
    weights = project / "weights.json"
    weights.write_text(json.dumps(payload), encoding="utf-8")
    return weights
