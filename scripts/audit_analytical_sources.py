"""Read-only receipt/source-manifest comparison for locally retained datasets."""

import argparse
import json
from pathlib import Path

from chess_analytics.common import hash_json, read_json, write_json


def audit(root: Path) -> dict:
    roots = [root, *sorted(root.glob("work/m7-*-project"))]
    records = []
    for project in roots:
        data = project / "data"
        pointer = data / "analytical-current.json"
        receipts = sorted((data / "analytical").glob("*.receipt.json"))
        if not pointer.exists():
            records.append({"project": str(project.relative_to(root)), "state": "no_pointer"})
            continue
        snapshot_id = read_json(pointer)["snapshot_id"]
        manifest_path = data / "published" / snapshot_id / "manifest.json"
        if not manifest_path.exists() or not receipts:
            records.append({"project": str(project.relative_to(root)), "state": "missing_pair"})
            continue
        manifest = read_json(manifest_path)
        plan = read_json(project / "config/datasets.json")["analytical"]
        matching_receipts = [
            read_json(p)
            for p in receipts
            if p.name == (f"complete-{plan['period']}-first-{plan['max_games']}.receipt.json")
        ]
        if not matching_receipts:
            records.append({"project": str(project.relative_to(root)), "state": "missing_receipt"})
            continue
        receipt = matching_receipts[0]
        records.append(
            {
                "project": str(project.relative_to(root)),
                "state": "match"
                if manifest["source_sha256"] == receipt["source_sha256"]
                else "mismatch",
                "plan_match": all(manifest["plan"].get(k) == v for k, v in plan.items()),
                "receipt_plan_match": receipt.get("plan_sha256") in (None, hash_json(plan)),
                "prefix_match": receipt.get("compressed_prefix_sha256")
                == plan.get("compressed_prefix_sha256"),
                "snapshot_id": snapshot_id,
            }
        )
    return {
        "kind": "read-only local retained analytical source/receipt audit",
        "checked_pairs": sum(item["state"] in ("match", "mismatch") for item in records),
        "mismatches": sum(item["state"] == "mismatch" for item in records),
        "records": records,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = audit(args.project.resolve())
    if args.out:
        write_json(args.out, result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
