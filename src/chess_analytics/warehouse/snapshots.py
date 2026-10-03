import shutil
import uuid
from pathlib import Path

import duckdb

from chess_analytics.common import digest, guard_disk, now, read_json, write_json
from chess_analytics.ingest.pipeline import implementation_hash
from chess_analytics.metrics.draw_rate import draw_rate

CHECKS = {
    "game_keys": """SELECT count(*) FROM (
        SELECT provider, game_id FROM fact_game GROUP BY ALL HAVING count(*) != 1)""",
    "player_keys": """SELECT count(*) FROM (
        SELECT provider, game_id, color FROM fact_player_game GROUP BY ALL HAVING count(*) != 1)""",
    "required_game_fields": """SELECT count(*) FROM fact_game WHERE provider IS NULL
        OR provider != 'lichess' OR game_id IS NULL OR length(game_id) != 8
        OR result IS NULL OR result NOT IN ('1-0','0-1','1/2-1/2','*')
        OR rated IS DISTINCT FROM true OR variant IS DISTINCT FROM 'Standard'
        OR source_ordinal IS NULL OR source_ordinal < 1 OR marked_bot IS NULL
        OR record_fingerprint IS NULL OR ply_count IS NULL OR ply_count < 0""",
    "two_participants": """SELECT count(*) FROM (
        SELECT g.provider, g.game_id FROM fact_game g LEFT JOIN fact_player_game p
        USING(provider, game_id) GROUP BY ALL
        HAVING count(p.color) != 2 OR count(DISTINCT p.color) != 2)""",
    "no_orphans": """SELECT count(*) FROM fact_player_game p LEFT JOIN fact_game g
        USING(provider, game_id) WHERE g.game_id IS NULL""",
    "participant_scores": """SELECT count(*) FROM fact_player_game p JOIN fact_game g
        USING(provider, game_id) WHERE color IS NULL OR color NOT IN ('white','black')
        OR score IS DISTINCT FROM CASE WHEN result = '*' THEN NULL
        WHEN result = '1/2-1/2' THEN 0.5
        WHEN (result = '1-0' AND color = 'white') OR
             (result = '0-1' AND color = 'black') THEN 1.0 ELSE 0.0 END""",
    "score_conservation": """SELECT count(*) FROM (
        SELECT game_id, sum(score) AS total FROM fact_player_game
        GROUP BY game_id HAVING total IS NOT NULL AND total != 1)""",
    "wins_equal_losses": """SELECT abs(count(*) FILTER (WHERE score = 1) -
        count(*) FILTER (WHERE score = 0)) FROM fact_player_game""",
    "rating_symmetry": """SELECT count(*) FROM fact_player_game w JOIN fact_player_game b
        USING(provider,game_id) WHERE w.color='white' AND b.color='black'
        AND (w.rating IS DISTINCT FROM b.opponent_rating OR
             b.rating IS DISTINCT FROM w.opponent_rating)""",
}


def validate_connection(connection, manifest):
    failures = {name: connection.execute(sql).fetchone()[0] for name, sql in CHECKS.items()}
    actual = connection.execute("SELECT count(*) FROM fact_game").fetchone()[0]
    failures["accepted_count"] = abs(actual - manifest["counts"]["accepted"])
    counts = manifest["counts"]
    failures["reconciliation"] = abs(
        counts["seen"]
        - sum(counts[k] for k in ("accepted", "duplicate", "excluded", "quarantine", "conflict"))
    )
    if any(failures.values()):
        raise ValueError(f"quality checks failed: {failures}")
    return failures


def verify_artifacts(directory, manifest):
    for name, expected in manifest["artifacts"].items():
        if digest(directory / name) != expected:
            raise ValueError(f"artifact checksum mismatch: {name}")


def current(root, dataset):
    pointer = read_json(root / f"{dataset}-current.json")
    return root / "published" / pointer["snapshot_id"]


