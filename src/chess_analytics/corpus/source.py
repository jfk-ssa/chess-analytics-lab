"""Fixed byte-range acquisition and complete-PGN extraction."""

import os
import urllib.request
import uuid
from pathlib import Path

from chess_analytics.common import digest, guard_disk, hash_json, now, read_json, write_json
from chess_analytics.ingest.acquire import bounded_copy
from chess_analytics.ingest.pgn import records


def compressed_path(root: Path, plan: dict) -> Path:
    return (
        root
        / "analytical"
        / f"lichess-standard-rated-{plan['period']}-prefix-{plan['max_download_bytes']}.zst"
    )


def extracted_path(root: Path, plan: dict) -> Path:
    return root / "analytical" / f"complete-{plan['period']}-first-{plan['max_games']}.pgn"


def acquire_prefix(root: Path, plan: dict) -> Path:
    """Caller owns writer_lock. Never request beyond the configured byte range."""
    path = compressed_path(root, plan)
    path.parent.mkdir(parents=True, exist_ok=True)
    expected_bytes = plan["range_end_inclusive"] - plan["range_start"] + 1
    if expected_bytes != plan["max_download_bytes"] or plan["range_start"] != 0:
        raise ValueError("invalid fixed prefix bounds")
    if path.exists():
        if (
            path.stat().st_size != expected_bytes
            or digest(path) != plan["compressed_prefix_sha256"]
        ):
            raise ValueError("cached analytical prefix failed pinned size/hash")
        method = "cached_verified_prefix"
    else:
        attempt = path.parent / f"download-{uuid.uuid4().hex}.part"
        request = urllib.request.Request(
            plan["url"],
            headers={
                "Range": f"bytes=0-{plan['range_end_inclusive']}",
                "User-Agent": "ChessAnalyticsLab/0.1",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=plan["timeout_seconds"]) as response:
                expected_range = (
                    f"bytes 0-{plan['range_end_inclusive']}/{plan['archive_listed_bytes']}"
                )
                if (
                    response.status != 206
                    or response.headers.get("Content-Range") != expected_range
                ):
                    raise ValueError("server did not honor fixed archive byte range")
                length = response.headers.get("Content-Length")
                if length and int(length) != expected_bytes:
                    raise ValueError("unexpected range response length")
                count = bounded_copy(
                    response, attempt, expected_bytes, root, plan["max_generated_bytes"]
                )
                if count != expected_bytes:
                    raise ValueError("incomplete range response")
            if digest(attempt) != plan["compressed_prefix_sha256"]:
                raise ValueError("analytical prefix SHA256 differs from pinned value")
            attempt.replace(path)
            method = "http_206_range_verified"
        except BaseException as error:
            write_json(
                path.parent / f"{attempt.name}.failure.json",
                {
                    "at": now(),
                    "error": f"{type(error).__name__}: {error}",
                    "retained_bytes": attempt.stat().st_size if attempt.exists() else 0,
                },
            )
            raise
    write_json(
        path.parent / "acquisition.json",
        {
            "at": now(),
            "url": plan["url"],
            "period": plan["period"],
            "archive_listed_bytes": plan["archive_listed_bytes"],
            "archive_listed_games": plan["archive_listed_games"],
            "range_start": 0,
            "range_end_inclusive": plan["range_end_inclusive"],
            "retained_compressed_bytes": expected_bytes,
            "compressed_prefix_sha256": plan["compressed_prefix_sha256"],
            "method": method,
            "partial_archive": True,
            "publisher_full_checksum_verified": False,
        },
    )
    return path


def extract_complete_games(root: Path, plan: dict, compressed: Path) -> tuple[Path, dict]:
    """Retain complete records only; the final open record of a partial frame is dropped."""
    target = extracted_path(root, plan)
    receipt = target.with_suffix(".receipt.json")
    plan_hash = hash_json(plan)
    if target.exists() and receipt.exists():
        previous = read_json(receipt)
        if previous.get("plan_sha256") == plan_hash and previous.get("source_sha256") == digest(
            target
        ):
            return target, previous
        raise ValueError("cached extracted corpus failed plan/hash verification")
    attempt = target.with_suffix(f".{uuid.uuid4().hex}.part")
    count = 0
    end = 0
    pending = None
    stopped_at_cap = False
    try:
        scan_plan = {**plan, "max_games": plan["max_games"] + 1}
        write_batch = 32 * 1024 * 1024
        guard_disk(root, plan["max_generated_bytes"], write_batch)
        batch_remaining = write_batch
        with attempt.open("wb") as out:
            for record in records(compressed, scan_plan):
                if pending is not None:
                    encoded = pending[1].encode("utf-8")
                    if len(encoded) > batch_remaining:
                        guard_disk(root, plan["max_generated_bytes"], write_batch)
                        batch_remaining = write_batch
                    out.write(encoded)
                    batch_remaining -= len(encoded)
                    count += 1
                    end = pending[2]
                    if count == plan["max_games"]:
                        stopped_at_cap = True
                        break
                pending = record
            out.flush()
            os.fsync(out.fileno())
        if count == 0:
            raise ValueError("no complete games in analytical prefix")
        receipt_value = {
            "at": now(),
            "plan_sha256": plan_hash,
            "source_sha256": digest(attempt),
            "compressed_prefix_sha256": digest(compressed),
            "complete_games": count,
            "decompressed_bytes_through_last_complete_game": end,
            "extracted_bytes": attempt.stat().st_size,
            "stopped_at_game_cap": stopped_at_cap,
            "trailing_open_record_discarded": not stopped_at_cap,
            "partial_archive": True,
            "publisher_full_checksum_verified": False,
        }
        attempt.replace(target)
        write_json(receipt, receipt_value)
        return target, receipt_value
    except BaseException as error:
        write_json(
            attempt.with_suffix(".failure.json"),
            {
                "at": now(),
                "error": f"{type(error).__name__}: {error}",
                "complete_games_written": count,
                "retained_bytes": attempt.stat().st_size if attempt.exists() else 0,
            },
        )
        raise
