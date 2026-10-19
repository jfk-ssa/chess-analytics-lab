"""Pass-rate intervals and paired comparisons for one live analyst eval.

Pure Python. Nothing here calls a model or reads a credential. The alert
cutoff is advisory. A high-severity miss is a separate hard fail.
"""

import math
import random

WILSON_Z_95 = 1.959963984540054
ALERT_ALPHA = 0.05


def wilson_interval(successes: int, trials: int, *, z: float = WILSON_Z_95) -> dict:
    """Two-sided Wilson score interval for a binomial pass rate.

    ``z`` defaults to the 97.5% standard-normal quantile used for a 95%
    interval. The bounds are the usual center and margin form.
    """
    if type(successes) is not int or type(trials) is not int:
        raise ValueError("wilson counts must be integers")
    if trials < 1 or not 0 <= successes <= trials:
        raise ValueError("wilson successes must lie in 0..trials")
    if isinstance(z, bool) or not isinstance(z, (int, float)) or not math.isfinite(z) or z <= 0:
        raise ValueError("wilson z must be a positive finite number")
    p = successes / trials
    z2 = z * z
    denom = 1 + z2 / trials
    center = (p + z2 / (2 * trials)) / denom
    margin = z * math.sqrt(p * (1 - p) / trials + z2 / (4 * trials * trials)) / denom
    return {
        "alpha": 0.05,
        "lower": center - margin,
        "method": "wilson",
        "successes": successes,
        "trials": trials,
        "upper": center + margin,
        "z": z,
    }


def binomial_cdf(k: int, trials: int, rate: float) -> float:
    """Lower tail P(X <= k) for X ~ Binomial(trials, rate)."""
    if type(k) is not int or type(trials) is not int or trials < 0:
        raise ValueError("binomial cdf needs integer k and non-negative trials")
    if k < 0:
        return 0.0
    if trials == 0:
        return 1.0
    if k >= trials:
        return 1.0
    _check_rate(rate)
    if rate == 0:
        return 1.0
    if rate == 1:
        return 0.0
    probability = (1 - rate) ** trials
    total = probability
    for index in range(k):
        probability *= (trials - index) / (index + 1) * rate / (1 - rate)
        total += probability
    if total < 0:
        return 0.0
    if total > 1:
        return 1.0
    return total


def binomial_alert_cutoff(trials: int, baseline_rate: float, *, alpha: float = ALERT_ALPHA) -> int:
    """Largest pass count whose lower tail at the baseline rate is at most ``alpha``.

    A perfect baseline (rate 1) yields ``trials - 1``: any miss is an alert,
    because every count below the baseline has probability 0. When even zero
    passes has a lower tail above ``alpha``, the cutoff is -1 and no count alerts.
    """
    if type(trials) is not int or trials < 1:
        raise ValueError("alert cutoff needs at least one trial")
    _check_rate(baseline_rate)
    _check_alpha(alpha)
    if baseline_rate == 1:
        return trials - 1
    cutoff = -1
    for count in range(trials):
        if binomial_cdf(count, trials, baseline_rate) <= alpha:
            cutoff = count
        else:
            break
    return cutoff


def binomial_alert(observed_passes: int, trials: int, baseline_rate: float) -> dict:
    """Advisory one-sided 5% alert. Not a CI failure."""
    if type(observed_passes) is not int or not 0 <= observed_passes <= trials:
        raise ValueError("observed passes must lie in 0..trials")
    cutoff = binomial_alert_cutoff(trials, baseline_rate)
    return {
        "alert": observed_passes <= cutoff,
        "alpha": ALERT_ALPHA,
        "baseline_rate": baseline_rate,
        "cutoff": cutoff,
        "observed_passes": observed_passes,
        "trials": trials,
    }


