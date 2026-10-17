"""Pure calibration scores and the one-population Markdown report.

Log-loss uses `score_played` on positions whose played probability is positive.
A played probability of zero stays out of that loss and counts as a top-1 and
top-3 miss. This module does not import torch or start a worker.
"""

import random

from chess_analytics.analyst.maia_trust import reliability, score_played

BANDS = ("below-1000", "1000–1599", "1600–1999", "2000–2299", "2300+")
ZERO_SHARE_WARN = 0.01


def empty_bins() -> list[dict]:
    return [
        {"low": index / 10, "high": (index + 1) / 10, "count": 0, "predicted": 0.0, "observed": 0.0}
        for index in range(10)
    ]


def add_reliability(bins: list[dict], rows: list[dict]) -> None:
    if not rows:
        return
    for bucket in reliability(rows):
        slot = bins[int(bucket["low"] * 10)]
        count = int(bucket["count"])
        slot["count"] += count
        if count and bucket["mean_predicted"] is not None:
            slot["predicted"] += float(bucket["mean_predicted"]) * count
            slot["observed"] += float(bucket["mean_observed"]) * count


def finish_bins(bins: list[dict]) -> list[dict]:
    finished = []
    for slot in bins:
        count = slot["count"]
        finished.append(
            {
                "low": slot["low"],
                "high": slot["high"],
                "count": count,
                "mean_predicted": None if count == 0 else slot["predicted"] / count,
                "mean_observed": None if count == 0 else slot["observed"] / count,
            }
        )
    return finished


def _interval(values: list[float]) -> list[float] | None:
    """Same percentile ends as the M4 cluster bootstrap."""
    if not values:
        return None
    ordered = sorted(values)
    last = len(ordered) - 1
    return [ordered[int(0.025 * last)], ordered[int(0.975 * last)]]


def _rates(rows: list[dict]) -> tuple[float | None, float | None, float | None]:
    """Log-loss on positive probabilities. Top-1 and top-3 treat zero as a miss."""
    count = len(rows)
    if count == 0:
        return None, None, None
    positive = [row for row in rows if row["probability"] > 0]
    loss = score_played(positive)["log_loss"]
    top1 = sum(row["probability"] > 0 and row["rank"] == 1 for row in rows) / count
    top3 = sum(row["probability"] > 0 and row["rank"] <= 3 for row in rows) / count
    return loss, top1, top3


def bootstrap(rows: list[dict], seed: int, reps: int) -> dict:
    """Resample games. Every scored ply of a drawn game stays with that game."""
    grouped: dict[int, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row["game"], []).append(row)
    keys = list(grouped)
    if not keys:
        return {"log_loss": None, "top1": None, "top3": None}
    rng = random.Random(seed)
    samples: dict[str, list[float]] = {"log_loss": [], "top1": [], "top3": []}
    width = len(keys)
    for _ in range(reps):
        drawn = [item for _draw in range(width) for item in grouped[keys[rng.randrange(width)]]]
        loss, top1, top3 = _rates(drawn)
        if loss is not None:
            samples["log_loss"].append(loss)
        if top1 is not None and top3 is not None:
            samples["top1"].append(top1)
            samples["top3"].append(top3)
    return {name: _interval(values) for name, values in samples.items()}


def metrics(rows: list[dict], seed: int, reps: int) -> dict:
    loss, top1, top3 = _rates(rows)
    interval = bootstrap(rows, seed, reps)
    count = len(rows)
    zeros = sum(row["probability"] <= 0 for row in rows)
    return {
        "n_games": len({row["game"] for row in rows}),
        "n_positions": count,
        "log_loss": loss,
        "log_loss_interval": interval["log_loss"],
        "top1": top1,
        "top1_interval": interval["top1"],
        "top3": top3,
        "top3_interval": interval["top3"],
        "zero_probability_count": zeros,
        "zero_probability_share": None if count == 0 else zeros / count,
    }


def labeled(rows: list[dict], key: str, labels, seed: int, reps: int) -> list[dict]:
    blocks = []
    for label in labels:
        block = metrics([row for row in rows if row[key] == label], seed, reps)
        block[key] = label
        blocks.append(block)
    return blocks


def _fmt(value) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "[" + ", ".join(_fmt(item) for item in value) + "]"
    return f"{float(value):.4f}"


def _table(headers: list[str], rows: list[list[str]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    rule = "|" + "|".join("---" for _ in headers) + "|"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([head, rule, *body])


def _cells(row: dict, label) -> list[str]:
    positive = row["n_positions"] - row["zero_probability_count"]
    return [
        str(label),
        str(row["n_games"]),
        str(row["n_positions"]),
        str(positive),
        _fmt(row["log_loss"]),
        _fmt(row["log_loss_interval"]),
        _fmt(row["top1"]),
        _fmt(row["top1_interval"]),
        _fmt(row["top3"]),
        _fmt(row["top3_interval"]),
    ]


def render_markdown(report: dict) -> str:
    """One population. Band and ply tables include the same intervals as the headline."""
    pop = report["population"]
    notes = ["One population. This file is not pooled with any other population."]
    if not pop["blitz_filter"]:
        notes.append("Elite headline is the curated month. The blitz counts are a labeled subset.")
    if pop["id"] == "public_2026_08_blitz":
        notes.append("The public sample is the ordered 2026-08-01 prefix, not a full month.")
    positions = str(pop["n_positions"])
    scored = str(pop["n_positions"] - pop["zero_probability_count"])
    share = pop["zero_probability_share"]
    share_text = "" if share is None else f" ({share:.1%})"
    scores = _table(
        ["Score", "Estimate", "95% interval", "Counted"],
        [
            [
                "log-loss",
                _fmt(pop["log_loss"]),
                _fmt(pop["log_loss_interval"]),
                f"{scored} positive",
            ],
            ["top-1", _fmt(pop["top1"]), _fmt(pop["top1_interval"]), f"{positions} played"],
            ["top-3", _fmt(pop["top3"]), _fmt(pop["top3_interval"]), f"{positions} played"],
        ],
    )
    header = [
        "Label",
        "Games",
        "Played",
        "Positive",
        "Log-loss",
        "95% interval",
        "Top-1",
        "95% interval",
        "Top-3",
        "95% interval",
    ]
    bands = _table(header, [_cells(row, row["band"]) for row in pop["by_rating_band"]])
    plies = _table(header, [_cells(row, row["ply"]) for row in pop["by_ply"]])
    state = "on" if pop["blitz_filter"] else "off"
    met = str(pop["sample_target_met"]).lower()
    return (
        f"# Maia corpus calibration — {pop['id']}\n\n" + "\n".join(notes) + "\n\n"
        f"- Source: `{pop['source_file']}`\n"
        f"- Blitz filter: {state}\n"
        f"- Sample: {pop['sample_games']} games (target {report['sample_target_games']})\n"
        f"- Sample target met: {met}\n"
        f"- Scanned games passing `lichess_blitz`: {pop['games_passing_blitz']}\n"
        f"- Sampled games passing `lichess_blitz`: {pop['sample_blitz_games']}\n"
        f"- Positions: {positions}\n"
        f"- Zero played probability: {pop['zero_probability_count']}{share_text}\n\n"
        f"{scores}\n\n## By rating band\n\n{bands}\n\n## By ply\n\n{plies}\n\n"
        "The 55–57% top-1 range is context only. It is not a pass/fail bar.\n"
        "Intervals resample games and keep every scored ply of a drawn game.\n"
        "A played probability of zero is a top-1 and top-3 miss and is left out of log-loss.\n"
    )
