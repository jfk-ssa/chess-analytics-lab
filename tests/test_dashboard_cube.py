"""Cube builder, filters, KPI deltas, and drill state. No network."""

from datetime import date
from pathlib import Path

import pytest

from chess_analytics.dashboard_cube import (
    CUBE_FILENAME,
    MIN_CELL,
    SIZE_BUDGET_BYTES,
    Drill,
    Filters,
    breadcrumb,
    build_rows,
    climb,
    clock_display,
    clock_slices,
    connect,
    cube_path,
    explorer_cohort,
    kpis,
    locate_warehouse,
    opening_lines,
    previous_periods,
    public_issues,
    select_clock,
    select_family,
    select_line,
    select_position,
    sql_text,
    transpositions,
    warehouse_rows,
    write_cube,
)

ROOT = Path(__file__).resolve().parents[1]


def _sources() -> tuple[dict, dict, dict, dict, dict]:
    corpus = {
        "training_sources": [
            {
                "cohort": "elite_reference",
                "period": "2025-11",
                "first_date": "2025-11-01",
                "last_date": "2025-11-30",
                "games": 10,
            },
            {
                "cohort": "rated_public",
                "period": "2025-12",
                "first_date": "2025-12-01",
                "last_date": "2025-12-01",
                "games": 4,
            },
            {
                "cohort": "rated_public",
                "period": "2026-01",
                "first_date": "2026-01-01",
                "last_date": "2026-01-01",
                "games": 6,
            },
        ]
    }
    fen = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR w KQkq -"
    positions = {
        "cohorts": {
            "rated_public": {
                "opening_families": [
                    {"family": "French Defense", "games": 12, "share": 0.5},
                    {"family": "Amazon Attack", "games": 4, "share": 0.1},
                ],
                "views": {
                    "French Defense": {
                        "family": "French Defense",
                        "positions": {
                            "p1": {
                                "position_key": fen,
                                "games": 3,
                                "opening_labels": [{"eco": "C00", "games": 3}],
                                "routes": [
                                    {"san": "1.e4 e6", "games": 12, "share": 1.0},
                                    {"san": "1.e4 e6 2.d4", "games": 4, "share": 0.2},
                                ],
                                "continuations": [
                                    {"san": "d4", "games": 12, "share_of_position_games": 0.66},
                                    {"san": "Nf3", "games": 3, "share_of_position_games": 0.1},
                                ],
                            }
                        },
                    },
                    "all": {"family": None, "positions": {}},
                },
            }
        }
    }
    reference = {
        "opening_families": {"French Defense": 12, "Amazon Attack": 4},
        "opening_player_cohorts": {
            "French Defense|black|rating_1400_1599|60+0": {
                "wins": 1,
                "draws": 0,
                "losses": 1,
                "games": 2,
            }
        },
        "eligible_games": 10,
        "drawn_eligible_games": 1,
    }
    figures = {
        "clock": {
            "strata": [
                {
                    "time_control": "60+0",
                    "rating_band": "1200_1599",
                    "bucket": "under_10",
                    "phase": "early_ply",
                    "eligible_moves": 12,
                    "evaluable_moves": 4,
                    "proxy_errors": 1,
                },
                {
                    "time_control": "180+0",
                    "rating_band": "2000_plus",
                    "bucket": "60_plus",
                    "phase": "late_ply",
                    "eligible_moves": 11,
                    "evaluable_moves": 0,
                    "proxy_errors": 0,
                },
                {
                    "time_control": "15+0",
                    "rating_band": "under_1200",
                    "bucket": "under_10",
                    "phase": "early_ply",
                    "eligible_moves": 4,
                    "evaluable_moves": 4,
                    "proxy_errors": 1,
                },
            ]
        }
    }
    analytical = {"observed_date_coverage": {"first_utc_date": "2026-08-01"}}
    return corpus, positions, reference, figures, analytical


def _tiny(tmp_path: Path):
    rows = build_rows(*_sources())
    path = tmp_path / CUBE_FILENAME
    write_cube(rows, path)
    return connect(path)


