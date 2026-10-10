"""Independently reconcile bounded insight summaries with raw, checked visit shards."""

import argparse
from pathlib import Path

import duckdb

from chess_analytics.common import digest, read_json, write_json


def verify(snapshot, report_path, output):
    manifest = read_json(snapshot / "manifest.json")
    report = read_json(report_path)
    for name, expected in manifest["artifacts"].items():
        if digest(snapshot / name) != expected:
            raise ValueError("Visit artifact changed")
    if report["visit_manifest_sha256"] != digest(snapshot / "manifest.json"):
        raise ValueError("Visit manifest changed")
    work = output.parent / "insight-check"
    work.mkdir(parents=True, exist_ok=True)
    checks = {"rankings": 0, "curve_points": 0, "position_details": 0, "lenses": {}}
    with duckdb.connect(str(work / "check.duckdb")) as db:
        db.execute("set memory_limit='1GB'")
        db.execute("set max_temp_directory_size='2GB'")
        db.execute("set threads=1")
        db.execute("set preserve_insertion_order=false")
        db.execute("set temp_directory=?", [str(work / "temp")])
        db.read_parquet(str(snapshot / "visits-*.parquet")).create_view("raw_visits")
        for cohort_name, cohort in report["cohorts"].items():
            db.execute(
                """create or replace table earliest as select * from raw_visits
                where cohort=? qualify row_number() over(
                    partition by provider,game_id,position_id order by ply)=1""",
                [cohort_name],
            )
            for name, view in cohort["views"].items():
                if view.get("lens"):
                    moves = view["lens"]["moves"]
                    condition = " and ".join(
                        "list_contains(string_split(route,' '),?)" for _ in moves
                    )
                    db.execute(
                        """create or replace temporary table eligible_ids as
                        select distinct provider,game_id from raw_visits
                        where cohort=? and ply=? and split_part(route,' ',1)='d2d4' and """
                        + condition,
                        [cohort_name, report["plan"]["max_ply"], *moves],
                    )
                    db.execute("""create or replace temporary table chosen as select * from earliest
                        join eligible_ids using(provider,game_id)""")
                    checks["lenses"][cohort_name + "/" + name] = view["denominator_games"]
                elif name == "all":
                    db.execute("create or replace temporary table chosen as select * from earliest")
                else:
                    db.execute(
                        """create or replace temporary table chosen as select * from earliest
                        where opening_family=?""",
                        [name],
                    )
                denominator = db.execute(
                    "select count(distinct (provider,game_id)) from chosen"
                ).fetchone()[0]
                assert denominator == view["denominator_games"], (cohort_name, name)
                for kind, ranking in view["rankings"].items():
                    cutoff = min((view["positions"][p]["games"] for p in ranking["ids"]), default=2)
                    # First bound by frequency; route distinctness is needed only for
                    # boards that could displace a published rank. Keep the 2GB scratch cap.
                    db.execute(
                        """create or replace temporary table candidates as
                        select position_id,count(*) games from chosen group by position_id
                        having count(*)>=?""",
                        [cutoff],
                    )
                    condition = "games>=2" if kind == "recurring" else "routes>=2"
                    ids = [
                        row[0]
                        for row in db.execute(
                            """with route_counts as (
                        select position_id,count(distinct route) filter(
                            where not route_has_repeat) routes from chosen
                        where position_id in(select position_id from candidates)
                        group by position_id)
                        select position_id from candidates join route_counts using(position_id)
                        where """
                            + condition
                            + " order by games desc,position_id limit ?",
                            [report["plan"]["published_positions_per_view"]],
                        ).fetchall()
                    ]
                    assert ids == ranking["ids"], (cohort_name, name, kind)
                    # Independent union query: each N joins all matching ranks <= N.
                    rows = db.execute(
                        """with ranked as (
                        select unnest(?) position_id,unnest(?) rank)
                        select n,count(distinct (provider,game_id)) from chosen
                        join ranked using(position_id) cross join range(1,?) counts(n)
                        where rank<=n group by n order by n""",
                        [ids, list(range(1, len(ids) + 1)), len(ids) + 1],
                    ).fetchall()
                    assert [r[1] for r in rows] == [p["games"] for p in ranking["coverage_curve"]]
                    checks["rankings"] += 1
                    checks["curve_points"] += len(rows)
                for identifier, position in view["positions"].items():
                    games, loops, families, ecos, unknown, g3 = db.execute(
                        """select count(*),
                        count(*) filter(where route_has_repeat),
                        count(distinct opening_family) filter(where opening_family!='Unknown'),
                        count(distinct eco) filter(where eco is not null and eco!=''),
                        count(*) filter(where opening_family='Unknown'),
                        count(*) filter(where list_contains(string_split(route,' '),'g2g3'))
                        from chosen where position_id=?""",
                        [identifier],
                    ).fetchone()
                    routes = db.execute(
                        """select route,count(*) games from chosen where
                        position_id=? and not route_has_repeat group by route
                        order by games desc,route""",
                        [identifier],
                    ).fetchall()
                    assert games == position["games"] and loops == position["loop_prefix_games"]
                    assert len(routes) == position["acyclic_routes"]
                    assert [families, ecos, unknown, g3] == [
                        position[k]
                        for k in (
                            "distinct_recorded_families",
                            "distinct_recorded_ecos",
                            "unknown_family_games",
                            "white_g3_played_games",
                        )
                    ]
                    dominant = routes[0][1] if routes else 0
                    alternative = (
                        (games - loops - dominant) / (games - loops) if games > loops else None
                    )
                    actual = position["alternative_route_share"]
                    assert (
                        actual is None if alternative is None else abs(actual - alternative) < 1e-12
                    )
                    assert [(r["uci"], r["games"]) for r in position["routes"]] == routes[:3]
                    checks["position_details"] += 1
    result = {
        "kind": "raw_visit_opening_insight_reconciliation",
        "passed": True,
        "report_sha256": digest(report_path),
        "visit_snapshot_id": manifest["snapshot_id"],
        "checker_sha256": digest(Path(__file__)),
        "checks": checks,
        "live_requests": 0,
        "data_downloads": 0,
    }
    write_json(output, result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--report", type=Path, default=Path("reports/opening-positions.json"))
    parser.add_argument("--output", type=Path, default=Path("work/opening-insights-check.json"))
    args = parser.parse_args()
    print(verify(args.snapshot, args.report, args.output))
