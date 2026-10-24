"""Public dashboard cube: build, filter, KPI deltas, and drill state.

The hosted app queries the committed Parquet file with DuckDB. The builder
reads the same published reports as the public extract. It does not open the
analytical warehouse and it does not copy player or game identifiers.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

CUBE_FILENAME = "dashboard_cube.parquet"
SIZE_BUDGET_BYTES = 10_000_000
AUGUST_DAY = date(2026, 8, 1)
RATING_BANDS = ("under_1200", "1200_1599", "1600_1999", "2000_plus")
RATING_SUBSET = {"1200_1599": "1400_1599"}
CLOCK_BANDS = ("under_10", "10_to_29", "30_to_59", "60_plus")
_COLOR_LABEL = {"white": "White", "black": "Black"}
_RATING_LABEL = {
    "under_1200": "Under 1200",
    "1200_1599": "1200–1599",
    "1400_1599": "1400–1599",
    "1600_1999": "1600–1999",
    "2000_plus": "2000+",
}
EXPLORER_COHORTS = ("rated_public", "elite_reference")
MIN_CELL = 10
WAREHOUSE_GRAINS = ("game_cell", "result_cell", "result_line", "clock_cell")
_WIDE = (date(2000, 1, 1), date(2100, 1, 1))
_DIM_LABEL = {
    "time_control": "time",
    "rating_band": "rating",
    "opening_family": "opening",
    "color": "color",
}
_EMPTY_CUT = "cut"
_NO_CELLS = "no cells for this cut"
COLUMNS = (
    "grain",
    "cohort",
    "period",
    "period_start",
    "period_end",
    "time_control",
    "color",
    "rating_band",
    "opening_family",
    "opening_line",
    "fen",
    "eco",
    "clock_band",
    "phase",
    "continuation",
    "games",
    "wins",
    "draws",
    "losses",
    "share",
    "moves",
    "evaluable_moves",
    "proxy_errors",
    "error_proxy_rate",
    "ply",
    "rating_diff",
    "mean_ply",
)
INTEGER_COLUMNS = (
    "games",
    "wins",
    "draws",
    "losses",
    "moves",
    "evaluable_moves",
    "proxy_errors",
    "ply",
)
FORBIDDEN_PARTS = (
    "player_key",
    "game_id",
    "headers_json",
    "fingerprint",
    "username",
    "absolute_path",
    "source_file",
)
_LEAK = re.compile(r"player_key|username|headers_json|\.pgn\b|/[A-Za-z0-9._/-]+\.json")
_SELECT = """
select
  "grain",
  "cohort",
  "period",
  "period_start",
  "period_end",
  "time_control",
  "color",
  "rating_band",
  "opening_family",
  "opening_line",
  "fen",
  "eco",
  "clock_band",
  "phase",
  "continuation",
  "games",
  "wins",
  "draws",
  "losses",
  "share",
  "moves",
  "evaluable_moves",
  "proxy_errors",
  "error_proxy_rate",
  "ply",
  "rating_diff",
  "mean_ply"
