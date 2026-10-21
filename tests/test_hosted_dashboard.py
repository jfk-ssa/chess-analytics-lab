"""AppTest for the hosted dashboard. Offline; no warehouse."""

import hashlib
import json
import re
from html import escape

import pytest

from chess_analytics.public_extract import extract_path, load_extract, table_rows


def _visible(app) -> str:
    parts: list[str] = []
    blocks = (
        app.title,
        app.header,
        app.subheader,
        app.markdown,
        app.caption,
        app.text,
        app.metric,
        app.error,
        app.warning,
        app.info,
    )
    for block in blocks:
        for item in block:
            parts.append(str(item.value))
    for item in app.table:
        parts.append(item.value.to_csv(index=False))
    return "\n".join(parts)


def _run(project, monkeypatch):
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv(
        "CHESSLAB_PUBLIC_EXTRACT",
        str(project / "data" / "public" / "dashboard_extract.json"),
    )
    app = AppTest.from_file(str(project / "hosted" / "dashboard.py"), default_timeout=60).run()
    return app


def test_hosted_font_matches_the_dashboard_font(project):
    hosted = project / "hosted" / "static" / "fonts"
    source = project / "src" / "chess_analytics" / "dashboard" / "static" / "fonts"
    for name in ("inter-latin-wght-normal.woff2", "LICENSE.inter.txt"):
        assert (
            hashlib.sha256((hosted / name).read_bytes()).digest()
            == hashlib.sha256((source / name).read_bytes()).digest()
        )


def _lock_version(lock_text: str, name: str) -> str:
    saw_name = False
    for line in lock_text.splitlines():
        if line == f'name = "{name}"':
            saw_name = True
            continue
        if saw_name and line.startswith("version = "):
            return line.split("=", 1)[1].strip().strip('"')
        if saw_name and line.startswith("name = "):
            break
    raise AssertionError(name)


def test_hosted_streamlit_pin_matches_the_lock(project):
    requirements = [
        line.strip()
        for line in (project / "hosted" / "requirements.txt").read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]
    assert requirements == [
        "streamlit==1.65.0",
        "altair==5.5.0",
        "narwhals==2.26.0",
        "jsonschema==4.26.0",
        "pandas==2.3.3",
        "protobuf==6.33.6",
        "duckdb==1.5.6",
    ]
    assert "streamlit==1.65.0" in (project / "pyproject.toml").read_text()
    assert "1.65.0" in (project / "THIRD_PARTY_NOTICES.md").read_text()
    lock_text = (project / "uv.lock").read_text()
    for pin in requirements:
        name, version = pin.split("==")
        assert _lock_version(lock_text, name) == version


