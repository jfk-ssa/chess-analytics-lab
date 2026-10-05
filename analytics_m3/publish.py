"""Checked analytical move snapshot and descriptive metric evidence."""

import re
import shutil
import time
import uuid
from pathlib import Path

import duckdb

from analytics_m3.moves import SAMPLE_MODULUS, write_sampled_moves
from analytics_m3.source import extracted_path
from chess_analytics.common import digest, guard_disk, hash_json, now, read_json, write_json
from chess_analytics.warehouse.snapshots import current, report


def analytics_hash(project: Path) -> str:
    paths = sorted((project / "analytics_m3").glob("*.py"))
    paths += sorted((project / "contracts").glob("*.json"))
    return hash_json({str(path.relative_to(project)): digest(path) for path in paths})


def snapshot_identity(project: Path, source_id: str, extracted_hash: str) -> str:
    return hash_json(
        {
            "source_snapshot": source_id,
            "extracted_source": extracted_hash,
            "analytics_implementation": analytics_hash(project),
            "sample_modulus": SAMPLE_MODULUS,
        }
    )[:24]


def summarize(connection) -> dict:
    coverage = connection.execute("""
        select count(*) as moves,
               count(distinct game_id) as selected_games,
               count(*) filter (where clock_after_seconds is not null) as after_clock_moves,
               count(*) filter (where clock_before_seconds is not null) as before_clock_moves,
               count(*) filter (where eval_after_cp_white is not null) as cp_eval_moves,
               count(*) filter (where eval_after_mate_white is not null) as mate_eval_moves
        from fact_move
    """).fetchone()
    opening = connection.execute("""
        select count(*) filter (where result in ('1-0','0-1','1/2-1/2') and not marked_bot)
                   as eligible_games,
               count(*) filter (where result in ('1-0','0-1','1/2-1/2') and not marked_bot
                   and nullif(trim(split_part(source_opening, ':', 1)), '') is not null)
                   as known_opening_games,
               count(*) filter (where source_opening is null or trim(source_opening) = '')
                   as missing_source_opening
        from fact_game
    """).fetchone()
    families = connection.execute("""
        select trim(split_part(source_opening, ':', 1)) as family, count(*) as games
        from fact_game
        where result in ('1-0','0-1','1/2-1/2') and not marked_bot
          and nullif(trim(source_opening), '') is not null
        group by 1 order by games desc, family limit 12
    """).fetchall()
    clock_rows = connection.execute("""
        select m.clock_bucket,
               count(*) as eligible_moves,
               count(*) filter (where m.centipawn_deterioration is not null) as evaluable_moves,
               count(*) filter (where m.error_proxy) as proxy_errors,
               count(*) filter (where m.eval_before_mate_white is not null
                                  or m.eval_after_mate_white is not null) as mate_transition_moves
        from fact_move m join fact_game g using (provider, game_id)
        where g.result in ('1-0','0-1','1/2-1/2') and not g.marked_bot
          and g.increment_seconds = 0 and m.clock_before_seconds is not null
        group by 1 order by 1
    """).fetchall()
    return {
        "move_coverage": dict(
            zip(
                (
                    "moves",
                    "selected_games",
                    "after_clock_moves",
                    "before_clock_moves",
                    "cp_eval_moves",
                    "mate_eval_moves",
                ),
                coverage,
                strict=True,
            )
        ),
        "opening_coverage": dict(
            zip(
                ("eligible_games", "known_opening_games", "missing_source_opening"),
                opening,
                strict=True,
            )
        ),
        "top_opening_families": [
            {"family": family, "eligible_games": games} for family, games in families
        ],
        "clock_buckets": [
            {
                "bucket": bucket,
                "eligible_moves": eligible,
                "evaluable_moves": evaluable,
                "proxy_errors": errors,
                "mate_transition_moves": mates,
                "evaluation_coverage": evaluable / eligible if eligible else None,
                "error_proxy_rate": errors / evaluable if evaluable else None,
            }
            for bucket, eligible, evaluable, errors, mates in clock_rows
        ],
    }


def validate_analytical(directory: Path) -> dict:
    if not re.fullmatch(r"[0-9a-f]{24}", directory.name):
        raise ValueError("invalid analytical snapshot ID")
    manifest = read_json(directory / "manifest.json")
    if directory.name != manifest["analytical_id"] or manifest["status"] != "published":
        raise ValueError("invalid analytical snapshot manifest")
    for name, expected in manifest["artifacts"].items():
        if digest(directory / name) != expected:
            raise ValueError(f"analytical artifact checksum mismatch: {name}")
    with duckdb.connect(str(directory / "warehouse.duckdb"), read_only=True) as con:
        observed = summarize(con)
        invalid = con.execute("""
            select count(*) from (
                select m.provider, m.game_id, count(*) as rows, max(m.ply) as max_ply,
                       max(g.ply_count) as expected
                from fact_move m join fact_game g using (provider, game_id)
                group by m.provider, m.game_id
                having rows != expected or max_ply != expected)
        """).fetchone()[0]
        duplicate = con.execute("""
            select count(*) from (
                select provider, game_id, ply from fact_move
                group by all having count(*) != 1)
        """).fetchone()[0]
    selection = manifest["selection"]
    mismatch = (
        observed["move_coverage"]["moves"] != selection["move_rows"]
        or observed["move_coverage"]["selected_games"] + selection["selected_zero_ply_games"]
        != selection["selected_games"]
    )
    if invalid or duplicate or mismatch or observed != manifest["summary"]:
        raise ValueError("analytical move or metric validation failed")
    return manifest