from "cube"
""".strip()
_CREATE = """
create table "cube" (
  "grain" varchar,
  "cohort" varchar,
  "period" varchar,
  "period_start" date,
  "period_end" date,
  "time_control" varchar,
  "color" varchar,
  "rating_band" varchar,
  "opening_family" varchar,
  "opening_line" varchar,
  "fen" varchar,
  "eco" varchar,
  "clock_band" varchar,
  "phase" varchar,
  "continuation" varchar,
  "games" bigint,
  "wins" bigint,
  "draws" bigint,
  "losses" bigint,
  "share" double,
  "moves" bigint,
  "evaluable_moves" bigint,
  "proxy_errors" bigint,
  "error_proxy_rate" double,
  "ply" integer,
  "rating_diff" double,
  "mean_ply" double
)
""".strip()


@dataclass(frozen=True)
class Filters:
    """Global dashboard filters. None means all values of that dimension."""

    start: date
    end: date
    time_control: str | None = None
    color: str | None = None
    rating_band: str | None = None
    opening_family: str | None = None

    def __post_init__(self) -> None:
        if self.start > self.end:
            raise ValueError("filter start is after filter end")


@dataclass(frozen=True)
class Kpi:
    label: str
    value: str
    detail: str


@dataclass(frozen=True)
class Drill:
    family: str | None = None
    line: str | None = None
    fen: str | None = None
    clock_band: str | None = None


def cube_path(project: Path | None = None) -> Path:
    """Committed cube. An explicit project wins over the environment."""
    if project is not None:
        return Path(project) / "data" / "public" / CUBE_FILENAME
    override = os.environ.get("CHESSLAB_DASHBOARD_CUBE")
    if override:
        return Path(override)
    for candidate in _cube_candidates():
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        "dashboard cube not found; set CHESSLAB_DASHBOARD_CUBE to the parquet file"
    )


def connect(path: Path | None = None):
    """Register the Parquet cube. The caller owns the connection."""
    import duckdb

    source = Path(path) if path is not None else cube_path()
    if not source.is_file():
        raise FileNotFoundError(
            "dashboard cube not found; set CHESSLAB_DASHBOARD_CUBE to the parquet file"
        )
    connection = duckdb.connect()
    quoted = str(source.resolve()).replace("'", "''")
    connection.execute(f"create view \"cube\" as select * from read_parquet('{quoted}')")
    return connection


def build_rows(
    corpus: Mapping[str, object],
    positions: Mapping[str, object],
    reference: Mapping[str, object],
    figures: Mapping[str, object],
    analytical: Mapping[str, object],
) -> list[dict[str, object]]:
    """One cube row per published aggregate. Rows share ``COLUMNS``."""
    spans = cohort_spans(corpus)
    august = _august_day(analytical)
    rows: list[dict[str, object]] = []
    rows.extend(corpus_month_rows(corpus))
    rows.extend(opening_rows(positions, spans))
    rows.extend(august_family_rows(reference, august))
    rows.extend(color_score_rows(reference, august))
    rows.append(draw_row(reference, august))
    rows.extend(clock_slice_rows(figures, august))
    issues = public_issues(rows)
    if issues:
        raise ValueError(f"dashboard cube failed the public check: {issues[0]}")
    return sorted(rows, key=_sort_key)


def write_cube(rows: Sequence[Mapping[str, object]], path: Path) -> int:
    """Write Parquet with an explicit schema. Returns the file size."""
    import duckdb

    if not rows:
        raise ValueError("dashboard cube has no rows")
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect()
    try:
        connection.execute(_CREATE)
        placeholders = ", ".join("?" for _ in COLUMNS)
        connection.executemany(
            f'insert into "cube" values ({placeholders})',
            [_tuple(row) for row in rows],
        )
        quoted = str(destination.resolve()).replace("'", "''")
        connection.execute(f"copy \"cube\" to '{quoted}' (format parquet)")
    finally:
        connection.close()
    size = destination.stat().st_size
    if size > SIZE_BUDGET_BYTES or size <= 0:
        raise ValueError(f"dashboard cube size is outside the budget: {size}")
    return size


def public_issues(rows: Sequence[Mapping[str, object]]) -> list[str]:
    """Column names and string values that would publish an identifier."""
    issues: list[str] = []
    for index, row in enumerate(rows):
        if tuple(row) != COLUMNS:
            issues.append(f"row {index} columns")
            continue
        for column, value in row.items():
            if any(part in column for part in FORBIDDEN_PARTS):
                issues.append(f"column {column}")
            if isinstance(value, str) and _LEAK.search(value):
                issues.append(f"value {column}")
    return issues


def cohort_spans(
    corpus: Mapping[str, object],
) -> dict[str, tuple[date, date]]:
    grouped: dict[str, list[tuple[date, date]]] = {}
    for source in _as_list(corpus.get("training_sources")):
        cohort = str(source["cohort"])
        grouped.setdefault(cohort, []).append(
            (_parse_date(source["first_date"]), _parse_date(source["last_date"]))
        )
    return {
        cohort: (min(item[0] for item in windows), max(item[1] for item in windows))
        for cohort, windows in grouped.items()
    }


def corpus_month_rows(corpus: Mapping[str, object]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for source in _as_list(corpus.get("training_sources")):
        start = _parse_date(source["first_date"])
        end = _parse_date(source["last_date"])
        rows.append(
            _row(
                grain="corpus_month",
                cohort=str(source["cohort"]),
                period=str(source["period"]),
                period_start=start,
                period_end=end,
                games=_num(source["games"]),
            )
        )
    return rows


def opening_rows(
    positions: Mapping[str, object],
    spans: Mapping[str, tuple[date, date]],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    cohorts = positions.get("cohorts")
    if not isinstance(cohorts, Mapping):
        raise ValueError("opening positions report has no cohorts")
    for cohort, body in cohorts.items():
        if not isinstance(body, Mapping) or cohort not in spans:
            continue
        start, end = spans[str(cohort)]
        period = _span_label(start, end)
        for family in _as_list(body.get("opening_families")):
            games = _num(family["games"])
            if games < MIN_CELL:
                continue
            rows.append(
                _row(
                    grain="opening_family",
                    cohort=str(cohort),
                    period=period,
                    period_start=start,
                    period_end=end,
                    opening_family=str(family["family"]),
                    games=games,
                    share=float(family["share"]),
                )
            )
        views = body.get("views")
        if not isinstance(views, Mapping):
            continue
        for view in views.values():
            if not isinstance(view, Mapping) or not isinstance(view.get("family"), str):
                continue
            rows.extend(_view_rows(str(cohort), period, start, end, view))
    return rows


def august_family_rows(reference: Mapping[str, object], august: date) -> list[dict[str, object]]:
    families = reference.get("opening_families")
    if not isinstance(families, Mapping) or not families:
        raise ValueError("august opening families are missing")
    counted = [(str(name), _num(games)) for name, games in families.items()]
    if sum(games for _name, games in counted) <= 0:
        raise ValueError("august opening families do not sum")
    kept = [(name, games) for name, games in counted if games >= MIN_CELL]
    total = sum(games for _name, games in kept)
    if total <= 0:
        return []
    return [
        _row(
            grain="august_family",
            cohort="m3_august_prefix",
            period=august.isoformat(),
            period_start=august,
            period_end=august,
            opening_family=name,
            games=games,
            share=games / total,
        )
        for name, games in kept
    ]


def color_score_rows(reference: Mapping[str, object], august: date) -> list[dict[str, object]]:
    cohorts = reference.get("opening_player_cohorts")
    if not isinstance(cohorts, Mapping):
        raise ValueError("opening player cohorts are missing")
    rows: list[dict[str, object]] = []
    for key, counts in cohorts.items():
        family, color, rating, control = str(key).split("|")
        if not isinstance(counts, Mapping):
            raise ValueError("opening player cohort counts are missing")
        wins = _num(counts["wins"])
        draws = _num(counts["draws"])
        losses = _num(counts["losses"])
        games = _num(counts["games"])
        rows.append(
            _row(
                grain="color_score",
                cohort="m3_august_prefix",
                period=august.isoformat(),
                period_start=august,
                period_end=august,
                time_control=control,
                color=color,
                rating_band=rating.removeprefix("rating_"),
                opening_family=family,
                games=games,
                wins=wins,
                draws=draws,
                losses=losses,
                share=(wins + draws * 0.5) / games,
            )
        )
    return rows


def draw_row(reference: Mapping[str, object], august: date) -> dict[str, object]:
    games = _num(reference["eligible_games"])
    draws = _num(reference["drawn_eligible_games"])
    return _row(
        grain="august_draw",
        cohort="m3_august_prefix",
        period=august.isoformat(),
        period_start=august,
        period_end=august,
        games=games,
        draws=draws,
        share=draws / games,
    )


def clock_slice_rows(figures: Mapping[str, object], august: date) -> list[dict[str, object]]:
    clock = figures.get("clock")
    if not isinstance(clock, Mapping):
        raise ValueError("clock figures are missing")
    rows: list[dict[str, object]] = []
    for item in _as_list(clock.get("strata")):
        moves = _num(item["eligible_moves"])
        if moves < MIN_CELL:
            continue
        evaluable = _num(item["evaluable_moves"])
        errors = _num(item["proxy_errors"])
        rate = None if evaluable == 0 else errors / evaluable
        rows.append(
            _row(
                grain="clock_slice",
                cohort="m3_august_prefix",
                period=august.isoformat(),
                period_start=august,
                period_end=august,
                time_control=str(item["time_control"]),
                rating_band=str(item["rating_band"]),
                clock_band=str(item["bucket"]),
                phase=str(item["phase"]),
                moves=moves,
                evaluable_moves=evaluable,
                proxy_errors=errors,
                error_proxy_rate=rate,
            )
        )
    return rows


def bounds(connection) -> tuple[date, date]:
    row = connection.execute('select min("period_start"), max("period_end") from "cube"').fetchone()
    if row is None or row[0] is None or row[1] is None:
        raise ValueError("dashboard cube has no dates")
    return row[0], row[1]


def dimension_values(connection, column: str) -> list[str]:
    if column not in {"time_control", "rating_band", "opening_family", "clock_band"}:
        raise ValueError("unknown cube dimension")
    sql = f'select distinct "{column}" from "cube" where "{column}" is not null order by "{column}"'
    return [str(item[0]) for item in connection.execute(sql).fetchall()]


def active_filter_text(filters: Filters) -> str:
    """One line of the current global filter state."""
    color = None if filters.color is None else _COLOR_LABEL.get(filters.color, filters.color)
    rating = (
        None
        if filters.rating_band is None
        else _RATING_LABEL.get(filters.rating_band, filters.rating_band)
    )
    return (
        f"Date {filters.start.isoformat()}–{filters.end.isoformat()}"
        f" · Time {_or_all(filters.time_control)}"
        f" · Color {_or_all(color)}"
        f" · Rating {_or_all(rating)}"
        f" · Opening {_or_all(filters.opening_family)}"
    )


def previous_periods(periods: Sequence[str], selected: Sequence[str]) -> list[str] | None:
    """The N periods immediately before the earliest selected period.

    ``None`` when the prior window is shorter than the selection. Periods are
    the published month keys, already sorted.
    """
    if not selected:
        return None
    ordered = list(periods)
    earliest = min(selected)
    if earliest not in ordered:
        return None
    index = ordered.index(earliest)
    width = len(selected)
    if index < width:
        return None
    return ordered[index - width : index]


def kpis(connection, filters: Filters) -> list[Kpi]:
    """Cards for the current filters. A missing cross keeps the coarser figure."""
    months = _inside(connection, "corpus_month", filters, dimensional=False)
    if _grain_present(connection, "game_cell") or _grain_present(connection, "result_cell"):
        games = _warehouse_games_kpi(connection, filters)
        win, loss, draw = _warehouse_result_kpis(connection, filters)
    else:
        games = _games_kpi(connection, filters, months)
        win, loss, draw = _result_kpis(connection, filters)
    clock = _clock_kpi(connection, filters)
    positions = _position_kpi(connection, filters)
    return [games, win, draw, loss, clock, positions, *_mean_kpis(connection, filters)]


def opening_families(
    connection, filters: Filters, cohort: str, *, dates: bool = True
) -> list[dict[str, object]]:
    return _labeled(
        _inside(
            connection,
            "opening_family",
            filters,
            dimensional=True,
            cohort=cohort,
            adaptive=True,
            dates=dates,
        ),
        "opening_family",
        "games",
    )


def opening_lines(
    connection, filters: Filters, cohort: str, family: str, *, dates: bool = True
) -> list[dict[str, object]]:
    rows = _inside(
        connection,
        "opening_line",
        _with_family(filters, family),
        dimensional=True,
        cohort=cohort,
        adaptive=True,
        dates=dates,
    )
    grouped: dict[str, dict[str, object]] = {}
    for row in rows:
        line = str(row["opening_line"])
        slot = grouped.setdefault(line, {"label": line, "games": 0, "fens": []})
        slot["games"] = _num(slot["games"]) + _num(row["games"])
        fens = slot["fens"]
        assert isinstance(fens, list)
        fen = str(row["fen"])
        if fen not in fens:
            fens.append(fen)
    return sorted(grouped.values(), key=lambda item: _num(item["games"]), reverse=True)


def opening_position(
    connection, filters: Filters, cohort: str, family: str, fen: str, *, dates: bool = True
) -> dict[str, object] | None:
    rows = [
        row
        for row in _inside(
            connection,
            "opening_position",
            _with_family(filters, family),
            dimensional=True,
            cohort=cohort,
            adaptive=True,
            dates=dates,
        )
        if row["fen"] == fen
    ]
    return rows[0] if rows else None


def continuations(
    connection, filters: Filters, cohort: str, family: str, fen: str, *, dates: bool = True
) -> list[dict[str, object]]:
    rows = [
        row
        for row in _inside(
            connection,
            "opening_continuation",
            _with_family(filters, family),
            dimensional=True,
            cohort=cohort,
            adaptive=True,
            dates=dates,
        )
        if row["fen"] == fen
    ]
    return _labeled(rows, "continuation", "games")


def explorer_cohort(connection, filters: Filters) -> str | None:
    """Rated public when its span is inside the range, else the elite month."""
    cohort, covered = position_cohort(connection, filters)
    if covered:
        return cohort
    return None


def position_cohort(connection, filters: Filters) -> tuple[str | None, bool]:
    """Explorer cohort, and whether its span sits inside the date range."""
    present = {
        str(row["cohort"])
        for row in _inside(connection, "opening_family", filters, dimensional=False)
    }
    for cohort in EXPLORER_COHORTS:
        if cohort in present:
            return cohort, True
    catalog = {
        str(item[0])
        for item in connection.execute(
            'select distinct "cohort" from "cube" where "grain" = ?',
            ["opening_family"],
        ).fetchall()
    }
    for cohort in EXPLORER_COHORTS:
        if cohort in catalog:
            return cohort, False
    return None, False


def clock_bands(connection, filters: Filters) -> list[dict[str, object]]:
    rows, _ignored, _named = _clock_source_rows(connection, filters)
    return _band_rows(rows)


def clock_display(connection, filters: Filters) -> tuple[list[dict[str, object]], str | None, str]:
    """Bands, one section caption, and a short tag for the clock KPI."""
    rows, fell_back, named = _clock_source_rows(connection, filters)
    warehouse = _grain_present(connection, "clock_cell")
    grain = "clock_cell" if warehouse else "clock_slice"
    ignored = _unapplied(connection, grain, filters)
    tag_parts = list(ignored)
    for label in named:
        if label not in tag_parts:
            tag_parts.append(label)
    if fell_back and rows and "date" not in tag_parts:
        tag_parts.append("date")
    caption = _clock_caption(tag_parts, fell_back and bool(rows), bool(rows), warehouse=warehouse)
    tag = ""
    if tag_parts == ["date"]:
        tag = "warehouse window" if warehouse else "August"
    elif tag_parts:
        tag = "not by " + ", ".join(tag_parts)
    return _band_rows(rows), caption, tag


def clock_slices(connection, filters: Filters, band: str) -> list[dict[str, object]]:
    rows, _fell_back, _named = _clock_source_rows(connection, filters)
    chosen = [row for row in rows if row["clock_band"] == band]
    chosen.sort(key=lambda item: _num(item["evaluable_moves"] or 0), reverse=True)
    return chosen


def month_display(connection, filters: Filters) -> tuple[list[dict[str, object]], str | None]:
    """Period bars, plus one caption when a filter cannot split them."""
    rows = month_bars(connection, filters)
    notes: list[str] = []
    if not rows:
        rows = month_bars(connection, Filters(_WIDE[0], _WIDE[1]))
        if rows:
            notes.append("No published period sits fully inside this date range.")
    ignored = [
        label
        for value, label in (
            (filters.color, "color"),
            (filters.time_control, "time control"),
            (filters.rating_band, "rating"),
            (filters.opening_family, "opening"),
        )
        if value
    ]
    if ignored:
        notes.append("Period totals are not split by " + _join_or(ignored) + ".")
    return rows, " ".join(notes) if notes else None


def transpositions(
    connection, filters: Filters, *, limit: int = 6
) -> tuple[list[dict[str, object]], str]:
    """Positions reached by at least two acyclic move orders.

    ``routes`` on each row are the top three surviving orders. The caption
    names every sidebar filter this grain cannot apply.
    """
    cohort, date_ok = position_cohort(connection, filters)
    if cohort is None or not _grain_present(connection, "transposition"):
        return [], "No published transposing positions."
    clauses = ['"grain" = ?', '"cohort" = ?']
    params: list[object] = ["transposition", cohort]
    if date_ok:
        clauses.extend(['"period_start" >= ?', '"period_end" <= ?'])
        params.extend((filters.start, filters.end))
    if filters.opening_family:
        clauses.append('"opening_family" = ?')
        params.append(filters.opening_family)
    notes: list[str] = []
    if not date_ok:
        notes.append("date")
    _apply_carried(connection, "transposition", filters, clauses, params, notes)
    sql = _SELECT + " where " + " and ".join(clauses) + ' order by "games" desc'
    found = _records(connection.execute(sql, params))[:limit]
    packed = [_pack_transposition(connection, cohort, row) for row in found]
    return packed, _transposition_caption(notes)


def month_bars(connection, filters: Filters) -> list[dict[str, object]]:
    rows = _inside(connection, "corpus_month", filters, dimensional=False)
    return [
        {"label": str(row["period"]), "games": _num(row["games"])}
        for row in sorted(rows, key=lambda item: str(item["period"]))
    ]


def select_family(drill: Drill, family: str | None) -> Drill:
    if not family:
        return Drill(clock_band=drill.clock_band)
    if family == drill.family:
        return drill
    return Drill(family=family, clock_band=drill.clock_band)


def select_line(drill: Drill, line: str, fens: Sequence[str]) -> Drill:
    if drill.family is None:
        raise ValueError("line drill needs a family")
    fen = fens[0] if len(fens) == 1 else None
    return Drill(family=drill.family, line=line, fen=fen, clock_band=drill.clock_band)


def select_position(drill: Drill, fen: str) -> Drill:
    if drill.family is None or drill.line is None:
        raise ValueError("position drill needs a family and a line")
    return Drill(family=drill.family, line=drill.line, fen=fen, clock_band=drill.clock_band)


def select_clock(drill: Drill, band: str | None) -> Drill:
    return Drill(
        family=drill.family,
        line=drill.line,
        fen=drill.fen,
        clock_band=band or None,
    )


def climb(drill: Drill, *, line_fen_count: int = 1) -> Drill:
    """One step up. A line with a single position climbs past that position."""
    if drill.fen:
        if line_fen_count > 1:
            return Drill(family=drill.family, line=drill.line, clock_band=drill.clock_band)
        return Drill(family=drill.family, clock_band=drill.clock_band)
    if drill.line:
        return Drill(family=drill.family, clock_band=drill.clock_band)
    if drill.family:
        return Drill(clock_band=drill.clock_band)
    if drill.clock_band:
        return Drill()
    return drill


def breadcrumb(drill: Drill) -> list[str]:
    parts = ["Openings"]
    if drill.family:
        parts.append(drill.family)
    if drill.line:
        parts.append(drill.line)
    if drill.fen:
        parts.append("Position")
    if drill.clock_band:
        parts.append(f"Clock {drill.clock_band}")
    return parts


def sql_text() -> list[str]:
    """SQL owned by this module, for the lowercase-identifier check."""
    return [
        _SELECT,
        _CREATE,
        'create view "cube" as select * from read_parquet(?)',
        'insert into "cube" values (?)',
        'copy "cube" to ? (format parquet)',
        'select min("period_start"), max("period_end") from "cube"',
        (
            'select distinct "time_control" from "cube" '
            'where "time_control" is not null order by "time_control"'
        ),
        (
            'select count(distinct "fen") from "cube" '
            'where "grain" = ? and "cohort" = ? '
            'and "period_start" >= ? and "period_end" <= ? '
            'and "opening_family" = ?'
        ),
        'select "period" from "cube" where "grain" = ? order by "period"',
        'select coalesce(sum("games"), 0) from "cube" where "grain" = ? and "period" in (?)',
        _GAME_CELL_SQL,
        _RESULT_CELL_SQL,
        _RESULT_LINE_SQL,
        _CLOCK_CELL_SQL,
        _OPENING_GAME_CELL_SQL,
        _OPENING_RESULT_CELL_SQL,
    ]


def _games_kpi(connection, filters: Filters, months: Sequence[Mapping[str, object]]) -> Kpi:
    if not _dimensional(filters):
        current = sum(_num(row["games"]) for row in months)
        delta = _training_delta(connection, filters, months)
        detail = "no prior period" if delta is None else f"{delta:+,} vs prior"
        return Kpi("Games", f"{current:,}", detail)
    if filters.color:
        scored = _color_rows(connection, filters)
        if scored:
            total = sum(_num(row["games"]) for row in scored)
            return Kpi("Games", f"{total:,}", "published cells")
    if filters.opening_family:
        cohort, covered = position_cohort(connection, filters)
        if cohort:
            matched = opening_families(connection, filters, cohort, dates=covered)
            if matched:
                total = sum(_num(row["games"]) for row in matched)
                pool = "rated public" if cohort == "rated_public" else "elite month"
                ignored = _set_labels(filters, skip_opening=True)
                if not covered:
                    ignored.append("date")
                return Kpi("Games", f"{total:,}", _with_note(pool, ignored))
    if months:
        return Kpi("Games", f"{sum(_num(row['games']) for row in months):,}", _period_note(filters))
    wider = _inside(connection, "corpus_month", Filters(_WIDE[0], _WIDE[1]), dimensional=False)
    total = sum(_num(row["games"]) for row in wider)
    return Kpi("Games", f"{total:,}", _with_note("wider window", _set_labels(filters)))


def _result_kpis(connection, filters: Filters) -> tuple[Kpi, Kpi, Kpi]:
    scores, notes = _collect(
        connection, "color_score", filters, force_color=filters.color or "white"
    )
    win, loss, draw = _score_cards(scores, notes)
    if _dimensional(filters):
        return win, loss, draw
    drawn = _inside(connection, "august_draw", filters, dimensional=False)
    if not drawn:
        drawn = _inside(connection, "august_draw", Filters(_WIDE[0], _WIDE[1]), dimensional=False)
        if drawn:
            games = _num(drawn[0]["games"])
            draws = _num(drawn[0]["draws"])
            draw = Kpi("Draw rate", _percent(draws / games), f"{draws:,} / {games:,} · August")
            return win, loss, draw
    if drawn:
        games = _num(drawn[0]["games"])
        draws = _num(drawn[0]["draws"])
        draw = Kpi("Draw rate", _percent(draws / games), f"{draws:,} / {games:,}")
    return win, loss, draw


def _clock_kpi(connection, filters: Filters) -> Kpi:
    _bands, _caption, tag = clock_display(connection, filters)
    rows, _fell_back, named = _clock_source_rows(connection, filters)
    if not rows and named:
        return Kpi("Clock error", "0.0%", _NO_CELLS + " · not by " + ", ".join(named))
    evaluable = sum(_num(row["evaluable_moves"] or 0) for row in rows)
    errors = sum(_num(row["proxy_errors"] or 0) for row in rows)
    if evaluable == 0:
        detail = "no evaluable moves" if not tag else f"no evaluable moves · {tag}"
        return Kpi("Clock error", "0.0%", detail)
    detail = f"{errors:,} / {evaluable:,}"
    if tag:
        detail = f"{detail} · {tag}"
    return Kpi("Clock error", _percent(errors / evaluable), detail)


def _position_kpi(connection, filters: Filters) -> Kpi:
    cohort, covered = position_cohort(connection, filters)
    if cohort is None:
        return Kpi("Positions", "0", "no published positions")
    sql = 'select count(distinct "fen") from "cube" where "grain" = ? and "cohort" = ?'
    params: list[object] = ["opening_position", cohort]
    if covered:
        sql += ' and "period_start" >= ? and "period_end" <= ?'
        params.extend((filters.start, filters.end))
    if filters.opening_family:
        sql += ' and "opening_family" = ?'
        params.append(filters.opening_family)
    count = _num(connection.execute(sql, params).fetchone()[0])
    detail = "rated public" if cohort == "rated_public" else "elite month"
    ignored = _set_labels(filters, skip_opening=True)
    if not covered:
        ignored.append("date")
    return Kpi("Positions", f"{count:,}", _with_note(detail, ignored))


def _training_delta(
    connection, filters: Filters, months: Sequence[Mapping[str, object]]
) -> int | None:
    selected = [str(row["period"]) for row in months]
    catalog = [
        str(item[0])
        for item in connection.execute(
            'select "period" from "cube" where "grain" = ? order by "period"',
            ["corpus_month"],
        ).fetchall()
    ]
    prior = previous_periods(catalog, selected)
    if prior is None:
        return None
    current = sum(_num(row["games"]) for row in months)
    placeholders = ", ".join("?" for _ in prior)
    earlier = connection.execute(
        'select coalesce(sum("games"), 0) from "cube" '
        f'where "grain" = ? and "period" in ({placeholders})',
        ["corpus_month", *prior],
    ).fetchone()
    return current - _num(earlier[0])


def _color_rows(connection, filters: Filters) -> list[dict[str, object]]:
    return _inside(connection, "color_score", filters, dimensional=True)


def _inside(
    connection,
    grain: str,
    filters: Filters,
    *,
    dimensional: bool,
    cohort: str | None = None,
    adaptive: bool = False,
    dates: bool = True,
) -> list[dict[str, object]]:
    clauses: list[str] = []
    params: list[object] = [grain]
    if dates:
        clauses.extend(['"period_start" >= ?', '"period_end" <= ?'])
        params.extend((filters.start, filters.end))
    if cohort is not None:
        clauses.append('"cohort" = ?')
        params.append(cohort)
    if dimensional:
        _apply_dimensions(connection, grain, filters, clauses, params, adaptive=adaptive)
    sql = _SELECT + ' where "grain" = ?'
    if clauses:
        sql += " and " + " and ".join(clauses)
    return _records(connection.execute(sql, params))


def _apply_dimensions(
    connection,
    grain: str,
    filters: Filters,
    clauses: list[str],
    params: list[object],
    *,
    adaptive: bool,
) -> None:
    for column, value in (
        ("time_control", filters.time_control),
        ("color", filters.color),
        ("rating_band", filters.rating_band),
        ("opening_family", filters.opening_family),
    ):
        if value is None:
            continue
        if adaptive and not _carries(connection, grain, column):
            continue
        if column == "rating_band":
            _append_rating(clauses, params, value)
            continue
        _append_dimension(clauses, params, f'"{column}"', value)


def _append_dimension(
    clauses: list[str], params: list[object], column: str, value: str | None
) -> None:
    if value is None:
        return
    clauses.append(f"{column} = ?")
    params.append(value)


def _append_rating(clauses: list[str], params: list[object], band: str | None) -> None:
    if band is None:
        return
    subset = RATING_SUBSET.get(band)
    if subset is None:
        clauses.append('"rating_band" = ?')
        params.append(band)
        return
    clauses.append('("rating_band" = ? or "rating_band" = ?)')
    params.extend((band, subset))


def _tally(rows: Sequence[Mapping[str, object]]) -> tuple[int, int, int, int]:
    wins = sum(_num(row["wins"]) for row in rows)
    draws = sum(_num(row["draws"]) for row in rows)
    losses = sum(_num(row["losses"]) for row in rows)
    games = sum(_num(row["games"]) for row in rows)
    return wins, draws, losses, games


def _labeled(
    rows: Sequence[Mapping[str, object]], field: str, value: str
) -> list[dict[str, object]]:
    labeled = [
        {"label": str(row[field]), "games": _num(row[value]), "fen": row.get("fen")} for row in rows
    ]
    labeled.sort(key=lambda item: _num(item["games"]), reverse=True)
    return labeled


def _with_family(filters: Filters, family: str) -> Filters:
    return Filters(
        filters.start,
        filters.end,
        filters.time_control,
        filters.color,
        filters.rating_band,
        family,
    )


def _view_rows(
    cohort: str,
    period: str,
    start: date,
    end: date,
    view: Mapping[str, object],
) -> list[dict[str, object]]:
    family = str(view["family"])
    positions = view.get("positions")
    if not isinstance(positions, Mapping):
        return []
    rows: list[dict[str, object]] = []
    for body in positions.values():
        if not isinstance(body, Mapping):
            continue
        fen = str(body["position_key"])
        eco = _dominant_eco(body.get("opening_labels"))
        games = _num(body["games"])
        rows.append(
            _row(
                grain="opening_position",
                cohort=cohort,
                period=period,
                period_start=start,
                period_end=end,
                opening_family=family,
                fen=fen,
                eco=eco,
                games=games,
            )
        )
        rows.extend(_line_rows(cohort, period, start, end, family, fen, eco, body))
        rows.extend(_continuation_rows(cohort, period, start, end, family, fen, body))
        rows.extend(_transposition_rows(cohort, period, start, end, family, fen, eco, games, body))
    return rows


def _line_rows(
    cohort: str,
    period: str,
    start: date,
    end: date,
    family: str,
    fen: str,
    eco: str | None,
    body: Mapping[str, object],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for route in _as_list(body.get("routes")):
        games = _num(route["games"])
        if games < MIN_CELL:
            continue
        san = str(route["san"])
        rows.append(
            _row(
                grain="opening_line",
                cohort=cohort,
                period=period,
                period_start=start,
                period_end=end,
                opening_family=family,
                opening_line=san,
                fen=fen,
                eco=eco,
                games=games,
                share=float(route["share"]),
                ply=len(san.split()),
            )
        )
    return rows


def _continuation_rows(
    cohort: str,
    period: str,
    start: date,
    end: date,
    family: str,
    fen: str,
    body: Mapping[str, object],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for move in _as_list(body.get("continuations")):
        games = _num(move["games"])
        if games < MIN_CELL:
            continue
        rows.append(
            _row(
                grain="opening_continuation",
                cohort=cohort,
                period=period,
                period_start=start,
                period_end=end,
                opening_family=family,
                fen=fen,
                continuation=str(move["san"]),
                games=games,
                share=float(move["share_of_position_games"]),
            )
        )
    return rows


def _transposition_rows(
    cohort: str,
    period: str,
    start: date,
    end: date,
    family: str,
    fen: str,
    eco: str | None,
    games: int,
    body: Mapping[str, object],
) -> list[dict[str, object]]:
    """One summary row plus each acyclic route that clears the cell floor.

    A transposing board has at least two distinct acyclic arrival prefixes.
    The published ``routes`` list is that set. Repetition prefixes are already
    excluded from it. Routes under ``MIN_CELL`` games are omitted, and a board
    that then has fewer than two routes is not transposing in this cube.
    """
    kept = [route for route in _as_list(body.get("routes")) if _num(route["games"]) >= MIN_CELL]
    if games < MIN_CELL or len(kept) < 2:
        return []
    rows = [
        _row(
            grain="transposition",
            cohort=cohort,
            period=period,
            period_start=start,
            period_end=end,
            opening_family=family,
            fen=fen,
            eco=eco,
            games=games,
            ply=len(kept),
        )
    ]
    for route in kept:
        san = str(route["san"])
        rows.append(
            _row(
                grain="transposition_route",
                cohort=cohort,
                period=period,
                period_start=start,
                period_end=end,
                opening_family=family,
                opening_line=san,
                fen=fen,
                eco=eco,
                games=_num(route["games"]),
                share=float(route["share"]),
                ply=len(san.split()),
            )
        )
    return rows


def _dominant_eco(labels: object) -> str | None:
    if not isinstance(labels, list) or not labels:
        return None
    best = max(labels, key=lambda item: _num(item["games"]))
    eco = best.get("eco")
    return str(eco) if eco else None


def _august_day(analytical: Mapping[str, object]) -> date:
    coverage = analytical.get("observed_date_coverage")
    if isinstance(coverage, Mapping) and coverage.get("first_utc_date"):
        return _parse_date(coverage["first_utc_date"])
    return AUGUST_DAY


def _dimensional(filters: Filters) -> bool:
    return any((filters.time_control, filters.color, filters.rating_band, filters.opening_family))


def _set_labels(filters: Filters, *, skip_opening: bool = False) -> list[str]:
    labels: list[str] = []
    if filters.color:
        labels.append("color")
    if filters.time_control:
        labels.append("time")
    if filters.rating_band:
        labels.append("rating")
    if filters.opening_family and not skip_opening:
        labels.append("opening")
    return labels


def _period_note(filters: Filters) -> str:
    return _with_note("published periods", _set_labels(filters))


def _join_or(items: Sequence[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    if len(items) == 2:
        return f"{items[0]} or {items[1]}"
    return ", ".join(items[:-1]) + ", or " + items[-1]


def _with_note(base: str, ignored: Sequence[str]) -> str:
    if not ignored:
        return base
    return base + " · not by " + ", ".join(ignored)


def _score_cards(
    scores: Sequence[Mapping[str, object]], notes: Sequence[str]
) -> tuple[Kpi, Kpi, Kpi]:
    if not scores:
        empty = _NO_CELLS if _EMPTY_CUT in notes else "no scored cells"
        return (
            Kpi("Win rate", "0.0%", empty),
            Kpi("Loss rate", "0.0%", empty),
            Kpi("Draw rate", "0.0%", empty),
        )
    wins, draws, losses, games = _tally(scores)
    return (
        Kpi("Win rate", _percent(wins / games), _score_detail(wins, games, notes)),
        Kpi("Loss rate", _percent(losses / games), _score_detail(losses, games, notes)),
        Kpi("Draw rate", _percent(draws / games), _score_detail(draws, games, notes)),
    )


def _score_detail(count: int, games: int, notes: Sequence[str]) -> str:
    population = [item for item in notes if item == "White"]
    ignored = [item for item in notes if item != "White"]
    detail = f"{count:,} / {games:,}"
    if population:
        detail += " · White"
    if ignored:
        detail += " · not by " + ", ".join(ignored)
    return detail


def _grain_present(connection, grain: str) -> bool:
    row = connection.execute(
        'select count(*) from "cube" where "grain" = ?',
        [grain],
    ).fetchone()
    return row is not None and _num(row[0]) > 0


def _carries(connection, grain: str, column: str) -> bool:
    if column not in _DIM_LABEL:
        raise ValueError("unknown cube dimension")
    row = connection.execute(
        f'select count(*) from "cube" where "grain" = ? and "{column}" is not null',
        [grain],
    ).fetchone()
    return row is not None and _num(row[0]) > 0


def _unapplied(connection, grain: str, filters: Filters) -> list[str]:
    labels: list[str] = []
    for column, value in (
        ("color", filters.color),
        ("opening_family", filters.opening_family),
        ("time_control", filters.time_control),
        ("rating_band", filters.rating_band),
    ):
        if value and not _carries(connection, grain, column):
            labels.append(_DIM_LABEL[column])
    return labels


def _collect(
    connection,
    grain: str,
    filters: Filters,
    *,
    force_color: str | None = None,
) -> tuple[list[dict[str, object]], list[str]]:
    """Finest rows for ``grain``, then the filters that had to be dropped."""
    notes: list[str] = []
    color = force_color if force_color is not None else filters.color
    if force_color is not None and filters.color is None:
        notes.append("White")
    active = Filters(
        filters.start,
        filters.end,
        filters.time_control,
        color,
        filters.rating_band,
        filters.opening_family,
    )
    notes.extend(_unapplied(connection, grain, active))

    def pull(candidate: Filters, *, dates: bool) -> list[dict[str, object]]:
        return _inside(connection, grain, candidate, dimensional=True, adaptive=True, dates=dates)

    found = pull(active, dates=True)
    if found:
        return found, _unique(notes)
    undated = pull(active, dates=False)
    if undated:
        notes.append("date")
        return undated, _unique(notes)
    if _requested_carried(connection, grain, active):
        notes.append(_EMPTY_CUT)
    return [], _unique(notes)


def _requested_carried(connection, grain: str, filters: Filters) -> bool:
    """True when a filter is set on a column this grain actually stores."""
    for column, value in (
        ("time_control", filters.time_control),
        ("color", filters.color),
        ("rating_band", filters.rating_band),
        ("opening_family", filters.opening_family),
    ):
        if value and _carries(connection, grain, column):
            return True
    return False


def _unique(items: Sequence[str]) -> list[str]:
    seen: list[str] = []
    for item in items:
        if item not in seen:
            seen.append(item)
    return seen


def _clock_source_rows(
    connection, filters: Filters
) -> tuple[list[dict[str, object]], bool, list[str]]:
    """Clock rows, whether the date window was widened, and filters that matched nothing.

    A time control or rating the grain does not contain returns no slices. The
    same is true when the selected range already contains the slice dates and
    the cut is empty. Widening the dates, and tagging that as August, happens
    only when the range does not contain those dates and the time and rating
    values are present. The unfiltered August population is not a stand-in.
    """
    grain = "clock_cell" if _grain_present(connection, "clock_cell") else "clock_slice"
    if not _grain_present(connection, grain):
        return [], False, []
    absent = _absent_clock_filters(connection, grain, filters)
    if absent:
        return [], False, absent
    rows = _inside(connection, grain, filters, dimensional=True, adaptive=True)
    if rows:
        return rows, False, []
    span = _grain_span(connection, grain)
    named = _set_clock_labels(connection, grain, filters)
    if span is not None and filters.start <= span[0] and filters.end >= span[1]:
        return [], False, named
    wider = _inside(
        connection,
        grain,
        Filters(_WIDE[0], _WIDE[1], filters.time_control, None, filters.rating_band, None),
        dimensional=True,
        adaptive=True,
        dates=False,
    )
    if wider:
        return wider, True, []
    return [], False, named


def _absent_clock_filters(connection, grain: str, filters: Filters) -> list[str]:
    absent: list[str] = []
    for column in ("time_control", "rating_band"):
        value = getattr(filters, column)
        if (
            value
            and _carries(connection, grain, column)
            and not _value_present(connection, grain, column, value)
        ):
            absent.append(_DIM_LABEL[column])
    return absent


def _set_clock_labels(connection, grain: str, filters: Filters) -> list[str]:
    labels: list[str] = []
    for column in ("time_control", "rating_band"):
        value = getattr(filters, column)
        if value and _carries(connection, grain, column):
            labels.append(_DIM_LABEL[column])
    return labels


def _value_present(connection, grain: str, column: str, value: str) -> bool:
    if column not in _DIM_LABEL:
        raise ValueError("unknown cube dimension")
    if column == "rating_band":
        subset = RATING_SUBSET.get(value)
        if subset is None:
            sql = 'select count(*) from "cube" where "grain" = ? and "rating_band" = ?'
            params: list[object] = [grain, value]
        else:
            sql = (
                'select count(*) from "cube" where "grain" = ? '
                'and ("rating_band" = ? or "rating_band" = ?)'
            )
            params = [grain, value, subset]
    else:
        sql = f'select count(*) from "cube" where "grain" = ? and "{column}" = ?'
        params = [grain, value]
    row = connection.execute(sql, params).fetchone()
    return row is not None and _num(row[0]) > 0


def _grain_span(connection, grain: str) -> tuple[date, date] | None:
    row = connection.execute(
        'select min("period_start"), max("period_end") from "cube" where "grain" = ?',
        [grain],
    ).fetchone()
    if row is None or row[0] is None or row[1] is None:
        return None
    return row[0], row[1]


def _band_rows(rows: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    grouped: dict[str, list[int]] = {}
    for row in rows:
        slot = grouped.setdefault(str(row["clock_band"]), [0, 0, 0])
        slot[0] += _num(row["moves"] or 0)
        slot[1] += _num(row["evaluable_moves"] or 0)
        slot[2] += _num(row["proxy_errors"] or 0)
    bands = []
    for band in CLOCK_BANDS:
        if band not in grouped:
            continue
        moves, evaluable, errors = grouped[band]
        bands.append(
            {
                "label": band,
                "games": evaluable,
                "moves": moves,
                "evaluable_moves": evaluable,
                "proxy_errors": errors,
                "error_proxy_rate": None if evaluable == 0 else errors / evaluable,
            }
        )
    return bands


def _clock_caption(
    parts: Sequence[str], fell_back: bool, has_rows: bool, *, warehouse: bool = False
) -> str | None:
    if not has_rows:
        named = [item for item in parts if item != "date"]
        if named:
            return "No clock slices for this " + _join_or(named) + "."
        if not parts and not fell_back:
            return None
        return "No clock slices are published for this cut."
    if not parts and not fell_back:
        return None
    ignored = [item for item in parts if item != "date"]
    window = "the warehouse window" if warehouse else "the August prefix"
    if fell_back and ignored:
        return "Clock pressure is " + window + " and is not split by " + _join_or(ignored) + "."
    if fell_back:
        return "These slices are " + window + "."
    if ignored:
        return "Clock pressure is not split by " + _join_or(ignored) + "."
    return None


def _apply_carried(
    connection,
    grain: str,
    filters: Filters,
    clauses: list[str],
    params: list[object],
    notes: list[str],
) -> None:
    for column, value, label in (
        ("color", filters.color, "color"),
        ("time_control", filters.time_control, "time control"),
        ("rating_band", filters.rating_band, "rating"),
    ):
        if not value:
            continue
        if not _carries(connection, grain, column):
            notes.append(label)
            continue
        if column == "rating_band":
            _append_rating(clauses, params, value)
        else:
            _append_dimension(clauses, params, f'"{column}"', value)


def _transposition_caption(notes: Sequence[str]) -> str:
    if not notes:
        return "Distinct acyclic move orders. Routes under 10 games are omitted."
    ignored = [item for item in notes if item != "date"]
    if "date" in notes and ignored:
        return (
            "Move orders use the full published window. They are not split by "
            + _join_or(ignored)
            + "."
        )
    if "date" in notes:
        return "Move orders use the full published window, which is wider than this date range."
    return "Move orders are not split by " + _join_or(ignored) + "."


def _position_title(ply: int, san: str) -> str:
    """Name a board the way the transpositions page names a row.

    The explorer's row button is ``After Black's move N``, from the leading
    arrival. The same page prints that arrival's SAN as the line. Every card
    uses both, in that order.
    """
    whole, remainder = divmod(ply, 2)
    depth = str(whole) if remainder == 0 else f"{ply / 2:g}"
    line = san.strip()
    if not line:
        return f"After Black's move {depth}"
    return f"After Black's move {depth} · {line}"


def _pack_transposition(connection, cohort: str, row: Mapping[str, object]) -> dict[str, object]:
    fen = str(row["fen"])
    family = str(row["opening_family"])
    routes = connection.execute(
        'select "opening_line", "games", "ply" from "cube" '
        'where "grain" = ? and "cohort" = ? and "fen" = ? and "opening_family" = ? '
        'order by "games" desc',
        ["transposition_route", cohort, fen, family],
    ).fetchall()
    top = [(str(san), _num(games)) for san, games, _ply in routes[:3]]
    title = _position_title(_num(routes[0][2]), str(routes[0][0])) if routes else "Inspect board"
    return {
        "fen": fen,
        "family": family,
        "title": title,
        "games": _num(row["games"]),
        "kept_games": sum(_num(games) for _san, games, _ply in routes),
        "move_orders": _num(row["ply"]),
        "routes": top,
        "eco": row.get("eco"),
    }


def _as_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _month_index(period: str) -> int | None:
    """YYYY-MM as a month count. Other period labels are not a series."""
    if len(period) != 7 or period[4] != "-":
        return None
    year, month = period[:4], period[5:]
    if not (year.isdigit() and month.isdigit()):
        return None
    month_number = int(month)
    if not 1 <= month_number <= 12:
        return None
    return int(year) * 12 + month_number


def _contiguous_months(periods: Sequence[str]) -> bool:
    indexes: list[int] = []
    for period in sorted(periods):
        index = _month_index(period)
        if index is None:
            return False
        indexes.append(index)
    if not indexes:
        return False
    return all(indexes[index] + 1 == indexes[index + 1] for index in range(len(indexes) - 1))


def _period_signature(rows: Sequence[Mapping[str, object]], period: str) -> tuple[str, int] | None:
    """Cohort and span, when every row of ``period`` agrees. None when it does not."""
    matched = [row for row in rows if str(row["period"]) == period]
    if not matched:
        return None
    cohorts = {str(row["cohort"]) for row in matched}
    spans: set[int] = set()
    for row in matched:
        start = _as_date(row["period_start"])
        end = _as_date(row["period_end"])
        if start is None or end is None:
            return None
        spans.add((end - start).days)
    if len(cohorts) != 1 or len(spans) != 1:
        return None
    return cohorts.pop(), spans.pop()


def _prior_period_rows(
    connection,
    grain: str,
    filters: Filters,
    current: Sequence[Mapping[str, object]],
    notes: Sequence[str],
    *,
    force_color: str | None = None,
) -> list[dict[str, object]] | None:
    """Previous equal block of periods, or None when that comparison would mislead.

    The date range has already chosen the periods that sit fully inside it.
    The prior block is that many periods immediately before, with the same
    time, color, rating, and opening filters. Both blocks have to be
    contiguous months, the prior block has to end the month before the
    current block, and every period has to share one cohort and one span.
    A missing block, a gap, or a different kind of period returns None.
    A card that ignored the date range is not compared.
    """
    if not current or _EMPTY_CUT in notes or "date" in notes:
        return None
    selected = sorted({str(row["period"]) for row in current if row.get("period") is not None})
    if not selected:
        return None
    color = force_color if force_color is not None else filters.color
    active = Filters(
        filters.start,
        filters.end,
        filters.time_control,
        color,
        filters.rating_band,
        filters.opening_family,
    )
    catalog = _inside(connection, grain, active, dimensional=True, adaptive=True, dates=False)
    ordered = sorted({str(row["period"]) for row in catalog if row.get("period") is not None})
    if any(period not in ordered for period in selected):
        return None
    prior = previous_periods(ordered, selected)
    if prior is None or not _contiguous_months(selected) or not _contiguous_months(prior):
        return None
    last = _month_index(max(prior))
    first = _month_index(min(selected))
    if last is None or first is None or last + 1 != first:
        return None
    current_signature = {_period_signature(catalog, period) for period in selected}
    prior_signature = {_period_signature(catalog, period) for period in prior}
    if len(current_signature) != 1 or current_signature != prior_signature:
        return None
    if None in current_signature:
        return None
    chosen = set(prior)
    found = [row for row in catalog if str(row["period"]) in chosen]
    if not found or sum(_num(row["games"]) for row in found) <= 0:
        return None
    return found


def _signed_text(value: object) -> str:
    text = format(value, "f")
    if text.startswith("-"):
        return text
    return f"+{text}"


def _with_count_delta(
    detail: str, current: int, prior_rows: Sequence[Mapping[str, object]] | None
) -> str:
    if not prior_rows:
        return detail
    prior = sum(_num(row["games"]) for row in prior_rows)
    if prior <= 0:
        return detail
    return f"{detail} · {current - prior:+,} vs prior"


def _with_pp_delta(
    detail: str,
    current_count: int,
    current_games: int,
    prior_count: int,
    prior_games: int,
) -> str:
    from decimal import Decimal

    if current_games <= 0 or prior_games <= 0:
        return detail
    current_points = Decimal(_percent(current_count / current_games).removesuffix("%"))
    prior_points = Decimal(_percent(prior_count / prior_games).removesuffix("%"))
    return f"{detail} · {_signed_text(current_points - prior_points)} pp vs prior"


def _with_mean_delta(detail: str, current: float, prior: float | None) -> str:
    from decimal import Decimal

    if prior is None:
        return detail
    delta = Decimal(_tenth(current)) - Decimal(_tenth(prior))
    return f"{detail} · {_signed_text(delta)} vs prior"


def _warehouse_games_kpi(connection, filters: Filters) -> Kpi:
    """Count each game once. A rating filter with no color uses the White cells."""
    player = bool(filters.color or filters.rating_band)
    if player and _grain_present(connection, "result_cell"):
        grain, force = "result_cell", filters.color or "white"
    elif _grain_present(connection, "game_cell"):
        grain, force = "game_cell", None
    else:
        grain, force = "result_cell", filters.color or "white"
    rows, notes = _collect(connection, grain, filters, force_color=force)
    if _EMPTY_CUT in notes:
        return Kpi("Games", "0", _NO_CELLS)
    total = sum(_num(row["games"]) for row in rows)
    if not notes and not _dimensional(filters):
        detail = "warehouse"
    else:
        detail = "warehouse"
        if "White" in notes:
            detail += " · White"
        ignored = [item for item in notes if item != "White"]
        if ignored:
            detail = _with_note(detail, ignored)
    prior = _prior_period_rows(connection, grain, filters, rows, notes, force_color=force)
    return Kpi("Games", f"{total:,}", _with_count_delta(detail, total, prior))


def _warehouse_result_kpis(connection, filters: Filters) -> tuple[Kpi, Kpi, Kpi]:
    force = filters.color or "white"
    rows, notes = _collect(connection, "result_cell", filters, force_color=force)
    win, loss, draw = _score_cards(rows, notes)
    prior = _prior_period_rows(connection, "result_cell", filters, rows, notes, force_color=force)
    if prior is None or not rows:
        return win, loss, draw
    current_wins, current_draws, current_losses, current_games = _tally(rows)
    prior_wins, prior_draws, prior_losses, prior_games = _tally(prior)
    if current_games <= 0 or prior_games <= 0:
        return win, loss, draw
    return (
        Kpi(
            win.label,
            win.value,
            _with_pp_delta(win.detail, current_wins, current_games, prior_wins, prior_games),
        ),
        Kpi(
            loss.label,
            loss.value,
            _with_pp_delta(loss.detail, current_losses, current_games, prior_losses, prior_games),
        ),
        Kpi(
            draw.label,
            draw.value,
            _with_pp_delta(draw.detail, current_draws, current_games, prior_draws, prior_games),
        ),
    )


def _mean_kpis(connection, filters: Filters) -> list[Kpi]:
    cards: list[Kpi] = []
    if _grain_present(connection, "result_cell"):
        rows, notes = _collect(
            connection, "result_cell", filters, force_color=filters.color or "white"
        )
        if _EMPTY_CUT in notes:
            cards.append(Kpi("Rating diff", "0.0", _NO_CELLS))
            if filters.color or filters.rating_band or not _grain_present(connection, "game_cell"):
                cards.append(Kpi("Game length", "0.0", _NO_CELLS))
        else:
            prior = _prior_period_rows(
                connection,
                "result_cell",
                filters,
                rows,
                notes,
                force_color=filters.color or "white",
            )
            diff = _weighted_mean(rows, "rating_diff")
            if diff is not None:
                prior_diff = None if prior is None else _weighted_mean(prior, "rating_diff")
                cards.append(
                    Kpi(
                        "Rating diff",
                        _signed(diff),
                        _with_mean_delta(_mean_detail(notes), diff, prior_diff),
                    )
                )
            length = _weighted_mean(rows, "mean_ply")
            use_player_length = bool(filters.color or filters.rating_band)
            if not _grain_present(connection, "game_cell"):
                use_player_length = True
            if length is not None and use_player_length:
                prior_length = None if prior is None else _weighted_mean(prior, "mean_ply")
                cards.append(
                    Kpi(
                        "Game length",
                        _tenth(length),
                        _with_mean_delta(_mean_detail(notes, "mean ply"), length, prior_length),
                    )
                )
    if _grain_present(connection, "game_cell") and not any(
        card.label == "Game length" for card in cards
    ):
        rows, notes = _collect(connection, "game_cell", filters)
        if _EMPTY_CUT in notes:
            cards.append(Kpi("Game length", "0.0", _NO_CELLS))
        else:
            length = _weighted_mean(rows, "mean_ply")
            if length is not None:
                prior = _prior_period_rows(connection, "game_cell", filters, rows, notes)
                prior_length = None if prior is None else _weighted_mean(prior, "mean_ply")
                cards.append(
                    Kpi(
                        "Game length",
                        _tenth(length),
                        _with_mean_delta(_mean_detail(notes, "mean ply"), length, prior_length),
                    )
                )
    return cards


def _mean_detail(notes: Sequence[str], suffix: str = "mean") -> str:
    ignored = [item for item in notes if item != "White"]
    population = "White" if "White" in notes else ""
    parts = [part for part in (population, suffix) if part]
    detail = " · ".join(parts) if parts else suffix
    if ignored:
        detail += " · not by " + ", ".join(ignored)
    return detail


def _weighted_mean(rows: Sequence[Mapping[str, object]], field: str) -> float | None:
    total = 0
    acc = 0.0
    for row in rows:
        games = _num(row["games"] or 0)
        value = row.get(field)
        if isinstance(value, bool) or not isinstance(value, int | float | str) or games == 0:
            continue
        acc += float(value) * games
        total += games
    if total == 0:
        return None
    return acc / total


def _num(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        raise TypeError("dashboard cube count is not a number")
    return int(value)


def _records(result) -> list[dict[str, object]]:
    names = [item[0] for item in result.description]
    return [dict(zip(names, row, strict=True)) for row in result.fetchall()]


def _row(**values: object) -> dict[str, object]:
    blank: dict[str, object] = {}
    for column in COLUMNS:
        blank[column] = None
    blank.update(values)
    return blank


def _tuple(row: Mapping[str, object]) -> tuple[object, ...]:
    return tuple(row[column] for column in COLUMNS)


def _sort_key(row: Mapping[str, object]) -> tuple[str, ...]:
    return tuple("" if row[column] is None else str(row[column]) for column in COLUMNS)


def _as_list(value: object) -> list:
    if not isinstance(value, list):
        raise ValueError("dashboard cube source list is missing")
    return value


def _parse_date(value: object) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _span_label(start: date, end: date) -> str:
    if start == end:
        return start.isoformat()
    return f"{start.isoformat()}/{end.isoformat()}"


def _or_all(value: str | None) -> str:
    return "All" if value is None else value


def _percent(value: float) -> str:
    from decimal import ROUND_HALF_UP, Decimal

    shown = (Decimal(repr(value)) * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return f"{shown}%"


def _tenth(value: float) -> str:
    from decimal import ROUND_HALF_UP, Decimal

    shown = Decimal(repr(value)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return f"{shown}"


def _signed(value: float) -> str:
    text = _tenth(value)
    if text.startswith("-"):
        return text
    return f"+{text}"


def _cube_candidates() -> Iterable[Path]:
    yield Path.cwd() / "data" / "public" / CUBE_FILENAME
    for directory in (Path.cwd(), *Path.cwd().parents):
        project = directory / "pyproject.toml"
        package = directory / "src" / "chess_analytics"
        if project.is_file() and package.is_dir():
            yield directory / "data" / "public" / CUBE_FILENAME
            break


_GAME_CELL_SQL = """
select
  printf(
    '%04d-%02d',
    extract(year from date_trunc('month', "utc_date")),
    extract(month from date_trunc('month', "utc_date"))
  ) as "period",
  cast(date_trunc('month', "utc_date") as date) as "period_start",
  cast(
    date_trunc('month', "utc_date") + interval '1 month' - interval '1 day' as date
  ) as "period_end",
  "time_control",
  nullif(trim(split_part(coalesce("source_opening", ''), ':', 1)), '') as "opening_family",
  count(*) as "games",
  avg("ply_count") as "mean_ply"