def cluster_bootstrap(
    case_repeats: list[list[bool]],
    *,
    seed: int,
    resamples: int = 2000,
    alpha: float = ALERT_ALPHA,
) -> dict:
    """Case-level cluster bootstrap of the pass rate.

    Each draw resamples cases with replacement and keeps every repeat of a
    sampled case. The interval is the percentile pair at ``alpha / 2`` and
    ``1 - alpha / 2`` on the sorted rates, using indices
    ``floor((B - 1) * q)`` and ``ceil((B - 1) * q)``.
    """
    if not case_repeats or any(not repeats for repeats in case_repeats):
        raise ValueError("bootstrap needs every case to have at least one repeat")
    if type(seed) is not int or seed < 0:
        raise ValueError("bootstrap seed must be a non-negative integer")
    if type(resamples) is not int or resamples < 1:
        raise ValueError("bootstrap resamples must be a positive integer")
    _check_alpha(alpha)
    rng = random.Random(seed)
    n_cases = len(case_repeats)
    rates: list[float] = []
    for _draw in range(resamples):
        passed = 0
        total = 0
        for _pick in range(n_cases):
            repeats = case_repeats[rng.randrange(n_cases)]
            total += len(repeats)
            passed += sum(bool(item) for item in repeats)
        rates.append(passed / total)
    rates.sort()
    lower_index = math.floor((resamples - 1) * (alpha / 2))
    upper_index = math.ceil((resamples - 1) * (1 - alpha / 2))
    upper_index = min(upper_index, resamples - 1)
    successes = sum(sum(bool(item) for item in repeats) for repeats in case_repeats)
    trials = sum(len(repeats) for repeats in case_repeats)
    return {
        "alpha": alpha,
        "lower": rates[lower_index],
        "method": "case_cluster_percentile",
        "point": successes / trials,
        "resamples": resamples,
        "seed": seed,
        "upper": rates[upper_index],
    }


def exact_sign_test(left: list[list[bool]], right: list[list[bool]]) -> dict:
    """Exact two-sided sign test on discordant cases (McNemar).

    A case is discordant when the two models' pass counts across paired
    repeats differ. Ties are discarded. Under the null, the number of cases
    favoring one model is Binomial(n, 1/2). The p-value is
    ``min(1, 2 * P(X <= min(b, c)))``.
    """
    if len(left) != len(right) or not left:
        raise ValueError("sign test needs the same non-empty case list for both models")
    favor_right = 0
    favor_left = 0
    for left_repeats, right_repeats in zip(left, right, strict=True):
        if len(left_repeats) != len(right_repeats) or not left_repeats:
            raise ValueError("paired cases need the same positive repeat count")
        left_passes = sum(bool(item) for item in left_repeats)
        right_passes = sum(bool(item) for item in right_repeats)
        if right_passes > left_passes:
            favor_right += 1
        elif left_passes > right_passes:
            favor_left += 1
    discordant = favor_left + favor_right
    if discordant == 0:
        p_value = 1.0
    else:
        tail = _half_cdf(min(favor_left, favor_right), discordant)
        p_value = min(1.0, 2 * tail)
    return {
        "discordant": discordant,
        "favor_left": favor_left,
        "favor_right": favor_right,
        "method": "exact_sign_mcnemar",
        "p_value": p_value,
        "ties": len(left) - discordant,
    }


def passes_by_case(rows: list[dict]) -> list[list[bool]]:
    """Pass bits grouped by case id, sorted by id, repeats in encounter order.

    Rows that were not scored are omitted. Pair two models with
    ``exact_sign_test(passes_by_case(left), passes_by_case(right))``.
    """
    grouped: dict[str, list[bool]] = {}
    for row in rows:
        if row.get("passed") is None:
            continue
        grouped.setdefault(str(row["case_id"]), []).append(bool(row["passed"]))
    return [grouped[case_id] for case_id in sorted(grouped)]


def flaky_case_ids(rows: list[dict]) -> list[str]:
    """Cases that both pass and fail across repeats."""
    grouped: dict[str, list[bool]] = {}
    for row in rows:
        if row.get("passed") is None:
            continue
        grouped.setdefault(row["case_id"], []).append(bool(row["passed"]))
    return sorted(case_id for case_id, flags in grouped.items() if any(flags) and not all(flags))


def hard_fail(rows: list[dict]) -> bool:
    """True when any scored high-severity case missed. Advisory alerts do not count."""
    return any(bool(row.get("high_severity_miss")) for row in rows)


def _half_cdf(k: int, trials: int) -> float:
    total = sum(math.comb(trials, index) for index in range(k + 1))
    return total / 2**trials


def _check_rate(rate: float) -> None:
    if isinstance(rate, bool) or not isinstance(rate, (int, float)) or not math.isfinite(rate):
        raise ValueError("baseline rate must be finite")
    if not 0 <= rate <= 1:
        raise ValueError("baseline rate must lie in 0..1")


def _check_alpha(alpha: float) -> None:
    if isinstance(alpha, bool) or not isinstance(alpha, (int, float)) or not math.isfinite(alpha):
        raise ValueError("alpha must be finite")
    if not 0 < alpha < 1:
        raise ValueError("alpha must lie between 0 and 1")
