"""Publish a rating-filtered opening-game index over checked retained source snapshots.

PGNs stay in their existing source locations. This command does not download games
or create graph positions; it creates the corpus selection those operations can reuse.
"""

import json
import re
import shutil
import uuid
from pathlib import Path

import duckdb

from chess_analytics.common import digest, hash_json, now, read_json, write_json, writer_lock
from chess_analytics.warehouse.snapshots import validate_snapshot

PROJECT = Path(__file__).resolve().parents[1]


def checked_source(manifest_path):
    manifest = read_json(manifest_path)
    snapshot = manifest_path.parent
    validate_snapshot(snapshot)
    source_root = snapshot.parent.parent
    name = manifest["source_file"]
    candidates = [source_root / name, source_root / "analytical" / name, source_root / "raw" / name]
    source = next((p for p in candidates if p.is_file()), None)
    if source is None or digest(source) != manifest["source_sha256"]:
        raise ValueError(f"missing or changed source PGN for {snapshot.name}")
    return {
        "manifest": str(manifest_path.relative_to(PROJECT)),
        "manifest_sha256": digest(manifest_path),
        "snapshot_id": snapshot.name,
        "period": manifest["plan"]["period"],
        "source_file": str(source.relative_to(PROJECT)),
        "source_sha256": manifest["source_sha256"],
        "accepted": manifest["counts"]["accepted"],
        "complete_archive": manifest["plan"].get("complete_archive", False),
        "source_kind": manifest["plan"].get("source_kind", "historical_foundation"),
    }


def validate_publication(path):
    manifest = read_json(path / "manifest.json")
    for name, expected in manifest["artifacts"].items():
        if digest(path / name) != expected:
            raise ValueError(f"opening corpus artifact hash changed: {name}")
    policy = manifest["policy"]
    with duckdb.connect(str(path / "warehouse.duckdb"), read_only=True) as db:
        count, unique, bad = db.execute(
            """
            select count(*), count(distinct (provider,game_id)), count(*) filter (
              where white_rating < ? or black_rating < ? or white_rating is null
              or black_rating is null or marked_bot or result='*' or ply_count < ?
              or source_period='2013-01') from opening_game
            """,
            [
                policy["minimum_rating_both_players"],
                policy["minimum_rating_both_players"],
                policy["minimum_plies"],
            ],
        ).fetchone()
        if count != unique or bad or count != manifest["counts"]["training_games"]:
            raise ValueError("opening corpus selection does not reconcile")
    return manifest