from "fact_game"
where "result" in ('1-0', '0-1', '1/2-1/2')
  and "marked_bot" = false
  and lower("variant") = 'standard'
group by 1, 2, 3, 4, 5
having count(*) >= 10
""".strip()
_RESULT_CELL_SQL = """
select
  printf(
    '%04d-%02d',
    extract(year from date_trunc('month', g."utc_date")),
    extract(month from date_trunc('month', g."utc_date"))
  ) as "period",
  cast(date_trunc('month', g."utc_date") as date) as "period_start",
  cast(
    date_trunc('month', g."utc_date") + interval '1 month' - interval '1 day' as date
  ) as "period_end",
  g."time_control",
  p."color",
  case
    when p."rating" < 1200 then 'under_1200'
    when p."rating" < 1600 then '1200_1599'
    when p."rating" < 2000 then '1600_1999'
    else '2000_plus'
  end as "rating_band",
  nullif(trim(split_part(coalesce(g."source_opening", ''), ':', 1)), '') as "opening_family",
  count(*) as "games",
  count(*) filter (where p."score" = 1) as "wins",
  count(*) filter (where p."score" = 0.5) as "draws",
  count(*) filter (where p."score" = 0) as "losses",
  avg(p."rating" - p."opponent_rating") as "rating_diff",
  avg(g."ply_count") as "mean_ply"
