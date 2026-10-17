"""Held-out comparison, the maia_v1 tolerance check, and the 1.d4 reply view.

The pinned model, the adapter, and the evidence-ID rule stay as they are.
This module does not import torch. A missing config or runtime skips the
weight check. Corpus files are not downloaded.
"""

import importlib.util
import math
import platform
from pathlib import Path

from chess_analytics.analyst.maia import predict_human_moves
from chess_analytics.analyst.tool_catalog import MAIA_CAVEATS
from chess_analytics.common import read_json

HOLDOUT_START = "2025-08"
PROBABILITY_TOLERANCE = 1e-4
REPERTOIRE_RATINGS = (1200, 1500, 1800)
BLITZ_ESTIMATED_MIN = 180
BLITZ_ESTIMATED_MAX = 480
INDEX_CAVEAT = "The opening corpus is a game index, not a metrics snapshot."


def lichess_blitz(base_seconds, increment_seconds) -> bool:
    """Lichess speed is base plus 40 times the increment. Blitz is 180 up to 480."""
    if isinstance(base_seconds, bool) or not isinstance(base_seconds, int):
        return False
    increment = 0 if increment_seconds is None else increment_seconds
    if isinstance(increment, bool) or not isinstance(increment, int):
        return False
    estimated = base_seconds + 40 * increment
    return BLITZ_ESTIMATED_MIN <= estimated < BLITZ_ESTIMATED_MAX


def holdout_inventory(report: dict) -> dict:
    """Opening-corpus training-index rows from August 2025 onward.

    "Training" here is that index, not Maia-3's own training set. The report
    is not a Maia score, and this function does not look for the index on disk.
    """
    sources = []
    for row in report.get("training_sources") or []:
        period = str(row.get("period") or "")
        if period < HOLDOUT_START:
            continue
        sources.append(
            {
                "period": period,
                "cohort": row.get("cohort"),
                "games": row.get("games"),
                "first_date": row.get("first_date"),
                "last_date": row.get("last_date"),
            }
        )
    games = sum(int(row["games"]) for row in sources)
    return {
        "holdout_start": HOLDOUT_START,
        "sources": sources,
        "games": games,
        "measured": False,
        "reason": "played_moves_not_extracted",
        "caveat": INDEX_CAVEAT,
    }


def score_played(rows: list[dict]) -> dict:
    """Log-loss and top-1/top-3 agreement for the move that was played."""
    if not rows:
        return {"n": 0, "log_loss": None, "top1": None, "top3": None}
    losses = []
    top1 = 0
    top3 = 0
    for row in rows:
        probability = float(row["probability"])
        rank = int(row["rank"])
        if not math.isfinite(probability) or probability <= 0:
            raise ValueError("played probability must be finite and positive")
        if rank < 1:
            raise ValueError("played rank starts at 1")
        losses.append(-math.log(probability))
        top1 += rank == 1
        top3 += rank <= 3
    count = len(rows)
    return {
        "n": count,
        "log_loss": sum(losses) / count,
        "top1": top1 / count,
        "top3": top3 / count,
    }


def reliability(rows: list[dict]) -> list[dict]:
    """Ten equal bins of predicted probability against an observed frequency."""
    buckets = []
    for index in range(10):
        low = index / 10
        high = (index + 1) / 10
        chosen = []
        for row in rows:
            predicted = float(row["predicted"])
            if low <= predicted < high or (index == 9 and predicted == 1.0):
                chosen.append(row)
        count = sum(int(row["count"]) for row in chosen)
        if count:
            mean_predicted = (
                sum(float(row["predicted"]) * int(row["count"]) for row in chosen) / count
            )
            mean_observed = (
                sum(float(row["observed"]) * int(row["count"]) for row in chosen) / count
            )
        else:
            mean_predicted = None
            mean_observed = None
        buckets.append(
            {
                "low": low,
                "high": high,
                "count": count,
                "mean_predicted": mean_predicted,
                "mean_observed": mean_observed,
            }
        )
    return buckets


