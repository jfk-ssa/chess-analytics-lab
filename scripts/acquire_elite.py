"""Manually acquire one bounded Elite ZIP; no download occurs on import."""

import json
import shutil
import urllib.request
import zipfile
from pathlib import Path

from chess_analytics.common import digest, now, read_json, write_json, writer_lock
from chess_analytics.ingest.acquire import bounded_copy

PROJECT = Path(__file__).resolve().parents[1]


def main():
    plan = read_json(PROJECT / "config/opening-corpus.json")["elite"]
    root = PROJECT / "data/opening-sources/elite"
    with writer_lock(root):
        target = root / plan["url"].rsplit("/", 1)[-1]
        receipt = target.with_suffix(".receipt.json")
        write_json(root / "acquisition-plan.json", {"recorded_at": now(), **plan})
        if target.exists():
            saved = read_json(receipt)
            if digest(target) != saved["download_sha256"]:
                raise ValueError("cached Elite ZIP differs from its acquisition receipt")
        else:
            part = target.with_suffix(".zip.part")
            request = urllib.request.Request(
                plan["url"], headers={"User-Agent": "ChessAnalyticsLab/0.1"}
            )
            try:
                with urllib.request.urlopen(request, timeout=plan["timeout_seconds"]) as response:
                    if response.status != 200:
                        raise ValueError("Elite download did not return HTTP 200")
                    size = response.headers.get("Content-Length")
                    if size and int(size) > plan["max_download_bytes"]:
                        raise ValueError("Elite download exceeds configured bound")
                    count = bounded_copy(
                        response,
                        part,
                        plan["max_download_bytes"],
                        root,
                        plan["max_generated_bytes"],
                    )
                    saved = {
                        "retrieved_at": now(),
                        "url": plan["url"],
                        "final_url": response.url,
                        "download_bytes": count,
                        "download_sha256": digest(part),
                        "publisher_checksum_verified": False,
                        "hash_kind": "locally computed receipt, not publisher checksum",
                    }
                part.replace(target)
                write_json(receipt, saved)
            except BaseException as error:
                write_json(
                    root / "acquisition-failure.json",
                    {
                        "at": now(),
                        "error": f"{type(error).__name__}: {error}",
                        "retained_bytes": part.stat().st_size if part.exists() else 0,
                    },
                )
                raise
        with zipfile.ZipFile(target) as archive:
            members = [m for m in archive.infolist() if m.filename.lower().endswith(".pgn")]
            if len(members) != 1:
                raise ValueError("expected exactly one PGN member in Elite ZIP")
            member = members[0]
            if member.file_size > plan["max_decompressed_bytes"]:
                raise ValueError("Elite PGN exceeds decompressed bound")
            extracted = root / Path(member.filename).name
            if extracted.exists():
                if saved.get("pgn_sha256") != digest(extracted):
                    raise ValueError("cached Elite PGN differs from its extraction receipt")
            else:
                part = extracted.with_suffix(".pgn.part")
                with archive.open(member) as source:
                    bounded_copy(
                        source,
                        part,
                        plan["max_decompressed_bytes"],
                        root,
                        plan["max_generated_bytes"],
                    )
                part.replace(extracted)
            if extracted.stat().st_size != member.file_size:
                raise ValueError("Elite PGN size differs from the ZIP member")
            saved.update(
                {
                    "pgn_file": extracted.name,
                    "pgn_bytes": extracted.stat().st_size,
                    "pgn_sha256": digest(extracted),
                    "zip_member": member.filename,
                }
            )
            write_json(receipt, saved)
        if shutil.disk_usage(root).free < 5_000_000_000:
            raise ValueError("less than 5 GB free before later ingestion")
        print(json.dumps(saved, indent=2))


if __name__ == "__main__":
    main()
