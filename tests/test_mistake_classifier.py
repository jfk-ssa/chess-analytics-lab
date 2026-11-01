"""Synthetic frame contract, replay safety and optional-ml calibration checks."""

import importlib.util
import json
import math
from pathlib import Path

import duckdb
import pytest

from chess_analytics.mistake_training import (
    FEATURES,
    TrainingRow,
    build_frame,
    feature_matrix,
    grouped_split,
    opening_family,
    prefix_opening_family,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((ROOT / "tests/fixtures/mistake_training.json").read_text())
ROWS = FIXTURE["training_frame"]
SPEC = importlib.util.spec_from_file_location(
    "mistake_trainer", ROOT / "scripts/train_mistake_classifier.py"
)
assert SPEC is not None and SPEC.loader is not None
TRAINER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TRAINER)


@pytest.fixture
def warehouse(tmp_path):
    path = tmp_path / "warehouse.duckdb"
    games = json.loads((ROOT / "contracts/tables.json").read_text())["fact_game"]
    moves = json.loads((ROOT / "contracts/m3_tables.json").read_text())["fact_move"]
    with duckdb.connect(str(path)) as connection:
        for name, schema in (("fact_game", games), ("fact_move", moves)):
            connection.execute(
                f"create table {name} ({', '.join(f'{k} {v}' for k, v in schema.items())})"
            )
            connection.executemany(
                f"insert into {name} values ({', '.join('?' for _ in schema)})",
                [[row.get(column) for column in schema] for row in FIXTURE[name]],
            )
    return path


def test_fixture_contract_and_no_leakage():
    assert FIXTURE["version"] == "1"
    assert len(ROWS) == 36 and len({row["game_id"] for row in ROWS}) == 6
    for row in ROWS:
        assert set(row) == TrainingRow.__required_keys__
        assert type(row["error_proxy"]) is bool
        assert type(row["material_balance"]) is int and type(row["ply"]) is int
        assert row["color"] in {"white", "black"}
        assert row["phase_proxy"] in {"early_ply", "middle_ply", "late_ply"}
        assert row["opening_family"] is None or isinstance(row["opening_family"], str)
        assert row["clock_before_seconds"] is None or isinstance(row["clock_before_seconds"], float)
    leaks = dict.fromkeys(
        (
            "centipawn_deterioration",
            "eval_after_cp_white",
            "eval_after_mate_white",
            "clock_after_seconds",
            "uci",
        ),
        9999,
    )
    poisoned = [{**row, **leaks} for row in ROWS]
    assert set(FEATURES) == {
        "clock_before_seconds",
        "phase_proxy",
        "ply",
        "color",
        "opening_family",
        "material_balance",
    }
    for clean, dirty in zip(feature_matrix(ROWS), feature_matrix(poisoned), strict=True):
        assert set(clean) == set(FEATURES) == set(dirty)
        for key in FEATURES:
            assert clean[key] == dirty[key] or (
                key == "clock_before_seconds" and math.isnan(clean[key]) and math.isnan(dirty[key])
            )


def test_builder_replays_unevaluable_captures_before_filtering(warehouse):
    assert build_frame(warehouse) == ROWS
    by_ply = {(row["game_id"], row["ply"]): row for row in ROWS}
    assert by_ply["syn00001", 3]["material_balance"] == 0  # Before White captures.
    assert by_ply["syn00001", 5]["material_balance"] == 0  # Unevaluable recapture at ply 4.
    assert by_ply["syn00002", 5]["material_balance"] == -1
    assert by_ply["syn00003", 6]["material_balance"] == 1  # Prior en passant capture.


def test_shared_prefix_opening_features_ignore_game_headers(warehouse):
    frame = build_frame(warehouse)
    games = {
        game: {row["ply"]: row for row in frame if row["game_id"] == game}
        for game in ("syn00002", "syn00005")
    }
    prefixes = {
        game: {
            row["ply"]: tuple(
                move["uci"]
                for move in FIXTURE["fact_move"]
                if move["game_id"] == game and move["ply"] < row["ply"]
            )
            for row in rows.values()
        }
        for game, rows in games.items()
    }
    assert games["syn00002"].keys() == games["syn00005"].keys()
    for ply, first in games["syn00002"].items():
        assert prefixes["syn00002"][ply] == prefixes["syn00005"][ply]
        second = games["syn00005"][ply]
        expected = None if ply <= 3 else "Queen's Gambit"
        assert first["opening_family"] == second["opening_family"] == expected
        assert (
            feature_matrix([first])[0]["opening_family"]
            == feature_matrix([second])[0]["opening_family"]
        )
    with duckdb.connect(str(warehouse)) as connection:
        connection.execute("update fact_game set source_opening = 'Unrelated header'")
    assert build_frame(warehouse) == frame


