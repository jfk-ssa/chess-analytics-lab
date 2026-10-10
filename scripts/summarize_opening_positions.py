"""Publish bounded recurring-position rankings; preserve per-game denominators and routes."""

import argparse
import json
import time
from pathlib import Path

import chess
import duckdb

from chess_analytics.common import digest, now, read_json, write_json


def san_route(route):
    board = chess.Board()
    tokens = []
    for index, uci in enumerate(route.split()):
        move = chess.Move.from_uci(uci)
        if move not in board.legal_moves:
            raise ValueError("Published route contains an illegal move")
        prefix = f"{index // 2 + 1}." if index % 2 == 0 else ""
        tokens.append(prefix + board.san(move))
        board.push(move)
    return " ".join(tokens), " ".join(board.fen(en_passant="legal").split()[:4])


def configure(db, output):
    db.execute("set memory_limit='1GB'")
    db.execute("set max_temp_directory_size='2GB'")
    db.execute("set threads=2")
    db.execute("set preserve_insertion_order=false")
    db.execute("set temp_directory=?", [str(output / "temp")])


def position_details(db, row, denominator):
    position_id, key, games, route_count, loop_games = row
    route_rows = db.execute(
        """select route,count(*) games from detail_visits
        where position_id=? and not route_has_repeat group by route
        order by games desc,route limit 3""",
        [position_id],
    ).fetchall()
    routes = []
    for route, count in route_rows:
        text, endpoint = san_route(route)
        if endpoint != key:
            raise ValueError("Example route endpoint differs from its position")
        routes.append({"uci": route, "san": text, "games": count, "share": count / games})
    continuations = []
    board = chess.Board(key + " 0 1")
    following = db.execute(
        """select next_move,count(*) games from detail_visits
      where position_id=? and next_move is not null and next_move!=''
      group by next_move order by games desc,next_move""",
        [position_id],
    ).fetchall()
    for move, count in following[:5]:
        parsed = chess.Move.from_uci(move)
        if parsed not in board.legal_moves:
            raise ValueError("Observed continuation is not legal from its position")
        continuations.append(
            {
                "uci": move,
                "san": board.san(parsed),
                "games": count,
                "share_of_position_games": count / games,
            }
        )
    openings = db.execute(
        """select opening_family,eco,count(*) games from detail_visits
      where position_id=? group by all order by games desc,opening_family,eco limit 5""",
        [position_id],
    ).fetchall()
    families, ecos, unknown = db.execute(
        """select count(distinct opening_family) filter(where opening_family!='Unknown'),
        count(distinct eco) filter(where eco is not null and eco!=''),
        count(*) filter(where opening_family='Unknown')
        from detail_visits where position_id=?""",
        [position_id],
    ).fetchone()
    acyclic_games = games - loop_games
    dominant = route_rows[0][1] if route_rows else 0
    g3_games = db.execute(
        "select count(*) from detail_visits where position_id=? "
        "and list_contains(string_split(route,' '),'g2g3')",
        [position_id],
    ).fetchone()[0]
    return {
        "id": position_id,
        "position_key": key,
        "games": games,
        "frequency": games / denominator,
        "acyclic_routes": route_count,
        "loop_prefix_games": loop_games,
        "acyclic_games": acyclic_games,
        "dominant_route_games": dominant,
        "alternative_route_share": 1 - dominant / acyclic_games if acyclic_games else None,
        "other_acyclic_route_games": acyclic_games - sum(row[1] for row in route_rows),
        "distinct_recorded_families": families,
        "distinct_recorded_ecos": ecos,
        "unknown_family_games": unknown,
        "white_g3_played_games": g3_games,
        "routes": routes,
        "next_move_games": sum(count for _, count in following),
        "continuations": continuations,
        "opening_labels": [
            {"family": family, "eco": eco, "games": count} for family, eco, count in openings
        ],
    }


def coverage(db, positions):
    if not positions:
        return 0
    identifiers = [row[0] for row in positions]
    return db.execute(
        """select count(distinct (provider,game_id)) from selected_visits
      where position_id in (select unnest(?))""",
        [identifiers],
    ).fetchone()[0]