def test_hosted_dashboard_renders_the_committed_extract(project, monkeypatch):
    app = _run(project, monkeypatch)
    assert not app.exception, [item.message for item in app.exception]
    assert not app.error
    assert not app.file_uploader
    assert not app.text_input
    assert not app.text_area
    assert not app.chat_input
    assert [item.label for item in app.button] == ["Reset filters"]
    assert len(app.date_input) == 1
    assert app.date_input[0].label == "Date range"
    labels = {item.label: list(item.options) for item in app.selectbox}
    assert set(labels) == {
        "Time control",
        "Color",
        "Rating band",
        "Opening family",
        "Board",
    }
    assert "Top positions" in labels["Board"]
    titled = [option for option in labels["Board"] if option != "Top positions"]
    assert titled
    assert all("After Black's move " in option for option in titled)
    assert any("1.e4\u00a0c5" in option for option in titled)
    assert len(titled) == len(set(titled))
    assert labels["Color"] == ["All", "White", "Black"]
    assert "French Defense" in labels["Opening family"]
    assert "Sicilian Defense" in labels["Opening family"]
    text = re.sub(r"<[^>]+>", "", _visible(app))
    assert "1 over-abstentions" not in text
    extract = load_extract(extract_path(project))
    receipts = {row["receipt_id"]: row for row in table_rows(extract, "metric_receipt")}
    draw = receipts["game_draw_rate"]
    path = extract_path(project)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    expected = (
        "1,042,346",
        "1,009,445",
        "warehouse",
        "49.2%",
        "476,741 / 968,874 · White",
        "5.1%",
        "49,271 / 968,874 · White",
        "45.7%",
        "442,862 / 968,874 · White",
        "9.3%",
        "2,128 / 22,978",
        "+0.1",
        "72.8",
        "warehouse cells of at least 10 games",
        "Most common transpositions",
        "Distinct acyclic move orders",
        "rated public",
        "99,467",
        "100,000",
        "533",
        "342",
        "86.3%",
        "97.5%",
        "97.1%",
        "gpt-6-luna and grok-4.7 · low clear; gpt-6-sol hard-fails",
        "boundary_budget is 0 of 5",
        "25 over-abstentions",
        "6 over-abstentions",
        "1 over-abstention",
        "not strictly comparable",
        "45/48",
        "47/48",
        "06bc03a3eabab5bbf3b958ec",
        "bea194558220eb669940d8f3",
        "coverage_1",
        "coverage_2",
        "indirect_opening_1",
        "share frozen inputs",
        "not compared",
        "all three 1-repeat runs",
        "repeat count both differ",
        "14,768",
        "\\$0.22253",
        "\\$0.322454",
        "\\$0.408746",
        draw["mart_id"],
        extract["build"]["source_snapshot_id"],
        extract["build"]["model_sha256"],
        extract["build"]["lock_sha256"],
        extract["build"]["semantic_manifest_sha256"],
        digest,
        "nikonoel",
        "Date 2025-11-01–2026-08-01 · Time All · Color All · Rating All · Opening All",
    )
    missing = [item for item in expected if item not in text]
    assert not missing, missing
    assert "Receipt not in yet." not in text
    assert "The 1-repeat low run is not in this test." not in text
    _assert_section_origins(app)
    _assert_live_eval_link(app)
    _assert_build_table_omits_the_figure_id(app, extract)
    _assert_alt_text(app)
    _assert_equal_width_markup(app)
    for table in app.table:
        assert len(table.value.columns) <= 3


def _chart_alts(app) -> list[str]:
    return [node.proto.alt for node in app if getattr(node, "type", None) == "vega_lite_chart"]


def _caption(app, fragment: str) -> str:
    matches = [item.value for item in app.caption if fragment in item.value]
    assert len(matches) == 1, matches
    return matches[0]


def test_cost_captions_keep_a_literal_dollar(project, monkeypatch):
    app = _run(project, monkeypatch)
    caption = _caption(app, "Known cost")
    visible = caption.replace(r"\$", "$")
    assert "gpt-6-luna $0.0150, grok-4.7 · low $1.0033, gpt-6-sol $0.2550" in visible
    assert "gpt-6-luna and gpt-6-sol do not overlap" in visible
    assert "gpt-6-luna and gpt-6-sol share frozen inputs" in visible
    assert "grok-4.7 · low does not" in visible
    assert "its interval is not compared with theirs" in visible
    assert "grok-4.7 · low overlap" not in visible
    assert "grok-4.7 · low do not overlap" not in visible
    for item in app.caption:
        assert "$" not in item.value.replace(r"\$", "")
    cards = "\n".join(item.value for item in app.markdown if "cal-card" in item.value)
    for amount in ("&#36;0.0150", "&#36;0.2550", "&#36;1.0033", "&#36;0.5000", "&#36;10.0000"):
        assert amount in cards
    assert "$" not in cards
    assert r"\$" not in cards


def _assert_live_eval_link(app) -> None:
    caption = _caption(app, "Published live-eval report")
    assert "https://jfk-ssa.github.io/chess-analytics-lab/live-eval.html" in caption


def _assert_section_origins(app) -> None:
    openings = _caption(app, "Published positions only")
    assert "Query origin:" not in openings
    clock = _caption(app, "not a game")
    assert clock.startswith("Reviewed SQL.")
    assert "metricflow" not in clock
    periods = _caption(app, "one published period")
    assert "Query origin:" not in periods
    assert "warehouse cells of at least 10 games" in periods
    lineage = _caption(app, "lineages separately")
    assert "Query origin: committed_report" in lineage
    assert "metricflow" not in lineage
    assert "reviewed_sql" not in lineage


def _field_table(app, field: str):
    matches = [
        table
        for table in app.table
        if "Field" in table.value.columns and field in set(table.value["Field"])
    ]
    assert len(matches) == 1
    return matches[0].value


