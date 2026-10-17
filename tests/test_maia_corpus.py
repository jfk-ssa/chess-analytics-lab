"""Offline corpus extractor. The fake distribution stands in for Maia weights."""

import contextlib
import math
import random
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from chess_analytics.analyst.maia_corpus import (
    SEED,
    _close,
    _outcome,
    _positions,
    _send,
    calibrate,
    main,
    select_games,
)
from chess_analytics.analyst.maia_pins import CODE_COMMIT, CODE_REPO, PINS, RATING_SCALE
from chess_analytics.analyst.maia_report import render_markdown
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


def test_fake_distribution_scores_one_population(tmp_path, monkeypatch, capsys):
    weights = tmp_path / "weights.json"
    weights.write_text(DISTRIBUTION.read_text(), encoding="utf-8")
    write_maia(tmp_path, weights)
    calls = []
    real_popen = subprocess.Popen

    def popen(cmd, *args, **kwargs):
        calls.append(cmd)
        return real_popen(cmd, *args, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", popen)
    report = calibrate(
        tmp_path,
        CORPUS,
        "public",
        sample_size=20,
        seed=SEED,
        plies=12,
        batch_size=5,
        bootstrap=400,
        progress_every=2,
    )
    err = capsys.readouterr().err
    pop = report["population"]
    assert report["measured"] is True
    assert report["reason"] is None
    assert "populations" not in report
    assert pop["id"] == "public_2026_08_blitz"
    assert pop["blitz_filter"] is True
    assert pop["n_positions"] == 17
    assert pop["zero_probability_count"] == 10
    assert pop["zero_probability_share"] == pytest.approx(10 / 17)
    assert "excluded_zero_probability" not in pop
    assert pop["top1"] == pytest.approx(6 / 17)
    assert pop["top3"] == pytest.approx(7 / 17)
    opening = -math.log(0.625)
    queen = -math.log(0.375)
    assert pop["log_loss"] == pytest.approx((3 * opening + queen) / 7)
    low, high = pop["log_loss_interval"]
    assert low <= high
    bands = {row["band"]: row["n_positions"] for row in pop["by_rating_band"]}
    assert bands["below-1000"] == 1
    assert bands["1000–1599"] == 7
    assert bands["1600–1999"] == 6
    assert bands["2000–2299"] == 1
    assert bands["2300+"] == 2
    assert pop["by_ply"][0]["n_positions"] == 4
    assert pop["by_ply"][1]["n_positions"] == 3
    assert all(row["n_positions"] == 1 for row in pop["by_ply"] if row["ply"] > 2)
    progress = [line for line in err.splitlines() if line.startswith("maia corpus:")]
    assert progress[0].startswith("maia corpus: 5/17")
    assert "ETA" not in progress[0]
    assert any(line.startswith("maia corpus: 10/17") and "ETA" in line for line in progress)
    assert any(line.startswith("maia corpus: finished 17/17") for line in progress)
    assert "zero played-move probability" in err
    games, _stats = select_games(CORPUS, blitz_only=True, sample_size=20, seed=SEED, plies=12)
    opening_plies = list(_positions(games[0], 0))
    assert [len(row["boards"]) for row in opening_plies] == [1, 2, 3, 4, 5, 6, 7, 8, 8, 8, 8, 8]
    assert opening_plies[0]["legal"] == sorted(opening_plies[0]["legal"])
    clamped = list(_positions(games[-1], 3))[-1]
    assert clamped["rating_self"] == 5000
    assert clamped["rating_opp"] == 1500
    e4_bin = next(row for row in pop["reliability"] if math.isclose(row["low"], 0.6))
    assert e4_bin["count"] == 4
    assert e4_bin["mean_predicted"] == pytest.approx(0.625)
    assert e4_bin["mean_observed"] == pytest.approx(0.75)
    text = render_markdown(report)
    assert "not pooled" in text
    assert "95% interval" in text
    assert "2026-08-01" in text
    assert "public_2026_08_blitz" in text
    assert "elite_2025_11" not in text
    assert "public_sample_is_the_2026-08-01_prefix" in report["caveats"]
    assert len(calls) == 1
    elite = calibrate(
        tmp_path, CORPUS, "elite", sample_size=20, seed=SEED, plies=12, batch_size=8, bootstrap=5
    )
    assert len(calls) == 2
    assert elite["population"]["blitz_filter"] is False
    assert elite["population"]["sample_games"] == 6
    assert "public_sample_is_the_2026-08-01_prefix" not in elite["caveats"]
    elite_text = render_markdown(elite)
    assert "labeled subset" in elite_text
    assert "2026-08-01" not in elite_text


def test_missing_config_skips_without_a_worker(tmp_path):
    with pytest.raises(ValueError, match="maia_not_configured"):
        calibrate(tmp_path, CORPUS, "elite", sample_size=2, bootstrap=1)


def test_tied_probabilities_share_rank_one():
    row, _rows = _outcome(
        {
            "legal": ["a2a4", "a2a3"],
            "played": "a2a3",
            "game": 0,
            "ply": 1,
            "band": "1000–1599",
        },
        {"a2a3": 0.4, "a2a4": 0.4},
    )
    assert row["rank"] == 1
    assert row["probability"] == pytest.approx(0.5)


@contextlib.contextmanager
def _spawn(code: str):
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as errors:
        proc = subprocess.Popen(
            [sys.executable, "-c", code],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=errors,
            text=True,
        )
        try:
            yield proc, errors
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=5)


