"""Independently tally M7 April v8 opening families and cohorts from retained raw PGNs."""

import json
from collections import Counter
from pathlib import Path

import duckdb

from chess_analytics.common import read_json, write_json
from chess_analytics.ingest.pgn import records
from chess_analytics.warehouse.snapshots import current
from scripts.reference_m3 import HEADER, family

PROJECT = Path(__file__).resolve().parents[1]
USAGE_FAMILIES = (
    "Sicilian Defense",
    "Queen's Pawn Game",
    "French Defense",
    "Caro-Kann Defense",
    "Scandinavian Defense",
    "Italian Game",
    "English Opening",
    "King's Pawn Game",
    "Zukertort Opening",
    "Queen's Gambit Declined",
    "Modern Defense",
    "Pirc Defense",
    "Indian Defense",
    "Philidor Defense",
    "Scotch Game",
    "Nimzo-Larsen Attack",
    "Van't Kruijs Opening",
    "Ruy Lopez",
    "Hungarian Opening",
    "Bishop's Opening",
    "Horwitz Defense",
    "Benoni Defense",
    "Petrov's Defense",
    "Four Knights Game",
    "Englund Gambit",
)
COHORT_FAMILIES = (
    "Queen's Pawn Game",
    "Sicilian Defense",
    "Scandinavian Defense",
    "French Defense",
)


def build(project: Path = PROJECT) -> dict:
    plan = read_json(project / "config/datasets.json")["analytical"]
    source = (
        project / "data/analytical" / f"complete-{plan['period']}-first-{plan['max_games']}.pgn"
    )
    snapshot = current(project / "data", "analytical")
    with duckdb.connect(str(snapshot / "warehouse.duckdb"), read_only=True) as con:
        accepted = {row[0] for row in con.execute("select game_id from fact_game").fetchall()}
    usage = Counter()
    cohorts = Counter()
    known = 0
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
        result = headers.get("Result")
        if result not in {"1-0", "0-1", "1/2-1/2"} or any(
            headers.get(color + "Title") == "BOT" for color in ("White", "Black")
        ):
            continue
        label = family(headers.get("Opening"))
        if not label:
            continue
        known += 1
        if label not in USAGE_FAMILIES:
            continue
        usage[label] += 1
        if label not in COHORT_FAMILIES or headers.get("TimeControl") != "60+0":
            continue
        rating = headers.get("WhiteElo", "")
        if not rating.isdigit() or not 1400 <= int(rating) < 1600:
            continue
        cohorts[(label, "games")] += 1
        if result == "1/2-1/2":
            cohorts[(label, "draws")] += 1
        elif result == "1-0":
            cohorts[(label, "wins")] += 1
        else:
            cohorts[(label, "losses")] += 1
    if any(usage[name] == 0 for name in USAGE_FAMILIES) or any(
        cohorts[(name, "games")] == 0 for name in COHORT_FAMILIES
    ):
        raise ValueError("M7 April v8 family or cohort has no reference records")
    m3 = json.loads((project / "reports/M3-independent-reference.json").read_text())
    if known != m3["known_opening_games"] or any(
        usage[name] != m3["opening_families"][name] for name in USAGE_FAMILIES
    ):
        raise ValueError("independent opening tallies disagree")
    return {
        "kind": "independent raw-PGN M7 April v8 reference; no model responses",
        "dataset_id": json.loads((project / "reports/M3-analytical-manifest.json").read_text())[
            "analytical_id"
        ],
        "source_snapshot_id": snapshot.name,
        "source": str(source.relative_to(project)),
        "families": list(USAGE_FAMILIES),
        "known_opening_games": known,
        "opening_usage": {name: usage[name] for name in USAGE_FAMILIES},
        "white_rating_1400_1599_60_plus_0": {
            name: {field: cohorts[(name, field)] for field in ("games", "wins", "draws", "losses")}
            for name in COHORT_FAMILIES
        },
        "clock_buckets_reference": "reports/M3-independent-reference.json",
    }


if __name__ == "__main__":
    result = build()
    write_json(PROJECT / "reports/M7-independent-reference-v8.json", result)
    print(
        json.dumps(
            {
                "families": len(result["families"]),
                "known_opening_games": result["known_opening_games"],
            }
        )
    )