def test_builder_rows_are_public_and_skip_unlabeled_views() -> None:
    rows = build_rows(*_sources())
    assert public_issues(rows) == []
    grains = {row["grain"] for row in rows}
    assert grains == {
        "corpus_month",
        "opening_family",
        "opening_line",
        "opening_position",
        "opening_continuation",
        "august_family",
        "color_score",
        "august_draw",
        "clock_slice",
    }
    assert all(row["opening_family"] != "all" for row in rows)
    assert all(row["opening_family"] != "Amazon Attack" for row in rows)
    for grain in ("opening_line", "opening_continuation", "opening_family", "august_family"):
        small = [row for row in rows if row["grain"] == grain and int(row["games"]) < MIN_CELL]
        assert small == []
    short_clock = [
        row for row in rows if row["grain"] == "clock_slice" and int(row["moves"]) < MIN_CELL
    ]
    assert short_clock == []
    assert not any(row["time_control"] == "15+0" for row in rows if row["grain"] == "clock_slice")
    leaked = build_rows(*_sources())
    leaked[0]["opening_family"] = "player_key"
    assert public_issues(leaked)


def test_sql_is_lowercase_and_quotes_identifiers() -> None:
    statements = sql_text()
    assert statements
    for statement in statements:
        assert statement == statement.lower()
        assert '"' in statement


def test_filter_and_query_respect_unpublished_crosses(tmp_path: Path) -> None:
    connection = _tiny(tmp_path)
    wide = Filters(date(2025, 11, 1), date(2026, 8, 1))
    assert explorer_cohort(connection, wide) == "rated_public"
    french = opening_lines(connection, wide, "rated_public", "French Defense")
    assert french[0]["label"] == "1.e4 e6"
    black = Filters(wide.start, wide.end, None, "black", None, "French Defense")
    assert explorer_cohort(connection, black) == "rated_public"
    assert kpis(connection, black)[0].value == "2"
    assert kpis(connection, black)[5].value == "1"
    assert "not by color" in kpis(connection, black)[5].detail
    rated_only = Filters(date(2025, 12, 1), date(2026, 1, 1))
    bands = clock_slices(connection, wide, "under_10")
    assert len(bands) == 1
    assert clock_slices(connection, Filters(wide.start, wide.end, "180+0"), "under_10") == []
    assert explorer_cohort(connection, rated_only) == "rated_public"
    november = Filters(date(2025, 11, 1), date(2025, 11, 30))
    assert explorer_cohort(connection, november) is None


def test_kpi_delta_uses_the_previous_equal_period_count(tmp_path: Path) -> None:
    connection = _tiny(tmp_path)
    catalog = ["2025-11", "2025-12", "2026-01"]
    assert previous_periods(catalog, ["2025-11", "2025-12", "2026-01"]) is None
    assert previous_periods(catalog, ["2026-01"]) == ["2025-12"]
    january = Filters(date(2026, 1, 1), date(2026, 1, 1))
    games = kpis(connection, january)[0]
    assert games.value == "6"
    assert games.detail == "+2 vs prior"
    wide = Filters(date(2025, 11, 1), date(2026, 8, 1))
    assert kpis(connection, wide)[0].detail == "no prior period"
    with pytest.raises(ValueError, match="start is after"):
        Filters(date(2026, 2, 1), date(2026, 1, 1))


def test_drill_climbs_from_position_to_family_and_clock() -> None:
    drill = select_family(Drill(), "French Defense")
    drill = select_line(drill, "1.e4 e6", ["fen-a"])
    assert drill.fen == "fen-a"
    assert breadcrumb(drill) == ["Openings", "French Defense", "1.e4 e6", "Position"]
    climbed = climb(drill, line_fen_count=1)
    assert climbed.line is None and climbed.fen is None and climbed.family == "French Defense"
    two = select_line(select_family(Drill(), "French Defense"), "1.e4 e6", ["fen-a", "fen-b"])
    assert two.fen is None
    opened = select_position(two, "fen-b")
    assert climb(opened, line_fen_count=2).fen is None
    assert climb(opened, line_fen_count=2).line == "1.e4 e6"
    band = select_clock(Drill(), "under_10")
    assert breadcrumb(band)[-1] == "Clock under_10"
    assert climb(band).clock_band is None
    with pytest.raises(ValueError, match="line drill"):
        select_line(Drill(), "1.e4", ["fen-a"])


