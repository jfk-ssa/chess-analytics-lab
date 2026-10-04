"""Pin one bounded June 2026 source prefix; never fetch the full archive."""

import json
import urllib.request
import uuid
from pathlib import Path

from chess_analytics.common import digest, now, write_json
from chess_analytics.ingest.acquire import bounded_copy

PROJECT = Path(__file__).resolve().parents[1]
URL = "https://database.lichess.org/standard/lichess_db_standard_rated_2026-06.pgn.zst"
ARCHIVE_BYTES = 28_241_946_492
ARCHIVE_GAMES = 86_483_328
PREFIX_BYTES = 40_000_000


def pin(project: Path = PROJECT) -> dict:
    target = project / "work/m7-june-prefix-40000000.zst"
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        attempt = target.with_name(f"{target.name}.{uuid.uuid4().hex}.part")
        request = urllib.request.Request(
            URL,
            headers={"Range": f"bytes=0-{PREFIX_BYTES - 1}", "User-Agent": "ChessAnalyticsLab/0.1"},
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                expected_range = f"bytes 0-{PREFIX_BYTES - 1}/{ARCHIVE_BYTES}"
                if (
                    response.status != 206
                    or response.headers.get("Content-Range") != expected_range
                ):
                    raise ValueError("publisher did not honor exact fixed range")
                if response.headers.get("Content-Length") != str(PREFIX_BYTES):
                    raise ValueError("unexpected Content-Length for fixed range")
                copied = bounded_copy(
                    response, attempt, PREFIX_BYTES, project / "work", 5_000_000_000
                )
                if copied != PREFIX_BYTES:
                    raise ValueError("short source prefix")
            attempt.replace(target)
        except BaseException as exc:
            write_json(
                attempt.with_suffix(".failure.json"),
                {
                    "kind": "retained failed bounded June source acquisition",
                    "error": f"{type(exc).__name__}: {exc}",
                    "retained_bytes": attempt.stat().st_size if attempt.exists() else 0,
                    "at": now(),
                },
            )
            raise
    if target.stat().st_size != PREFIX_BYTES:
        raise ValueError("cached June prefix has wrong size")
    prefix_sha = digest(target)
    plan = {
        "url": URL,
        "period": "2026-06",
        "source_kind": "bounded_standard_rated_prefix",
        "complete_archive": False,
        "archive_listed_games": ARCHIVE_GAMES,
        "archive_listed_bytes": ARCHIVE_BYTES,
        "listing_verified_on": "2026-10-04",
        "range_start": 0,
        "range_end_inclusive": PREFIX_BYTES - 1,
        "compressed_prefix_sha256": prefix_sha,
        "max_download_bytes": PREFIX_BYTES,
        "max_source_bytes": 500_000_000,
        "max_decompressed_bytes": 500_000_000,
        "max_generated_bytes": 5_000_000_000,
        "max_games": 100_000,
        "max_record_bytes": 1_000_000,
        "timeout_seconds": 30,
    }
    write_json(project / "config/m7_june_source.json", plan)
    evidence = {
        "kind": "M7 exact bounded monthly-prefix acquisition; no full-archive checksum claim",
        "source_url": URL,
        "listing_url": "https://database.lichess.org/",
        "range": [0, PREFIX_BYTES - 1],
        "retained_compressed_bytes": PREFIX_BYTES,
        "compressed_prefix_sha256": prefix_sha,
        "archive_listed_bytes": ARCHIVE_BYTES,
        "archive_listed_games": ARCHIVE_GAMES,
        "partial_archive": True,
        "publisher_full_checksum_verified": False,
        "local_prefix": str(target.relative_to(project)),
    }
    write_json(project / "reports/M7-June-acquisition.json", evidence)
    return evidence


if __name__ == "__main__":
    result = pin()
    print(
        json.dumps(
            {
                "retained_bytes": result["retained_compressed_bytes"],
                "sha256": result["compressed_prefix_sha256"],
            }
        )
    )