from "fact_player_game" as p
join "fact_game" as g using ("provider", "game_id")
where g."result" in ('1-0', '0-1', '1/2-1/2')
  and g."marked_bot" = false
  and p."rating" is not null
  and p."opponent_rating" is not null
group by 1, 2, 3, 4, 5, 6, 7
having count(*) >= 10
""".strip()
_RESULT_LINE_SQL = """
select
  printf(
    '%04d-%02d',
    extract(year from date_trunc('month', g."utc_date")),
    extract(month from date_trunc('month', g."utc_date"))
  ) as "period",
  cast(date_trunc('month', g."utc_date") as date) as "period_start",
  cast(
    date_trunc('month', g."utc_date") + interval '1 month' - interval '1 day' as date
  ) as "period_end",
  g."time_control",
  p."color",
  case
    when p."rating" < 1200 then 'under_1200'
    when p."rating" < 1600 then '1200_1599'
    when p."rating" < 2000 then '1600_1999'
    else '2000_plus'
  end as "rating_band",
  nullif(trim(split_part(coalesce(g."source_opening", ''), ':', 1)), '') as "opening_family",
  nullif(trim(g."source_opening"), '') as "opening_line",
  count(*) as "games",
  count(*) filter (where p."score" = 1) as "wins",
  count(*) filter (where p."score" = 0.5) as "draws",
  count(*) filter (where p."score" = 0) as "losses",
  avg(p."rating" - p."opponent_rating") as "rating_diff",
  avg(g."ply_count") as "mean_ply"
