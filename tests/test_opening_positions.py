"""Independent legal-route, repetition and denominator checks; no bulk data required."""

import importlib.util
import io
from pathlib import Path

import chess
import chess.pgn
import duckdb
import pytest

ROOT = Path(__file__).resolve().parents[1]


def script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def replay(line, maximum=6):
    module = script("build_opening_positions")
    source = io.StringIO('[Site "https://lichess.org/abcd1234"]\n\n' + line + " *\n")
    return chess.pgn.read_game(
        source,
        Visitor=lambda: module.OpeningVisitor(
            {"game_id": "abcd1234"}, {"min_ply": 6, "max_ply": maximum}
        ),
    )


def test_different_legal_orders_join_and_retain_the_actual_continuation():
    first = replay("1. d4 Nf6 2. c4 e6 3. Nf3 d5 4. g3")
    second = replay("1. d4 d5 2. c4 e6 3. Nf3 Nf6 4. e3")
    assert first[0]["position_key"] == second[0]["position_key"]
    assert first[0]["route"] != second[0]["route"]
    assert first[0]["next_move"] == "g2g3"
    assert second[0]["next_move"] == "e2e3"
    assert first[0]["route_has_repeat"] is False


def test_reversible_loops_are_flagged_and_initial_position_is_excluded():
    rows = replay("1. Nf3 Nf6 2. Ng1 Ng8 3. d4 d5 4. c4", maximum=6)
    assert len(rows) == 1 and rows[0]["ply"] == 6
    assert rows[0]["route_has_repeat"] is True


def test_position_identity_preserves_castling_and_legal_en_passant():
    module = script("build_opening_positions")
    board = chess.Board()
    without_castling = board.copy()
    without_castling.castling_rights = 0
    assert module.position_key(board) != module.position_key(without_castling)
    no_capture = chess.Board("4k3/8/8/3p4/8/8/8/4K3 w - d6 0 1")
    no_capture.ep_square = None
    assert module.position_key(no_capture).endswith(" -")
    capture = chess.Board("4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 1")
    assert module.position_key(capture).endswith(" d6")


def test_wrong_source_identity_and_illegal_prefix_fail_closed():
    module = script("build_opening_positions")
    with pytest.raises(ValueError, match="identity"):
        chess.pgn.read_game(
            io.StringIO('[Site "https://lichess.org/other"]\n\n1. d4 *\n'),
            Visitor=lambda: module.OpeningVisitor(
                {"game_id": "abcd1234"}, {"min_ply": 6, "max_ply": 6}
            ),
        )
    with pytest.raises(ValueError):
        replay("1. d4 d5 2. Ke4")


def test_top_position_coverage_is_a_union_of_games():
    module = script("summarize_opening_positions")
    with duckdb.connect() as db:
        db.execute(
            "create table selected_visits(provider varchar,game_id varchar,position_id varchar)"
        )
        db.execute("insert into selected_visits values ('x','a','p'),('x','a','q'),('x','b','p')")
        assert module.coverage(db, [("p",), ("q",)]) == 2
        assert module.coverage(db, []) == 0
        curve = module.coverage_curve(db, [("p",), ("q",)], 3)
        assert curve == [
            {"n": 1, "games": 2, "share": 2 / 3, "additional_games": 2},
            {"n": 2, "games": 2, "share": 2 / 3, "additional_games": 0},
        ]


def miniature_corpus(root):
    import json

    from chess_analytics.common import digest

    snapshot_id = "a" * 24
    published = root / "data/openings/published" / snapshot_id
    published.mkdir(parents=True)
    source = root / "games.pgn"
    source.write_text(
        '[Site "https://lichess.org/abcd1234"]\n\n'
        "1. d4 Nf6 2. c4 e6 3. Nf3 d5 4. g3 *\n\n"
        '[Site "https://lichess.org/efgh5678"]\n\n'
        "1. d4 d5 2. c4 e6 3. Nf3 Nf6 4. e3 *\n"
    )
    with duckdb.connect(str(published / "warehouse.duckdb")) as db:
        db.execute("""create table opening_game(source_file varchar,source_ordinal integer,
            source_snapshot_id varchar,provider varchar,game_id varchar,source_cohort varchar,
            source_opening varchar,source_eco varchar)""")
        db.execute("""insert into opening_game values
            ('games.pgn',1,'s1','lichess','abcd1234','elite_reference','Queen''s Gambit: A','D30'),
            ('games.pgn',2,'s1','lichess','efgh5678','elite_reference','Queen''s Gambit: B','D35')
            """)
    manifest = {
        "snapshot_id": snapshot_id,
        "artifacts": {"warehouse.duckdb": digest(published / "warehouse.duckdb")},
        "sources": [{"source_file": "games.pgn", "source_sha256": digest(source)}],
        "counts": {"training_games": 2},
        "training_sources": [{"cohort": "elite_reference", "games": 2}],
    }
    (published / "manifest.json").write_text(json.dumps(manifest))
    (root / "data/opening-current.json").write_text(json.dumps({"snapshot_id": snapshot_id}))
    plan = {
        "min_ply": 6,
        "max_ply": 6,
        "learner_color": "white",
        "cohorts": ["elite_reference"],
        "minimum_free_bytes": 0,
        "max_output_bytes": 1000000,
        "published_positions_per_view": 20,
        "minimum_opening_games": 1,
    }
    return plan