def test_dead_worker_reports_its_stderr_and_is_killed():
    code = (
        "import sys\n"
        "sys.stdin.readline()\n"
        "print('model exploded', file=sys.stderr, flush=True)\n"
        "raise SystemExit(3)\n"
    )
    position = {"boards": ["fen"], "rating_self": 1500, "rating_opp": 1500}
    with _spawn(code) as (proc, errors):
        with pytest.raises(ValueError, match="model exploded") as caught:
            _send(proc, [position], errors, 2)
        assert "Broken pipe" not in str(caught.value)
        assert proc.poll() is not None


def test_hung_worker_times_out_and_is_killed():
    position = {"boards": ["fen"], "rating_self": 1500, "rating_opp": 1500}
    with _spawn("import sys, time\nsys.stdin.readline()\ntime.sleep(30)\n") as (proc, errors):
        with pytest.raises(ValueError, match="timed out"):
            _send(proc, [position], errors, 0.2)
        assert proc.poll() is not None


def test_close_kills_a_worker_that_ignores_done():
    with _spawn("import time\ntime.sleep(30)\n") as (proc, errors):
        with pytest.raises(subprocess.TimeoutExpired, match="timed out"):
            _close(proc, errors, timeout=0.2)
        assert proc.poll() is not None


def test_main_reports_a_timeout_and_writes_nothing(tmp_path, monkeypatch, capsys):
    weights = tmp_path / "weights.json"
    weights.write_text(DISTRIBUTION.read_text(), encoding="utf-8")
    write_maia(tmp_path, weights)
    procs = []
    real_popen = subprocess.Popen
    code = (
        "import json, sys, time\n"
        "sys.stdin.readline()\n"
        "message = json.loads(sys.stdin.readline())\n"
        "count = len(message.get('positions') or [])\n"
        "blank = {'moves': {}}\n"
        "print(json.dumps({'ok': True, 'results': [blank] * count}), flush=True)\n"
        "time.sleep(30)\n"
    )

    def popen(cmd, *args, **kwargs):
        if isinstance(cmd, list) and any("maia_worker" in part for part in cmd):
            cmd = [sys.executable, "-c", code]
        proc = real_popen(cmd, *args, **kwargs)
        procs.append(proc)
        return proc

    monkeypatch.setattr(subprocess, "Popen", popen)
    status = main(
        [
            "--project",
            str(tmp_path),
            "--pgn",
            str(CORPUS),
            "--population",
            "public",
            "--json",
            str(tmp_path / "out.json"),
            "--markdown",
            str(tmp_path / "out.md"),
            "--sample-size",
            "20",
            "--bootstrap",
            "1",
            "--batch-size",
            "64",
            "--read-timeout",
            "0.2",
        ]
    )
    assert status == 1
    assert "timed out" in capsys.readouterr().err
    assert procs[0].poll() is not None
    assert not (tmp_path / "out.json").exists()
