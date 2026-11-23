"""Fail-closed, public-only JSON view of the committed dashboard cube.

Only the two named public inputs are opened. Extract lineage is deliberately
separate from the mixed published populations in the cube.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from datetime import date
from pathlib import Path

from chess_analytics import dashboard_cube as cube
from chess_analytics.public_extract import load_extract, table_rows

CUBE = "data/public/dashboard_cube.parquet"
EXTRACT = "data/public/dashboard_extract.json"
GRAINS = {
    "august_draw",
    "august_family",
    "clock_game",
    "clock_slice",
    "clock_cell",
    "color_score",
    "corpus_month",
    "game_cell",
    "result_cell",
    "result_line",
    "opening_continuation",
    "opening_family",
    "opening_line",
    "opening_position",
    "transposition",
    "transposition_route",
}
POPULATIONS = (
    "Mixed published populations: training months and warehouse aggregate cells; "
    "rated-public and elite opening positions; August prefix clock slices and game sample. "
    "Extract lineage does not establish the origin of every cube grain."
)


def byte_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate(rows: list[dict]) -> None:
    issues = cube.public_issues(rows)
    if issues or not rows:
        raise ValueError(f"invalid public cube: {issues[:1] or 'no rows'}")
    clock_cells = Counter()
    for row in rows:
        if row["grain"] not in GRAINS:
            raise ValueError("unknown public cube grain")
        for name in ("period_start", "period_end"):
            if not isinstance(row[name], date):
                raise ValueError(f"invalid cube date: {name}")
        if row["period_start"] > row["period_end"]:
            raise ValueError("invalid cube date range")
        for name, value in row.items():
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError("non-finite cube value")
            if (
                name in cube.INTEGER_COLUMNS
                and value is not None
                and (type(value) is not int or value < 0)
            ):
                raise ValueError(f"invalid cube count: {name}")
        game = row["grain"] == cube.CLOCK_GAME_GRAIN
        if game:
            cell = tuple(
                row[name] for name in ("clock_band", "time_control", "rating_band", "color")
            )
            clock_cells[cell] += 1
            if clock_cells[cell] > cube.GAMES_PER_CLOCK_CELL:
                raise ValueError("clock game publication cap exceeded")
            if re.fullmatch(r"[A-Za-z0-9]{8}", row["lichess_id"] or "") is None:
                raise ValueError("invalid public Lichess id")
            if row["clock_band"] not in cube.CLOCK_BANDS or row["games"] is not None:
                raise ValueError("invalid clock game")
        elif row["lichess_id"] is not None or row["white_rating"] is not None:
            raise ValueError("game identifiers outside clock_game")
        elif row["black_rating"] is not None:
            raise ValueError("game ratings outside clock_game")
        elif row["games"] is not None and row["games"] < cube.MIN_CELL:
            raise ValueError("cube count below ten-game floor")
        elif row["grain"] == "clock_slice" and (row["moves"] or 0) < cube.MIN_CELL:
            raise ValueError("cube clock slice below publication floor")


def pack_rows(rows: list[dict]) -> dict:
    """Per-grain columns and string dictionaries keep repeated FEN/SAN small."""
    packed = {}
    for grain in sorted({row["grain"] for row in rows}):
        group = [row for row in rows if row["grain"] == grain]
        columns = [
            name
            for name in cube.COLUMNS
            if name != "grain" and any(row[name] is not None for row in group)
        ]
        dictionaries = {}
        indexes = {}
        for name in columns:
            if any(isinstance(row[name], str | date) for row in group):
                values = sorted({str(row[name]) for row in group if row[name] is not None})
                dictionaries[name] = values
                indexes[name] = {value: index for index, value in enumerate(values)}
        packed[grain] = {
            "columns": columns,
            "dictionaries": dictionaries,
            "rows": [
                [
                    indexes[name][str(row[name])]
                    if name in indexes and row[name] is not None
                    else row[name]
                    for name in columns
                ]
                for row in group
            ],
        }
    return packed


def export_dashboard(repo: Path, output: Path, revision: str) -> dict:
    """Write a compact array view; return separately scoped manifest sources."""
    paths = [repo / CUBE, repo / EXTRACT]
    for path in paths:
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"missing or symlink dashboard input: {path.name}")
    if not 0 < paths[0].stat().st_size <= cube.SIZE_BUDGET_BYTES:
        raise ValueError("cube outside public size budget")
    hashes = [byte_hash(path) for path in paths]
    extract = load_extract(paths[1])
    receipts = [
        row
        for row in table_rows(extract, "metric_receipt")
        if row["receipt_id"] == "game_draw_rate"
    ]
    if len(receipts) != 1:
        raise ValueError("extract needs one game_draw_rate receipt")
    connection = cube.connect(paths[0])
    try:
        result = connection.execute('select * from "cube"')
        names = tuple(item[0] for item in result.description)
        if names != cube.COLUMNS:
            raise ValueError("cube columns differ from public allowlist")
        rows = [dict(zip(names, row, strict=True)) for row in result.fetchall()]
    finally:
        connection.close()
    _validate(rows)
    ranks = {
        row["lichess_id"]: cube.clock_game_rank(row["lichess_id"])[0].hex()
        for row in rows
        if row["grain"] == cube.CLOCK_GAME_GRAIN
    }
    sources = {
        CUBE: {
            "sha256": hashes[0],
            "scope": "cube chart rows; mixed published populations",
            "path": CUBE,
            "row_count": len(rows),
            "grain_counts": dict(sorted(Counter(row["grain"] for row in rows).items())),
            "site_source_revision": revision,
            "populations": POPULATIONS,
        },
        EXTRACT: {
            "sha256": hashes[1],
            "scope": "extract provenance only; not cube-wide lineage",
            "path": EXTRACT,
            "build": extract["build"],
            "game_draw_rate_mart_id": receipts[0]["mart_id"],
        },
    }
    payload = {
        "version": 1,
        "grains": pack_rows(rows),
        "clock_ranks": ranks,
        "provenance": sources,
    }
    # A mutation during the build must never pair rows with a stale byte hash.
    if hashes != [byte_hash(path) for path in paths]:
        raise ValueError("dashboard input changed during export")
    output.mkdir(parents=True, exist_ok=True)
    (output / "dashboard.json").write_text(
        json.dumps(payload, default=str, separators=(",", ":"), allow_nan=False) + "\n"
    )
    return sources