def _assert_build_table_omits_the_figure_id(app, extract) -> None:
    figure_ids = {
        row["analytical_id"]
        for name in ("opening_family_share", "opening_score_cell", "clock_bucket")
        for row in table_rows(extract, name)
    }
    assert figure_ids == {"84a38a404815ed2729917d76"}
    figure_id = next(iter(figure_ids))
    snapshot = extract["build"]["source_snapshot_id"]
    assert figure_id != snapshot
    build = _field_table(app, "Mart id")
    assert list(build["Field"]) == [
        "Mart id",
        "Source snapshot",
        "Model sha256",
        "Lock sha256",
        "Semantic manifest sha256",
        "Extract sha256",
    ]
    rendered = build.to_csv(index=False)
    assert figure_id not in rendered
    assert "analytical_id" not in rendered
    assert "Analytical id" not in rendered
    figure = _field_table(app, "analytical_id")
    assert list(figure["Value"]) == [figure_id]
    caption = _caption(app, "committed rows of opening_family_share")
    assert "opening_score_cell" in caption
    assert "clock_bucket" in caption
    assert "is not build.source_snapshot_id" in caption
    assert "different publication" in caption
    assert snapshot not in caption


def _assert_alt_text(app) -> None:
    assert app.table
    for table in app.table:
        assert isinstance(table.proto.alt, str) and table.proto.alt.strip()
    charts = [node for node in app if getattr(node, "type", None) == "vega_lite_chart"]
    alts = [node.proto.alt for node in charts]
    assert all(isinstance(item, str) and item.strip() for item in alts)
    expected = (
        "Opening families by games. Select a bar to drill into lines.",
        "Clock bands by evaluable moves. Select a bar to list the slices in that band.",
        "Training games by published period.",
        "Headline pass rate for each model with its Wilson 95 percent interval.",
        "Dumbbell of pass rate by category. Each point is one model.",
        "Grid of cases by model, colored by how many repeats passed.",
        (
            "Grok reasoning-effort pass rates with Wilson 95 percent intervals. "
            "Low, medium, and high are 1-repeat runs on the same instructions."
        ),
    )
    assert alts == list(expected)


_TRACKS = "repeat(auto-fill,minmax(min(100%,256px),1fr))"


def _assert_equal_width_markup(app) -> None:
    markup = "\n".join(item.value for item in app.markdown)
    for count in (3, 6, 8):
        assert f'data-cards="{count}"' in markup
    assert _TRACKS in markup
    assert "white-space:nowrap" in markup
    assert "overflow-wrap:anywhere" not in markup
    assert "auto-fit,minmax(0,1fr)" not in markup


