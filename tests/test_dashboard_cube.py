"""Cube builder, filters, KPI deltas, and drill state. No network."""

from datetime import date
from pathlib import Path

import pytest

from chess_analytics.dashboard_cube import (
    CUBE_FILENAME,
    SIZE_BUDGET_BYTES,
    Drill,
    Filters,
    breadcrumb,
    build_rows,
    climb,
    clock_slices,
    connect,
    cube_path,
    explorer_cohort,
    kpis,
    opening_lines,
    previous_periods,
    public_issues,
    select_clock,
    select_family,
    select_line,
    select_position,
    sql_text,
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
                "opening_families": [{"family": "French Defense", "games": 3, "share": 0.5}],
                "views": {
                    "French Defense": {
                        "family": "French Defense",
                        "positions": {
                            "p1": {
                                "position_key": fen,
                                "games": 3,
                                "opening_labels": [{"eco": "C00", "games": 3}],
                                "routes": [{"san": "1.e4 e6", "games": 3, "share": 1.0}],
                                "continuations": [
                                    {"san": "d4", "games": 2, "share_of_position_games": 0.66}
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
        "opening_families": {"French Defense": 2},
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
                    "eligible_moves": 5,
                    "evaluable_moves": 4,
                    "proxy_errors": 1,
                },
                {
                    "time_control": "180+0",
                    "rating_band": "2000_plus",
                    "bucket": "60_plus",
                    "phase": "late_ply",
                    "eligible_moves": 8,
                    "evaluable_moves": 0,
                    "proxy_errors": 0,
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
    assert kpis(connection, black)[5].value == "—"
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


def test_committed_cube_matches_the_published_totals() -> None:
    path = cube_path(ROOT)
    assert path.stat().st_size < SIZE_BUDGET_BYTES
    connection = connect(path)
    wide = Filters(date(2025, 11, 1), date(2026, 8, 1))
    cards = {item.label: item for item in kpis(connection, wide)}
    assert cards["Games"].value == "1,042,346"
    assert cards["Games"].detail == "no prior period"
    assert cards["Draw rate"].value == "3.7%"
    assert cards["Draw rate"].detail == "3,669 / 99,117"
    assert cards["Clock error"].detail == "2,132 / 22,994"
    assert cards["Positions"].value == "256"
    june = Filters(date(2026, 6, 1), date(2026, 8, 1))
    assert kpis(connection, june)[0] == cards["Games"].__class__(
        "Games", "266,770", "+500 vs prior"
    )
    french = Filters(wide.start, wide.end, None, "black", None, "French Defense")
    french_cards = kpis(connection, french)
    assert french_cards[0].value == "239"
    assert french_cards[1].detail == "114 / 239"
    line = opening_lines(connection, wide, "rated_public", "Sicilian Defense")[0]
    assert line["label"] == "1.e4 c5 2.Nf3 Nc6 3.d4 cxd4"
    assert "r1bqkbnr/pp1ppppp/2n5/8/3pP3/5N2/PPP2PPP/RNBQKB1R w KQkq -" in line["fens"]
    issues = connection.execute('select count(*) from "cube"').fetchone()
    assert issues is not None and int(issues[0]) > 0