def main():
    policy = read_json(PROJECT / "config/opening-corpus.json")
    elite_id = read_json(PROJECT / "data/elite/elite-current.json")["snapshot_id"]
    if not re.fullmatch(r"[0-9a-f]{24}", elite_id):
        raise ValueError("invalid Elite source snapshot identity")
    # Elite goes first if a game appears in both sources; compare metadata before merging.
    manifests = [PROJECT / f"data/elite/published/{elite_id}/manifest.json"]
    manifests.extend(PROJECT / name for name in policy["retained_source_manifests"])
    sources = [checked_source(path) for path in manifests]
    identity = hash_json(
        {"policy": policy, "sources": sources, "builder_sha256": digest(Path(__file__))}
    )[:24]
    root = PROJECT / "data/openings"
    with writer_lock(root):
        final = root / "published" / identity
        if final.exists():
            manifest = validate_publication(final)
        else:
            candidate = root / "staging" / uuid.uuid4().hex
            candidate.mkdir(parents=True)
            if shutil.disk_usage(root).free < 3_000_000_000:
                raise ValueError("opening corpus needs 3 GB free before indexing")
            try:
                with duckdb.connect(str(candidate / "warehouse.duckdb")) as db:
                    db.execute("set memory_limit='1GB'")
                    db.execute("set max_temp_directory_size='2GB'")
                    db.execute("set preserve_insertion_order=false")
                    db.execute("set threads=2")
                    parts = []
                    for i, (source, path) in enumerate(zip(sources, manifests, strict=True)):
                        source_db = path.parent / "warehouse.duckdb"
                        quoted_db = str(source_db).replace("'", "''")
                        db.execute(f"attach '{quoted_db}' as s{i} (read_only)")
                        db.execute(
                            f"""create temporary table t{i} as
                          select g.provider,g.game_id,g.result,g.rated,g.variant,g.utc_date,
                          g.time_control,g.base_seconds,g.increment_seconds,g.source_opening,
                          g.source_eco,g.marked_bot,g.ply_count,g.source_ordinal,
                          json_extract_string(g.headers_json,'$.Event') source_event,
                          g.record_fingerprint,w.rating white_rating,b.rating black_rating,
                          ? source_snapshot_id,? source_period,? source_file,? source_rank,
                          ? source_cohort from s{i}.fact_game g
                          join s{i}.fact_player_game w using(provider,game_id)
                          join s{i}.fact_player_game b using(provider,game_id)
                          where w.color='white' and b.color='black'
                          """,
                            [
                                source["snapshot_id"],
                                source["period"],
                                source["source_file"],
                                i,
                                "elite_reference" if i == 0 else "rated_public",
                            ],
                        )
                        parts.append(f"select * from t{i}")
                    db.execute("create temporary table source_rows as " + " union all ".join(parts))
                    for i in range(len(parts)):
                        db.execute(f"drop table t{i}")
                    conflicts = db.execute("""select count(*) from (
                      select provider,game_id from source_rows group by all having
                      count(distinct (result,white_rating,black_rating,time_control))>1)
                      """).fetchone()[0]
                    if conflicts:
                        raise ValueError(
                            "cross-source game metadata conflict; publication withheld"
                        )
                    db.execute("""create temporary table winners as
                      select provider,game_id,min(source_rank) source_rank
                      from source_rows group by all""")
                    db.execute("""create table retained_game as select s.* exclude(source_rank)
                      from source_rows s join winners using(provider,game_id,source_rank)""")
                    rows = db.execute("select count(*) from source_rows").fetchone()[0]
                    count, floor, above, missing = db.execute("""select count(*),
                      count(*) filter(where white_rating>=1000 and black_rating>=1000),
                      count(*) filter(where white_rating>1000 and black_rating>1000),
                      count(*) filter(where white_rating is null or black_rating is null)
                      from retained_game""").fetchone()
                    db.execute(
                        """create table opening_game as select * from retained_game
                      where white_rating>=? and black_rating>=? and not marked_bot
                      and result!='*' and ply_count>=? and source_period!='2013-01'
                      and (source_cohort!='elite_reference' or
                      (least(white_rating,black_rating)>=2300 and
                      greatest(white_rating,black_rating)>=2500 and
                      source_event not ilike '%bullet%'))
                      """,
                        [
                            policy["minimum_rating_both_players"],
                            policy["minimum_rating_both_players"],
                            policy["minimum_plies"],
                        ],
                    )
                    training, elite, high = db.execute("""select count(*),
                      count(*) filter(where source_cohort='elite_reference'),
                      count(*) filter(where white_rating>=2000 and black_rating>=2000)
                      from opening_game""").fetchone()
                    elite_below_selection = db.execute("""select count(*) from retained_game
                      where source_cohort='elite_reference' and (least(white_rating,black_rating)
                      <2300 or greatest(white_rating,black_rating)<2500)""").fetchone()[0]
                    summary = db.execute("""select source_period,source_cohort,count(*) games,
                      min(utc_date) first_date,max(utc_date) last_date,
                      min(least(white_rating,black_rating)) minimum_rating
                      from opening_game group by all order by source_period""").fetchall()
                    bands = db.execute("""select case when least(white_rating,black_rating)>=2300
                      then '2300+' when least(white_rating,black_rating)>=2000 then '2000–2299'
                      when least(white_rating,black_rating)>=1600 then '1600–1999'
                      else '1000–1599' end rating_band,count(*) from opening_game
                      group by all order by min(least(white_rating,black_rating))""").fetchall()
                    db.sql("select * from opening_game").write_parquet(
                        str(candidate / "opening_game.parquet")
                    )
                manifest = {
                    "kind": "checked_opening_training_game_index",
                    "version": "1.0.0",
                    "snapshot_id": identity,
                    "created_at": now(),
                    "policy": policy,
                    "sources": sources,
                    "builder_sha256": digest(Path(__file__)),
                    "resource_limits": {
                        "duckdb_memory_bytes": 1000000000,
                        "duckdb_temporary_bytes": 2000000000,
                        "free_disk_required_bytes": 3000000000,
                    },
                    "counts": {
                        "source_rows": rows,
                        "unique_retained_games": count,
                        "duplicates_removed": rows - count,
                        "both_at_least_1000": floor,
                        "both_above_1000": above,
                        "missing_either_rating": missing,
                        "training_games": training,
                        "elite_training_games": elite,
                        "both_at_least_2000_training": high,
                        "elite_below_publisher_rating_rule": elite_below_selection,
                    },
                    "training_sources": [
                        dict(
                            zip(
                                [
                                    "period",
                                    "cohort",
                                    "games",
                                    "first_date",
                                    "last_date",
                                    "minimum_rating",
                                ],
                                [
                                    str(value) if hasattr(value, "isoformat") else value
                                    for value in row
                                ],
                                strict=True,
                            )
                        )
                        for row in summary
                    ],
                    "rating_bands": dict(bands),
                    "artifacts": {p.name: digest(p) for p in candidate.iterdir() if p.is_file()},
                    "notes": [
                        "Both players meet the rating floor; source ratings are Lichess ratings.",
                        "No personal-history weighting; elite and broader frequency stay separate.",
                        "Game index points to legally validated full source PGNs; "
                        "positions are derived later.",
                        "Monthly prefixes cover observed first-day windows; "
                        "Elite is a curated month.",
                        "Historical foundation counts are reported but excluded from training.",
                    ],
                }
                write_json(candidate / "manifest.json", manifest)
                validate_publication(candidate)
                final.parent.mkdir(parents=True, exist_ok=True)
                candidate.rename(final)
            except BaseException as error:
                write_json(
                    candidate / "failure.json",
                    {"at": now(), "error": f"{type(error).__name__}: {error}"},
                )
                raise
        write_json(PROJECT / "data/opening-current.json", {"snapshot_id": identity})
        write_json(PROJECT / "reports/opening-corpus.json", manifest)
        print(json.dumps(manifest["counts"], indent=2))


if __name__ == "__main__":
    main()
