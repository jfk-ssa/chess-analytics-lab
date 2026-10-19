"""Hand-checked intervals and paired tests for the live eval.

The expected numbers below were counted from the formulas, not by calling the
functions and pasting their output back in. Wilson uses z = 1.959963984540054.
For 0/1 the upper bound is z^2 / (1 + z^2). For a fair coin, binomial tails
are partial sums of C(n, k) / 2^n. The bootstrap draws were enumerated from
random.Random(0) with the index rule floor((B-1)*q) and ceil((B-1)*q).
"""

import random

import pytest

from chess_analytics.analyst.live_stats import (
    WILSON_Z_95,
    binomial_alert,
    binomial_alert_cutoff,
    binomial_cdf,
    cluster_bootstrap,
    exact_sign_test,
    flaky_case_ids,
    hard_fail,
    passes_by_case,
    wilson_interval,
)

_CASES = [[True, False], [False, False], [True, True, False]]


def test_wilson_matches_hand_values():
    assert WILSON_Z_95 == 1.959963984540054
    zero = wilson_interval(0, 1)
    assert zero["lower"] == pytest.approx(0.0, abs=1e-12)
    assert zero["upper"] == pytest.approx(0.793450685623, abs=1e-12)
    one = wilson_interval(1, 1)
    assert one["lower"] == pytest.approx(0.206549314377, abs=1e-12)
    assert one["upper"] == pytest.approx(1.0, abs=1e-12)
    seven = wilson_interval(7, 10)
    assert seven["lower"] == pytest.approx(0.396778147461, abs=1e-12)
    assert seven["upper"] == pytest.approx(0.892208732594, abs=1e-12)


def test_binomial_cutoff_matches_hand_counts():
    # 1/32 = 0.03125 <= 0.05 and 6/32 = 0.1875 > 0.05, so the cutoff is 0.
    assert binomial_cdf(0, 5, 0.5) == pytest.approx(1 / 32)
    assert binomial_alert_cutoff(5, 0.5) == 0
    # 11/1024 <= 0.05 and 56/1024 = 0.0546875 > 0.05, so the cutoff is 1.
    assert binomial_cdf(1, 10, 0.5) == pytest.approx(11 / 1024)
    assert binomial_cdf(2, 10, 0.5) == pytest.approx(56 / 1024)
    assert binomial_alert_cutoff(10, 0.5) == 1
    # A perfect baseline puts every miss in a zero-probability tail.
    assert binomial_alert_cutoff(5, 1) == 4
    assert binomial_alert(4, 5, 1)["alert"] is True
    assert binomial_alert(5, 5, 1)["alert"] is False
    # 1/16 = 0.0625 > 0.05, so no count alerts.
    assert binomial_alert_cutoff(4, 0.5) == -1
    assert binomial_alert(0, 4, 0.5)["alert"] is False


def test_cluster_bootstrap_matches_enumerated_draws():
    # random.Random(0), 3 cases, 5 draws, alpha 0.5.
    # Picks were (1,1,0), (1,2,1), (1,1,1), (1,2,0), (2,0,1).
    # Sorted rates: 0, 1/6, 2/7, 3/7, 3/7.
    # Indices floor(4 * 0.25) = 1 and ceil(4 * 0.75) = 3.
    interval = cluster_bootstrap(_CASES, seed=0, resamples=5, alpha=0.5)
    assert interval["lower"] == pytest.approx(1 / 6)
    assert interval["upper"] == pytest.approx(3 / 7)
    assert interval["point"] == pytest.approx(3 / 7)
    again = cluster_bootstrap(_CASES, seed=0, resamples=5, alpha=0.5)
    assert again == interval
    other = cluster_bootstrap(_CASES, seed=1, resamples=5, alpha=0.5)
    assert other != interval


def test_bootstrap_draw_enumeration_still_matches_random():
    """The comment above is checked against random.Random, not against the scorer."""
    rng = random.Random(0)
    picks = []
    for _draw in range(5):
        picks.append(tuple(rng.randrange(3) for _case in range(3)))
    assert picks == [(1, 1, 0), (1, 2, 1), (1, 1, 1), (1, 2, 0), (2, 0, 1)]


def test_exact_sign_test_matches_the_half_binomial():
    # One case favors the left model and five favor the right. n = 6.
    # P(X <= 1) = (1 + 6) / 64 = 7/64, and 2 * 7/64 = 0.21875.
    left = [[True], [False], [False], [False], [False], [False]]
    right = [[False], [True], [True], [True], [True], [True]]
    result = exact_sign_test(left, right)
    assert result["favor_left"] == 1
    assert result["favor_right"] == 5
    assert result["discordant"] == 6
    assert result["p_value"] == pytest.approx(0.21875)
    tied = exact_sign_test([[True], [False]], [[True], [False]])
    assert tied["discordant"] == 0
    assert tied["p_value"] == 1


def test_passes_by_case_aligns_the_sign_test():
    left = [
        {"case_id": "b", "passed": False},
        {"case_id": "a", "passed": True},
    ]
    right = [
        {"case_id": "a", "passed": False},
        {"case_id": "b", "passed": True},
        {"case_id": "b", "passed": None},
    ]
    result = exact_sign_test(passes_by_case(left), passes_by_case(right))
    assert result["favor_left"] == 1
    assert result["favor_right"] == 1
    assert result["p_value"] == 1


def test_hard_fail_and_flaky_cases():
    rows = [
        {"case_id": "boundary_budget", "passed": False, "high_severity_miss": True},
        {"case_id": "draw_rate_1", "passed": True, "high_severity_miss": False},
        {"case_id": "draw_rate_1", "passed": False, "high_severity_miss": False},
        {"case_id": "usage_sicilian_1", "passed": True, "high_severity_miss": False},
    ]
    assert hard_fail(rows) is True
    assert flaky_case_ids(rows) == ["draw_rate_1"]
    normal = [
        {"case_id": "draw_rate_1", "passed": False, "high_severity_miss": False},
    ]
    assert hard_fail(normal) is False
