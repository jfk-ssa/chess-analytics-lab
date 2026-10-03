import json
import platform
import subprocess
import time
import uuid
from collections import Counter
from pathlib import Path

import chess
import duckdb
import zstandard

from chess_analytics import __version__
from chess_analytics.common import digest, guard_disk, hash_json, now, write_json
from chess_analytics.ingest.pgn import normalize, records


def implementation_hash(project):
    files = sorted((project / "src").rglob("*.py")) + sorted((project / "src").rglob("*.sql"))
    files += sorted((project / "contracts").glob("*.json"))
    return hash_json({str(p.relative_to(project)): digest(p) for p in files})


def ingest(project: Path, root: Path, dataset: str, source: Path, plan: dict):
    """Normalize one full input into a new staging run. Caller owns writer_lock."""
    start = time.monotonic()
    stage = root / "staging" / uuid.uuid4().hex
    stage.mkdir(parents=True)
    manifest = {
        "run_id": stage.name,
        "dataset": dataset,
        "started_at": now(),
        "status": "running",
        "plan": plan,
        "partial": False,
        "source_file": source.name,
        "source_bytes": source.stat().st_size,
        "software": {
            "chesslab": __version__,
            "python": platform.python_version(),
            "chess": chess.__version__,
            "duckdb": duckdb.__version__,
            "zstandard": zstandard.__version__,
        },
        "implementation_sha256": implementation_hash(project),
        "lock_sha256": digest(project / "uv.lock"),
    }
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=project, capture_output=True, text=True
    )
    manifest["git_commit"] = commit.stdout.strip() if commit.returncode == 0 else None
    manifest["working_tree_dirty"] = bool(
        subprocess.run(
            ["git", "status", "--porcelain"], cwd=project, capture_output=True, text=True
        ).stdout
    )
    write_json(stage / "manifest.json", manifest)
    counts = Counter(seen=0, accepted=0, duplicate=0, excluded=0, quarantine=0, conflict=0)
    reasons = Counter()
    fingerprints = {}
    dates = []
    missing = Counter()
    scanned = 0
    try:
        if source.stat().st_size > plan["max_source_bytes"]:
            raise ValueError("source byte limit exceeded")
        source_hash = digest(source)
        manifest["source_sha256"] = source_hash
        if plan.get("sha256") and source_hash != plan["sha256"]:
            raise ValueError("source checksum mismatch")
        manifest["publisher_checksum_verified"] = bool(plan.get("sha256"))
        manifest["snapshot_id"] = hash_json(
            {
                "source": source_hash,
                "plan": plan,
                "implementation": manifest["implementation_sha256"],
                "lock": manifest["lock_sha256"],
            }
        )[:24]
        with (
            (stage / "games.jsonl").open("w") as games,
            (stage / "players.jsonl").open("w") as players,
            (stage / "quarantine.jsonl").open("w") as quarantine,
        ):
            for ordinal, raw, record_end in records(source, plan):
                scanned = record_end
                counts["seen"] += 1
                status, reason, normalized = normalize(raw, ordinal)
                if normalized:
                    row, participants = normalized
                    key = (row["provider"], row["game_id"])
                    previous = fingerprints.get(key)
                    if previous:
                        status = (
                            "duplicate" if previous == row["record_fingerprint"] else "conflict"
                        )
                        reason = "identical_game" if status == "duplicate" else "conflicting_game"
                    else:
                        fingerprints[key] = row["record_fingerprint"]
                counts[status] += 1
                # Check before every record write, including quarantine. Use UTF-8 byte sizes.
                if status == "accepted":
                    game_line = json.dumps(row) + "\n"
                    player_lines = "".join(json.dumps(p) + "\n" for p in participants)
                    guard_disk(
                        root,
                        plan["max_generated_bytes"],
                        len(game_line.encode()) + len(player_lines.encode()) + 65536,
                    )
                    games.write(game_line)
                    players.write(player_lines)
                    if row["utc_date"]:
                        dates.append(row["utc_date"])
                    for field in ("utc_date", "played_at", "source_opening"):
                        missing[field] += row[field] is None
                    missing["participant_rating"] += sum(p["rating"] is None for p in participants)
                elif status != "duplicate":
                    reasons[reason] += 1
                    entry = (
                        json.dumps(
                            {
                                "ordinal": ordinal,
                                "disposition": status,
                                "reason": reason,
                                "raw_pgn": raw,
                            }
                        )
                        + "\n"
                    )
                    guard_disk(root, plan["max_generated_bytes"], len(entry.encode()) + 65536)
                    quarantine.write(entry)
        if counts["conflict"]:
            raise ValueError("conflicting duplicate; entire candidate withheld pending resolution")
        if plan.get("expected_records") is not None and counts["seen"] != plan["expected_records"]:
            raise ValueError("record count differs from complete archive listing")
        if not counts["accepted"]:
            raise ValueError("no accepted games; candidate not publishable")
        manifest["artifacts"] = {p.name: digest(p) for p in stage.glob("*.jsonl")}
        manifest["status"] = "staged"
    except BaseException as e:
        manifest["status"] = "failed"
        manifest["error"] = f"{type(e).__name__}: {e}"
        raise
    finally:
        manifest.update(
            {
                "finished_at": now(),
                "elapsed_seconds": time.monotonic() - start,
                "counts": dict(counts),
                "reasons": dict(reasons),
                "decompressed_bytes_scanned": scanned,
                "coverage": {
                    "first_utc_date": min(dates) if dates else None,
                    "last_utc_date": max(dates) if dates else None,
                    "missing": dict(missing),
                },
            }
        )
        write_json(stage / "manifest.json", manifest)
    write_json(root / f"{dataset}-staged.json", {"run_id": stage.name})
    return stage
