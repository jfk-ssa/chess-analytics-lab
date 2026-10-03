"""Independent header-only reference: does NOT import pipeline, chess, SQL or DuckDB.

Checks the metric, not move legality. This comparison is appropriate only when the
pipeline reports zero quarantined/conflicting games for this complete archive.
"""

import argparse
import hashlib
import io
import json
from collections import Counter
from pathlib import Path

import zstandard


def reference(path):
    counts = Counter()
    ids = set()
    dates = []
    headers = {}

    def consume():
        if not headers:
            return
        counts["source_records"] += 1
        identity = headers["Site"]
        if identity in ids:
            raise ValueError("reference requires unique source IDs")
        ids.add(identity)
        if (
            not headers["Event"].startswith("Rated ")
            or headers.get("Variant", "Standard") != "Standard"
        ):
            counts["excluded"] += 1
            return
        if any(headers.get(color + "Title") == "BOT" for color in ("White", "Black")):
            counts["marked_bots"] += 1
            return
        result = headers["Result"]
        if result not in {"1-0", "0-1", "1/2-1/2"}:
            counts["unknown_results"] += 1
            return
        counts["denominator"] += 1
        counts["numerator"] += result == "1/2-1/2"
        counts[result] += 1
        if headers.get("UTCDate"):
            dates.append(headers["UTCDate"])

    with path.open("rb") as source, zstandard.ZstdDecompressor().stream_reader(source) as reader:
        for line in io.TextIOWrapper(reader, encoding="utf-8"):
            if line.startswith('[Event "'):
                consume()
                headers = {}
            if line.startswith("["):
                name, quoted_value = line.strip()[1:-1].split(" ", 1)
                headers[name] = quoted_value[1:-1]
        consume()
    with path.open("rb") as source:
        checksum = hashlib.file_digest(source, "sha256").hexdigest()
    return {
        "method": "independent source-header tally; no production parser or SQL",
        "source_sha256": checksum,
        "counts": dict(counts),
        "value": counts["numerator"] / counts["denominator"],
        "first_utc_date": min(dates),
        "last_utc_date": max(dates),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    print(json.dumps(reference(args.source), indent=2, sort_keys=True))
