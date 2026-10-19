"""Independent raw-PGN references for the 100-game live-eval fixture.

This script uses python-chess as a PGN parser only. It does not import the
reviewed metric functions, the semantic layer, or the analyst tools. Bucket
cuts, the 200-centipawn error rule, the opening-family split, and the score
arithmetic are restated here so a change in those tools can disagree with this
file. ``source_kind`` and ``partial_archive`` are labels of the import plan,
not quantities read off the move text.

Hand counts locked below were tallied from the generator index rules, not from
the tool output. The script refuses to write when a computed integer disagrees.
"""

import io
import re
from pathlib import Path

import chess.pgn

from chess_analytics.common import write_json

PROJECT = Path(__file__).resolve().parents[1]
SOURCE = PROJECT / "tests/fixtures/live_eval_100.pgn"
DESTINATION = PROJECT / "tests/fixtures/live_eval_100_expected.json"
RESULTS = {"1-0", "0-1", "1/2-1/2"}
BUCKETS = ("under_10", "10_to_29", "30_to_59", "60_plus")
SCORE_FILTERS = {
    "base_seconds": 60,
    "color": "white",
    "increment_seconds": 0,
    "rating_max_exclusive": 1600,
    "rating_min": 1400,
}
# Integer tallies from the generator tables. See the ADR for the arithmetic.
HAND = {
    "games": 100,
    "draws": 33,
    "white_wins": 34,
    "black_wins": 33,
    "opening_known_games": 100,
    "family_count": 12,
    "sicilian_games": 18,
    "french_games": 14,
    "time_60_0": 70,
    "sicilian_white_games": 7,
    "sicilian_white_wins": 3,
    "sicilian_white_draws": 2,
    "sicilian_white_losses": 2,
    "french_white_games": 5,
    "french_white_wins": 1,
    "french_white_draws": 2,
    "french_white_losses": 2,
    "increment_zero_games": 80,
    "populated_eligible_moves": 160,
    "populated_evaluable_moves": 130,
    "under_10_errors": 25,
    "bucket_30_to_59_errors": 15,
    "empty_eligible_moves": 0,
    "move_rows_if_all_sampled": 600,
}


def opening_family(value: str | None) -> str | None:
    """Text before the first colon. Blank text is missing."""
    if not value:
        return None
    head = value.split(":", 1)[0].strip()
    return head or None


def clock_bucket(seconds: float | None) -> str | None:
    """Same four cuts as the warehouse. This copy does not import that helper."""
    if seconds is None or seconds < 0:
        return None
    if seconds < 10:
        return "under_10"
    if seconds < 30:
        return "10_to_29"
    if seconds < 60:
        return "30_to_59"
    return "60_plus"


def _time_control(value: str | None) -> tuple[int | None, int | None]:
    match = re.fullmatch(r"(\d+)\+(\d+)", value or "")
    if not match:
        return None, None
    return int(match[1]), int(match[2])


def _evaluation(node) -> tuple[int | None, int | None]:
    value = node.eval()
    if value is None:
        return None, None
    white = value.white()
    return white.score(), white.mate()


def _walk(game) -> list[dict]:
    """Per-ply clock and error fields. The nulling rule matches move extraction."""
    headers = game.headers
    base, increment = _time_control(headers.get("TimeControl"))
    rows = []
    previous = (None, None)
    same_side: dict[str, float | None] = {"white": None, "black": None}
    for node in game.mainline():
        ply = node.ply()
        color = "white" if ply % 2 else "black"
        after = node.clock()
        if after is not None and after < 0:
            after = None
        if after is not None and increment == 0 and base is not None and after > base:
            after = None
        before = same_side[color]
        after_cp, after_mate = _evaluation(node)
        before_cp, _before_mate = previous
        deterioration = None
        if before_cp is not None and after_cp is not None:
            direction = 1 if color == "white" else -1
            deterioration = max(0, direction * (before_cp - after_cp))
        rows.append(
            {
                "before_clock": before,
                "bucket": clock_bucket(before),
                "deterioration": deterioration,
                "error": deterioration >= 200 if deterioration is not None else None,
                "has_after_cp": after_cp is not None,
                "has_after_mate": after_mate is not None,
            }
        )
        same_side[color] = after
        previous = (after_cp, after_mate)
    return rows


def _read_games(text: str) -> list:
    handle = io.StringIO(text)
    games = []
    while game := chess.pgn.read_game(handle):
        games.append(game)
    return games


