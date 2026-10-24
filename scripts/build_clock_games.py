"""Add a capped clock-band game sample to the hosted cube.

Reads a local PGN prefix or a ``fact_move`` warehouse. It does not download.
Player names stay out of the file. The public Lichess site id and the two
ratings are the fields the page shows. The script prints the cube's bytes
and rows before and after the write.

From the repository root, with the pinned August prefix on disk:

    uv run --locked --no-editable --extra dashboard \
      python scripts/build_clock_games.py \
      --pgn /path/to/lichess-standard-rated-2026-08-prefix-40000000.zst

``build_dashboard_cube.py`` replaces the file and drops these rows. Run this
script again after that builder. ``build_warehouse_cube.py`` keeps them,
because ``clock_game`` is not a warehouse aggregate grain.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from chess_analytics.dashboard_cube import (  # noqa: E402
    CLOCK_BANDS,
    CLOCK_GAME_GRAIN,
    align_row,
    clock_game_rows_from_pgn,
    clock_game_rows_from_warehouse,
    connect,
    locate_warehouse,
    public_issues,
    write_cube,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sample clock-band games into the cube")
    parser.add_argument("--pgn", type=Path, default=None)
    parser.add_argument("--warehouse", type=Path, default=None)
    parser.add_argument(
        "--cube",
        type=Path,
        default=ROOT / "data" / "public" / "dashboard_cube.parquet",
    )
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--max-games", type=int, default=100_000)
    args = parser.parse_args(argv)
    if not args.cube.is_file():
        print(f"Dashboard cube is not at {args.cube}", file=sys.stderr)
        return 2
    before_bytes = args.cube.stat().st_size
    existing = _read_cube(args.cube)
    print(f"Before: {before_bytes} bytes, {len(existing)} rows")
    added = _added_rows(args.pgn, args.warehouse, args.max_games)
    kept = [row for row in existing if row["grain"] != CLOCK_GAME_GRAIN]
    merged = [*kept, *added]
    issues = public_issues(merged)
    if issues:
        print(f"clock games failed the public check: {issues[0]}", file=sys.stderr)
        return 2
    destination = args.output or args.cube
    size = write_cube(merged, destination)
    distinct = len({row["lichess_id"] for row in added})
    print(
        f"After: {size} bytes, {len(merged)} rows, "
        f"{len(added)} {CLOCK_GAME_GRAIN} rows, {distinct} distinct games"
    )
    counts = Counter(str(row["clock_band"]) for row in added)
    for band in CLOCK_BANDS:
        print(f"  {band}: {counts[band]} rows")
    return 0


def _added_rows(pgn: Path | None, warehouse: Path | None, max_games: int) -> list[dict]:
    if pgn is not None:
        if not pgn.is_file():
            print(f"PGN prefix is not at {pgn}", file=sys.stderr)
            raise SystemExit(2)
        return clock_game_rows_from_pgn(
            pgn,
            max_games=max_games,
            log=lambda message: print(message, file=sys.stderr),
        )
    source = locate_warehouse(warehouse, ROOT)
    if source is None:
        print(
            "No PGN prefix or fact_move warehouse. Pass --pgn or --warehouse.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    import duckdb

    connection = duckdb.connect(str(source), read_only=True)
    try:
        tables = {
            str(item[0])
            for item in connection.execute(
                "select table_name from information_schema.tables where table_schema = 'main'"
            ).fetchall()
        }
        if "fact_move" not in tables:
            print("warehouse has no fact_move table.", file=sys.stderr)
            raise SystemExit(2)
        return clock_game_rows_from_warehouse(connection)
    finally:
        connection.close()


def _read_cube(path: Path) -> list[dict[str, object]]:
    connection = connect(path)
    try:
        result = connection.execute('select * from "cube"')
        names = [item[0] for item in result.description]
        return [align_row(dict(zip(names, row, strict=True))) for row in result.fetchall()]
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