def coverage_curve(db, positions, denominator):
    """Count a game's earliest ranked hit; cumulative unions do not double-count it."""
    if not positions:
        return []
    identifiers = [row[0] for row in positions]
    histogram = dict(
        db.execute(
            """with ranked as (select unnest(?) position_id,unnest(?) rank),
        first_hit as (select provider,game_id,min(rank) first_rank
        from selected_visits join ranked using(position_id) group by provider,game_id)
        select first_rank,count(*) from first_hit group by first_rank""",
            [identifiers, list(range(1, len(positions) + 1))],
        ).fetchall()
    )
    covered = 0
    result = []
    for n in range(1, len(positions) + 1):
        added = histogram.get(n, 0)
        covered += added
        result.append(
            {"n": n, "games": covered, "share": covered / denominator, "additional_games": added}
        )
    return result


def summarize_view(db, family, denominator, top_n, relation_name="cohort_visits"):
    relation = db.table(relation_name)
    if family:
        relation = relation.filter("opening_family='" + family.replace("'", "''") + "'")
    relation.create_view("selected_visits", replace=True)
    db.execute("""create or replace temporary table position_counts as
      select position_id,any_value(position_key) position_key,count(*) games,
      count(distinct route) filter(where not route_has_repeat) acyclic_routes,
      count(*) filter(where route_has_repeat) loop_prefix_games
      from selected_visits group by position_id""")
    distinct, recurring, transposing = db.execute("""select count(*),
      count(*) filter(where games>=2),count(*) filter(where acyclic_routes>=2)
      from position_counts""").fetchone()
    rankings = {}
    selected = {}
    for kind, condition in (("recurring", "games>=2"), ("transposing", "acyclic_routes>=2")):
        rows = db.execute(
            f"""select * from position_counts where {condition}
          order by games desc,position_id limit ?""",
            [top_n],
        ).fetchall()
        curve = coverage_curve(db, rows, denominator)
        rankings[kind] = {
            "ids": [row[0] for row in rows],
            "top_10_game_coverage": curve[min(10, len(curve)) - 1]["games"] if curve else 0,
            "top_20_game_coverage": curve[-1]["games"] if curve else 0,
            "coverage_curve": curve,
        }
        selected.update({row[0]: row for row in rows})
    db.execute(
        """create or replace temporary table detail_visits as
      select * from selected_visits where position_id in (select unnest(?))""",
        [list(selected)],
    )
    details = {key: position_details(db, row, denominator) for key, row in selected.items()}
    return {
        "family": family,
        "denominator_games": denominator,
        "distinct_positions": distinct,
        "recurring_positions": recurring,
        "transposing_positions": transposing,
        "rankings": rankings,
        "positions": details,
    }


LENSES = {
    "d4-g3": {"label": "1.d4 with g3", "moves": ["d2d4", "g2g3"]},
    "d4-g3-catalan": {
        "label": "Catalan-style fianchetto",
        "moves": ["d2d4", "c2c4", "g2g3", "f1g2", "e7e6", "d7d5"],
    },
    "d4-g3-kings-indian": {
        "label": "King's Indian fianchetto",
        "moves": ["d2d4", "c2c4", "g2g3", "f1g2", "g8f6", "g7g6", "f8g7", "d7d6"],
    },
}


def summarize_lenses(db, cohort, plan):
    """Curated move-sequence facets, independent of provider's later opening labels."""
    result = {}
    for name, definition in LENSES.items():
        db.execute(
            """create or replace temporary table lens_games as
            select distinct provider,game_id from visits
            where cohort=? and ply=? and starts_with(route,'d2d4 ')
            and list_has_all(string_split(route,' '),?)""",
            [cohort, plan["max_ply"], definition["moves"]],
        )
        count = db.execute("select count(*) from lens_games").fetchone()[0]
        if not count:
            continue
        db.execute("""create or replace temporary table lens_visits as
            select * from cohort_visits join lens_games using(provider,game_id)""")
        view = summarize_view(db, None, count, plan["published_positions_per_view"], "lens_visits")
        view["lens"] = {
            "version": "1.0.0",
            **definition,
            "rule": "First White move d4; all listed UCI moves played within the opening window.",
            "includes_pre_g3_positions": True,
        }
        result[name] = view
    return result