def _eligible(headers) -> bool:
    if headers.get("Result") not in RESULTS:
        return False
    return headers.get("WhiteTitle") != "BOT" and headers.get("BlackTitle") != "BOT"


def _white_score(result: str) -> float:
    return {"1-0": 1.0, "1/2-1/2": 0.5, "0-1": 0.0}[result]


def _cohort(headers, family: str) -> bool:
    if opening_family(headers.get("Opening")) != family:
        return False
    base, increment = _time_control(headers.get("TimeControl"))
    if base != SCORE_FILTERS["base_seconds"] or increment != SCORE_FILTERS["increment_seconds"]:
        return False
    try:
        rating = int(headers.get("WhiteElo", ""))
    except ValueError:
        return False
    return SCORE_FILTERS["rating_min"] <= rating < SCORE_FILTERS["rating_max_exclusive"]


def _score_block(games, family: str) -> dict:
    wins = draws = losses = 0
    for game in games:
        headers = game.headers
        if not _eligible(headers) or not _cohort(headers, family):
            continue
        result = headers["Result"]
        wins += result == "1-0"
        draws += result == "1/2-1/2"
        losses += result == "0-1"
    total = wins + draws + losses
    score = wins + 0.5 * draws
    return {
        "draws": draws,
        "eligible_player_games": total,
        "losses": losses,
        "score_rate": score / total if total else None,
        "win_rate": wins / total if total else None,
        "wins": wins,
    }


def _clock_blocks(games) -> dict:
    tallies = {bucket: {"eligible": 0, "errors": 0, "evaluable": 0} for bucket in BUCKETS}
    for game in games:
        headers = game.headers
        _base, increment = _time_control(headers.get("TimeControl"))
        if not _eligible(headers) or increment != 0:
            continue
        for row in _walk(game):
            bucket = row["bucket"]
            if bucket is None:
                continue
            tallies[bucket]["eligible"] += 1
            if row["deterioration"] is not None:
                tallies[bucket]["evaluable"] += 1
            if row["error"]:
                tallies[bucket]["errors"] += 1
    blocks = {}
    for bucket in BUCKETS:
        eligible = tallies[bucket]["eligible"]
        evaluable = tallies[bucket]["evaluable"]
        errors = tallies[bucket]["errors"]
        blocks[bucket] = {
            "bucket": bucket,
            "eligible_moves": eligible,
            "error_proxy_rate": errors / evaluable if evaluable else None,
            "evaluable_moves": evaluable,
            "evaluation_coverage": evaluable / eligible if eligible else None,
            "proxy_errors": errors,
        }
    return blocks


def _difference(left, right, key: str):
    if left[key] is None or right[key] is None:
        return None
    return left[key] - right[key]


def _population(games) -> dict:
    families: dict[str, int] = {}
    controls: dict[str, int] = {}
    draws = white_wins = black_wins = known = increment_zero = 0
    for game in games:
        headers = game.headers
        result = headers.get("Result")
        draws += result == "1/2-1/2"
        white_wins += result == "1-0"
        black_wins += result == "0-1"
        family = opening_family(headers.get("Opening"))
        if family and _eligible(headers):
            known += 1
            families[family] = families.get(family, 0) + 1
        control = headers.get("TimeControl")
        if control:
            controls[control] = controls.get(control, 0) + 1
        _base, increment = _time_control(control)
        increment_zero += increment == 0 and _eligible(headers)
    return {
        "black_wins": black_wins,
        "draws": draws,
        "families": dict(sorted(families.items())),
        "family_count": len(families),
        "games": len(games),
        "increment_zero_games": increment_zero,
        "opening_known_games": known,
        "time_controls": dict(sorted(controls.items())),
        "white_wins": white_wins,
    }


