"""Restore Elite LichessURL identity, then reuse the existing legal ingestion pipeline."""

import json
import re
from pathlib import Path

from chess_analytics.common import digest, now, read_json, write_json, writer_lock
from chess_analytics.ingest.pgn import records
from chess_analytics.ingest.pipeline import ingest
from chess_analytics.warehouse.snapshots import build, validate_snapshot

PROJECT = Path(__file__).resolve().parents[1]
ADAPTER_VERSION = "elite-lichessurl-to-site-v1"
IDENTITY = re.compile(r'^\[LichessURL "(https://lichess\.org/[A-Za-z0-9]{8})"\]$', re.M)


def main():
    plan = read_json(PROJECT / "config/opening-corpus.json")["elite"]
    source_root = PROJECT / "data/opening-sources/elite"
    receipt = read_json(source_root / "lichess_elite_2025-11.receipt.json")
    original = source_root / receipt["pgn_file"]
    if digest(original) != receipt["pgn_sha256"]:
        raise ValueError("Elite source differs from its retained receipt")
    root = PROJECT / "data/elite"
    with writer_lock(root):
        canonical = root / "elite-2025-11-compatible.pgn"
        adapted_receipt = canonical.with_suffix(".receipt.json")
        if canonical.exists():
            adapted = read_json(adapted_receipt)
            if adapted["source_sha256"] != digest(canonical):
                raise ValueError("adapted Elite source differs from its receipt")
            if adapted["original_sha256"] != receipt["pgn_sha256"]:
                raise ValueError("adapted Elite source belongs to a different input")
        else:
            target = canonical.with_suffix(".pgn.part")
            count = 0
            with target.open("w") as output:
                for ordinal, raw, _ in records(original, plan):
                    identity = IDENTITY.search(raw)
                    if not identity:
                        raise ValueError(f"Elite record {ordinal} has no unambiguous LichessURL")
                    site = re.search(r'^\[Site "([^"\n]*)"\]$', raw, re.M)
                    if site:
                        raw = raw[: site.start()] + raw[site.end() :]
                    first, remainder = raw.split("\n", 1)
                    output.write(first + f'\n[Site "{identity[1]}"]\n' + remainder)
                    count += 1
            target.replace(canonical)
            adapted = {
                "at": now(),
                "adapter_version": ADAPTER_VERSION,
                "original_sha256": receipt["pgn_sha256"],
                "source_sha256": digest(canonical),
                "games": count,
                "change": "restore original game URL to Site; preserve LichessURL and moves",
            }
            write_json(adapted_receipt, adapted)
        ingest_plan = {
            **plan,
            "complete_archive": True,
            "source_kind": "complete_curated_elite_month",
            "max_source_bytes": plan["max_decompressed_bytes"],
            "expected_records": adapted["games"],
            "original_acquisition": receipt,
            "adapter_version": ADAPTER_VERSION,
            "period": plan["period"],
        }
        staged = ingest(PROJECT, root, "elite", canonical, ingest_plan)
        print(json.dumps({"staged": str(staged)}, default=str), flush=True)
        snapshot = build(PROJECT, root, "elite")
        validate_snapshot(snapshot)
        manifest = read_json(snapshot / "manifest.json")
        write_json(
            PROJECT / "reports/elite-2025-11-ingestion.json",
            {
                "kind": "complete_curated_elite_month_legal_ingestion",
                "snapshot_id": snapshot.name,
                "counts": manifest["counts"],
                "coverage": manifest["coverage"],
                "reasons": manifest["reasons"],
                "acquisition": receipt,
                "adapter": adapted,
                "quality_checks": manifest["quality_checks"],
                "publisher_selection": plan["publisher_selection"],
            },
        )
        print(json.dumps({"snapshot": snapshot.name, "counts": manifest["counts"]}), flush=True)


if __name__ == "__main__":
    main()