def build_analytical(project: Path, root: Path) -> Path:
    """Caller owns writer_lock; source M1 snapshot and failed attempts remain intact."""
    project, root = project.resolve(), root.resolve()
    plan = read_json(project / "config/datasets.json")["analytical"]
    source_file = extracted_path(root, plan)
    receipt = read_json(source_file.with_suffix(".receipt.json"))
    if digest(source_file) != receipt["source_sha256"] or not receipt["partial_archive"]:
        raise ValueError("analytical extracted source failed receipt check")
    source_snapshot = current(root, "analytical")
    source_report = report(project, source_snapshot)
    source_manifest = read_json(source_snapshot / "manifest.json")
    if any(source_manifest["plan"].get(key) != value for key, value in plan.items()):
        raise ValueError("analytical source snapshot differs from configured plan")
    if receipt.get("plan_sha256") is not None and receipt["plan_sha256"] != hash_json(plan):
        raise ValueError("analytical extraction receipt differs from configured plan")
    if (
        "compressed_prefix_sha256" in plan
        and receipt.get("compressed_prefix_sha256") != plan["compressed_prefix_sha256"]
    ):
        raise ValueError("analytical extraction receipt differs from configured prefix")
    if source_report["source_sha256"] != receipt["source_sha256"]:
        raise ValueError("analytical extracted source differs from checked source snapshot")
    if not source_manifest["partial"]:
        raise ValueError("analytical source must be marked partial")
    identity = snapshot_identity(project, source_snapshot.name, receipt["source_sha256"])
    final = root / "analytical/published" / identity
    if final.exists():
        validate_analytical(final)
        write_json(root / "analytical-moves-current.json", {"analytical_id": identity})
        return final
    guard_disk(
        root,
        plan["max_generated_bytes"],
        3 * (source_snapshot / "warehouse.duckdb").stat().st_size + 100_000_000,
    )
    candidate = root / "analytical/staging" / uuid.uuid4().hex
    candidate.mkdir(parents=True)
    state = {
        "status": "running",
        "started_at": now(),
        "analytical_id": identity,
        "source_snapshot_id": source_snapshot.name,
    }
    write_json(candidate / "attempt.json", state)
    start = time.monotonic()
    try:
        move_counts = write_sampled_moves(
            source_file, source_snapshot, candidate / "moves.jsonl", plan, root
        )
        shutil.copy2(source_snapshot / "warehouse.duckdb", candidate / "warehouse.duckdb")
        with duckdb.connect(str(candidate / "warehouse.duckdb")) as con:
            con.execute("SET memory_limit = '256MB'")
            con.execute("SET max_temp_directory_size = '512MB'")
            con.execute("SET threads = 2")
            schema = read_json(project / "contracts/m3_tables.json")["fact_move"]
            con.read_json(
                str(candidate / "moves.jsonl"), columns=schema, format="newline_delimited"
            ).write_parquet(str(candidate / "fact_move.parquet"))
            con.read_parquet(str(candidate / "fact_move.parquet")).create("fact_move")
            summary = summarize(con)
        if summary["move_coverage"]["moves"] != move_counts["move_rows"]:
            raise ValueError("move Parquet row count differs from source extraction")
        if (
            summary["move_coverage"]["selected_games"] + move_counts["selected_zero_ply_games"]
            != move_counts["selected_games"]
        ):
            raise ValueError("selected game coverage does not reconcile")
        final.parent.mkdir(parents=True, exist_ok=True)
        staging_final = final.parent / f".candidate-{uuid.uuid4().hex}"
        staging_final.mkdir()
        for name in ("warehouse.duckdb", "fact_move.parquet"):
            shutil.copy2(candidate / name, staging_final / name)
        manifest = {
            "status": "published",
            "published_at": now(),
            "analytical_id": identity,
            "source_snapshot_id": source_snapshot.name,
            "source_sha256": source_report["source_sha256"],
            "compressed_prefix_sha256": receipt["compressed_prefix_sha256"],
            "source_period": plan["period"],
            "partial_archive": True,
            "observed_date_coverage": source_report["coverage"],
            "selection": move_counts,
            "summary": summary,
            "analytics_implementation_sha256": analytics_hash(project),
            "artifacts": {
                name: digest(staging_final / name)
                for name in ("warehouse.duckdb", "fact_move.parquet")
            },
        }
        write_json(staging_final / "manifest.json", manifest)
        # Validate after rename because the public identity is part of validation.
        guard_disk(root, plan["max_generated_bytes"])
        staging_final.rename(final)
        validate_analytical(final)
        write_json(root / "analytical-moves-current.json", {"analytical_id": identity})
        state["status"] = "published"
        return final
    except BaseException as error:
        state.update(status="failed", error=f"{type(error).__name__}: {error}")
        raise
    finally:
        state.update(finished_at=now(), elapsed_seconds=time.monotonic() - start)
        write_json(candidate / "attempt.json", state)