def _check_hand(population: dict, sicilian: dict, french: dict, clock: dict) -> None:
    """Refuse to write when the PGN disagrees with the hand tally."""
    expected = {
        "games": population["games"],
        "draws": population["draws"],
        "white_wins": population["white_wins"],
        "black_wins": population["black_wins"],
        "opening_known_games": population["opening_known_games"],
        "family_count": population["family_count"],
        "sicilian_games": population["families"].get("Sicilian Defense"),
        "french_games": population["families"].get("French Defense"),
        "time_60_0": population["time_controls"].get("60+0"),
        "sicilian_white_games": sicilian["eligible_player_games"],
        "sicilian_white_wins": sicilian["wins"],
        "sicilian_white_draws": sicilian["draws"],
        "sicilian_white_losses": sicilian["losses"],
        "french_white_games": french["eligible_player_games"],
        "french_white_wins": french["wins"],
        "french_white_draws": french["draws"],
        "french_white_losses": french["losses"],
        "increment_zero_games": population["increment_zero_games"],
        "populated_eligible_moves": clock["under_10"]["eligible_moves"],
        "populated_evaluable_moves": clock["under_10"]["evaluable_moves"],
        "under_10_errors": clock["under_10"]["proxy_errors"],
        "bucket_30_to_59_errors": clock["30_to_59"]["proxy_errors"],
        "empty_eligible_moves": clock["10_to_29"]["eligible_moves"],
        "move_rows_if_all_sampled": population["games"] * 6,
    }
    mismatched = [key for key, value in expected.items() if value != HAND[key]]
    if mismatched or clock["60_plus"]["eligible_moves"] != 0:
        raise ValueError("hand tally mismatch: " + ", ".join(mismatched))
    if clock["30_to_59"]["eligible_moves"] != HAND["populated_eligible_moves"]:
        raise ValueError("hand tally mismatch: 30_to_59 eligible")
    if clock["30_to_59"]["evaluable_moves"] != HAND["populated_evaluable_moves"]:
        raise ValueError("hand tally mismatch: 30_to_59 evaluable")


def references_for(text: str) -> dict:
    """Reference object for one PGN document. Counts are exact; rates are ratios."""
    games = _read_games(text)
    population = _population(games)
    sicilian = _score_block(games, "Sicilian Defense")
    french = _score_block(games, "French Defense")
    clock = _clock_blocks(games)
    _check_hand(population, sicilian, french, clock)
    under = clock["under_10"]
    mid = clock["30_to_59"]
    known = population["opening_known_games"]
    return {
        "clock": clock,
        "clock_compare_under_10_minus_30_to_59": {
            "error_proxy_rate_difference_first_minus_second": _difference(
                under, mid, "error_proxy_rate"
            ),
            "evaluation_coverage_difference_first_minus_second": _difference(
                under, mid, "evaluation_coverage"
            ),
        },
        "compare_openings": {
            "families": ["Sicilian Defense", "French Defense"],
            "filters": SCORE_FILTERS,
            "score_rate_difference_first_minus_second": _difference(sicilian, french, "score_rate"),
            "win_rate_difference_first_minus_second": _difference(sicilian, french, "win_rate"),
        },
        "coverage": {
            "accepted": population["games"],
            "conflict": 0,
            "duplicate": 0,
            "eligible_games": population["games"],
            "excluded": 0,
            "known_opening_games": known,
            "missing_source_opening": 0,
            "move_rows": population["games"] * 6,
            "partial_archive": True,
            "quarantine": 0,
            "seen": population["games"],
            "selected_games": population["games"],
            "selected_zero_ply_games": 0,
            "source_kind": "synthetic_test_fixture",
        },
        "french_white_score": french,
        "game_draw_rate": {
            "denominator": population["games"],
            "numerator": population["draws"],
            "value": population["draws"] / population["games"] if population["games"] else None,
        },
        "hand_counts": HAND,
        "kind": "independent raw-pgn reference for the live-eval fixture; not a model result",
        "opening_usage": {
            "French Defense": {
                "denominator": known,
                "numerator": population["families"].get("French Defense", 0),
                "value": population["families"].get("French Defense", 0) / known if known else None,
            },
            "Sicilian Defense": {
                "denominator": known,
                "numerator": population["families"].get("Sicilian Defense", 0),
                "value": (
                    population["families"].get("Sicilian Defense", 0) / known if known else None
                ),
            },
        },
        "population": population,
        "seed": 20261018,
        "sicilian_white_score": sicilian,
        "source": "tests/fixtures/live_eval_100.pgn",
    }


def draw_count(text: str) -> int:
    """Draws in a PGN document. Used when a test flips one result."""
    return sum(game.headers.get("Result") == "1/2-1/2" for game in _read_games(text))


def main() -> None:
    payload = references_for(SOURCE.read_text(encoding="utf-8"))
    write_json(DESTINATION, payload)


if __name__ == "__main__":
    main()