def _load_hosted(project, name: str):
    import importlib.util

    path = project / "hosted" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"hosted_{name}_contract", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _scale_domains(spec: dict) -> list:
    found: list = []

    def walk(node) -> None:
        if isinstance(node, dict):
            scale = node.get("scale")
            if isinstance(scale, dict) and "domain" in scale:
                found.append(scale["domain"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(spec)
    return found


def test_san_groups_keep_each_move_pair_together(project):
    module = _load_hosted(project, "layout")
    assert module.san_groups("1.e4 c5 2.Nf3 Nc6 3.d4 cxd4") == [
        "1.e4 c5",
        "2.Nf3 Nc6",
        "3.d4 cxd4",
    ]
    assert module.san_groups("1.e4 c5 2.Nf3 d6 3.Nf3 d6") == [
        "1.e4 c5",
        "2.Nf3 d6",
        "3.Nf3 d6",
    ]
    assert module.san_groups("1.e4 c5 2.Nf3 Nc6 3.Bc4") == [
        "1.e4 c5",
        "2.Nf3 Nc6",
        "3.Bc4",
    ]
    assert module.san_text("3.d4 cxd4") == "3.d4\u00a0cxd4"
    html = module.transposition_cards(
        [
            {
                "title": "After Black's move 3 · 1.e4 c5 2.Nf3 Nc6 3.Bc4",
                "games": 40,
                "move_orders": 2,
                "routes": [
                    ("1.e4 c5 2.Nf3 Nc6 3.Bc4", 30),
                    ("1.e4 c5 2.d4 cxd4 3.Nf3 d6", 10),
                ],
            }
        ]
    )
    assert 'white-space:nowrap">3.Bc4<' in html
    assert 'white-space:nowrap">3.Nf3 d6<' in html
    assert 'white-space:nowrap">2.Nf3 Nc6<' in html
    assert 'white-space:nowrap">d6<' not in html
    assert "</span> <span" in html
    assert "</span>\u00a0<span" not in html


def test_time_control_sort_keeps_a_value_without_an_increment(project):
    pytest.importorskip("streamlit")
    module = _load_hosted(project, "bi")
    ordered = sorted(["180+2", "-", "60+0", "15+0", "180+0"], key=module._time_sort_key)
    assert ordered == ["15+0", "60+0", "180+0", "180+2", "-"]


def test_equal_width_rows_share_one_track_definition(project):
    module = _load_hosted(project, "layout")
    for count in range(1, 9):
        assert module.equal_width_columns(count) == _TRACKS
        cards = [(f"Label {index}", f"Value {index}", f"Detail {index}") for index in range(count)]
        html = module.equal_width_row(cards)
        assert f'data-cards="{count}"' in html
        assert f"grid-template-columns:{_TRACKS}" in html
        assert html.count('class="cal-card"') == count
        assert html.count('class="cal-v"') == count
        assert html.count("white-space:nowrap") == 3 * count
        assert 'class="cal-d"' in html
        detail_style = html.split('class="cal-d"', 1)[1].split(">", 1)[0]
        assert "white-space:nowrap" not in detail_style
        assert "overflow-wrap:anywhere" not in html
        assert "minmax(min(100%,256px),1fr)" in html
    with pytest.raises(ValueError, match="at least one card"):
        module.equal_width_columns(0)
    with pytest.raises(ValueError, match="at least one card"):
        module.equal_width_columns(True)
    board = module.transposition_cards(
        [
            {
                "family": "French Defense",
                "title": "After Black's move 2 · 1.e4 e6 2.d4 d5",
                "games": 1200,
                "move_orders": 2,
                "routes": [("1.e4 e6 2.d4 d5", 700), ("1.d4 d5 2.e4 e6", 500)],
            },
            {
                "family": "Sicilian Defense",
                "title": "After Black's move 5 · 1.e4 c5 2.Nf3 d6 3.d4 cxd4 4.Nxd4 Nf6 5.Nc3 a6",
                "games": 2530,
                "move_orders": 3,
                "routes": [
                    ("1.e4 c5 2.Nf3 d6 3.d4 cxd4 4.Nxd4 Nf6 5.Nc3 a6", 2253),
                ],
            },
        ]
    )
    assert 'data-cards="2"' in board
    assert f"grid-template-columns:{_TRACKS}" in board
    assert "grid-template-columns:6ch minmax(0,1fr)" in board
    assert "min-height:2.9em" in board
    assert board.count('class="cal-v"') == 2
    assert board.count('class="cal-share"') == 3
    assert board.count("white-space:nowrap") >= 4
    assert "overflow-wrap:anywhere" not in board
    assert "word-break:break-all" not in board
    assert "1,200" in board
    for pair in ("1.e4 e6", "2.d4 d5", "1.d4 d5", "2.e4 e6"):
        assert f'white-space:nowrap">{pair}<' in board
    for pair in ("1.e4 c5", "2.Nf3 d6", "3.d4 cxd4", "4.Nxd4 Nf6", "5.Nc3 a6"):
        assert f'white-space:nowrap">{pair}<' in board
    assert 'white-space:nowrap">4.Nxd4<' not in board
    assert 'white-space:nowrap">cxd4<' not in board
    assert escape("After Black's move 2") in board
    assert escape("After Black's move 5") in board
    assert " games" in board and "2 move orders" in board
    assert "position games" in board
    assert "width:58.3%" in board
    assert "width:100.0%" in board
    assert "width:89.1%" not in board
    assert board.index("After Black") < board.index("1,200")
    wrapped = module.equal_width_row([("Win rate", "49.2%", "476,741 / 968,874 · White")])
    assert 'white-space:nowrap">476,741 / 968,874<' in wrapped
    assert 'white-space:nowrap">476,741 / 968,874 · White<' not in wrapped
    marked = module.transposition_cards(
        [
            {
                "title": "After Black's move 2 · 1.e4 e6 2.d4 d5",
                "games": 40,
                "kept_games": 23,
                "move_orders": 2,
                "routes": [("1.e4 e6 2.d4 d5", 12), ("1.e4 e6 2.d4", 11)],
            }
        ]
    )
    assert "width:52.2%" in marked
    assert "width:47.8%" in marked
    assert "position games" in marked


def _chart_spec(node) -> dict:
    spec = getattr(node, "spec", None)
    if isinstance(spec, dict):
        return spec
    raw = node.proto.spec
    if isinstance(raw, str):
        return json.loads(raw)
    if isinstance(raw, bytes):
        return json.loads(raw.decode())
    return dict(raw)


def _y_sorts(spec: dict) -> list:
    found: list = []

    def walk(node) -> None:
        if isinstance(node, dict):
            encoding = node.get("encoding")
            if isinstance(encoding, dict):
                channel = encoding.get("y")
                if isinstance(channel, dict) and "sort" in channel:
                    found.append(channel["sort"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(spec)
    return found


def test_sweep_cards_and_chart_name_the_effort(project, monkeypatch):
    """Sweep titles are model and effort. The chart rows run low, medium, high."""
    app = _run(project, monkeypatch)
    cards = [
        item.value
        for item in app.markdown
        if "cal-card" in item.value and "45/48" in item.value and "47/48" in item.value
    ]
    assert len(cards) == 1
    labels = re.findall(r'class="cal-k"[^>]*>([^<]+)', cards[0])
    assert labels == ["grok-4.7 · low", "grok-4.7 · medium", "grok-4.7 · high"]
    assert "(" not in "".join(labels)
    assert "1f45f2" not in cards[0]
    charts = [node for node in app if getattr(node, "type", None) == "vega_lite_chart"]
    sweep = [node for node in charts if "Low, medium, and high" in node.proto.alt]
    assert len(sweep) == 1
    sorts = _y_sorts(_chart_spec(sweep[0]))
    assert sorts
    assert all(item == ["low", "medium", "high"] for item in sorts)
    caption = _caption(app, "outside this comparison")
    assert "different instruction hash, stays the headline" in caption
    assert "low $0.22253, medium $0.322454, high $0.408746" in caption.replace(r"\$", "$")
    assert "(1f45f2)" not in caption
    assert "(aded2b)" not in caption
    visible = _visible(app)
    assert "Of 48 cases" in visible
    assert "low ×5 versus low ×1" in visible
    tables = [
        table for table in app.table if list(table.value.columns) == ["Case", "Effort", "Result"]
    ]
    assert len(tables) == 1
    assert set(tables[0].value["Effort"]) == {"low", "medium", "high"}


def test_category_dumbbell_is_unstacked_on_a_unit_axis(project):
    pytest.importorskip("altair")
    charts = _load_hosted(project, "charts")
    chart = charts.category_dumbbell(
        [
            {"category": "coverage", "model": "gpt-6-luna", "rate": 0.25, "passed_label": "5 / 20"},
            {"category": "coverage", "model": "gpt-6-sol", "rate": 1.0, "passed_label": "20 / 20"},
            {"category": "boundary", "model": "gpt-6-luna", "rate": 1.0, "passed_label": "25 / 25"},
            {"category": "boundary", "model": "gpt-6-sol", "rate": 0.8, "passed_label": "20 / 25"},
        ],
        category_order=["coverage", "boundary"],
    )
    spec = chart.to_dict()
    layers = spec["layer"]
    marks = []
    for layer in layers:
        mark = layer["mark"]
        marks.append(mark["type"] if isinstance(mark, dict) else mark)
    assert marks == ["rule", "point"]
    blob = json.dumps(spec)
    assert "xOffset" not in blob
    assert '"stack": "zero"' not in blob
    assert [0, 1] in _scale_domains(spec)
    for layer in layers:
        encoding = layer["encoding"]
        for channel in ("x", "x2"):
            if channel not in encoding:
                continue
            stacked = encoding[channel].get("stack")
            assert stacked in (None, "none")


def test_chart_scales_follow_the_plotted_data(project):
    pytest.importorskip("altair")
    charts = _load_hosted(project, "charts")
    heat = charts.heatmap(
        [
            {
                "rating_band": "Under 1200",
                "time_control": "480+0",
                "error_proxy_rate": 0.405,
                "evaluable_moves": 10,
                "rate_label": "40.5%",
                "coverage_label": "1%",
            },
            {
                "rating_band": "2000+",
                "time_control": "60+0",
                "error_proxy_rate": 0.05,
                "evaluable_moves": 10,
                "rate_label": "5%",
                "coverage_label": "1%",
            },
            {
                "rating_band": "2000+",
                "time_control": "480+0",
                "error_proxy_rate": None,
                "evaluable_moves": 0,
                "rate_label": "none",
                "coverage_label": "none",
            },
        ],
        x_order=["60+0", "480+0"],
        y_order=["Under 1200", "2000+"],
    )
    assert [0.05, 0.405] in _scale_domains(heat.to_dict())
    scores = charts.score_intervals(
        [
            {
                "family": "French Defense",
                "series": "White, raw",
                "rate": 0.419,
                "low": None,
                "high": None,
                "rate_label": "41.9%",
                "interval_label": "not published",
                "support_label": "no",
            },
            {
                "family": "French Defense",
                "series": "Black, adjusted",
                "rate": 0.503,
                "low": 0.447,
                "high": 0.561,
                "rate_label": "50.3%",
                "interval_label": "44.7%–56.1%",
                "support_label": "no",
            },
        ]
    )
    assert [0, 1] in _scale_domains(scores.to_dict())
    wilson = charts.wilson(
        [
            {
                "label": "gpt-6-luna",
                "pass_rate": 0.8625,
                "wilson_low": 0.813,
                "wilson_high": 0.900,
                "gate": "Gate clear",
                "rate_label": "86.3%",
                "wilson_label": "81.3%–90.0%",
                "cost_label": "$0.0150",
            }
        ]
    )
    assert [0, 1] in _scale_domains(wilson.to_dict())
    grid = charts.case_grid(
        [
            {
                "case_id": "boundary_budget",
                "model": "gpt-6-sol",
                "passed": 0,
                "repeats": 5,
                "category": "boundary",
                "severity": "high",
            }
        ],
        case_order=["boundary_budget"],
        model_order=["gpt-6-sol"],
    )
    grid_spec = grid.to_dict()
    grid_marks = [
        layer["mark"]["type"] if isinstance(layer["mark"], dict) else layer["mark"]
        for layer in grid_spec["layer"]
    ]
    assert grid_marks == ["rect", "text"]
    assert "#b0892e" not in json.dumps(grid_spec)
    assert "#c4552a" not in json.dumps(grid_spec)


def test_hosted_dashboard_fails_closed_when_the_extract_is_missing(project, tmp_path, monkeypatch):
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    monkeypatch.delenv("CHESSLAB_PUBLIC_EXTRACT", raising=False)
    monkeypatch.chdir(tmp_path)
    app = AppTest.from_file(str(project / "hosted" / "dashboard.py"), default_timeout=60).run()
    assert not app.exception, [item.message for item in app.exception]
    assert not app.table
    assert not app.metric
    message = " ".join(item.value for item in app.error)
    assert "Public extract unavailable" in message
    assert "public extract not found" in message


def test_hosted_dashboard_renders_the_cube_when_the_extract_is_invalid(
    project, tmp_path, monkeypatch
):
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    invalid = tmp_path / "dashboard_extract.json"
    invalid.write_text(json.dumps({"extract_version": "0"}))
    monkeypatch.setenv("CHESSLAB_PUBLIC_EXTRACT", str(invalid))
    app = AppTest.from_file(str(project / "hosted" / "dashboard.py"), default_timeout=60).run()
    assert not app.exception, [item.message for item in app.exception]
    text = _visible(app)
    assert "Public extract failed validation" in text
    assert "unsupported public extract version" in text
    assert "1,009,445" in text


def test_hosted_dashboard_renders_the_cube_when_the_extract_has_an_extra_table(
    project, tmp_path, monkeypatch
):
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    payload = json.loads((project / "data" / "public" / "dashboard_extract.json").read_text())
    payload["tables"]["future_metric"] = [{"value": 1}]
    extra = tmp_path / "dashboard_extract.json"
    extra.write_text(json.dumps(payload))
    monkeypatch.setenv("CHESSLAB_PUBLIC_EXTRACT", str(extra))
    app = AppTest.from_file(str(project / "hosted" / "dashboard.py"), default_timeout=60).run()
    assert not app.exception, [item.message for item in app.exception]
    assert not app.error
    assert "1,009,445" in _visible(app)


def test_hosted_dashboard_fails_closed_when_the_cube_is_missing(project, tmp_path, monkeypatch):
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv(
        "CHESSLAB_PUBLIC_EXTRACT",
        str(project / "data" / "public" / "dashboard_extract.json"),
    )
    monkeypatch.setenv("CHESSLAB_DASHBOARD_CUBE", str(tmp_path / "missing.parquet"))
    app = AppTest.from_file(str(project / "hosted" / "dashboard.py"), default_timeout=60).run()
    assert not app.exception, [item.message for item in app.exception]
    message = " ".join(item.value for item in app.error)
    assert "Dashboard cube unavailable" in message
    assert "dashboard cube not found" in message


def test_hosted_dashboard_fails_closed_when_the_cube_is_not_parquet(project, tmp_path, monkeypatch):
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    bad = tmp_path / "cube.parquet"
    bad.write_bytes(b"not a parquet file")
    monkeypatch.setenv(
        "CHESSLAB_PUBLIC_EXTRACT",
        str(project / "data" / "public" / "dashboard_extract.json"),
    )
    monkeypatch.setenv("CHESSLAB_DASHBOARD_CUBE", str(bad))
    app = AppTest.from_file(str(project / "hosted" / "dashboard.py"), default_timeout=60).run()
    assert not app.exception, [item.message for item in app.exception]
    message = " ".join(item.value for item in app.error)
    assert "Dashboard cube unavailable" in message
    assert "1,009,445" not in _visible(app)


def test_color_filter_hides_positions_and_shows_the_french_cell(project, monkeypatch):
    app = _run(project, monkeypatch)
    app.session_state["filter_color"] = "Black"
    app.session_state["filter_family"] = "French Defense"
    app.run()
    assert not app.exception, [item.message for item in app.exception]
    text = _visible(app)
    assert "Positions are not split by color." in text
    assert "Move orders are not split by color." in text
    assert "Clock pressure is not split by color or opening." in text
    assert "Period totals are not split by color or opening." in text
    assert "63,484" in text
    assert "46.8%" in text
    assert "29,728 / 63,484" in text
    assert "Opening lines by games. Select a bar to open the position." in _chart_alts(app)
    assert "Training games by published period." in _chart_alts(app)
    clock_alt = "Clock bands by evaluable moves. Select a bar to list the slices in that band."
    assert clock_alt in _chart_alts(app)
    sidebar = " ".join(item.value for item in app.sidebar.caption)
    assert "Color Black" in sidebar
    assert "Opening French Defense" in sidebar


def test_opening_drill_lists_lines_and_climbs_back(project, monkeypatch):
    from chess_analytics.dashboard_cube import Drill

    app = _run(project, monkeypatch)
    app.session_state["filter_family"] = "Sicilian Defense"
    app.session_state["drill"] = Drill(family="Sicilian Defense")
    app.run()
    assert not app.exception, [item.message for item in app.exception]
    text = _visible(app)
    assert "Openings / Sicilian Defense" in text
    assert "Opening lines by games. Select a bar to open the position." in _chart_alts(app)
    line = "1.e4 c5 2.Nf3 Nc6 3.d4 cxd4"
    shown = _load_hosted(project, "layout").san_text(line)
    assert shown in text
    tables = [table for table in app.table if "Line" in list(table.value.columns)]
    assert tables and shown in set(tables[0].value["Line"])
    assert "1.e4\u00a0c5" in shown
    line_chart = next(
        node
        for node in app
        if getattr(node, "type", None) == "vega_lite_chart"
        and "Opening lines by games" in node.proto.alt
    )
    encoded = json.dumps(_chart_spec(line_chart))
    assert '"stack": null' in encoded or '"stack":null' in encoded
    assert "line_label" in encoded
    backs = [item for item in app.button if item.label == "Back"]
    assert len(backs) == 1
    backs[0].click().run()
    assert not app.exception, [item.message for item in app.exception]
    assert "Opening families by games. Select a bar to drill into lines." in _chart_alts(app)
    assert [item.label for item in app.button] == ["Reset filters"]
