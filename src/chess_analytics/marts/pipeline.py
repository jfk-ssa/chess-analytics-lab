"""dbt candidate publication, rollback, and operational evidence."""

import json
import os
import re
import shutil
import subprocess
import time
import uuid
from pathlib import Path

import duckdb

from chess_analytics.common import (
    digest,
    disk_bytes,
    guard_disk,
    hash_json,
    now,
    read_json,
    write_json,
)
from chess_analytics.warehouse.snapshots import current, report


def checked_id(value: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{24}", value):
        raise ValueError("expected a 24-character local snapshot or mart ID")
    return value


def model_hash(project: Path) -> str:
    paths = sorted((project / "dbt").rglob("*.sql")) + sorted((project / "dbt").rglob("*.yml"))
    return hash_json({str(path.relative_to(project)): digest(path) for path in paths})


def mart_id(project: Path, source_id: str) -> str:
    return hash_json(
        {
            "snapshot_id": source_id,
            "model_sha256": model_hash(project),
            "lock_sha256": digest(project / "uv.lock"),
        }
    )[:24]


def validate_mart(directory: Path, *, require_name: bool = True) -> dict:
    if require_name:
        checked_id(directory.name)
    manifest = read_json(directory / "manifest.json")
    if manifest["status"] != "published" or (
        require_name and directory.name != manifest["mart_id"]
    ):
        raise ValueError("invalid mart manifest")
    if digest(directory / "warehouse.duckdb") != manifest["warehouse_sha256"]:
        raise ValueError("mart warehouse checksum mismatch")
    with duckdb.connect(str(directory / "warehouse.duckdb"), read_only=True) as con:
        row = con.execute(
            """select sum(accepted_games), sum(eligible_games), sum(drawn_games),
                      sum(unknown_results), sum(marked_bots) from mart_game_outcomes"""
        ).fetchone()
        player_row = con.execute("select count(*) from mart_player_outcomes").fetchone()
    if row is None or player_row is None:
        raise RuntimeError("mart query returned no row")
    players = player_row[0]
    accepted, eligible, drawn, unknown, bots = row
    observed = {
        "accepted": accepted,
        "eligible": eligible,
        "drawn": drawn,
        "unknown": unknown,
        "bots": bots,
        "player_rows": players,
    }
    if observed != manifest["observed"]:
        raise ValueError("mart counts differ from manifest")
    return manifest


def build_mart(
    project: Path,
    root: Path,
    dataset: str,
    dbt_executable: Path,
    *,
    source_id: str | None = None,
    fail_before_publish: bool = False,
) -> Path:
    """Caller owns writer_lock. Every failed candidate remains under marts/attempts."""
    project, root = project.resolve(), root.resolve()
    selected = checked_id(source_id or current(root, dataset).name)
    source = root / "published" / selected
    source_report = report(project, source)
    if source_report["dataset"] != dataset:
        raise ValueError("snapshot belongs to another dataset")
    identity = mart_id(project, selected)
    final = root / "marts/published" / identity
    if final.exists():
        validate_mart(final)
        if selected == current(root, dataset).name:
            write_json(root / f"{dataset}-mart-current.json", {"mart_id": identity})
        return final
    source_manifest = read_json(source / "manifest.json")
    guard_disk(
        root,
        source_manifest["plan"]["max_generated_bytes"],
        3 * (source / "warehouse.duckdb").stat().st_size + 100_000_000,
    )
    attempt = root / "marts/attempts" / uuid.uuid4().hex
    attempt.mkdir(parents=True)
    started = time.monotonic()
    state: dict[str, object] = {
        "status": "running",
        "started_at": now(),
        "dataset": dataset,
        "snapshot_id": selected,
        "mart_id": identity,
    }
    write_json(attempt / "attempt.json", state)
    try:
        # dbt only writes a copy. The M1 source remains immutable and queryable.
        shutil.copy2(source / "warehouse.duckdb", attempt / "warehouse.duckdb")
        env = os.environ.copy()
        env.update(
            CHESSLAB_DBT_PATH=str(attempt / "warehouse.duckdb"),
            DBT_SEND_ANONYMOUS_USAGE_STATS="false",
            DBT_PROFILES_DIR=str(project / "dbt"),
        )
        completed = subprocess.run(
            [
                str(dbt_executable),
                "build",
                "--project-dir",
                str(project / "dbt"),
                "--profiles-dir",
                str(project / "dbt"),
                "--target-path",
                str(attempt / "target"),
                "--log-path",
                str(attempt / "log"),
                "--no-use-colors",
            ],
            cwd=project,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        (attempt / "dbt-stdout.log").write_text(completed.stdout)
        (attempt / "dbt-stderr.log").write_text(completed.stderr)
        if completed.returncode:
            raise ValueError(f"dbt build failed ({completed.returncode}); see retained logs")
        with duckdb.connect(str(attempt / "warehouse.duckdb"), read_only=True) as con:
            values = con.execute(
                """select sum(accepted_games), sum(eligible_games), sum(drawn_games),
                          sum(unknown_results), sum(marked_bots) from mart_game_outcomes"""
            ).fetchone()
            player_row = con.execute("select count(*) from mart_player_outcomes").fetchone()
        if values is None or player_row is None:
            raise RuntimeError("mart query returned no row")
        players = player_row[0]
        accepted, eligible, drawn, unknown, bots = values
        observed = {
            "accepted": accepted,
            "eligible": eligible,
            "drawn": drawn,
            "unknown": unknown,
            "bots": bots,
            "player_rows": players,
        }
        expected = {
            "accepted": source_report["counts"]["accepted"],
            "eligible": source_report["metric"]["denominator"],
            "drawn": source_report["metric"]["numerator"],
            "unknown": source_report["metric"]["unknown_results"],
            "bots": source_report["metric"]["marked_bots"],
            "player_rows": source_report["counts"]["accepted"] * 2,
        }
        if observed != expected:
            raise ValueError(f"mart reconciliation failed: {observed} != {expected}")
        if fail_before_publish:
            raise RuntimeError("injected failure before mart publication")
        # Keep only reviewable dbt result and lineage files in the immutable mart.
        result_path = attempt / "target/run_results.json"
        dbt_results = json.loads(result_path.read_text())
        results = {
            "passed": sum(r["status"] == "pass" for r in dbt_results["results"]),
            "created": sum(r["status"] == "success" for r in dbt_results["results"]),
        }
        if results["passed"] + results["created"] != len(dbt_results["results"]):
            raise ValueError(f"unexpected dbt result counts: {results}")
        published = root / "marts/published"
        published.mkdir(parents=True, exist_ok=True)
        candidate = published / f".candidate-{uuid.uuid4().hex}"
        candidate.mkdir()
        shutil.copy2(attempt / "warehouse.duckdb", candidate / "warehouse.duckdb")
        for name in ("manifest.json", "run_results.json"):
            shutil.copy2(attempt / "target" / name, candidate / f"dbt-{name}")
        manifest = {
            "status": "published",
            "dataset": dataset,
            "snapshot_id": selected,
            "mart_id": identity,
            "source_sha256": source_report["source_sha256"],
            "model_sha256": model_hash(project),
            "lock_sha256": digest(project / "uv.lock"),
            "warehouse_sha256": digest(candidate / "warehouse.duckdb"),
            "observed": observed,
            "dbt_results": results,
            "published_at": now(),
        }
        write_json(candidate / "manifest.json", manifest)
        validate_mart(candidate, require_name=False)
        guard_disk(root, source_manifest["plan"]["max_generated_bytes"])
        candidate.rename(final)
        validate_mart(final)
        if selected == current(root, dataset).name:
            write_json(root / f"{dataset}-mart-current.json", {"mart_id": identity})
        state["status"] = "published"
        return final
    except BaseException as error:
        state.update(status="failed", error=f"{type(error).__name__}: {error}")
        raise
    finally:
        state.update(finished_at=now(), elapsed_seconds=time.monotonic() - started)
        write_json(attempt / "attempt.json", state)


def rollback_mart(root: Path, dataset: str, identity: str) -> Path:
    """Caller owns writer_lock. Select only an existing validated mart for dataset."""
    target = root / "marts/published" / checked_id(identity)
    manifest = validate_mart(target)
    if manifest["dataset"] != dataset:
        raise ValueError("mart belongs to another dataset")
    write_json(root / f"{dataset}-mart-current.json", {"mart_id": identity})
    return target


def operational_report(root: Path, dataset: str) -> dict:
    """Observed local attempt ledger; absent measures stay null."""
    root = root.resolve()
    ingestion = []
    for path in sorted((root / "staging").glob("*/manifest.json")):
        item = read_json(path)
        if item.get("dataset") == dataset:
            elapsed = item.get("elapsed_seconds")
            scanned = item.get("decompressed_bytes_scanned")
            ingestion.append(
                {
                    "run_id": item.get("run_id"),
                    "status": item.get("status"),
                    "counts": item.get("counts"),
                    "reasons": item.get("reasons"),
                    "coverage": item.get("coverage"),
                    "elapsed_seconds": elapsed,
                    "source_bytes": item.get("source_bytes"),
                    "decompressed_bytes_scanned": scanned,
                    "scan_bytes_per_second": scanned / elapsed if scanned and elapsed else None,
                    "source_sha256": item.get("source_sha256"),
                    "expected_source_sha256": item.get("plan", {}).get("sha256"),
                    "error": item.get("error"),
                }
            )
    builds = []
    dataset_snapshots = set()
    for path in (root / "staging").glob("*/manifest.json"):
        item = read_json(path)
        if item.get("dataset") == dataset and item.get("snapshot_id"):
            dataset_snapshots.add(item["snapshot_id"])
    for path in sorted((root / "staging").glob("*/build-*.json")):
        item = read_json(path)
        if item.get("snapshot_id") in dataset_snapshots:
            builds.append(
                {
                    "snapshot_id": item.get("snapshot_id"),
                    "status": item.get("status"),
                    "error": item.get("error"),
                }
            )
    marts = []
    for path in sorted((root / "marts/attempts").glob("*/attempt.json")):
        item = read_json(path)
        if item.get("dataset") == dataset:
            marts.append(
                {
                    "mart_id": item.get("mart_id"),
                    "snapshot_id": item.get("snapshot_id"),
                    "status": item.get("status"),
                    "elapsed_seconds": item.get("elapsed_seconds"),
                    "error": item.get("error"),
                }
            )
    pointer = root / f"{dataset}-mart-current.json"
    source_pointer = root / f"{dataset}-current.json"
    versions = list(
        dict.fromkeys(item["source_sha256"] for item in ingestion if item.get("source_sha256"))
    )
    drift = []
    for item in ingestion:
        expected = item.get("expected_source_sha256")
        if expected and item.get("source_sha256") and item["source_sha256"] != expected:
            drift.append(
                {
                    "run_id": item["run_id"],
                    "severity": "failure",
                    "reason": "publisher checksum mismatch",
                }
            )
    if len(versions) > 1:
        drift.append(
            {
                "severity": "warning",
                "reason": "multiple source versions observed",
                "source_sha256_values": versions,
            }
        )
    return {
        "kind": "observed local pipeline operations",
        "dataset": dataset,
        "generated_at": now(),
        "ingestion_attempts": ingestion,
        "snapshot_build_attempts": builds,
        "mart_attempts": marts,
        "current_mart": read_json(pointer)["mart_id"] if pointer.exists() else None,
        "current_snapshot": read_json(source_pointer)["snapshot_id"]
        if source_pointer.exists()
        else None,
        "source_drift": drift,
        "generated_disk_bytes": disk_bytes(root),
        "peak_memory_bytes": None,
        "peak_memory_note": "not measured; DuckDB memory limit is configured, not process RSS",
    }
