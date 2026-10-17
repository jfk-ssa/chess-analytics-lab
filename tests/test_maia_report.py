"""Pure corpus scores. No worker and no PGN."""

import math

import pytest

from chess_analytics.analyst.maia_report import (
    add_reliability,
    bootstrap,
    empty_bins,
    finish_bins,
    metrics,
)


def test_bootstrap_endpoints_on_two_known_games():
    rows = [
        {"game": 0, "probability": 0.5, "rank": 1},
        {"game": 1, "probability": 0.25, "rank": 2},
    ]
    scored = metrics(rows, 20251017, 400)
    loss = (-math.log(0.5) + -math.log(0.25)) / 2
    assert scored["n_games"] == 2
    assert scored["n_positions"] == 2
    assert scored["zero_probability_count"] == 0
    assert scored["log_loss"] == pytest.approx(loss)
    assert scored["top1"] == pytest.approx(0.5)
    assert scored["top3"] == pytest.approx(1)
    low, high = scored["log_loss_interval"]
    assert low == pytest.approx(-math.log(0.5))
    assert high == pytest.approx(-math.log(0.25))
    top_low, top_high = scored["top1_interval"]
    assert top_low == pytest.approx(0)
    assert top_high == pytest.approx(1)
    assert bootstrap(rows, 20251017, 400)["top3"] == pytest.approx([1, 1])


def test_empty_bins_stay_empty():
    finished = finish_bins(empty_bins())
    assert len(finished) == 10
    assert [row["count"] for row in finished] == [0] * 10
    assert all(row["mean_predicted"] is None and row["mean_observed"] is None for row in finished)


def test_one_game_reliability_bin():
    bins = empty_bins()
    add_reliability(
        bins,
        [
            {"predicted": 0.625, "observed": 1, "count": 1},
            {"predicted": 0.375, "observed": 0, "count": 1},
        ],
    )
    finished = finish_bins(bins)
    opening = next(row for row in finished if math.isclose(row["low"], 0.6))
    assert opening["count"] == 1
    assert opening["mean_predicted"] == pytest.approx(0.625)
    assert opening["mean_observed"] == pytest.approx(1)
    quiet = next(row for row in finished if math.isclose(row["low"], 0.0))
    assert quiet["count"] == 0
    assert quiet["mean_predicted"] is None


def test_zero_probability_is_a_ranking_miss_and_stays_out_of_log_loss():
    rows = [
        {"game": 0, "probability": 0.5, "rank": 1},
        {"game": 0, "probability": 0.0, "rank": 0},
    ]
    scored = metrics(rows, 1, 20)
    assert scored["n_positions"] == 2
    assert scored["zero_probability_count"] == 1
    assert scored["zero_probability_share"] == pytest.approx(0.5)
    assert scored["top1"] == pytest.approx(0.5)
    assert scored["top3"] == pytest.approx(0.5)
    assert scored["log_loss"] == pytest.approx(-math.log(0.5))


def test_all_zero_rows_have_no_log_loss_interval():
    scored = metrics([{"game": 0, "probability": 0.0, "rank": 0}], 1, 10)
    assert scored["log_loss"] is None
    assert scored["log_loss_interval"] is None
    assert scored["top1"] == 0
    assert scored["top1_interval"] == [0, 0]
    assert metrics([], 1, 5)["zero_probability_share"] is None