def test_committed_cube_matches_the_warehouse_and_published_totals() -> None:
    path = cube_path(ROOT)
    assert path.stat().st_size == 580_528
    assert path.stat().st_size < SIZE_BUDGET_BYTES
    connection = connect(path)
    counted = connection.execute('select count(*) from "cube"').fetchone()
    assert counted is not None and int(counted[0]) == 34_798
    covered = connection.execute(
        'select coalesce(sum("games"), 0) from "cube" where "grain" = ?',
        ["game_cell"],
    ).fetchone()
    assert covered is not None and int(covered[0]) == 1_009_445
    wide = Filters(date(2025, 11, 1), date(2026, 8, 1))
    cards = {item.label: item for item in kpis(connection, wide)}
    assert cards["Games"].value == "1,009,445"
    assert cards["Games"].detail == "warehouse"
    assert cards["Win rate"].value == "49.2%"
    assert cards["Win rate"].detail == "476,741 / 968,874 · White"
    assert cards["Loss rate"].value == "45.7%"
    assert cards["Loss rate"].detail == "442,862 / 968,874 · White"
    assert cards["Draw rate"].value == "5.1%"
    assert cards["Draw rate"].detail == "49,271 / 968,874 · White"
    assert cards["Clock error"].detail == "2,132 / 22,994"
    assert cards["Positions"].value == "256"
    assert cards["Rating diff"].value == "+0.1"
    assert cards["Rating diff"].detail == "White · mean"
    assert cards["Game length"].value == "72.8"
    assert cards["Game length"].detail == "mean ply"
    june = Filters(date(2026, 6, 1), date(2026, 8, 1))
    june_cards = {item.label: item for item in kpis(connection, june)}
    assert june_cards["Games"].value == "256,031"
    assert june_cards["Games"].detail == "warehouse"
    french = Filters(wide.start, wide.end, None, "black", None, "French Defense")
    french_cards = {item.label: item for item in kpis(connection, french)}
    assert french_cards["Games"].value == "63,484"
    assert french_cards["Win rate"].value == "46.8%"
    assert french_cards["Win rate"].detail == "29,728 / 63,484"
    assert french_cards["Clock error"].value == "9.3%"
    assert "not by" in french_cards["Clock error"].detail
    assert french_cards["Positions"].value == "21"
    november = Filters(date(2025, 11, 1), date(2025, 11, 30))
    november_cards = {item.label: item for item in kpis(connection, november)}
    assert november_cards["Games"].value == "238,819"
    assert november_cards["Clock error"].value == "9.3%"
    assert november_cards["Draw rate"].value == "9.4%"
    assert november_cards["Win rate"].value == "47.9%"
    routes = connection.execute(
        'select count(*) from "cube" where "grain" = ? and "games" < ?',
        ["transposition_route", MIN_CELL],
    ).fetchone()
    assert routes is not None and int(routes[0]) == 0
    short = connection.execute(
        'select count(*) from "cube" where "grain" = ? and "ply" < 2',
        ["transposition"],
    ).fetchone()
    assert short is not None and int(short[0]) == 0
    boards, caption = transpositions(connection, wide)
    assert boards and caption.startswith("Distinct acyclic")
    assert all(item["move_orders"] >= 2 and len(item["routes"]) <= 3 for item in boards)
    sicilian = Filters(wide.start, wide.end, None, None, None, "Sicilian Defense")
    sicilian_boards, sicilian_caption = transpositions(connection, sicilian)
    assert sicilian_boards
    assert all(item["family"] == "Sicilian Defense" for item in sicilian_boards)
    titles = [str(item["title"]) for item in sicilian_boards]
    assert len(titles) == len(set(titles))
    assert all(title.startswith("After Black's move ") and " · " in title for title in titles)
    assert titles[0] == "After Black's move 3 · 1.e4 c5 2.Nf3 Nc6 3.d4 cxd4"
    assert "not split" not in sicilian_caption
    colored = Filters(wide.start, wide.end, None, "black", None, "Sicilian Defense")
    colored_boards, colored_caption = transpositions(connection, colored)
    assert colored_boards[0]["fen"] == sicilian_boards[0]["fen"]
    assert "color" in colored_caption
    line = opening_lines(connection, wide, "rated_public", "Sicilian Defense")[0]
    assert line["label"] == "1.e4 c5 2.Nf3 Nc6 3.d4 cxd4"
    assert "r1bqkbnr/pp1ppppp/2n5/8/3pP3/5N2/PPP2PPP/RNBQKB1R w KQkq -" in line["fens"]
    issues = connection.execute('select count(*) from "cube"').fetchone()
    assert issues is not None and int(issues[0]) > 0


