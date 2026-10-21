"""Build the hosted dashboard cube from the published reports.

The opening-position rankings are not on the branch tip. Restore them with
scripts/materialize_opening_positions.py, or pass ``--positions``. This script
does not download data and does not open the analytical warehouse.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from chess_analytics.dashboard_cube import build_rows, write_cube  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build data/public/dashboard_cube.parquet")
    parser.add_argument(
        "--positions",
        type=Path,
        default=ROOT / "reports" / "opening-positions.json",
        help="Restored opening-positions report",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "data" / "public" / "dashboard_cube.parquet",
    )
    args = parser.parse_args(argv)
    if not args.positions.is_file():
        print(f"Opening rankings are not at {args.positions}", file=sys.stderr)
        return 2
    rows = build_rows(
        _read(ROOT / "reports" / "opening-corpus.json"),
        _read(args.positions),
        _read(ROOT / "reports" / "M3-independent-reference.json"),
        _read(ROOT / "reports" / "M4-figures.json"),
        _read(ROOT / "reports" / "M3-analytical-manifest.json"),
    )
    size = write_cube(rows, args.output)
    print(f"Wrote {args.output} ({size} bytes, {len(rows)} rows)")
    return 0


def _read(path: Path) -> dict:
    return json.loads(path.read_text())


if __name__ == "__main__":
    raise SystemExit(main())
