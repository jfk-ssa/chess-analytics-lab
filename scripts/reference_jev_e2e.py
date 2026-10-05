"""Raw-PGN opening reference for the fresh M8 end-to-end experiment."""

import json
from collections import Counter
from pathlib import Path

import duckdb

from chess_analytics.common import digest, read_json, write_json
from chess_analytics.ingest.pgn import records
from chess_analytics.warehouse.snapshots import current
from scripts.reference_m3 import HEADER, family

FAMILIES = (
    "Vienna Game",
    "Owen Defense",
    "Nimzowitsch Defense",
    "Bird Opening",
    "Slav Defense",
    "Alekhine Defense",
    "Mieses Opening",
    "King's Indian Defense",
)


def build(project: Path) -> dict:
    plan = read_json(project / "config/datasets.json")["analytical"]
    source = (
        project / "data/analytical" / f"complete-{plan['period']}-first-{plan['max_games']}.pgn"
    )
    snapshot = current(project / "data", "analytical")
    with duckdb.connect(str(snapshot / "warehouse.duckdb"), read_only=True) as con:
        accepted = {row[0] for row in con.execute("select game_id from fact_game").fetchall()}
    counts = Counter()
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
        opening = family(headers.get("Opening"))
        if not opening:
            continue
        known += 1
        if opening not in FAMILIES:
            continue
        counts[opening] += 1
        if headers.get("TimeControl") != "60+0":
            continue
        rating = headers.get("WhiteElo", "")
        if not rating.isdigit() or not 1400 <= int(rating) < 1600:
            continue
        cohorts[(opening, "games")] += 1
        if result == "1/2-1/2":
            cohorts[(opening, "draws")] += 1
        elif result == "1-0":
            cohorts[(opening, "wins")] += 1
        else:
            cohorts[(opening, "losses")] += 1
    if not all(counts[name] and cohorts[(name, "games")] for name in FAMILIES):
        raise ValueError("a frozen opening family has no raw-PGN support")
    old = json.loads((project / "reports/M7-independent-reference-v12.json").read_text())
    if known != old["known_opening_games"] or set(FAMILIES) & set(old["families"]):
        raise ValueError("new reference denominator or novelty failed")
    manifest = json.loads((project / "reports/M3-analytical-manifest.json").read_text())
    clocks = json.loads((project / "reports/M3-independent-reference.json").read_text())
    return {
        "kind": "m8_new_family_raw_pgn_reference_no_model_responses",
        "source": str(source.relative_to(project)),
        "source_sha256": digest(source),
        "source_snapshot_id": snapshot.name,
        "dataset_id": manifest["analytical_id"],
        "known_opening_games": known,
        "opening_usage": {name: counts[name] for name in FAMILIES},
        "white_rating_1400_1599_60_plus_0": {
            name: {field: cohorts[(name, field)] for field in ("games", "wins", "draws", "losses")}
            for name in FAMILIES
        },
        "clock_reference_sha256": digest(project / "reports/M3-independent-reference.json"),
        "clock_reference_kind": clocks["kind"],
        "prior_family_overlap": 0,
    }


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    result = build(root / "work/m7-december-project")
    write_json(root / "reports/M8-e2e-independent-reference.json", result)
    print(
        json.dumps(
            {"families": len(result["opening_usage"]), "known": result["known_opening_games"]}
        )
    )