def test_missing_time_and_opening_do_not_widen_the_population() -> None:
    connection = connect(cube_path(ROOT))
    wide = Filters(date(2025, 11, 1), date(2026, 8, 1))
    for control in ("180+2", "-"):
        chosen = Filters(wide.start, wide.end, control)
        cards = {item.label: item for item in kpis(connection, chosen)}
        clock = cards["Clock error"]
        assert "2,132" not in clock.detail
        assert "22,994" not in clock.detail
        assert "August" not in clock.detail
        assert clock.detail == "no cells for this cut · not by time"
        bands, note, tag = clock_display(connection, chosen)
        assert bands == []
        assert tag == "not by time"
        assert note == "No clock slices for this time."
        assert clock_slices(connection, chosen, "under_10") == []
    dash = {item.label: item for item in kpis(connection, Filters(wide.start, wide.end, "-"))}
    assert dash["Games"].value != "1,009,445"
    assert dash["Win rate"].detail == "no cells for this cut"
    assert "476,741" not in dash["Win rate"].detail
    amazon = Filters(wide.start, wide.end, None, None, None, "Amazon Attack")
    empty = {item.label: item for item in kpis(connection, amazon)}
    assert empty["Games"].value == "0"
    assert empty["Games"].detail == "no cells for this cut"
    assert empty["Win rate"].detail == "no cells for this cut"
    assert "1,009,445" not in empty["Games"].value
    kept = Filters(wide.start, wide.end, "180+0")
    kept_bands, _kept_note, kept_tag = clock_display(connection, kept)
    assert kept_bands
    assert kept_tag != "August"
    assert (
        "no cells for this cut"
        not in {item.label: item for item in kpis(connection, kept)}["Clock error"].detail
    )
    november = Filters(date(2025, 11, 1), date(2025, 11, 30), "180+2")
    november_clock = {item.label: item for item in kpis(connection, november)}["Clock error"]
    assert "2,132" not in november_clock.detail
    assert "August" not in november_clock.detail


def test_transposition_rows_drop_routes_under_ten_games(tmp_path: Path) -> None:
    corpus, positions, reference, figures, analytical = _sources()
    fen = "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq -"
    positions["cohorts"]["rated_public"]["views"]["French Defense"]["positions"]["p2"] = {
        "position_key": fen,
        "games": 40,
        "opening_labels": [{"eco": "C00", "games": 40}],
        "routes": [
            {"san": "1.e4 e6 2.d4 d5", "games": 12, "share": 0.3},
            {"san": "1.e4 e6 2.d4", "games": 11, "share": 0.27},
            {"san": "1.e4 e6", "games": 4, "share": 0.1},
        ],
        "continuations": [],
    }
    rows = build_rows(corpus, positions, reference, figures, analytical)
    summary = [row for row in rows if row["grain"] == "transposition"]
    routes = [row for row in rows if row["grain"] == "transposition_route"]
    assert len(summary) == 1
    assert summary[0]["games"] == 40
    assert summary[0]["ply"] == 2
    assert summary[0]["fen"] == fen
    assert sorted(row["games"] for row in routes) == [11, 12]
    assert public_issues(rows) == []
    path = tmp_path / CUBE_FILENAME
    write_cube(rows, path)
    connection = connect(path)
    found, caption = transpositions(
        connection, Filters(date(2025, 11, 1), date(2026, 8, 1), None, "white")
    )
    assert len(found) == 1
    assert found[0]["move_orders"] == 2
    assert found[0]["games"] == 40
    assert found[0]["kept_games"] == 23
    assert [item[0] for item in found[0]["routes"]] == ["1.e4 e6 2.d4 d5", "1.e4 e6 2.d4"]
    assert found[0]["title"] == "After Black's move 2 · 1.e4 e6 2.d4 d5"
    assert "color" in caption


