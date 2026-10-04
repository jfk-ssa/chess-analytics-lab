"""Independent raw-PGN tally for the new M6 opening-family holdout."""

import argparse
import json
from collections import Counter
from pathlib import Path

import duckdb

from chess_analytics.common import read_json, write_json
from chess_analytics.ingest.pgn import records
from chess_analytics.warehouse.snapshots import current
from scripts.reference_m3 import HEADER, family

PROJECT = Path(__file__).resolve().parents[1]
FAMILY_SETS = {
    1: ("Zukertort Opening", "King's Pawn Game"),
    2: ("Hungarian Opening", "Ruy Lopez"),
}


def build(project: Path = PROJECT, *, version: int = 1) -> dict:
    families = FAMILY_SETS[version]
    root = project / "data"
    plan = read_json(project / "config/datasets.json")["analytical"]
    source = root / "analytical" / f"complete-{plan['period']}-first-{plan['max_games']}.pgn"
    snapshot = current(root, "analytical")
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
        if label not in families:
            continue
        usage[label] += 1
        if headers.get("TimeControl") != "60+0":
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
    if any(cohorts[(name, "games")] == 0 for name in families):
        raise ValueError("holdout family has an empty cohort")
    analytical_id = json.loads((project / "reports/M3-analytical-manifest.json").read_text())[
        "analytical_id"
    ]
    return {
        "kind": "independent raw-PGN M6 holdout reference; no model responses",
        "dataset_id": analytical_id,
        "source_snapshot_id": snapshot.name,
        "source": str(source.relative_to(project)),
        "families": list(families),
        "known_opening_games": known,
        "opening_usage": {name: usage[name] for name in families},
        "white_rating_1400_1599_60_plus_0": {
            name: {field: cohorts[(name, field)] for field in ("games", "wins", "draws", "losses")}
            for name in families
        },
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", type=int, choices=tuple(FAMILY_SETS), default=1)
    version = parser.parse_args().version
    name = "M6-independent-reference.json" if version == 1 else "M6-independent-reference-v2.json"
    write_json(PROJECT / "reports" / name, build(version=version))
    print(json.dumps({"reference_written": True}))
