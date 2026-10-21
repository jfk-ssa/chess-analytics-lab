"""Append warehouse aggregates to the hosted dashboard cube.

The script reads a local ``warehouse.duckdb``. It does not download. Cells
under 10 games are dropped, and player or game identifiers are not written.
``opening_game`` is the training selection. ``retained_game`` is not read.
A ``fact_game`` warehouse still builds the analytical grains, including
clock cells when ``fact_move`` has them. This checkout has no warehouse,
so the committed cube stays the published aggregate until the command
below succeeds. The file stays under 10 MB or the write fails.

From the repository root on the machine that has the openings warehouse:

    uv run --locked --no-editable --extra dashboard \
      python scripts/build_warehouse_cube.py \
      --warehouse data/openings/published/00e7a73fbf67c401e23b4b4b/warehouse.duckdb

Search order when ``--warehouse`` is omitted: ``CHESSLAB_WAREHOUSE``,
``data/warehouse.duckdb``, ``warehouse.duckdb``, the latest
``data/published/*/warehouse.duckdb``, then the latest
``data/openings/published/*/warehouse.duckdb``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from chess_analytics.dashboard_cube import (  # noqa: E402
    WAREHOUSE_GRAINS,
    connect,
    locate_warehouse,
    warehouse_rows,
    warehouse_source,
    write_cube,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Aggregate warehouse.duckdb into the cube")
    parser.add_argument("--warehouse", type=Path, default=None)
    parser.add_argument(
        "--cube",
        type=Path,
        default=ROOT / "data" / "public" / "dashboard_cube.parquet",
    )
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)
    source = locate_warehouse(args.warehouse, ROOT)
    if source is None:
        print(
            "No warehouse.duckdb found. Pass --warehouse or set CHESSLAB_WAREHOUSE.",
            file=sys.stderr,
        )
        print(
            "The hosted cube stays the published aggregate until this command succeeds.",
            file=sys.stderr,
        )
        return 2
    connection = duckdb.connect(str(source), read_only=True)
    try:
        kind = warehouse_source(connection)
        if not kind:
            print(
                "warehouse is missing fact_game or opening_game.",
                file=sys.stderr,
            )
            return 2
        added = warehouse_rows(connection)
    finally:
        connection.close()
    existing = _read_cube(args.cube) if args.cube.is_file() else []
    kept = [row for row in existing if row["grain"] not in WAREHOUSE_GRAINS]
    destination = args.output or args.cube
    size = write_cube([*kept, *added], destination)
    covered = sum(int(row["games"]) for row in added if row["grain"] == "game_cell")
    print(
        f"Wrote {destination} ({size} bytes, {len(kept) + len(added)} rows, "
        f"{len(added)} from {kind}; game_cell covers {covered} games)"
    )
    return 0


def _read_cube(path: Path) -> list[dict[str, object]]:
    connection = connect(path)
    try:
        result = connection.execute('select * from "cube"')
        names = [item[0] for item in result.description]
        return [dict(zip(names, row, strict=True)) for row in result.fetchall()]
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