def test_warehouse_rows_suppress_cells_under_ten_games(tmp_path: Path) -> None:
    import duckdb

    path = tmp_path / "warehouse.duckdb"
    connection = duckdb.connect(str(path))
    connection.execute(
        """
        create table fact_game (
          provider varchar, game_id varchar, result varchar, variant varchar,
          utc_date date, time_control varchar, source_opening varchar,
          marked_bot boolean, ply_count bigint, increment_seconds bigint
        )
        """
    )
    connection.execute(
        """
        create table fact_player_game (
          provider varchar, game_id varchar, color varchar, player_key varchar,
          rating bigint, opponent_rating bigint, score double
        )
        """
    )
    for index in range(12):
        _insert_game(connection, index, "French Defense: Advance", 40, 1.0)
    for index in range(12, 22):
        _insert_game(connection, index, "Sicilian Defense", 30, 0.0)
    for index in range(22, 31):
        _insert_game(connection, index, "Caro-Kann Defense", 20, 0.5)
    rows = warehouse_rows(connection)
    connection.close()
    assert public_issues(rows) == []
    blob = " ".join(str(value) for row in rows for value in row.values())
    assert "player_key" not in blob
    assert "secret-user" not in blob
    families = {row["opening_family"] for row in rows if row["grain"] == "game_cell"}
    assert families == {"French Defense", "Sicilian Defense"}
    french = next(row for row in rows if row["grain"] == "result_cell" and row["games"] == 12)
    assert french["wins"] == 12
    assert french["rating_diff"] == 100
    assert french["mean_ply"] == 40
    assert locate_warehouse(path) == path
    assert locate_warehouse(tmp_path / "missing.duckdb") is None
    cube = tmp_path / CUBE_FILENAME
    write_cube(rows, cube)
    shown = kpis(connect(cube), Filters(date(2026, 8, 1), date(2026, 8, 31)))
    cards = {item.label: item for item in shown}
    assert cards["Games"].value == "22"
    assert cards["Win rate"].detail == "12 / 22 · White"
    assert cards["Rating diff"].value == "+100.0"
    assert cards["Game length"].value == "35.5"


def _insert_game(connection, index: int, opening: str, ply: int, score: float) -> None:
    game_id = f"{index:08d}"
    connection.execute(
        "insert into fact_game values (?, ?, '1-0', 'Standard', DATE '2026-08-01', "
        "'60+0', ?, false, ?, 0)",
        ["lichess", game_id, opening, ply],
    )
    connection.execute(
        "insert into fact_player_game values (?, ?, 'white', 'secret-user', 1500, 1400, ?)",
        ["lichess", game_id, score],
    )


