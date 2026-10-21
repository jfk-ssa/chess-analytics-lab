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
from datetime import date, timedelta
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
  "ply"
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
  "ply" integer
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
            rows.append(
                _row(
                    grain="opening_family",
                    cohort=str(cohort),
                    period=period,
                    period_start=start,
                    period_end=end,
                    opening_family=str(family["family"]),
                    games=_num(family["games"]),
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
    total = sum(_num(value) for value in families.values())
    if total <= 0:
        raise ValueError("august opening families do not sum")
    return [
        _row(
            grain="august_family",
            cohort="m3_august_prefix",
            period=august.isoformat(),
            period_start=august,
            period_end=august,
            opening_family=str(name),
            games=_num(games),
            share=_num(games) / total,
        )
        for name, games in families.items()
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
                moves=_num(item["eligible_moves"]),
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
    """Six cards. A missing cross is an em dash, not a mixed population."""
    months = _inside(connection, "corpus_month", filters, dimensional=False)
    games = _games_kpi(connection, filters, months)
    win, loss, draw = _result_kpis(connection, filters)
    clock = _clock_kpi(connection, filters)
    positions = _position_kpi(connection, filters)
    return [games, win, draw, loss, clock, positions]


def opening_families(connection, filters: Filters, cohort: str) -> list[dict[str, object]]:
    return _labeled(
        _inside(
            connection,
            "opening_family",
            filters,
            dimensional=True,
            cohort=cohort,
        ),
        "opening_family",
        "games",
    )


def opening_lines(
    connection, filters: Filters, cohort: str, family: str
) -> list[dict[str, object]]:
    rows = _inside(
        connection,
        "opening_line",
        _with_family(filters, family),
        dimensional=True,
        cohort=cohort,
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
    connection, filters: Filters, cohort: str, family: str, fen: str
) -> dict[str, object] | None:
    rows = [
        row
        for row in _inside(
            connection,
            "opening_position",
            _with_family(filters, family),
            dimensional=True,
            cohort=cohort,
        )
        if row["fen"] == fen
    ]
    return rows[0] if rows else None


def continuations(
    connection, filters: Filters, cohort: str, family: str, fen: str
) -> list[dict[str, object]]:
    rows = [
        row
        for row in _inside(
            connection,
            "opening_continuation",
            _with_family(filters, family),
            dimensional=True,
            cohort=cohort,
        )
        if row["fen"] == fen
    ]
    return _labeled(rows, "continuation", "games")


def explorer_cohort(connection, filters: Filters) -> str | None:
    """Rated public when its span is inside the range, else the elite month."""
    present = {
        str(row["cohort"])
        for row in _inside(connection, "opening_family", filters, dimensional=False)
    }
    for cohort in EXPLORER_COHORTS:
        if cohort in present:
            return cohort
    return None


def clock_bands(connection, filters: Filters) -> list[dict[str, object]]:
    grouped: dict[str, list[int]] = {}
    for row in _clock_rows(connection, filters):
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


def clock_slices(connection, filters: Filters, band: str) -> list[dict[str, object]]:
    rows = [row for row in _clock_rows(connection, filters) if row["clock_band"] == band]
    rows.sort(key=lambda item: _num(item["evaluable_moves"] or 0), reverse=True)
    return rows


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
    ]


def _games_kpi(connection, filters: Filters, months: Sequence[Mapping[str, object]]) -> Kpi:
    dimensional = any(
        (filters.time_control, filters.color, filters.rating_band, filters.opening_family)
    )
    if not dimensional:
        current = sum(_num(row["games"]) for row in months)
        delta = _training_delta(connection, filters, months)
        detail = "no prior period" if delta is None else f"{delta:+,} vs prior"
        return Kpi("Games", f"{current:,}", detail)
    scored = _color_rows(connection, filters)
    if filters.color and scored:
        total = sum(_num(row["games"]) for row in scored)
        return Kpi("Games", f"{total:,}", "published cells")
    cohort = explorer_cohort(connection, filters) if filters.opening_family else None
    if cohort and filters.opening_family and not filters.color and not filters.time_control:
        if filters.rating_band:
            return Kpi("Games", "—", "no rating split")
        matched = opening_families(connection, filters, cohort)
        if matched:
            total = sum(_num(row["games"]) for row in matched)
            detail = "rated public" if cohort == "rated_public" else "elite month"
            return Kpi("Games", f"{total:,}", detail)
    return Kpi("Games", "—", "not in this cut")


def _result_kpis(connection, filters: Filters) -> tuple[Kpi, Kpi, Kpi]:
    scored = _color_rows(connection, filters) if filters.color else []
    if scored:
        wins, draws, losses, games = _tally(scored)
        return (
            Kpi("Win rate", _percent(wins / games), f"{wins:,} / {games:,}"),
            Kpi("Loss rate", _percent(losses / games), f"{losses:,} / {games:,}"),
            Kpi("Draw rate", _percent(draws / games), f"{draws:,} / {games:,}"),
        )
    plain = Filters(filters.start, filters.end)
    if filters == plain:
        drawn = _inside(connection, "august_draw", filters, dimensional=False)
        if drawn:
            games = _num(drawn[0]["games"])
            draws = _num(drawn[0]["draws"])
            return (
                Kpi("Win rate", "—", "needs a color"),
                Kpi("Loss rate", "—", "needs a color"),
                Kpi("Draw rate", _percent(draws / games), f"{draws:,} / {games:,}"),
            )
    return (
        Kpi("Win rate", "—", "needs a color"),
        Kpi("Loss rate", "—", "needs a color"),
        Kpi("Draw rate", "—", "not in this cut"),
    )


def _clock_kpi(connection, filters: Filters) -> Kpi:
    if filters.color or filters.opening_family:
        return Kpi("Clock error", "—", "not by color")
    rows = _clock_rows(connection, filters)
    evaluable = sum(_num(row["evaluable_moves"] or 0) for row in rows)
    errors = sum(_num(row["proxy_errors"] or 0) for row in rows)
    if evaluable == 0:
        return Kpi("Clock error", "—", "no evaluable moves")
    return Kpi("Clock error", _percent(errors / evaluable), f"{errors:,} / {evaluable:,}")


def _position_kpi(connection, filters: Filters) -> Kpi:
    if filters.color or filters.time_control or filters.rating_band:
        return Kpi("Positions", "—", "not in this cut")
    cohort = explorer_cohort(connection, filters)
    if cohort is None:
        return Kpi("Positions", "—", "outside dates")
    family = filters.opening_family
    sql = (
        'select count(distinct "fen") from "cube" '
        'where "grain" = ? and "cohort" = ? '
        'and "period_start" >= ? and "period_end" <= ?'
    )
    params: list[object] = ["opening_position", cohort, filters.start, filters.end]
    if family:
        sql += ' and "opening_family" = ?'
        params.append(family)
    count = _num(connection.execute(sql, params).fetchone()[0])
    detail = "rated public" if cohort == "rated_public" else "elite month"
    return Kpi("Positions", f"{count:,}", detail)


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


def _clock_rows(connection, filters: Filters) -> list[dict[str, object]]:
    if filters.color or filters.opening_family:
        return []
    return _inside(connection, "clock_slice", filters, dimensional=True)


def _color_rows(connection, filters: Filters) -> list[dict[str, object]]:
    return _inside(connection, "color_score", filters, dimensional=True)


def _inside(
    connection,
    grain: str,
    filters: Filters,
    *,
    dimensional: bool,
    cohort: str | None = None,
) -> list[dict[str, object]]:
    clauses = ['"period_start" >= ?', '"period_end" <= ?']
    params: list[object] = [grain, filters.start, filters.end]
    if cohort is not None:
        clauses.append('"cohort" = ?')
        params.append(cohort)
    if dimensional:
        _append_dimension(clauses, params, '"time_control"', filters.time_control)
        _append_dimension(clauses, params, '"color"', filters.color)
        _append_rating(clauses, params, filters.rating_band)
        _append_dimension(clauses, params, '"opening_family"', filters.opening_family)
    sql = _SELECT + ' where "grain" = ? and ' + " and ".join(clauses)
    return _records(connection.execute(sql, params))


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
                games=_num(route["games"]),
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
                games=_num(move["games"]),
                share=float(move["share_of_position_games"]),
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


def _cube_candidates() -> Iterable[Path]:
    yield Path.cwd() / "data" / "public" / CUBE_FILENAME
    for directory in (Path.cwd(), *Path.cwd().parents):
        project = directory / "pyproject.toml"
        package = directory / "src" / "chess_analytics"
        if project.is_file() and package.is_dir():
            yield directory / "data" / "public" / CUBE_FILENAME
            break


def shift_back(start: date, end: date) -> tuple[date, date]:
    """Previous window of the same number of days. Used by period tests."""
    width = (end - start).days + 1
    previous_end = start - timedelta(days=1)
    return previous_end - timedelta(days=width - 1), previous_end