def test_extraction_and_summary_keep_routes_labels_and_denominators(tmp_path):
    import json

    root = tmp_path / "corpus"
    plan = miniature_corpus(root)
    extract = script("build_opening_positions")
    summary = script("summarize_opening_positions")
    snapshot = extract.extract(root, tmp_path / "derived", plan)
    report = summary.summarize(snapshot, tmp_path / "report.json", plan)
    view = report["cohorts"]["elite_reference"]["views"]["all"]
    assert view["denominator_games"] == 2
    assert view["transposing_positions"] == 1
    position = next(iter(view["positions"].values()))
    assert position["games"] == 2 and position["frequency"] == 1
    assert position["acyclic_routes"] == 2
    assert position["acyclic_games"] == 2
    assert position["alternative_route_share"] == 0.5
    assert position["distinct_recorded_families"] == 1
    assert position["distinct_recorded_ecos"] == 2
    assert position["other_acyclic_route_games"] == 0
    assert {r["san"] for r in position["continuations"]} == {"g3", "e3"}
    assert {r["eco"] for r in position["opening_labels"]} == {"D30", "D35"}
    assert view["rankings"]["transposing"]["top_20_game_coverage"] == 2
    assert (
        report["cohorts"]["elite_reference"]["compression_by_ply"][0]["endpoint_compression"] == 0.5
    )
    checked = script("check_opening_insights").verify(
        snapshot, tmp_path / "report.json", tmp_path / "checked.json"
    )
    assert checked["passed"] and checked["checks"]["curve_points"] == 4
    assert extract.extract(root, tmp_path / "derived", plan) == snapshot
    manifest = json.loads((snapshot / "manifest.json").read_text())
    shard = snapshot / next(n for n in manifest["artifacts"] if n.endswith(".parquet"))
    shard.write_bytes(b"changed")
    with pytest.raises(ValueError, match="artifact hash"):
        extract.extract(root, tmp_path / "derived", plan)


def test_changed_corpus_and_source_bytes_block_extraction(tmp_path):
    root = tmp_path / "corpus"
    plan = miniature_corpus(root)
    extract = script("build_opening_positions")
    (root / "games.pgn").write_text("changed")
    with pytest.raises(ValueError, match="Source PGN hash"):
        extract.extract(root, tmp_path / "derived", plan)


def test_repeated_visit_counts_once_and_uses_its_first_continuation(tmp_path):
    import json

    from chess_analytics.common import digest

    root = tmp_path / "corpus"
    plan = miniature_corpus(root)
    plan["max_ply"] = 10
    source = root / "games.pgn"
    source.write_text(
        '[Site "https://lichess.org/abcd1234"]\n\n'
        "1. Nf3 Nf6 2. d4 d5 3. Nc3 Nc6 4. Nb1 Nb8 5. Nc3 Nc6 6. g3 *\n\n"
        '[Site "https://lichess.org/efgh5678"]\n\n'
        "1. d4 d5 2. Nf3 Nf6 3. Nc3 Nc6 4. g3 g6 5. Bg2 Bg7 *\n"
    )
    manifest_path = root / "data/openings/published" / ("a" * 24) / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["sources"][0]["source_sha256"] = digest(source)
    manifest_path.write_text(json.dumps(manifest))
    snapshot = script("build_opening_positions").extract(root, tmp_path / "derived", plan)
    summary = script("summarize_opening_positions")
    with pytest.raises(ValueError, match="Summary plan differs"):
        summary.summarize(snapshot, tmp_path / "report.json", {**plan, "min_ply": 8})
    report = summary.summarize(snapshot, tmp_path / "report.json", plan)
    positions = report["cohorts"]["elite_reference"]["views"]["all"]["positions"]
    shared = next(p for p in positions.values() if p["games"] == 2)
    assert shared["games"] == 2 and shared["acyclic_routes"] == 2
    assert {m["san"] for m in shared["continuations"]} == {"Nb1", "g3"}