def test_opening_game_warehouse_matches_corpus_windows(tmp_path: Path) -> None:
    import duckdb

    path = tmp_path / "warehouse.duckdb"
    connection = duckdb.connect(str(path))
    columns = """
        provider varchar, game_id varchar, result varchar, rated boolean,
        variant varchar, utc_date date, time_control varchar,
        base_seconds bigint, increment_seconds bigint, source_opening varchar,
        source_eco varchar, marked_bot boolean, ply_count bigint,
        source_ordinal bigint, source_event varchar, record_fingerprint varchar,
        white_rating bigint, black_rating bigint, source_snapshot_id varchar,
        source_period varchar, source_file varchar, source_cohort varchar
    """
    connection.execute(f"create table opening_game ({columns})")
    connection.execute(f"create table retained_game ({columns})")
    for index in range(12):
        _insert_opening(connection, index, "French Defense: Advance", "1-0", 40, date(2026, 8, 1))
    for index in range(12, 22):
        _insert_opening(connection, index, "Sicilian Defense: Najdorf", "0-1", 30, date(2026, 8, 1))
    for index in range(22, 31):
        _insert_opening(connection, index, "Caro-Kann Defense", "1/2-1/2", 20, date(2026, 8, 1))
    _insert_opening(
        connection,
        31,
        "French Defense: Advance",
        "1-0",
        40,
        date(2026, 8, 1),
        marked_bot=True,
    )
    _insert_opening(connection, 32, "French Defense: Advance", "*", 40, date(2026, 8, 1))
    _insert_opening(
        connection,
        33,
        "French Defense: Advance",
        "1-0",
        40,
        date(2026, 8, 2),
        marked_bot=True,
    )
    _insert_opening(connection, 34, "French Defense: Advance", "*", 40, date(2026, 8, 3))
    for index, played in enumerate((date(2025, 11, 1),) * 6 + (date(2025, 11, 30),) * 4, start=40):
        _insert_opening(
            connection,
            index,
            "King's Indian Defense: Classical",
            "1-0",
            50,
            played,
            cohort="elite_reference",
            period="2025-11",
        )
    for index in range(60, 75):
        _insert_opening(
            connection,
            index,
            "Queen's Gambit: Declined",
            "1-0",
            40,
            date(2026, 8, 1),
            table="retained_game",
        )
    rows = warehouse_rows(connection)
    connection.close()
    assert public_issues(rows) == []
    blob = " ".join(str(value) for row in rows for value in row.values())
    assert "secret.pgn" not in blob
    assert "fingerprint-secret" not in blob
    assert {row["grain"] for row in rows} == {"game_cell", "result_cell"}
    families = {row["opening_family"] for row in rows if row["grain"] == "game_cell"}
    assert families == {"French Defense", "Sicilian Defense", "King's Indian Defense"}
    french = next(
        row
        for row in rows
        if row["grain"] == "game_cell" and row["opening_family"] == "French Defense"
    )
    assert french["cohort"] == "rated_public"
    assert french["period"] == "2026-08"
    assert french["period_start"] == date(2026, 8, 1)
    assert french["period_end"] == date(2026, 8, 1)
    assert french["games"] == 12
    elite = next(row for row in rows if row["cohort"] == "elite_reference")
    assert elite["period"] == "2025-11"
    assert elite["period_start"] == date(2025, 11, 1)
    assert elite["period_end"] == date(2025, 11, 30)
    white = next(
        row
        for row in rows
        if row["grain"] == "result_cell"
        and row["opening_family"] == "French Defense"
        and row["color"] == "white"
    )
    assert white["wins"] == 12
    assert white["rating_band"] == "1200_1599"
    assert white["rating_diff"] == 100
    assert white["mean_ply"] == 40
    black = next(
        row
        for row in rows
        if row["grain"] == "result_cell"
        and row["opening_family"] == "French Defense"
        and row["color"] == "black"
    )
    assert black["wins"] == 0
    assert black["losses"] == 12
    assert black["rating_diff"] == -100
    cube = tmp_path / CUBE_FILENAME
    write_cube(rows, cube)
    shown = connect(cube)
    august = Filters(date(2026, 8, 1), date(2026, 8, 1))
    cards = {item.label: item for item in kpis(shown, august)}
    assert cards["Games"].value == "22"
    assert cards["Win rate"].detail == "12 / 22 · White"
    rated = Filters(date(2026, 8, 1), date(2026, 8, 1), None, None, "1200_1599")
    rated_cards = {item.label: item for item in kpis(shown, rated)}
    assert rated_cards["Games"].value == "22"
    assert "White" in rated_cards["Games"].detail
    black_only = Filters(date(2026, 8, 1), date(2026, 8, 1), None, "black")
    black_cards = {item.label: item for item in kpis(shown, black_only)}
    assert black_cards["Games"].value == "22"
    assert black_cards["Win rate"].detail == "10 / 22"
    full = Filters(date(2025, 11, 1), date(2026, 8, 1))
    assert {item.label: item for item in kpis(shown, full)}["Games"].value == "32"
    search_root = tmp_path / "search"
    openings = search_root / "data" / "openings" / "published" / "abc"
    openings.mkdir(parents=True)
    found = openings / "warehouse.duckdb"
    found.write_bytes(b"")
    assert locate_warehouse(None, search_root) == found


def _insert_opening(
    connection,
    index: int,
    opening: str,
    result: str,
    ply: int,
    played: date,
    *,
    marked_bot: bool = False,
    cohort: str = "rated_public",
    period: str = "2026-08",
    table: str = "opening_game",
) -> None:
    connection.execute(
        f'insert into "{table}" values ('
        "?, ?, ?, true, 'standard', ?, '60+0', 60, 0, ?, 'C00', ?, ?, 1, "
        "'rated blitz', 'fingerprint-secret', 1500, 1400, 'snapshot', ?, "
        "'data/raw/secret.pgn', ?)",
        ["lichess", f"{index:08d}", result, played, opening, marked_bot, ply, period, cohort],
    )


def test_warehouse_script_exits_when_the_file_is_missing(tmp_path: Path) -> None:
    import importlib.util

    script = ROOT / "scripts" / "build_warehouse_cube.py"
    spec = importlib.util.spec_from_file_location("build_warehouse_cube", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.main(["--warehouse", str(tmp_path / "missing.duckdb")]) == 2
