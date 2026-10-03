import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from chess_analytics.common import digest, guard_disk, now, write_json


def bounded_copy(response, target, max_bytes, root, generated_limit):
    """Bound bytes even when Content-Length is absent or false."""
    written = 0
    with target.open("wb") as out:
        while True:
            chunk = response.read(min(1024 * 1024, max_bytes - written + 1))
            if not chunk:
                break
            if written + len(chunk) > max_bytes:
                raise ValueError("compressed source byte limit exceeded")
            guard_disk(root, generated_limit, len(chunk))
            out.write(chunk)
            written += len(chunk)
    return written


def acquire(root: Path, plan: dict):
    raw = root / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    target = raw / plan["url"].rsplit("/", 1)[-1]
    write_json(raw / "acquisition-plan.json", {"recorded_at": now(), **plan})
    if target.exists():
        if target.stat().st_size > plan["max_source_bytes"] or digest(target) != plan["sha256"]:
            raise ValueError("cached source failed bounds/checksum; preserved for investigation")
        return target
    job = raw / "acquisition" / uuid.uuid4().hex
    job.mkdir(parents=True)
    write_json(job / "plan.json", {"recorded_at": now(), **plan})
    errors = []
    previous_bytes = 0
    for attempt in range(1, plan["max_attempts"] + 1):
        part = job / f"attempt-{attempt}.part"
        try:
            remaining = plan["max_source_bytes"] - previous_bytes
            if remaining <= 0:
                raise ValueError("acquisition job byte limit exhausted across attempts")
            request = urllib.request.Request(plan["url"], headers={"User-Agent": "ChessLab/0.1"})
            with urllib.request.urlopen(request, timeout=plan["timeout_seconds"]) as response:
                if response.status != 200:
                    raise ValueError("complete acquisition requires HTTP 200")
                length = response.headers.get("Content-Length")
                if length and int(length) > remaining:
                    raise ValueError("declared compressed source exceeds limit")
                count = bounded_copy(response, part, remaining, root, plan["max_generated_bytes"])
                if length and count != int(length):
                    raise ValueError("incomplete HTTP body")
            if digest(part) != plan["sha256"]:
                raise ValueError("publisher SHA256 mismatch")
            part.replace(target)
            receipt = {
                "finished_at": now(),
                "bytes": count,
                "job_bytes_retained": previous_bytes + count,
                "attempts": attempt,
                "previous_errors": errors,
                "sha256": plan["sha256"],
                "publisher_checksum_verified": True,
            }
            write_json(job / "receipt.json", receipt)
            write_json(raw / "acquisition.json", receipt)
            return target
        except BaseException as e:
            previous_bytes += part.stat().st_size if part.exists() else 0
            errors.append(
                {"attempt": attempt, "error": str(e), "partial": str(part.relative_to(raw))}
            )
            write_json(job / "failures.json", errors)
            write_json(raw / "acquisition-failures.json", errors)
            # Policy and integrity failures are not repaired by repeated downloads.
            retryable = isinstance(e, (OSError, urllib.error.URLError))
            if not retryable or attempt == plan["max_attempts"]:
                raise
            time.sleep(min(attempt, 3))
    raise RuntimeError("unreachable")
