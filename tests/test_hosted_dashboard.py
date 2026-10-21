"""AppTest for the hosted read-only dashboard. Offline; no warehouse."""

import hashlib
import json
import re

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
    assert not app.button
    text = _visible(app)
    assert "1 over-abstentions" not in text
    extract = load_extract(extract_path(project))
    receipts = {row["receipt_id"]: row for row in table_rows(extract, "metric_receipt")}
    draw = receipts["game_draw_rate"]
    french = receipts["opening_player_score:French Defense"]
    sicilian = receipts["opening_player_score:Sicilian Defense"]
    clock = receipts["clock_pressure_error_proxy:under_10"]
    path = extract_path(project)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    expected = (
        f"{draw['numerator']:,} / {draw['denominator']:,}",
        f"{french['numerator']:,} / {french['denominator']:,}",
        f"{sicilian['numerator']:,} / {sicilian['denominator']:,}",
        f"{clock['numerator']:,} / {clock['denominator']:,}",
        "1,042,346",
        "99,467",
        "100,000",
        "French Defense",
        "Sicilian Defense",
        "50.3%",
        "48.0%",
        "44.7%–56.1%",
        "42.1%–53.3%",
        "41.9%",
        "44.8%",
        "106 / 253",
        "152 / 339",
        "883",
        "533",
        "342",
        "8.3%",
        "7.8%",
        "86.3%",
        "97.5%",
        "97.1%",
        "Luna, grok-4.7 low clear; Sol fail",
        "boundary_budget 0/5",
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
        "under_10",
        "10_to_29",
        "30_to_59",
        "60_plus",
    )
    missing = [item for item in expected if item not in text]
    assert not missing, missing
    assert "Receipt not in yet." not in text
    assert "The 1-repeat low run is not in this test." not in text
    _assert_section_origins(app)
    _assert_live_eval_link(app)
    _assert_build_table_omits_the_figure_id(app, extract)
    _assert_small_shares_are_below_a_tenth(app, extract)
    _assert_alt_text(app)
    _assert_equal_width_markup(app)
    for table in app.table:
        assert len(table.value.columns) <= 3


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
    sections = (
        ("m3_august_prefix:eligible_games", "metricflow"),
        ("opening_usage denominator", "metricflow"),
        ("wins plus half the draws", "metricflow"),
        ("adjusted_interval_low", "committed_report"),
        ("proxy_errors", "reviewed_sql"),
        ("lineages separately", "committed_report"),
    )
    origins = ("metricflow", "reviewed_sql", "committed_report")
    for fragment, origin in sections:
        caption = _caption(app, fragment)
        assert f"Query origin: {origin}" in caption
        for other in origins:
            if other != origin:
                assert other not in caption


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


def _assert_small_shares_are_below_a_tenth(app, extract) -> None:
    families = table_rows(extract, "opening_family_share")
    small = [row for row in families if row["numerator"] > 0 and f"{row['value']:.1%}" == "0.0%"]
    assert small
    catalogs = [
        table.value
        for table in app.table
        if list(table.value.columns) == ["Family", "Games", "Share"]
    ]
    catalog = max(catalogs, key=len)
    assert int((catalog["Share"] == "<0.1%").sum()) == len(small)
    assert "0.0%" not in set(catalog["Share"])


def _assert_alt_text(app) -> None:
    assert app.table
    for table in app.table:
        assert isinstance(table.proto.alt, str) and table.proto.alt.strip()
    charts = [node for node in app if getattr(node, "type", None) == "vega_lite_chart"]
    alts = [node.proto.alt for node in charts]
    assert all(isinstance(item, str) and item.strip() for item in alts)
    expected = (
        "Games removed from the August prefix: unrated, marked bots, and unknown results.",
        "Twelve largest opening families by games.",
        "Opening family game counts for the families selected above.",
        "Raw score by color and the Black adjusted score with its bootstrap interval.",
        "Endpoint compression by ply for the elite month and the rated public prefixes.",
        "Share of games covered by the top N recurring positions.",
        "Share of distinct positions that can be reached by more than one route.",
        "Heatmap of the clock-pressure error proxy by rating band and time control.",
        "Error proxy for the four clock buckets.",
        "Headline pass rate for each model with its Wilson 95 percent interval.",
        "Dumbbell of pass rate by category. Each point is one model.",
        "Grid of cases by model, colored by how many repeats passed.",
        (
            "Grok reasoning-effort pass rates with Wilson 95 percent intervals. "
            "Low, medium, and high are 1-repeat runs on the same instructions."
        ),
    )
    assert alts == list(expected)


_TRACKS = "repeat(auto-fit,minmax(min(100%,256px),1fr))"


def _assert_equal_width_markup(app) -> None:
    markup = "\n".join(item.value for item in app.markdown)
    for count in (3, 6):
        assert f'data-cards="{count}"' in markup
    assert _TRACKS in markup
    assert "white-space:nowrap" in markup
    assert "overflow-wrap:anywhere" not in markup
    assert "minmax(0,1fr)" not in markup


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


def test_equal_width_rows_share_one_track_definition(project):
    module = _load_hosted(project, "layout")
    for count in range(1, 8):
        assert module.equal_width_columns(count) == _TRACKS
        cards = [(f"Label {index}", f"Value {index}", f"Detail {index}") for index in range(count)]
        html = module.equal_width_row(cards)
        assert f'data-cards="{count}"' in html
        assert f"grid-template-columns:{_TRACKS}" in html
        assert html.count('class="cal-card"') == count
        assert html.count('class="cal-v"') == count
        assert html.count("white-space:nowrap") == 2 * count
        assert "overflow-wrap:anywhere" not in html
        assert "minmax(min(100%,256px),1fr)" in html
    with pytest.raises(ValueError, match="at least one card"):
        module.equal_width_columns(0)
    with pytest.raises(ValueError, match="at least one card"):
        module.equal_width_columns(True)


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


def test_hosted_dashboard_fails_closed_when_the_extract_is_invalid(project, tmp_path, monkeypatch):
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    invalid = tmp_path / "dashboard_extract.json"
    invalid.write_text(json.dumps({"extract_version": "0"}))
    monkeypatch.setenv("CHESSLAB_PUBLIC_EXTRACT", str(invalid))
    app = AppTest.from_file(str(project / "hosted" / "dashboard.py"), default_timeout=60).run()
    assert not app.exception, [item.message for item in app.exception]
    assert not app.table
    assert not app.metric
    message = " ".join(item.value for item in app.error)
    assert "Public extract failed validation" in message
    assert "unsupported public extract version" in message