def calibration_report(
    report: dict, played: list[dict] | None = None, frequencies: list[dict] | None = None
) -> dict:
    """Inventory plus scores when played-move rows were actually extracted.

    Passing no rows leaves `measured` false with `played_moves_not_extracted`.
    Nothing here reads the game index or the PGNs, whether or not they are on disk.
    """
    summary = holdout_inventory(report)
    if not played:
        return summary
    summary["measured"] = True
    summary["reason"] = None
    summary["played"] = score_played(played)
    summary["reliability"] = reliability(frequencies or [])
    return summary


def probability_deltas(actual: list[dict], expected: dict, tolerance: float) -> list[dict]:
    """Moves whose displayed probability is missing or farther than `tolerance`."""
    found = {row["uci"]: float(row["probability"]) for row in actual}
    misses = []
    for uci, target in expected.items():
        got = found.get(uci)
        if got is None or abs(got - float(target)) > tolerance:
            misses.append({"uci": uci, "expected": float(target), "actual": got})
    return misses


def skip_reason(
    config_exists: bool, runtime_present: bool, host: str, reference_platform: str
) -> str | None:
    if not config_exists:
        return "maia_not_configured"
    if not runtime_present:
        return "maia_unavailable"
    if host != reference_platform:
        return "platform_unmeasured"
    return None


def d4_repertoire(
    project: Path, ratings: tuple[int, ...] = REPERTOIRE_RATINGS, dataset_id: str = "repertoire"
) -> dict:
    """Black replies to 1.d4 at each rating, both players at that rating."""
    levels = []
    for rating in ratings:
        result = predict_human_moves(
            project,
            dataset_id,
            rating_self=rating,
            rating_opp=rating,
            moves=["d2d4"],
        )
        levels.append(
            {
                "rating_self": result["rating_self"],
                "rating_opp": result["rating_opp"],
                "reason": result.get("reason"),
                "moves": result["moves"],
                "caveats": result["caveats"],
            }
        )
    return {
        "opening": "1.d4",
        "moves": ["d2d4"],
        "side_to_move": "black",
        "levels": levels,
        "caveats": list(MAIA_CAVEATS),
    }


def _runtime_present() -> bool:
    return (
        importlib.util.find_spec("torch") is not None
        and importlib.util.find_spec("maia3") is not None
    )


def _case_kwargs(case: dict) -> dict:
    kwargs = {
        "rating_self": case["rating_self"],
        "rating_opp": case["rating_opp"],
        "top_k": case.get("top_k", 8),
    }
    if case.get("moves"):
        kwargs["moves"] = case["moves"]
    else:
        kwargs["fen"] = case["fen"]
    return kwargs


def score_maia_v1(project: Path) -> dict:
    """Compare `predict_human_moves` with the frozen displayed probabilities.

    Skips when config, torch, or the pinned Maia-3 package is missing, and
    when the host platform is not the one that wrote the reference.
    """
    host = f"{platform.system().lower()}-{platform.machine()}"
    config_exists = (project / "config" / "maia.json").is_file()
    runtime_present = _runtime_present()
    if not config_exists or not runtime_present:
        reason = skip_reason(config_exists, runtime_present, host, host)
        return {"skipped": True, "reason": reason, "platform": host, "failures": []}
    cases = read_json(project / "evals/cases/maia_v1.json")
    reference = read_json(project / "evals/references/maia_v1.json")
    reason = skip_reason(True, True, host, reference["platform"])
    if reason:
        return {"skipped": True, "reason": reason, "platform": host, "failures": []}
    tolerance = float(reference["probability_tolerance"])
    failures = []
    for case in cases:
        result = predict_human_moves(project, "maia_v1", **_case_kwargs(case))
        top = result["moves"][0]["uci"] if result.get("moves") else None
        misses = []
        if top != case["top_move"]:
            misses.append({"uci": case["top_move"], "expected": case["top_move"], "actual": top})
        misses.extend(
            probability_deltas(result.get("moves") or [], case["probabilities"], tolerance)
        )
        if misses:
            failures.append({"id": case["id"], "misses": misses})
    return {"skipped": False, "reason": None, "platform": host, "failures": failures}