from "fact_player_game" as p
join "fact_game" as g using ("provider", "game_id")
where g."result" in ('1-0', '0-1', '1/2-1/2')
  and g."marked_bot" = false
  and p."rating" is not null
  and p."opponent_rating" is not null
  and nullif(trim(g."source_opening"), '') is not null
group by 1, 2, 3, 4, 5, 6, 7, 8
having count(*) >= 10
""".strip()
_CLOCK_CELL_SQL = """
select
  m."clock_bucket" as "clock_band",
  g."time_control",
  m."phase_proxy" as "phase",
  case
    when p."rating" < 1200 then 'under_1200'
    when p."rating" < 1600 then '1200_1599'
    when p."rating" < 2000 then '1600_1999'
    else '2000_plus'
  end as "rating_band",
  p."color",
  nullif(trim(split_part(coalesce(g."source_opening", ''), ':', 1)), '') as "opening_family",
  min(g."utc_date") as "period_start",
  max(g."utc_date") as "period_end",
  count(*) as "moves",
  count(*) filter (where m."centipawn_deterioration" is not null) as "evaluable_moves",
  count(*) filter (where m."error_proxy") as "proxy_errors",
  count(distinct m."game_id") as "games"
from "fact_move" as m
join "fact_game" as g using ("provider", "game_id")
join "fact_player_game" as p
  on p."provider" = m."provider" and p."game_id" = m."game_id" and p."color" = m."color"
