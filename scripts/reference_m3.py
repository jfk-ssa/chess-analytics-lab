"""Independent PGN-header/comment tally for M3; does not use chess_analytics.corpus metric code."""

import hashlib
import io
import json
import re
from collections import Counter
from decimal import Decimal
from pathlib import Path

import chess.pgn
import duckdb

from chess_analytics.common import read_json
from chess_analytics.ingest.pgn import records
from chess_analytics.warehouse.snapshots import current

PROJECT = Path(__file__).resolve().parents[1]
HEADER = re.compile(r'^\[(\w+) "(.*)"\]$')
CLOCK = re.compile(r"\[%clk\s+(\d+):(\d+):(\d+(?:\.\d+)?)\]")
EVAL = re.compile(r"\[%eval\s+([#-]?[-\d.]+)\]")


def seconds(comment):
    match = CLOCK.search(comment)
    if not match:
        return None
    return int(match[1]) * 3600 + int(match[2]) * 60 + float(match[3])


def score(comment):
    match = EVAL.search(comment)
    if not match:
        return None, False
    value = match[1]
    if value.startswith("#"):
        return None, True
    return int(Decimal(value) * 100), False


def family(opening):
    return opening.split(":", 1)[0].strip() if opening and opening.strip() else None


def bucket(clock):
    if clock < 10:
        return "under_10"
    if clock < 30:
        return "10_to_29"
    if clock < 60:
        return "30_to_59"
    return "60_plus"


def reference(project=PROJECT, root=None):
    root = Path(root or project / "data")
    plan = read_json(project / "config/datasets.json")["analytical"]
    source = root / "analytical" / f"complete-{plan['period']}-first-{plan['max_games']}.pgn"
    snapshot = current(root, "analytical")
    with duckdb.connect(str(snapshot / "warehouse.duckdb"), read_only=True) as con:
        accepted = {row[0] for row in con.execute("select game_id from fact_game").fetchall()}
    families = Counter()
    eligible_games = 0
    known_opening_games = 0
    missing_source_opening = 0
    selected_games = 0
    selected_moves = 0
    clocks = Counter()
    cohort = Counter()
    draw_count = 0
    for _, raw, _ in records(source, plan):
        headers = {}
        for line in raw.splitlines():
            if not line.startswith("["):
                break
            match = HEADER.fullmatch(line)
            if match:
                headers[match[1]] = match[2]
        game_id = headers.get("Site", "").rsplit("/", 1)[-1]
        if game_id not in accepted:
            continue
        opening = headers.get("Opening")
        if not opening or not opening.strip():
            missing_source_opening += 1
        completed = headers.get("Result") in {"1-0", "0-1", "1/2-1/2"}
        bot = headers.get("WhiteTitle") == "BOT" or headers.get("BlackTitle") == "BOT"
        if completed and not bot:
            eligible_games += 1
            draw_count += headers.get("Result") == "1/2-1/2"
            label = family(opening)
            if label:
                known_opening_games += 1
                families[label] += 1
            if (
                label in {"Sicilian Defense", "French Defense"}
                and headers.get("TimeControl") == "60+0"
            ):
                for color in ("White", "Black"):
                    rating = headers.get(color + "Elo", "")
                    if rating.isdigit() and 1400 <= int(rating) < 1600:
                        key = (label, color.lower())
                        cohort[(key, "games")] += 1
                        outcome = headers["Result"]
                        if outcome == "1/2-1/2":
                            cohort[(key, "draws")] += 1
                        elif (outcome == "1-0" and color == "White") or (
                            outcome == "0-1" and color == "Black"
                        ):
                            cohort[(key, "wins")] += 1
                        else:
                            cohort[(key, "losses")] += 1
        number = int.from_bytes(hashlib.sha256(game_id.encode()).digest()[:8], "big")
        if number % 20:
            continue
        selected_games += 1
        game = chess.pgn.read_game(io.StringIO(raw))
        if game is None or game.errors:
            raise ValueError("reference PGN parse failed")
        prior_same = {"white": None, "black": None}
        prior_eval = (None, False)
        control = headers.get("TimeControl", "")
        base, _, increment = control.partition("+")
        valid_zero_increment = base.isdigit() and increment == "0"
        base_seconds = int(base) if base.isdigit() else None
        for node in game.mainline():
            selected_moves += 1
            color = "white" if node.ply() % 2 else "black"
            after_clock = seconds(node.comment)
            if after_clock is not None and valid_zero_increment and after_clock > base_seconds:
                after_clock = None
            before_clock = prior_same[color]
            current_eval = score(node.comment)
            if completed and not bot and valid_zero_increment and before_clock is not None:
                label = bucket(before_clock)
                clocks[(label, "eligible")] += 1
                if prior_eval[1] or current_eval[1]:
                    clocks[(label, "mate")] += 1
                if prior_eval[0] is not None and current_eval[0] is not None:
                    clocks[(label, "evaluable")] += 1
                    direction = 1 if color == "white" else -1
                    loss = direction * (prior_eval[0] - current_eval[0])
                    if loss >= 200:
                        clocks[(label, "errors")] += 1
            prior_same[color] = after_clock
            prior_eval = current_eval
    return {
        "kind": "independent raw-PGN reference; no model response",
        "source_snapshot_id": snapshot.name,
        "accepted_games": len(accepted),
        "eligible_games": eligible_games,
        "drawn_eligible_games": draw_count,
        "known_opening_games": known_opening_games,
        "missing_source_opening": missing_source_opening,
        "selected_games": selected_games,
        "selected_moves": selected_moves,
        "opening_families": dict(sorted(families.items())),
        "opening_player_cohorts": {
            f"{family_name}|{color}|rating_1400_1599|60+0": {
                field: cohort[((family_name, color), field)]
                for field in ("games", "wins", "draws", "losses")
            }
            for family_name in ("Sicilian Defense", "French Defense")
            for color in ("white", "black")
        },
        "clock_buckets": {
            label: {
                field: clocks[(label, field)]
                for field in ("eligible", "evaluable", "errors", "mate")
            }
            for label in ("under_10", "10_to_29", "30_to_59", "60_plus")
        },
    }


if __name__ == "__main__":
    result = reference()
    print(json.dumps(result, indent=2, sort_keys=True))
