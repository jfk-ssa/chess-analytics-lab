"""Offline public export and independent browser parity against the hosted cube."""

import dataclasses
import hashlib
import json
import shutil
import subprocess
from datetime import date
from pathlib import Path

import duckdb
import pytest

from chess_analytics import dashboard_cube as cube
from chess_analytics import dashboard_export as export

ROOT = Path(__file__).resolve().parents[1]
WIDE = {"start": "2000-01-01", "end": "2100-01-01"}


@pytest.fixture(scope="module")
def published(tmp_path_factory):
    output = tmp_path_factory.mktemp("dashboard")
    sources = export.export_dashboard(ROOT, output, "test-revision")
    return json.loads((output / "dashboard.json").read_text()), sources


def browser(payload, requests):
    result = subprocess.run(
        ["node", "tests/js/dashboard_query.mjs"],
        cwd=ROOT,
        input=json.dumps({"payload": payload, "requests": requests}),
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def request(method, *args):
    return {"method": method, "args": args}


def filters(raw):
    return cube.Filters(
        date.fromisoformat(raw["start"]),
        date.fromisoformat(raw["end"]),
        *(raw.get(k) for k in ("time_control", "color", "rating_band", "opening_family")),
    )


def pages_kpis(con, raw):
    """Retain hosted arithmetic expectations with the Pages population/perspective copy."""
    cards = [dataclasses.asdict(k) for k in cube.kpis(con, filters(raw))]
    for card in cards:
        detail = card["detail"]
        if card["label"] == "Games":
            base, _, ignored = detail.partition(" · not by ")
            notes = ignored.split(", ") if ignored else []
            label = "rated public games in range"
            if "date" in notes:
                label = "full published rated-public window; date filter unavailable"
                notes.remove("date")
            card["detail"] = base.replace("games in range", label)
            if notes:
                card["detail"] += " · not by " + ", ".join(notes)
        elif card["label"] in {"Win rate", "Loss rate", "Draw rate"} and " / " in detail:
            count, separator, notes = detail.replace(" · White", "").partition(" · ")
            perspective = "Black" if raw.get("color") == "black" else "White"
            card["detail"] = f"{count} · {perspective} perspective{separator}{notes}"
    return cards


def test_every_supported_dimension_cut_matches_scoped_hosted(published):
    """Every published value, missing values and intersected cuts; all displayed sections."""
    payload, _ = published
    con = cube.connect(ROOT / export.CUBE)
    try:
        # The hosted implementation predates the Pages single-cohort boundary.
        # Scope its independent SQL oracle, keeping the browser payload unfiltered.
        con.execute("""
            create table pages_cube as select * from cube
            where cohort = case when grain in ('clock_slice', 'clock_game')
                then 'm3_august_prefix' else 'rated_public' end
        """)
        con.execute("create or replace view cube as select * from pages_cube")
        cuts = [
            WIDE,
            {"start": "2025-11-01", "end": "2025-11-30"},
            {"start": "2026-08-01", "end": "2026-08-01"},
        ]
        cuts.extend(
            {"start": start.isoformat(), "end": end.isoformat()}
            for start, end in con.execute(
                "select distinct period_start, period_end from cube where grain = ?", ["game_cell"]
            ).fetchall()
        )
        cuts.append({"start": "2000-01-01", "end": "2000-01-02"})
        for key in ("time_control", "rating_band", "opening_family"):
            cuts.extend(
                {**WIDE, key: value} for value in [*cube.dimension_values(con, key), "absent"]
            )
        cuts.extend({**WIDE, "color": color} for color in ("white", "black", "absent"))
        cuts.extend(
            {
                **WIDE,
                "time_control": control,
                "color": color,
                "rating_band": rating,
                "opening_family": family,
            }
            for control, color, rating, family in (
                ("180+0", "black", "1600_1999", "Sicilian Defense"),
                ("60+0", "white", "1200_1599", "French Defense"),
                ("absent", "black", "2000_plus", "absent"),
            )
        )
        requests, expected = [], []
        for raw in cuts:
            f = filters(raw)
            requests.append(request("kpis", raw))
            expected.append(pages_kpis(con, raw))
            requests.append(request("clock", raw))
            bands, caption, tag = cube.clock_display(con, f)
            expected.append({"rows": bands, "caption": caption, "tag": tag})
            requests.append(request("openings", raw))
            cohort, covered = cube.position_cohort(con, f)
            expected.append({"rows": cube.opening_families(con, f, cohort, dates=covered)})
            requests.append(request("transpositions", raw))
            rows, caption = cube.transpositions(con, f)
            expected.append({"rows": rows, "caption": caption})
            requests.append(request("periods", raw))
            expected.append({"rows": cube.month_bars(con, f)})
        actual = browser(payload, requests)
        expected = json.loads(json.dumps(expected, default=str))
        for req, want, got in zip(requests, expected, actual, strict=True):
            for key, value in want.items() if isinstance(want, dict) else [(None, want)]:
                observed = got[key] if key else got
                # FEN is absent rather than null after sparse decoding.
                assert observed == value, (req, key, observed, value)
    finally:
        con.close()


def test_default_public_population_on_committed_cube(published):
    payload, _ = published
    start, end = browser(payload, [request("bounds")])[0]
    assert (start, end) == ("2025-12-01", "2026-08-01")
    for cut in ({"start": start, "end": end}, WIDE):
        cards, periods = browser(payload, [request("kpis", cut), request("periods", cut)])
        assert cards[0]["value"] == "770,626"
        assert "rated public" in cards[0]["detail"]
        assert [row["label"] for row in periods["rows"]] == [
            "2025-12",
            *(f"2026-{month:02}" for month in range(1, 9)),
        ]
        assert sum(row["games"] for row in periods["rows"]) == 802260


def test_opening_drills_and_clock_sample_parity(published):
    payload, _ = published
    con = cube.connect(ROOT / export.CUBE)
    try:
        f = filters(WIDE)
        cohort, covered = cube.position_cohort(con, f)
        families = cube.opening_families(con, f, cohort, dates=covered)
        requests, expected = [], []
        for family in families[:8]:
            name = family["label"]
            lines = cube.opening_lines(con, f, cohort, name, dates=covered)
            requests.append(request("openings", WIDE, {"family": name}))
            expected.append(lines)
            for line in lines[:2]:
                fen = line["fens"][0]
                requests.append(
                    request("openings", WIDE, {"family": name, "line": line["label"], "fen": fen})
                )
                expected.append(cube.continuations(con, f, cohort, name, fen, dates=covered))
        actual = browser(payload, requests)
        for want, got in zip(expected, actual, strict=True):
            assert got["rows"] == want
        requests, expected = [], []
        for band in cube.CLOCK_BANDS:
            for cut in [
                WIDE,
                {**WIDE, "color": "black"},
                {**WIDE, "rating_band": "1200_1599"},
                {**WIDE, "opening_family": "Sicilian Defense"},
                {**WIDE, "time_control": "180+0"},
                {**WIDE, "time_control": "absent"},
                {"start": "2025-11-01", "end": "2025-11-30"},
            ]:
                for limit in (1, 12):
                    rows, total, _ = cube.clock_games(con, filters(cut), band, limit=limit)
                    requests.append(request("clockGames", cut, band, limit))
                    expected.append((rows, total))
        for (rows, total), got in zip(expected, browser(payload, requests), strict=True):
            assert got["rows"] == json.loads(json.dumps(rows, default=str))
            assert got["total"] == total
            assert len(got["rows"]) <= 12
            assert "evaluable moves, not games" in got["caption"]
    finally:
        con.close()


def test_scoped_provenance_and_compact_public_fields(published):
    payload, sources = published
    c, e = sources[export.CUBE], sources[export.EXTRACT]
    assert c["row_count"] == sum(c["grain_counts"].values()) == 35100
    assert c["site_source_revision"] == "test-revision"
    assert "mart_id" not in c and "build" not in c
    assert e["game_draw_rate_mart_id"] and e["build"]["source_snapshot_id"]
    for name, record in sources.items():
        assert record["sha256"] == hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
    assert "not cube-wide lineage" in e["scope"]
    assert len(json.dumps(payload)) < 4_000_000
    for grain, table in payload["grains"].items():
        assert set(table["columns"]) <= set(cube.COLUMNS)
        if grain != "clock_game":
            assert not {"lichess_id", "white_rating", "black_rating"} & set(table["columns"])


@pytest.fixture
def inputs(tmp_path):
    for name in (export.CUBE, export.EXTRACT):
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    return tmp_path


@pytest.mark.parametrize("name", [export.CUBE, export.EXTRACT])
def test_missing_invalid_and_symlink_inputs_fail(inputs, name):
    path = inputs / name
    path.unlink()
    with pytest.raises(ValueError, match="missing"):
        export.export_dashboard(inputs, inputs / "out", "test")
    path.write_text("invalid")
    with pytest.raises((ValueError, duckdb.Error)):
        export.export_dashboard(inputs, inputs / "out", "test")
    path.unlink()
    path.symlink_to(ROOT / name)
    with pytest.raises(ValueError, match="symlink"):
        export.export_dashboard(inputs, inputs / "out", "test")


def test_public_field_boundary_and_floor(inputs):
    con = cube.connect(inputs / export.CUBE)
    rows = [
        dict(zip(cube.COLUMNS, row, strict=True))
        for row in con.execute("select * from cube limit 1").fetchall()
    ]
    con.close()
    for change in [
        {"username": "name"},
        {"games": 9},
        {"lichess_id": "abcdefgh"},
        {"opening_line": "username leaked"},
    ]:
        with pytest.raises(ValueError):
            export._validate([{**rows[0], **change}])
    con = duckdb.connect()
    con.execute("create table bad as select * from read_parquet(?)", [str(inputs / export.CUBE)])
    con.execute("alter table bad add column username varchar")
    path = inputs / export.CUBE
    path.unlink()
    con.execute("copy bad to ? (format parquet)", [str(path)])
    con.close()
    with pytest.raises(ValueError, match="allowlist"):
        export.export_dashboard(inputs, inputs / "out", "test")


@pytest.mark.parametrize("name", [export.CUBE, export.EXTRACT])
def test_each_input_changes_the_recorded_hash_and_generated_json(inputs, name):
    output = inputs / "out"
    before = export.export_dashboard(inputs, output, "test")
    old = (output / "dashboard.json").read_bytes()
    if name == export.EXTRACT:
        with (inputs / name).open("a") as handle:
            handle.write("\n")
    else:
        path = inputs / name
        con = duckdb.connect()
        con.execute("create table changed as select * from read_parquet(?)", [str(path)])
        con.execute("update changed set games = games + 10 where grain = 'game_cell'")
        path.unlink()
        con.execute("copy changed to ? (format parquet)", [str(path)])
        con.close()
    after = export.export_dashboard(inputs, output, "test")
    assert after[name]["sha256"] != before[name]["sha256"]
    other = export.CUBE if name == export.EXTRACT else export.EXTRACT
    assert after[other] == before[other]
    assert (output / "dashboard.json").read_bytes() != old


def test_unsupported_grain_captions_and_empty_cuts(published):
    payload, _ = published
    cut = {**WIDE, "color": "black", "time_control": "180+0", "rating_band": "2000_plus"}
    opening, trans, clock, periods, empty = browser(
        payload,
        [
            request("openings", cut),
            request("transpositions", cut),
            request("clock", cut),
            request("periods", cut),
            request("periods", {"start": "2000-01-01", "end": "2000-01-02"}),
        ],
    )
    assert "not split by color, time control, or rating" in opening["caption"]
    assert "not split by color, time control, or rating" in trans["caption"]
    assert "not split by color" in clock["caption"]
    assert "Period totals are not split by color, time control, or rating" in periods["caption"]
    assert not empty["rows"]
    assert "No published period" in empty["caption"]


def test_kpi_prior_period_deltas_match_python_on_fixture(inputs):
    rows = []
    for period, games, wins, diff, length in [
        ("2026-07", 100, 30, -7.25, 50),
        ("2026-08", 200, 100, -3.25, 60),
    ]:
        for grain in ("game_cell", "result_cell"):
            rows.append(
                cube._row(
                    grain=grain,
                    cohort="rated_public",
                    period=period,
                    period_start=date.fromisoformat(period + "-01"),
                    period_end=date.fromisoformat(period + "-31"),
                    time_control="180+0",
                    color="white" if grain == "result_cell" else None,
                    rating_band="1600_1999" if grain == "result_cell" else None,
                    opening_family="Sicilian Defense",
                    games=games,
                    wins=wins,
                    losses=games - wins - 10,
                    draws=10,
                    rating_diff=diff,
                    mean_ply=length,
                )
            )
    path = inputs / export.CUBE
    path.unlink()
    cube.write_cube(rows, path)
    export.export_dashboard(inputs, inputs / "out", "fixture")
    payload = json.loads((inputs / "out/dashboard.json").read_text())
    cut = {"start": "2026-08-01", "end": "2026-08-31"}
    got = browser(payload, [request("kpis", cut)])[0]
    con = cube.connect(path)
    try:
        expected = pages_kpis(con, cut)
    finally:
        con.close()
    # No position grain is published in this fixture; compare all six comparable KPIs.
    labels = {"Games", "Win rate", "Loss rate", "Draw rate", "Rating diff", "Game length"}
    assert [k for k in got if k["label"] in labels] == [k for k in expected if k["label"] in labels]
    assert all("vs prior" in k["detail"] for k in got if k["label"] in labels)


@pytest.mark.parametrize("field", ["extract_version", "build", "tables"])
def test_invalid_extract_records_fail_closed(inputs, field):
    path = inputs / export.EXTRACT
    body = json.loads(path.read_text())
    body[field] = None
    path.write_text(json.dumps(body))
    with pytest.raises(ValueError):
        export.export_dashboard(inputs, inputs / "out", "test")


def test_input_change_during_export_fails_closed(inputs, monkeypatch):
    original = export.byte_hash
    calls = 0

    def changed(path):
        nonlocal calls
        calls += 1
        return "0" * 64 if calls == 3 else original(path)

    monkeypatch.setattr(export, "byte_hash", changed)
    with pytest.raises(ValueError, match="changed during export"):
        export.export_dashboard(inputs, inputs / "out", "test")
    assert not (inputs / "out/dashboard.json").exists()


def test_static_layout_contract_at_desktop_and_phone():
    """Check CSS/template tokens and assumed track widths, not rendered browser layout."""
    css = (ROOT / "site/assets/dashboard.css").read_text()
    site_css = (ROOT / "site/assets/site.css").read_text()
    template = (ROOT / "scripts/templates/dashboard.html.j2").read_text()
    assert "--page-width: 1120px" in site_css
    assert "repeat(4, minmax(0, 1fr))" in css
    assert "@media (max-width: 600px)" in css
    assert "repeat(2, minmax(0, 1fr))" in css
    assert "white-space: nowrap" in css and "overflow-wrap: normal" in css
    assert "overflow: hidden" not in css and "rotate(" not in css
    assert "@font-face" not in css and not __import__("re").search(r"#[0-9a-fA-F]{3,8}\b", css)
    for token in ("--paper", "--ink", "--teal", "--accent", "--line"):
        assert f"var({token})" in css
    assert "From<input" in template and "Through<input" in template
    # Static track calculation under the assumed viewport, padding and gap values.
    for width, padding, columns, gap in ((1280, 28, 4, 16), (390, 18, 2, 10)):
        track = (min(width, 1120) - padding * 2 - gap * (columns - 1)) / columns
        assert track >= 160