def test_lenses_use_played_moves_not_provider_labels_and_include_pre_g3_boards():
    summary = script("summarize_opening_positions")
    lines = [
        "1.d4 Nf6 2.c4 e6 3.g3 d5 4.Bg2 Be7 5.Nf3 O-O 6.O-O c5 "
        "7.dxc5 Bxc5 8.Nc3 Nc6 9.Bg5 h6 10.Bxf6 Qxf6",
        "1.d4 Nf6 2.c4 g6 3.g3 Bg7 4.Bg2 d6 5.Nf3 O-O 6.O-O Nc6 "
        "7.Nc3 a6 8.h3 Rb8 9.Be3 b5 10.cxb5 axb5",
        "1.d4 Nf6 2.c4 e6 3.Nf3 d5 4.g3 Be7 5.Bg2 O-O 6.O-O c5 "
        "7.dxc5 Bxc5 8.Nc3 Nc6 9.Bg5 h6 10.Bxf6 Qxf6",
    ]
    lines.append(lines[2])
    with duckdb.connect() as db:
        db.execute("""create table visits(provider varchar,game_id varchar,cohort varchar,
            position_id varchar,position_key varchar,ply integer,route varchar,
            route_has_repeat boolean,next_move varchar,opening_family varchar,eco varchar)""")
        for i, line in enumerate(lines):
            for row in replay(line, maximum=20):
                db.execute(
                    "insert into visits values (?,?,?,?,?,?,?,?,?,?,?)",
                    [
                        "fixture",
                        str(i),
                        "elite_reference",
                        row["position_id"],
                        row["position_key"],
                        row["ply"],
                        row["route"],
                        row["route_has_repeat"],
                        row["next_move"],
                        "Unrelated provider label",
                        "X00",
                    ],
                )
        db.execute("""create table cohort_visits as select * from visits qualify
            row_number() over(partition by provider,game_id,position_id order by ply)=1""")
        views = summary.summarize_lenses(
            db,
            "elite_reference",
            {
                "max_ply": 20,
                "published_positions_per_view": 20,
            },
        )
        assert views["d4-g3"]["denominator_games"] == 4
        assert views["d4-g3-catalan"]["denominator_games"] == 3
        assert views["d4-g3-kings-indian"]["denominator_games"] == 1
        shared = next(
            p
            for p in views["d4-g3"]["positions"].values()
            if p["games"] == 2 and p["white_g3_played_games"] == 2
        )
        assert shared["distinct_recorded_families"] == 1
        assert any(
            p["white_g3_played_games"] < p["games"] for p in views["d4-g3"]["positions"].values()
        )


def test_route_balance_excludes_repetition_games_from_its_denominator():
    summary = script("summarize_opening_positions")
    route = "d2d4 d7d5"
    loop = "g1f3 g8f6 f3g1 f6g8 d2d4 d7d5"
    _, key = summary.san_route(route)
    with duckdb.connect() as db:
        db.execute("""create table detail_visits(position_id varchar,route varchar,
            route_has_repeat boolean,next_move varchar,opening_family varchar,eco varchar)""")
        db.execute("insert into detail_visits values ('p',?,false,'c2c4','Unknown',null)", [route])
        db.execute("insert into detail_visits values ('p',?,true,'c2c4','Unknown',null)", [loop])
        db.execute("insert into detail_visits values ('p',?,true,'c2c4','Unknown',null)", [loop])
        position = summary.position_details(db, ("p", key, 3, 1, 2), 3)
        assert position["alternative_route_share"] == 0
        assert position["routes"][0]["share"] == 1 / 3
        assert position["distinct_recorded_families"] == position["distinct_recorded_ecos"] == 0
        assert position["unknown_family_games"] == 3
        db.execute("delete from detail_visits where not route_has_repeat")
        position = summary.position_details(db, ("p", key, 2, 0, 2), 2)
        assert position["alternative_route_share"] is None
        assert position["acyclic_games"] == 0