where m."clock_bucket" is not null
  and g."increment_seconds" = 0
  and g."result" in ('1-0', '0-1', '1/2-1/2')
  and g."marked_bot" = false
  and p."rating" is not null
group by 1, 2, 3, 4, 5, 6
having count(distinct m."game_id") >= 10
""".strip()
_OPENING_GAME_CELL_SQL = """
with "bounds" as (
  select
    "source_cohort",
    "source_period",
    min("utc_date") as "period_start",
    max("utc_date") as "period_end"
  from "opening_game"
  where "result" in ('1-0', '0-1', '1/2-1/2')
    and "marked_bot" = false
  group by 1, 2
)
select
  g."source_period" as "period",
  g."source_cohort" as "cohort",
  b."period_start",
  b."period_end",
  g."time_control",
  nullif(trim(split_part(coalesce(g."source_opening", ''), ':', 1)), '') as "opening_family",
  count(*) as "games",
  avg(g."ply_count") as "mean_ply"
from "opening_game" as g
join "bounds" as b
  on b."source_cohort" = g."source_cohort"
 and b."source_period" = g."source_period"
where g."result" in ('1-0', '0-1', '1/2-1/2')
  and g."marked_bot" = false
group by 1, 2, 3, 4, 5, 6
having count(*) >= 10
""".strip()
_OPENING_RESULT_CELL_SQL = """
with "bounds" as (
  select
    "source_cohort",
    "source_period",
    min("utc_date") as "period_start",
    max("utc_date") as "period_end"
  from "opening_game"
  where "result" in ('1-0', '0-1', '1/2-1/2')
    and "marked_bot" = false
  group by 1, 2
),
"played" as (
  select
    "source_period" as "period",
    "source_cohort" as "cohort",
    "time_control",
    'white' as "color",
    "white_rating" as "rating",
    "black_rating" as "opponent_rating",
    case
      when "result" = '1-0' then 1.0
      when "result" = '1/2-1/2' then 0.5
      else 0.0
    end as "score",
    "ply_count",
    "source_opening"
  from "opening_game"
  where "result" in ('1-0', '0-1', '1/2-1/2')
    and "marked_bot" = false
    and "white_rating" is not null
    and "black_rating" is not null
  union all
  select
    "source_period",
    "source_cohort",
    "time_control",
    'black',
    "black_rating",
    "white_rating",
    case
      when "result" = '0-1' then 1.0
      when "result" = '1/2-1/2' then 0.5
      else 0.0
    end,
    "ply_count",
    "source_opening"
  from "opening_game"
  where "result" in ('1-0', '0-1', '1/2-1/2')
    and "marked_bot" = false
    and "white_rating" is not null
    and "black_rating" is not null
)
select
  played."period",
  played."cohort",
  bounds."period_start",
  bounds."period_end",
  played."time_control",
  played."color",
  case
    when played."rating" < 1200 then 'under_1200'
    when played."rating" < 1600 then '1200_1599'
    when played."rating" < 2000 then '1600_1999'
    else '2000_plus'
  end as "rating_band",
  nullif(trim(split_part(coalesce(played."source_opening", ''), ':', 1)), '')
    as "opening_family",
  count(*) as "games",
  count(*) filter (where played."score" = 1.0) as "wins",
  count(*) filter (where played."score" = 0.5) as "draws",
  count(*) filter (where played."score" = 0.0) as "losses",
  avg(played."rating" - played."opponent_rating") as "rating_diff",
  avg(played."ply_count") as "mean_ply"