def test_prefix_opening_family_uses_longest_match(monkeypatch):
    from chess_analytics.mistake_training import OPENING_PREFIXES

    monkeypatch.setitem(OPENING_PREFIXES, ("d2d4",), "Queen's Pawn Game")
    assert prefix_opening_family(()) is None
    assert prefix_opening_family(("e2e4",)) is None
    assert prefix_opening_family(("d2d4", "d7d5")) == "Queen's Pawn Game"
    assert prefix_opening_family(("d2d4", "d7d5", "c2c4", "d5c4")) == "Queen's Gambit"


@pytest.mark.parametrize(
    "source, expected",
    [
        (None, None),
        ("", None),
        (" : line", None),
        (" French Defense : A:B", "French Defense"),
    ],
)
def test_opening_family_matches_dbt(source, expected):
    with duckdb.connect() as connection:
        result = connection.execute(
            "select nullif(trim(split_part(?, ':', 1)), '')", [source]
        ).fetchone()
    assert result is not None
    assert opening_family(source) == expected == result[0]


@pytest.mark.parametrize(
    "mutation",
    [
        "delete from fact_move where game_id = 'syn00001' and ply = 2",
        "delete from fact_move where game_id = 'syn00001' and ply = 8",
        "update fact_move set uci = 'e2e5' where ply = 1",
        "update fact_move set color = 'black' where ply = 1",
        "update fact_move set error_proxy = null where ply = 3",
        "delete from fact_game where game_id = 'syn00001'",
        "insert into fact_game select * from fact_game where game_id = 'syn00001'",
        "insert into fact_move select * from fact_move where game_id = 'syn00001' and ply = 2",
        "update fact_game set variant = 'Chess960'",
    ],
)
def test_builder_rejects_invalid_sources(warehouse, mutation):
    with duckdb.connect(str(warehouse)) as connection:
        connection.execute(mutation)
    with pytest.raises(ValueError):
        build_frame(warehouse)


@pytest.mark.parametrize("ply", [2, 3])
def test_builder_rejects_error_proxy_inconsistent_with_deterioration(warehouse, ply):
    with duckdb.connect(str(warehouse)) as connection:
        connection.execute(
            "update fact_move set error_proxy = not error_proxy where ply = ?", [ply]
        )
    with pytest.raises(ValueError, match="error_proxy disagrees with deterioration"):
        build_frame(warehouse)


def test_grouped_split_is_disjoint_complete_and_deterministic():
    train, test = grouped_split(ROWS)
    assert train and test and len(train) + len(test) == len(ROWS)
    assert {r["game_id"] for r in train}.isdisjoint({r["game_id"] for r in test})
    assert (train, test) == grouped_split(ROWS)
    assert {r["game_id"] for r in test} == {
        r["game_id"] for r in grouped_split(list(reversed(ROWS)))[1]
    }
    with pytest.raises(ValueError, match="at least two games"):
        grouped_split([ROWS[0]])


def test_reliability_boundaries_and_empty_bins():
    table = TRAINER.reliability_table([False, True, False, True], [0.0, 0.2, 0.4, 1.0])
    assert [row["count"] for row in table] == [1, 1, 1, 0, 1]
    assert table[1]["mean_predicted_probability"] == 0.2
    assert table[1]["empirical_positive_rate"] == 1
    assert table[3]["mean_predicted_probability"] is None
    assert table[3]["empirical_positive_rate"] is None


def test_deterministic_training_and_holdout_calibration():
    pytest.importorskip("sklearn", reason="install the optional ml extra")
    result = TRAINER.train_evaluate(ROWS)
    assert result == TRAINER.train_evaluate(ROWS)
    groups = [set(ids) for ids in result["games"].values()]
    assert all(a.isdisjoint(b) for i, a in enumerate(groups) for b in groups[i + 1 :])
    assert set.union(*groups) == {r["game_id"] for r in ROWS}
    holdout = [r for r in ROWS if r["game_id"] in result["games"]["holdout"]]
    probabilities = result["probabilities"]
    assert len(holdout) == len(probabilities) == result["holdout_rows"]
    expected = sum(
        (r["error_proxy"] - p) ** 2 for r, p in zip(holdout, probabilities, strict=True)
    ) / len(holdout)
    assert result["brier_score"] == pytest.approx(expected)
    assert 0 <= result["brier_score"] <= 1
    assert result["reliability"] == TRAINER.reliability_table(
        [r["error_proxy"] for r in holdout],
        probabilities,
    )
    assert sum(b["count"] for b in result["reliability"]) == len(holdout)
    changed = [
        {**r, "error_proxy": not r["error_proxy"]}
        if r["game_id"] in result["games"]["holdout"]
        else r
        for r in ROWS
    ]
    assert TRAINER.train_evaluate(changed)["probabilities"] == probabilities