def summarize(snapshot, output, plan):
    snapshot, output = snapshot.resolve(), output.resolve()
    manifest = read_json(snapshot / "manifest.json")
    if plan != manifest["plan"]:
        raise ValueError("Summary plan differs from the checked visit extraction")
    for name, expected in manifest["artifacts"].items():
        if digest(snapshot / name) != expected:
            raise ValueError("Opening visit shard or receipt hash changed")
    output.parent.mkdir(parents=True, exist_ok=True)
    work = snapshot.parent.parent / "summaries" / manifest["snapshot_id"]
    work.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    result = {
        "kind": "observed_white_opening_positions",
        "version": "1.1.0",
        "created_at": now(),
        "visit_snapshot_id": manifest["snapshot_id"],
        "visit_manifest_sha256": digest(snapshot / "manifest.json"),
        "corpus_snapshot_id": manifest["corpus_snapshot_id"],
        "plan": plan,
        "training_sources": manifest["training_sources"],
        "cohorts": {},
        "builder_sha256": digest(Path(__file__)),
        "runtime": {
            "chess": chess.__version__,
            "duckdb": duckdb.__version__,
            "uv_lock_sha256": digest(Path(__file__).resolve().parents[1] / "uv.lock"),
        },
        "live_requests": 0,
        "data_downloads": 0,
    }
    with duckdb.connect(str(work / "rankings.duckdb")) as db:
        configure(db, work)
        db.read_parquet(str(snapshot / "visits-*.parquet")).create_view("visits", replace=True)
        games, visits = db.execute(
            "select count(distinct (provider,game_id)),count(*) from visits"
        ).fetchone()
        if games != manifest["games"] or visits != manifest["visits"]:
            raise ValueError("Opening visit counts differ from extraction manifest")
        for cohort in plan["cohorts"]:
            print(json.dumps({"summarizing": cohort}), flush=True)
            db.execute(
                """create or replace table cohort_visits as select * from visits
              where cohort=? qualify row_number() over (
                partition by provider,game_id,position_id order by ply)=1""",
                [cohort],
            )
            if db.execute("""select count(*) from (select position_id from cohort_visits
              group by position_id having count(distinct position_key)>1)""").fetchone()[0]:
                raise ValueError("Position identifier collision")
            denominator = db.execute(
                "select count(distinct (provider,game_id)) from cohort_visits"
            ).fetchone()[0]
            expected = sum(
                s["games"] for s in manifest["training_sources"] if s["cohort"] == cohort
            )
            if denominator != expected:
                raise ValueError("Cohort denominator does not match checked corpus")
            openings = db.execute("""select opening_family,count(distinct (provider,game_id)) games
              from cohort_visits group by opening_family
              order by games desc,opening_family""").fetchall()
            data = {
                "denominator_games": denominator,
                "opening_families": [
                    {"family": family, "games": count, "share": count / denominator}
                    for family, count in openings
                ],
                "views": {
                    "all": summarize_view(
                        db, None, denominator, plan["published_positions_per_view"]
                    )
                },
                "compression_by_ply": [],
            }
            for ply in range(plan["min_ply"], plan["max_ply"] + 1, 2):
                seq, pos, included = db.execute(
                    """select count(distinct route),
                  count(distinct position_id),count(*) from visits
                  where cohort=? and ply=? and not route_has_repeat""",
                    [cohort, ply],
                ).fetchone()
                data["compression_by_ply"].append(
                    {
                        "ply": ply,
                        "distinct_routes": seq,
                        "distinct_positions": pos,
                        "included_visits": included,
                        "endpoint_compression": 1 - pos / seq if seq else 0,
                    }
                )
            for family, count in openings[:12]:
                if family == "Unknown" or count < plan["minimum_opening_games"]:
                    continue
                data["views"][family] = summarize_view(
                    db, family, count, plan["published_positions_per_view"]
                )
            data["views"].update(summarize_lenses(db, cohort, plan))
            result["cohorts"][cohort] = data
            db.execute("drop table cohort_visits")
    result["elapsed_seconds"] = round(time.monotonic() - started, 2)
    result["limitations"] = [
        "White decision positions within the declared opening window, not all game positions.",
        "Each game counts once per position; repetition prefixes do not add acyclic routes.",
        "Opening families are recorded labels before the first colon; not position taxonomy.",
        "Elite is a curated November 2025 month; public data are nine first-day prefixes.",
        "Observed continuation frequency is not move quality or a causal result.",
        "Explorer shows top 20 positions and up to 12 largest labeled opening families per cohort.",
        "Top-position game coverage is a union, not the sum of individual frequencies.",
    ]
    write_json(output, result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("reports/opening-positions.json"))
    parser.add_argument("--plan", type=Path, default=Path("config/opening-positions.json"))
    args = parser.parse_args()
    report = summarize(args.snapshot, args.output, read_json(args.plan))
    print(
        json.dumps(
            {name: data["views"]["all"]["rankings"] for name, data in report["cohorts"].items()}
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