from "played"
join "bounds"
  on bounds."source_cohort" = played."cohort"
 and bounds."source_period" = played."period"
group by 1, 2, 3, 4, 5, 6, 7, 8
having count(*) >= 10
""".strip()


def warehouse_source(connection) -> str:
    """``fact_game`` when the analytical tables exist, else ``opening_game``."""
    tables = _table_names(connection)
    if "fact_game" in tables and "fact_player_game" in tables:
        return "fact_game"
    if "opening_game" in tables:
        return "opening_game"
    return ""


def warehouse_rows(connection) -> list[dict[str, object]]:
    """Aggregate a local warehouse. Cells under 10 games are dropped.

    ``fact_game`` plus ``fact_player_game`` is the analytical warehouse.
    ``fact_move`` adds clock cells when it is present. ``opening_game`` is
    the training selection; ``retained_game`` is not read, and that warehouse
    has no move table so it does not emit clock cells. Opening family is the
    text before the first colon, the same split as ``opening_family_expr``.
    Cohort and period are ``source_cohort`` and ``source_period``, and the
    row window is the min and max ``utc_date`` of that source, matching
    ``corpus_month``. Identifiers stay in the warehouse.
    """
    source = warehouse_source(connection)
    if source == "fact_game":
        rows = _fact_warehouse_rows(connection)
    elif source == "opening_game":
        rows = _opening_warehouse_rows(connection)
    else:
        raise ValueError("warehouse is missing fact_game or opening_game")
    issues = public_issues(rows)
    if issues:
        raise ValueError(f"warehouse cube failed the public check: {issues[0]}")
    return rows


def locate_warehouse(explicit: Path | None = None, root: Path | None = None) -> Path | None:
    """Find ``warehouse.duckdb``. Missing files return None. No download."""
    if explicit is not None:
        candidate = Path(explicit)
        return candidate if candidate.is_file() else None
    override = os.environ.get("CHESSLAB_WAREHOUSE")
    if override and Path(override).is_file():
        return Path(override)
    base = Path(root) if root is not None else Path.cwd()
    named = (
        base / "data" / "warehouse.duckdb",
        base / "warehouse.duckdb",
    )
    for path in named:
        if path.is_file():
            return path
    published = sorted((base / "data" / "published").glob("*/warehouse.duckdb"))
    if published:
        return published[-1]
    openings = sorted((base / "data" / "openings" / "published").glob("*/warehouse.duckdb"))
    if openings:
        return openings[-1]
    return None


def _table_names(connection) -> set[str]:
    found = connection.execute(
        "select table_name from information_schema.tables where table_schema = 'main'"
    ).fetchall()
    return {str(item[0]) for item in found}


def _clock_columns_ready(connection) -> bool:
    found = connection.execute(
        "select column_name from information_schema.columns where table_name = 'fact_move'"
    ).fetchall()
    columns = {str(item[0]) for item in found}
    required = {
        "clock_bucket",
        "phase_proxy",
        "provider",
        "game_id",
        "color",
        "centipawn_deterioration",
        "error_proxy",
    }
    return required <= columns


def _fact_warehouse_rows(connection) -> list[dict[str, object]]:
    tables = _table_names(connection)
    rows: list[dict[str, object]] = []
    rows.extend(_game_cells(connection))
    rows.extend(_result_cells(connection, "result_cell", _RESULT_CELL_SQL, line=False))
    rows.extend(_result_cells(connection, "result_line", _RESULT_LINE_SQL, line=True))
    if "fact_move" in tables and _clock_columns_ready(connection):
        rows.extend(_clock_cells(connection))
    return rows


def _opening_warehouse_rows(connection) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    rows.extend(_opening_game_cells(connection))
    rows.extend(_opening_result_cells(connection))
    return rows


def _game_cells(connection) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for period, start, end, control, family, games, mean_ply in connection.execute(
        _GAME_CELL_SQL
    ).fetchall():
        rows.append(
            _row(
                grain="game_cell",
                cohort="warehouse",
                period=str(period),
                period_start=start,
                period_end=end,
                time_control=None if control is None else str(control),
                opening_family=None if family is None else str(family),
                games=_num(games),
                mean_ply=None if mean_ply is None else float(mean_ply),
            )
        )
    return rows


def _opening_game_cells(connection) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    found = connection.execute(_OPENING_GAME_CELL_SQL).fetchall()
    for period, cohort, start, end, control, family, games, mean_ply in found:
        rows.append(
            _row(
                grain="game_cell",
                cohort=str(cohort),
                period=str(period),
                period_start=_parse_date(start),
                period_end=_parse_date(end),
                time_control=None if control is None else str(control),
                opening_family=None if family is None else str(family),
                games=_num(games),
                mean_ply=None if mean_ply is None else float(mean_ply),
            )
        )
    return rows


def _opening_result_cells(connection) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for record in connection.execute(_OPENING_RESULT_CELL_SQL).fetchall():
        period, cohort, start, end, control, color, rating, family = record[:8]
        games, wins, draws, losses, rating_diff, mean_ply = record[8:]
        rows.append(
            _row(
                grain="result_cell",
                cohort=str(cohort),
                period=str(period),
                period_start=_parse_date(start),
                period_end=_parse_date(end),
                time_control=None if control is None else str(control),
                color=None if color is None else str(color),
                rating_band=None if rating is None else str(rating),
                opening_family=None if family is None else str(family),
                games=_num(games),
                wins=_num(wins),
                draws=_num(draws),
                losses=_num(losses),
                rating_diff=None if rating_diff is None else float(rating_diff),
                mean_ply=None if mean_ply is None else float(mean_ply),
            )
        )
    return rows


def _result_cells(connection, grain: str, sql: str, *, line: bool) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for record in connection.execute(sql).fetchall():
        period, start, end, control, color, rating, family = record[:7]
        if line:
            opening_line = record[7]
            games, wins, draws, losses, rating_diff, mean_ply = record[8:]
        else:
            opening_line = None
            games, wins, draws, losses, rating_diff, mean_ply = record[7:]
        rows.append(
            _row(
                grain=grain,
                cohort="warehouse",
                period=str(period),
                period_start=start,
                period_end=end,
                time_control=None if control is None else str(control),
                color=None if color is None else str(color),
                rating_band=None if rating is None else str(rating),
                opening_family=None if family is None else str(family),
                opening_line=None if opening_line is None else str(opening_line),
                games=_num(games),
                wins=_num(wins),
                draws=_num(draws),
                losses=_num(losses),
                rating_diff=None if rating_diff is None else float(rating_diff),
                mean_ply=None if mean_ply is None else float(mean_ply),
            )
        )
    return rows


def _clock_cells(connection) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for record in connection.execute(_CLOCK_CELL_SQL).fetchall():
        band, control, phase, rating, color, family, start, end = record[:8]
        moves, evaluable, errors, games = record[8:]
        rate = None if _num(evaluable) == 0 else _num(errors) / _num(evaluable)
        rows.append(
            _row(
                grain="clock_cell",
                cohort="warehouse",
                period=_span_label(start, end),
                period_start=start,
                period_end=end,
                time_control=None if control is None else str(control),
                color=None if color is None else str(color),
                rating_band=None if rating is None else str(rating),
                opening_family=None if family is None else str(family),
                clock_band=str(band),
                phase=None if phase is None else str(phase),
                moves=_num(moves),
                evaluable_moves=_num(evaluable),
                proxy_errors=_num(errors),
                error_proxy_rate=rate,
                games=_num(games),
            )
        )
    return rows


def shift_back(start: date, end: date) -> tuple[date, date]:
    """Previous window of the same number of days. Used by period tests."""
    width = (end - start).days + 1
    previous_end = start - timedelta(days=1)
    return previous_end - timedelta(days=width - 1), previous_end