def validate_snapshot(snapshot):
    manifest = read_json(snapshot / "manifest.json")
    verify_artifacts(snapshot, manifest)
    with duckdb.connect(str(snapshot / "warehouse.duckdb"), read_only=True) as connection:
        return validate_connection(connection, manifest)


def build(project: Path, root: Path, dataset: str, *, fail_before_publish=False):
    """Materialize staged JSON through Parquet, then publish; caller owns writer_lock."""
    stage = root / "staging" / read_json(root / f"{dataset}-staged.json")["run_id"]
    manifest = read_json(stage / "manifest.json")
    if manifest["status"] != "staged":
        raise ValueError("candidate is not a successful staging run")
    if manifest["implementation_sha256"] != implementation_hash(project):
        raise ValueError("implementation changed after ingest; reingest before building")
    verify_artifacts(stage, manifest)
    final = root / "published" / manifest["snapshot_id"]
    attempt = {"started_at": now(), "status": "running", "snapshot_id": manifest["snapshot_id"]}
    attempt_path = stage / f"build-{uuid.uuid4().hex}.json"
    write_json(attempt_path, attempt)
    try:
        if final.exists():
            validate_snapshot(final)
        else:
            candidate = root / "staging" / f"build-{uuid.uuid4().hex}"
            candidate.mkdir()
            # Conservative workspace reservation includes DuckDB's capped spill space.
            reserve = sum(p.stat().st_size for p in stage.glob("*.jsonl")) * 8 + 550_000_000
            guard_disk(root, manifest["plan"]["max_generated_bytes"], reserve)
            schema = read_json(project / "contracts/tables.json")
            with duckdb.connect(str(candidate / "warehouse.duckdb")) as connection:
                connection.execute("SET memory_limit = '256MB'")
                connection.execute("SET max_temp_directory_size = '512MB'")
                connection.execute("SET threads = 2")
                for table, filename in (("fact_game", "games"), ("fact_player_game", "players")):
                    parquet = candidate / f"{table}.parquet"
                    connection.read_json(
                        str(stage / f"{filename}.jsonl"),
                        columns=schema[table],
                        format="newline_delimited",
                    ).write_parquet(str(parquet))
                    connection.read_parquet(str(parquet)).create(table)
                checks = validate_connection(connection, manifest)
                metric = draw_rate(connection, project)
            manifest = {
                **manifest,
                "status": "published",
                "published_at": now(),
                "quality_checks": checks,
                "metric": metric,
                "artifacts": {p.name: digest(p) for p in candidate.iterdir() if p.is_file()},
            }
            write_json(candidate / "manifest.json", manifest)
            guard_disk(root, manifest["plan"]["max_generated_bytes"])
            validate_snapshot(candidate)
            if fail_before_publish:
                raise RuntimeError("injected failure before publication")
            final.parent.mkdir(parents=True, exist_ok=True)
            candidate.rename(final)
        write_json(root / f"{dataset}-current.json", {"snapshot_id": final.name})
        attempt["status"] = "published"
    except BaseException as e:
        attempt.update(status="failed", error=f"{type(e).__name__}: {e}")
        raise
    finally:
        attempt["finished_at"] = now()
        write_json(attempt_path, attempt)
    return final


def report(project, snapshot):
    validate_snapshot(snapshot)
    manifest = read_json(snapshot / "manifest.json")
    if manifest["implementation_sha256"] != implementation_hash(project):
        raise ValueError("snapshot implementation differs; reingest and build before reporting")
    with duckdb.connect(str(snapshot / "warehouse.duckdb"), read_only=True) as connection:
        metric = draw_rate(connection, project)
    return {
        "snapshot_id": snapshot.name,
        "source_sha256": manifest["source_sha256"],
        "dataset": manifest["dataset"],
        "counts": manifest["counts"],
        "coverage": manifest["coverage"],
        "metric": metric,
        "evidence_kind": "deterministic data validation; no model experiment",
        "snapshot_disk_bytes": sum(p.stat().st_size for p in snapshot.iterdir() if p.is_file()),
        "free_disk_bytes": shutil.disk_usage(snapshot).free,
    }
