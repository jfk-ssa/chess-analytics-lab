"""AppTest for the hosted dashboard. Offline; no warehouse."""

import hashlib
import json
import re
from html import escape
from urllib.parse import urlsplit

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
        "streamlit==1.66.1",
        "altair==6.3.0",
        "narwhals==2.27.1",
        "jsonschema==4.26.0",
        "pandas==3.0.6",
        "protobuf==6.33.6",
        "pillow==13.0.0",
        "certifi==2026.10.19",
        "duckdb==1.5.6",
    ]
    project_text = (project / "pyproject.toml").read_text()
    assert "streamlit==1.66.1" in project_text
    assert "pillow==13.0.0" in project_text
    assert "certifi==2026.10.19" in project_text
    assert "1.66.1" in (project / "THIRD_PARTY_NOTICES.md").read_text()
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
    strips = [item.value for item in app.markdown if "cal-kpis" in item.value]
    assert len(strips) == 1
    assert re.findall(r'class="cal-k"[^>]*>([^<]+)', strips[0]) == [
        "Games",
        "Win rate",
        "Loss rate",
        "Draw rate",
        "Positions",
        "Rating diff",
        "Game length",
        "Clock error",
    ]
    assert "cal-kpi-frame" in strips[0]
    assert "minmax(min(100%,256px),1fr)" not in strips[0]
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
        "games in range",
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
        "grok-4.7 · low, grok-4.7 · medium, and grok-4.7 · high clear",
        "Five repeats",
        "Grok 4.7 effort sweep (one repeat)",
        "0/5 for gpt-6-sol",
        "1/1 for grok-4.7 · high",
        "5/5 and 1/1 are both a full pass",
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
    five = _caption(app, "gpt-6-luna and gpt-6-sol do not overlap").replace(r"\$", "$")
    one = _caption(app, "like-for-like with each other").replace(r"\$", "$")
    assert "gpt-6-luna $0.0150, grok-4.7 · low $1.0033, gpt-6-sol $0.2550" in five
    assert "Known cost is" in five
    assert "gpt-6-luna and gpt-6-sol share frozen inputs" in five
    assert "grok-4.7 · low does not" in five
    assert "frozen runner files changed" in five
    assert "its interval is not compared with theirs" in five
    assert "grok-4.7 · low $0.2225" in one
    assert "grok-4.7 · medium $0.3225" in one
    assert "grok-4.7 · high $0.4087" in one
    assert "grok-4.7 · low ×5" in one
    assert "48 trials" in one
    assert "different dataset snapshot" in one
    page = _visible(app)
    assert "dataset snapshot id" in page
    for caption in (five, one, page):
        assert "grok-4.7 · low ×5 and" not in caption
        assert "grok-4.7 · low overlap" not in caption
        assert "grok-4.7 · low do not overlap" not in caption
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
    clock = _caption(app, "evaluable moves, not games")
    assert clock.startswith("Each band is time remaining")
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
        (
            "Time remaining on the clock before the move, by evaluable moves. "
            "Select a band to list games with a move in that band."
        ),
        "Training games by published period.",
        (
            "Pass rate for the five-repeat runs with Wilson 95 percent intervals. "
            "gpt-6-luna, grok-4.7 low times five, and gpt-6-sol."
        ),
        ("Dumbbell of pass rate by category for the five-repeat runs. Each point is one run."),
        (
            "Dumbbell of pass rate by category for the grok-4.7 one-repeat effort sweep. "
            "Each point is one run."
        ),
        (
            "Grid of cases for the five-repeat runs, colored by pass fraction. "
            "Each cell prints passed/repeats. Column labels are horizontal."
        ),
        (
            "Grid of cases for the grok-4.7 one-repeat effort sweep, "
            "colored by pass fraction. Each cell prints passed/repeats. "
            "Column labels are horizontal."
        ),
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


def _assert_rows_reconcile(html: str) -> None:
    """Bars are shares of the headline. Rows sum to it unless the gap is under 10."""
    cards = html.split('class="cal-card"')[1:]
    assert cards
    for card in cards:
        headline = int(re.search(r'class="cal-v"[^>]*>([^<]+)', card).group(1).replace(",", ""))
        counts = [
            int(value.replace(",", "")) for value in re.findall(r'class="cal-n"[^>]*>([^<]+)', card)
        ]
        assert counts
        widths = [
            float(value)
            for value in re.findall(r'class="cal-share"[^>]*>\s*<div style="width:([0-9.]+)%', card)
        ]
        assert len(widths) == len(counts)
        for count, width in zip(counts, widths, strict=True):
            assert width == float(f"{100 * count / headline:.1f}")
        gaps = re.findall(r'class="cal-gap"[^>]*>([^<]*)', card)
        if gaps:
            assert gaps == ["rarer orders not shown"]
            assert "other orders" not in card
            assert "plus " not in card
            assert 1 <= headline - sum(counts) <= 9
        else:
            assert sum(counts) == headline


def test_clock_game_table_hides_opening_and_date_on_a_phone(project):
    module = _load_hosted(project, "layout")
    html = module.clock_game_table(
        [
            {
                "white_rating": 1834,
                "black_rating": 1790,
                "time_control": "180+0",
                "result": "1/2-1/2",
                "side": "Both",
                "opening": "Sicilian Defense: 1.e4 c5 2.Nf3 d6",
                "played_on": "2026-08-01",
                "lichess_id": "00000013",
            }
        ]
    )
    assert "cal-wide" in html
    assert "overflow-x" not in html
    assert "https://lichess.org/00000013" in html
    assert 'white-space:nowrap">1.e4 c5' in html
    assert 'white-space:nowrap">2.Nf3 d6' in html
    assert "½–½" in html
    assert ">Side<" in html
    assert ">Both<" in html
    css = (project / "hosted/static/dashboard.css").read_text()
    assert "@media (max-width: 640px)" in css
    assert "max-width: 480px" not in css
    assert (
        module.clock_game_table(
            [{"white_rating": 1, "black_rating": 2, "result": "1-0", "lichess_id": "not a url"}]
        ).count("https://lichess.org")
        == 0
    )
    with pytest.raises(ValueError, match="needs a game"):
        module.clock_game_table([])


def _chart_layers(spec: dict) -> list[dict]:
    return spec.get("layer", [spec])


def _mark_type(layer: dict) -> str:
    mark = layer["mark"]
    return mark["type"] if isinstance(mark, dict) else mark


def _layer(spec: dict, mark: str) -> dict:
    return next(layer for layer in _chart_layers(spec) if _mark_type(layer) == mark)


def test_clock_bars_keep_a_zero_baseline_and_a_horizontal_title(project):
    pytest.importorskip("altair")
    charts = _load_hosted(project, "charts")
    clock_source = (project / "hosted/bi.py").read_text().split("def _clock", 1)[1]
    clock_source = clock_source.split("def _games", 1)[0]
    assert "count_axis_domain" not in clock_source
    assert "horizontal_category_title=True" in clock_source
    drawn = charts.selectable_bars(
        [
            {"label": "Under 10s", "band": "under_10", "games": 1191},
            {"label": "60s+", "band": "60_plus", "games": 12567},
        ],
        name="clock_pick",
        field="band",
        value_title="Evaluable moves",
        label_field="label",
        category_title="Time remaining",
        horizontal_category_title=True,
    )
    spec = drawn.to_dict()
    bar = _layer(spec, "bar")
    y_axis = bar["encoding"]["y"]["axis"]
    assert y_axis["labelAngle"] == 0
    assert y_axis["titleAngle"] == 0
    assert bar["encoding"]["y"]["title"] == "Time remaining"
    domain = bar["encoding"]["x"]["scale"]["domain"]
    assert domain[0] == 0
    assert domain[1] > 12567
    assert bar["encoding"]["x"]["scale"]["zero"] is True
    assert bar["encoding"]["x"]["axis"] is None
    periods = charts.period_bars([{"label": "2026-08", "games": 10}]).to_dict()
    period_bar = _layer(periods, "bar")
    period_y = period_bar["encoding"]["y"]
    assert period_y["axis"] is None
    assert period_y["scale"]["domain"][0] == 0
    assert period_y["scale"]["zero"] is True
    assert period_bar["encoding"]["x"]["axis"]["labelAngle"] == 0
    assert period_bar["data"]["values"][0]["tick"] == "0|Aug 26"


def test_bar_charts_label_the_bar_end(project):
    pytest.importorskip("altair")
    charts = _load_hosted(project, "charts")
    assert charts.value_label_format("count") == ","
    assert charts.value_label_format("rate") == ".1%"
    assert charts.value_label_format("diff") == "+,.1f"
    assert charts.compact_count(240086) == "240k"
    assert charts.compact_count(90000) == "90k"
    assert charts.compact_count(1500) == "1.5k"
    assert charts.compact_count(1191) == "1.2k"
    with pytest.raises(ValueError, match="unknown label kind"):
        charts.value_label_format("games")
    clock = charts.selectable_bars(
        [
            {"label": "Under 10s", "band": "under_10", "games": 1191},
            {"label": "60s+", "band": "60_plus", "games": 12567},
        ],
        name="clock_pick",
        field="band",
        value_title="Evaluable moves",
        label_field="label",
    ).to_dict()
    text = _layer(clock, "text")
    assert text["encoding"]["text"]["format"] == ","
    assert "right" in text["mark"]["align"]["expr"]
    assert "left" in text["mark"]["align"]["expr"]
    assert "#f7f4ea" in text["mark"]["color"]["expr"]
    assert text["encoding"]["x"]["scale"]["domain"][0] == 0
    openings = charts.selectable_bars(
        [{"label": "Sicilian Defense", "games": 12000}],
        name="family_pick",
        field="label",
        value_title="Games",
    ).to_dict()
    assert _layer(openings, "text")["encoding"]["text"]["format"] == ","
    months = [{"label": f"2026-{index:02d}", "games": 80_000 + index} for index in range(1, 11)]
    periods = charts.period_bars(months).to_dict()
    period_texts = [
        layer["encoding"]["text"] for layer in _chart_layers(periods) if _mark_type(layer) == "text"
    ]
    wide = next(item for item in period_texts if item.get("condition", {}).get("format") == ",")
    assert wide["condition"]["test"] == "width >= 560"
    assert wide["value"] == ""
    compact = next(
        item for item in period_texts if item.get("condition", {}).get("field") == "compact"
    )
    assert compact["condition"]["test"] == "width < 560"
    assert compact["value"] == ""
    period_axis = _layer(periods, "bar")["encoding"]["x"]["axis"]
    assert period_axis["labelAngle"] == 0
    assert "split(datum.label, '|')" in period_axis["labelExpr"]
    assert _layer(periods, "bar")["data"]["values"][0]["tick"] == "0|Jan 26"
    assert _layer(periods, "bar")["data"]["values"][1]["tick"] == "1|Feb 26"
    assert _layer(periods, "bar")["data"]["values"][0]["compact"] == "80k"
    november = charts.period_bars(
        [{"label": "2025-11", "games": 240086}, {"label": "2025-12", "games": 90000}]
    ).to_dict()
    ticks = _layer(november, "bar")["data"]["values"]
    assert [row["tick"] for row in ticks] == ["0|Nov 25", "1|Dec 25"]
    assert [row["compact"] for row in ticks] == ["240k", "90k"]
    rates = charts.bucket_bars(
        [
            {"bucket": "Under 10s", "error_proxy_rate": 0.093, "rate_label": "9.3%"},
            {"bucket": "60s+", "error_proxy_rate": 0.041, "rate_label": "4.1%"},
        ]
    ).to_dict()
    assert _layer(rates, "text")["encoding"]["text"]["condition"]["format"] == ".1%"
    shares = charts.transposition_bars(
        [
            {
                "view": "French Defense",
                "share": 0.125,
                "share_label": "12.5%",
                "denominator_games": 80,
            }
        ]
    ).to_dict()
    assert _layer(shares, "text")["encoding"]["text"]["format"] == ".1%"
    single = charts.score_intervals(
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
            }
        ]
    ).to_dict()
    assert _layer(single, "text")["encoding"]["text"]["format"] == ".1%"
    grouped = charts.score_intervals(
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
    ).to_dict()
    assert all(_mark_type(layer) != "text" for layer in _chart_layers(grouped))


def _assert_category_axis(spec: dict, channel: str) -> None:
    """The bar's category axis labels the categories, and no layer clears it."""
    bar_axis = _layer(spec, "bar")["encoding"][channel]["axis"]
    assert isinstance(bar_axis, dict)
    assert bar_axis.get("labels", True) is not False
    assert bar_axis.get("labelAngle", 0) == 0
    seen = False
    for layer in _chart_layers(spec):
        encoding = layer.get("encoding") or {}
        if channel not in encoding:
            continue
        seen = True
        axis = encoding[channel].get("axis", "absent")
        assert axis is not None
        if isinstance(axis, dict):
            assert axis.get("labels", True) is not False
            assert axis.get("labelAngle", 0) == 0
    assert seen


def test_labeled_charts_keep_a_category_axis(project):
    pytest.importorskip("altair")
    charts = _load_hosted(project, "charts")
    clock = charts.selectable_bars(
        [
            {"label": "Under 10s", "band": "under_10", "games": 1191},
            {"label": "60s+", "band": "60_plus", "games": 12567},
        ],
        name="clock_pick",
        field="band",
        value_title="Evaluable moves",
        label_field="label",
        category_title="Time remaining",
        horizontal_category_title=True,
    ).to_dict()
    _assert_category_axis(clock, "y")
    for layer in _chart_layers(clock):
        assert layer["encoding"]["y"]["title"] == "Time remaining"
        assert layer["encoding"]["y"]["axis"]["titleAngle"] == 0
        assert layer["encoding"]["y"]["axis"]["titleAnchor"] == "start"
        assert layer["encoding"]["x"]["axis"] is None
        assert layer["encoding"]["x"]["scale"]["domain"][0] == 0
    openings = charts.selectable_bars(
        [{"label": "Sicilian Defense", "games": 85724}],
        name="family_pick",
        field="label",
        value_title="Games",
    ).to_dict()
    _assert_category_axis(openings, "y")
    assert _layer(openings, "bar")["encoding"]["y"]["field"] == "label"
    periods = charts.period_bars(
        [{"label": "2025-11", "games": 240086}, {"label": "2026-08", "games": 89532}]
    ).to_dict()
    _assert_category_axis(periods, "x")
    assert _layer(periods, "bar")["encoding"]["x"]["field"] == "tick"
    for layer in _chart_layers(periods):
        assert layer["encoding"]["y"]["axis"] is None
        assert layer["encoding"]["y"]["scale"]["zero"] is True
    buckets = charts.bucket_bars(
        [{"bucket": "Under 10s", "error_proxy_rate": 0.093, "rate_label": "9.3%"}]
    ).to_dict()
    _assert_category_axis(buckets, "x")
    assert _layer(buckets, "bar")["encoding"]["x"]["title"] == "Seconds left"
    assert _layer(buckets, "text")["encoding"]["y"]["axis"]["labelAngle"] == 0
    shares = charts.transposition_bars(
        [
            {
                "view": "French Defense",
                "share": 0.125,
                "share_label": "12.5%",
                "denominator_games": 80,
            }
        ]
    ).to_dict()
    _assert_category_axis(shares, "y")
    removed = charts.funnel([{"stage": "Unrated", "count": 12, "order": 1}]).to_dict()
    _assert_category_axis(removed, "y")
    families = charts.horizontal_bars(
        [{"family": "French Defense", "games": 40, "share_label": "10%"}],
        x_title="Games",
    ).to_dict()
    _assert_category_axis(families, "y")
    single = charts.score_intervals(
        [
            {
                "family": "French Defense",
                "series": "White, raw",
                "rate": 0.419,
                "low": 0.4,
                "high": 0.44,
                "rate_label": "41.9%",
                "interval_label": "40.0%–44.0%",
                "support_label": "no",
            }
        ]
    ).to_dict()
    _assert_category_axis(single, "x")
    for layer in _chart_layers(single):
        if "y" in layer.get("encoding", {}):
            assert layer["encoding"]["y"].get("axis", "absent") is None
    grouped = charts.score_intervals(
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
    ).to_dict()
    _assert_category_axis(grouped, "x")
    assert _layer(grouped, "bar")["encoding"]["y"]["axis"]["labelAngle"] == 0


def test_count_axis_starts_near_zero_unless_values_are_tight(project):
    pytest.importorskip("altair")
    charts = _load_hosted(project, "charts")
    assert charts.count_axis_domain([1191, 3183, 6053, 12567]) is None
    assert charts.count_axis_domain([0, 10]) is None
    tight = charts.count_axis_domain([100, 110])
    assert tight is not None
    assert tight[0] == pytest.approx(90)
    assert tight[1] > 110


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
    assert board.count('class="cal-share"') == 4
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
    assert "top 1 move order" in board
    assert "2,253" in board
    assert "2,530" in board
    assert "other orders" in board
    assert "277" in board
    assert "position games" not in board
    assert "rarer orders not shown" not in board
    assert "width:58.3%" in board
    assert "width:41.7%" in board
    assert "width:89.1%" in board
    assert "width:10.9%" in board
    assert "width:100.0%" not in board
    assert board.index("After Black") < board.index("1,200")
    _assert_rows_reconcile(board)
    strip = module.kpi_strip(
        [
            ("Games", "1,009,445", "games in range"),
            ("Win rate", "49.2%", "476,741 / 968,874 · White"),
            ("Loss rate", "45.7%", "442,862 / 968,874 · White"),
            ("Draw rate", "5.1%", "49,271 / 968,874 · White"),
            ("Positions", "256", "rated public"),
            ("Rating diff", "+0.1", "White · mean"),
            ("Game length", "72.8", "mean ply"),
            ("Clock error", "9.3%", "2,128 / 22,978"),
        ]
    )
    assert strip.startswith('<div class="cal-kpi-frame"><div class="cal-equal cal-kpis"')
    assert 'data-cards="8"' in strip
    assert re.findall(r'class="cal-k"[^>]*>([^<]+)', strip) == [
        "Games",
        "Win rate",
        "Loss rate",
        "Draw rate",
        "Positions",
        "Rating diff",
        "Game length",
        "Clock error",
    ]
    assert "minmax(min(100%,256px),1fr)" not in strip
    css = (project / "hosted" / "static" / "dashboard.css").read_text()
    assert ".cal-kpi-frame" in css and "container-type: inline-size" in css
    assert "grid-template-columns: repeat(2, minmax(0, 1fr));" in css
    assert "@container (min-width: 600px)" in css
    assert "grid-template-columns: repeat(4, minmax(0, 1fr));" in css
    with pytest.raises(ValueError, match="at least one card"):
        module.kpi_strip([])
    wrapped = module.equal_width_row([("Win rate", "49.2%", "476,741 / 968,874 · White")])
    assert 'white-space:nowrap">476,741 / 968,874<' in wrapped
    assert 'white-space:nowrap">476,741 / 968,874 · White<' not in wrapped
    delta = module.equal_width_row(
        [("Win rate", "49.5%", "120,072 / 242,616 · White · -0.3 pp vs prior")]
    )
    assert 'white-space:nowrap">-0.3 pp vs prior<' in delta
    assert 'white-space:nowrap">120,072 / 242,616 · White · -0.3 pp vs prior<' not in delta
    assert 'class="cal-k"' in delta and "Win rate" in delta
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
    assert "width:30.0%" in marked
    assert "width:27.5%" in marked
    assert "width:42.5%" in marked
    assert ">40<" in marked
    assert "other orders" in marked
    assert ">17<" in marked
    assert "position games" not in marked
    assert "top 2 move orders" in marked
    _assert_rows_reconcile(marked)


def test_visible_transposition_rows_reconcile(project):
    """A remainder of 10 or more is an other-orders row that meets the headline."""
    module = _load_hosted(project, "layout")
    folded = {
        "title": "After Black's move 4 · 1.e4 c5 2.Nf3 d6 3.d4 cxd4 4.Nxd4 Nf6",
        "games": 9000,
        "kept_games": 7000,
        "move_orders": 5,
        "routes": [
            ("1.e4 c5 2.Nf3 d6 3.d4 cxd4 4.Nxd4 Nf6", 4000),
            ("1.e4 c5 2.Nf3 Nc6 3.d4 cxd4 4.Nxd4 Nf6", 1800),
            ("1.e4 c5 2.d4 cxd4 3.Nf3 d6 4.Nxd4 Nf6", 700),
        ],
    }
    headline, rows, label, note = module._visible_routes(folded)
    assert (headline, label, note) == (9000, "top 3 move orders", "")
    assert rows[-1] == ("other orders", 2500)
    assert sum(games for _san, games in rows) == headline
    html = module.transposition_cards([folded])
    assert "9,000" in html
    assert "other orders" in html
    assert "2,500" in html
    assert 'class="cal-route cal-other"' in html
    assert "background:#5c726b" in html
    assert "top 3 move orders" in html
    assert "position games" not in html
    assert "width:44.4%" in html
    assert "width:20.0%" in html
    assert "width:7.8%" in html
    assert "width:27.8%" in html
    for pair in ("1.e4 c5", "2.Nf3 d6", "3.d4 cxd4", "4.Nxd4 Nf6", "2.Nf3 Nc6"):
        assert f'white-space:nowrap">{pair}<' in html
    _assert_rows_reconcile(html)
    counted = {
        "title": "After Black's move 3 · 1.e4 c5 2.Nf3 Nc6 3.d4 cxd4",
        "games": 7000,
        "kept_games": 7000,
        "move_orders": 5,
        "routes": [
            ("1.e4 c5 2.Nf3 Nc6 3.d4 cxd4", 4000),
            ("1.e4 c5 2.d4 cxd4 3.Nf3 Nc6", 1800),
            ("1.e4 c5 2.Nc3 Nc6 3.Nf3 d6", 700),
        ],
    }
    headline, rows, label, note = module._visible_routes(counted)
    assert (headline, label, note) == (7000, "5 move orders", "")
    assert rows[-1] == ("other orders", 500)
    assert sum(games for _san, games in rows) == headline
    boundary = {
        "title": "After Black's move 2 · 1.e4 e6 2.d4 d5",
        "games": 110,
        "kept_games": 100,
        "move_orders": 1,
        "routes": [("1.e4 e6 2.d4 d5", 100)],
    }
    headline, rows, label, note = module._visible_routes(boundary)
    assert (headline, rows[-1], label, note) == (110, ("other orders", 10), "top 1 move order", "")
    assert module.transposition_cards([boundary]).count("other orders") == 1
    small = {
        "title": "After Black's move 2 · 1.e4 e6 2.d4 d5",
        "games": 199,
        "kept_games": 190,
        "move_orders": 2,
        "routes": [("1.e4 e6 2.d4 d5", 100), ("1.d4 d5 2.e4 e6", 90)],
    }
    headline, rows, label, note = module._visible_routes(small)
    assert headline == 199
    assert rows == [("1.e4 e6 2.d4 d5", 100), ("1.d4 d5 2.e4 e6", 90)]
    assert label == "top 2 move orders"
    assert note == "rarer orders not shown"
    quiet = module.transposition_cards([small])
    assert "other orders" not in quiet
    assert "199" in quiet
    assert "rarer orders not shown" in quiet
    assert "plus " not in quiet
    assert re.search(r"cal-gap[^>]*>rarer orders not shown<", quiet)
    assert not re.search(r"cal-gap[^>]*>[^<]*\d", quiet)
    _assert_rows_reconcile(quiet)


def test_committed_transposition_cards_reconcile(project):
    """Position totals stay the headline. A remainder of 10 or more is on the card."""
    from datetime import date

    from chess_analytics.dashboard_cube import Filters, connect, cube_path, transpositions

    layout = _load_hosted(project, "layout")
    connection = connect(cube_path(project))
    boards, _caption = transpositions(
        connection, Filters(date(2000, 1, 1), date(2100, 1, 1)), limit=10_000
    )
    assert len(boards) == 217
    _assert_rows_reconcile(layout.transposition_cards(boards))
    other = small = zero = 0
    for item in boards:
        headline, rows, label, note = layout._visible_routes(item)
        shown_games = sum(int(games) for _san, games in item["routes"])
        remainder = int(item["games"]) - shown_games
        shown_count = len(item["routes"])
        assert headline == int(item["games"])
        if remainder >= 10:
            other += 1
            assert rows[-1] == ("other orders", remainder)
            assert sum(games for _name, games in rows) == headline
            assert note == ""
            assert label == f"top {shown_count} move orders"
        elif remainder > 0:
            small += 1
            assert note == "rarer orders not shown"
            assert all(name != "other orders" for name, _games in rows)
            assert label == f"top {shown_count} move orders"
        else:
            zero += 1
            assert note == ""
            assert sum(games for _name, games in rows) == headline
            assert label == f"{shown_count} move orders"
    assert (other, small, zero) == (154, 38, 25)
    nc6 = next(
        item
        for item in boards
        if item["title"] == "After Black's move 3 · 1.e4 c5 2.Nf3 Nc6 3.d4 cxd4"
    )
    headline, rows, label, note = layout._visible_routes(nc6)
    assert headline == 8054
    assert rows[-1] == ("other orders", 70)
    assert (label, note) == ("top 3 move orders", "")


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


def _axis_values(spec: dict, field: str) -> list:
    found: list = []

    def walk(node) -> None:
        if isinstance(node, dict):
            axis = node.get("axis")
            if isinstance(axis, dict) and field in axis:
                found.append(axis[field])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(spec)
    return found


def _channel_sorts(spec: dict, channel: str) -> list:
    found: list = []

    def walk(node) -> None:
        if isinstance(node, dict):
            encoding = node.get("encoding")
            if isinstance(encoding, dict):
                axis = encoding.get(channel)
                if isinstance(axis, dict) and "sort" in axis:
                    found.append(axis["sort"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(spec)
    return found


def _y_sorts(spec: dict) -> list:
    return _channel_sorts(spec, "y")


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
    assert labels == [
        "grok-4.7 · low",
        "grok-4.7 · medium",
        "grok-4.7 · high",
    ]
    assert "(" not in "".join(labels)
    assert "1f45f2" not in cards[0]
    assert 'white-space:nowrap">14,768 reasoning tokens<' in cards[0]
    assert 'white-space:nowrap">$0.22253 per repeat<' not in cards[0]
    assert 'white-space:nowrap">&#36;0.223 per repeat<' in cards[0]
    assert 'white-space:nowrap">&#36;0.322 per repeat<' in cards[0]
    assert 'white-space:nowrap">&#36;0.409 per repeat<' in cards[0]
    assert 'white-space:nowrap">32,410 reasoning tokens<' in cards[0]
    assert 'white-space:nowrap">46,763 reasoning tokens<' in cards[0]
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
    assert "10 percentage points" in caption


def _unit_domains(spec: dict) -> list:
    return [
        item
        for item in _scale_domains(spec)
        if len(item) == 2
        and all(isinstance(value, (int, float)) for value in item)
        and item[1] == 1
    ]


def _color_range(spec: dict) -> list[str]:
    found: list[list[str]] = []

    def walk(node) -> None:
        if isinstance(node, dict):
            scale = node.get("scale")
            if isinstance(scale, dict):
                domain = scale.get("domain")
                series = scale.get("range")
                if (
                    isinstance(domain, list)
                    and domain
                    and isinstance(domain[0], str)
                    and isinstance(series, list)
                    and any(
                        name.startswith("grok-4.7") or name.startswith("gpt-6") for name in domain
                    )
                ):
                    found.append(series)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(spec)
    assert len(found) == 1, found
    return found[0]


def _chart_numbers(spec: dict, field: str) -> list[float]:
    found: list[float] = []

    def walk(node) -> None:
        if isinstance(node, dict):
            values = node.get("values")
            if isinstance(values, list):
                for row in values:
                    if isinstance(row, dict) and isinstance(row.get(field), (int, float)):
                        found.append(float(row[field]))
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(spec)
    return found


def test_every_grok_run_is_on_the_live_eval_charts(project, monkeypatch):
    """Five-repeat runs and the one-repeat grok sweep stay on separate charts."""
    app = _run(project, monkeypatch)
    charts = [node for node in app if getattr(node, "type", None) == "vega_lite_chart"]
    five_order = ["gpt-6-luna", "grok-4.7 · low", "gpt-6-sol"]
    one_order = ["grok-4.7 · low", "grok-4.7 · medium", "grok-4.7 · high"]
    rate = [node for node in charts if "five-repeat runs with Wilson" in node.proto.alt]
    assert len(rate) == 1
    rate_spec = _chart_spec(rate[0])
    sorts = _y_sorts(rate_spec)
    assert sorts
    assert all(item == five_order for item in sorts)
    domains = _unit_domains(rate_spec)
    assert domains[0][0] == pytest.approx(0.8131895522590333 - 0.10)
    assert "width - 12" in json.dumps(rate_spec)
    sweep = [node for node in charts if "Low, medium, and high" in node.proto.alt]
    assert len(sweep) == 1
    sweep_spec = _chart_spec(sweep[0])
    sweep_domain = _unit_domains(sweep_spec)[0]
    sweep_lows = _chart_numbers(sweep_spec, "wilson_low")
    assert sweep_lows
    assert sweep_domain[0] == pytest.approx(min(sweep_lows) - 0.10)
    assert sweep_domain[0] != pytest.approx(domains[0][0])
    assert "width - 12" in json.dumps(sweep_spec)
    categories = [node for node in charts if "Dumbbell of pass rate by category" in node.proto.alt]
    assert len(categories) == 2
    five_cat, one_cat = categories
    five_cat_spec = _chart_spec(five_cat)
    one_cat_spec = _chart_spec(one_cat)
    assert _unit_domains(five_cat_spec)[0][0] == pytest.approx(0.15)
    one_rates = _chart_numbers(one_cat_spec, "rate")
    assert one_rates
    assert _unit_domains(one_cat_spec)[0][0] == pytest.approx(min(one_rates) - 0.10)
    assert _unit_domains(one_cat_spec)[0][0] != pytest.approx(0.15)
    five_colors = json.dumps(five_cat_spec)
    one_colors = json.dumps(one_cat_spec)
    for swatch in ("#116559", "#1d4ed8", "#a84a1f"):
        assert swatch in five_colors
    for swatch in ("#7c3aed", "#db2777", "#4d7c0f"):
        assert swatch in one_colors
        assert swatch not in five_colors
    assert _color_range(five_cat_spec) == ["#116559", "#1d4ed8", "#a84a1f"]
    assert _color_range(one_cat_spec) == ["#7c3aed", "#db2777", "#4d7c0f"]
    heat = [node for node in charts if "pass fraction" in node.proto.alt]
    assert len(heat) == 2
    five_x = ["gpt-6-luna", "grok-4.7\nlow", "gpt-6-sol"]
    one_x = ["grok-4.7\nlow", "grok-4.7\nmedium", "grok-4.7\nhigh"]
    five_heat = _chart_spec(heat[0])
    one_heat = _chart_spec(heat[1])
    assert all(item == five_x for item in _channel_sorts(five_heat, "x"))
    assert all(item == one_x for item in _channel_sorts(one_heat, "x"))
    for heat_spec in (five_heat, one_heat):
        assert all(angle == 0 for angle in _axis_values(heat_spec, "labelAngle"))
        blob = json.dumps(heat_spec)
        assert "cell_label" in blob
        assert '"step": 112' in blob
    misses = [
        table for table in app.table if list(table.value.columns) == ["Run", "Case", "Result"]
    ]
    assert len(misses) == 2
    assert set(misses[0].value["Run"]) == set(five_order)
    assert set(misses[1].value["Run"]) == set(one_order)
    assert "coverage_2" in set(misses[0].value["Case"]) | set(misses[1].value["Case"])
    one_results = set(misses[1].value["Result"])
    assert "0/1\n\nover_abstention" in one_results
    assert all(", " not in value for value in one_results)
    costs = [
        table
        for table in app.table
        if list(table.value.columns) == ["Run", "Known cost", "Reasoning tokens"]
    ]
    assert len(costs) == 2
    assert list(costs[0].value["Run"]) == five_order
    assert list(costs[1].value["Run"]) == one_order
    assert "14,768" in set(costs[1].value["Reasoning tokens"])
    assert set(costs[0].value["Known cost"]) == {"$0.015", "$1.003", "$0.255"}
    assert set(costs[1].value["Known cost"]) == {"$0.223", "$0.322", "$0.409"}
    assert "0" in set(costs[0].value["Reasoning tokens"])


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
    assert marks == ["rect", "text", "point"]
    blob = json.dumps(spec)
    assert "xOffset" not in blob
    assert "yOffset" not in blob
    assert '"stack": "zero"' not in blob
    domains = [
        item
        for item in _scale_domains(spec)
        if len(item) == 2
        and all(isinstance(value, (int, float)) for value in item)
        and item[1] == 1
        and item[0] < 0.5
    ]
    assert domains
    assert all(low == pytest.approx(0.15) and high == 1 for low, high in domains)
    assert "width - 12" in json.dumps(spec)
    for layer in layers:
        encoding = layer["encoding"]
        for channel in ("x", "x2"):
            if channel not in encoding:
                continue
            stacked = encoding[channel].get("stack")
            assert stacked in (None, "none")
    order = [
        "gpt-6-luna",
        "grok-4.7 · low ×5",
        "gpt-6-sol",
        "grok-4.7 · low ×1",
        "grok-4.7 · medium ×1",
        "grok-4.7 · high ×1",
    ]
    six = charts.category_dumbbell(
        [
            {"category": "coverage", "model": name, "rate": 1.0, "passed_label": "1 / 1"}
            for name in order
        ],
        category_order=["coverage"],
        model_order=order,
    )
    six_dict = six.to_dict()
    six_spec = json.dumps(six_dict)
    assert "yOffset" not in six_spec
    point_layer = next(
        layer
        for layer in six_dict["layer"]
        if (layer["mark"]["type"] if isinstance(layer["mark"], dict) else layer["mark"]) == "point"
    )
    ys = sorted(row["y"] for row in point_layer["data"]["values"])
    assert len(ys) == 6
    assert ys[0] == pytest.approx(-ys[-1])
    assert point_layer["mark"]["size"] == 64
    assert six_spec.count('"#116559"') >= 1
    for swatch in ("#1d4ed8", "#a84a1f", "#7c3aed", "#db2777", "#4d7c0f"):
        assert swatch in six_spec


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
    wilson_domains = [
        item
        for item in _scale_domains(wilson.to_dict())
        if len(item) == 2 and all(isinstance(value, (int, float)) for value in item)
    ]
    assert wilson_domains
    assert all(high == 1 and low == pytest.approx(0.713) for low, high in wilson_domains)
    assert "width - 12" in json.dumps(wilson.to_dict())
    assert charts.pass_rate_domain([0.04, 0.5]) == [0.0, 1.0]
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
    angles = _axis_values(grid_spec, "labelAngle")
    assert 0 in angles
    assert all(angle == 0 for angle in angles)
    blob = json.dumps(grid_spec)
    assert "0/5" in blob
    assert '"labelLimit": 0' in blob
    limits = _axis_values(grid_spec, "labelLimit")
    assert 180 not in limits


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
    clock_alt = (
        "Time remaining on the clock before the move, by evaluable moves. "
        "Select a band to list games with a move in that band."
    )
    assert clock_alt in _chart_alts(app)
    sidebar = " ".join(item.value for item in app.sidebar.caption)
    assert "Color Black" in sidebar
    assert "Opening French Defense" in sidebar


def test_clock_band_drill_lists_games(project, monkeypatch):
    from chess_analytics.dashboard_cube import Drill

    app = _run(project, monkeypatch)
    app.session_state["drill"] = Drill(clock_band="under_10")
    app.run()
    assert not app.exception, [item.message for item in app.exception]
    text = _visible(app)
    assert "Under 10s left on the clock" in text
    assert "Showing 12 of 191 published games" in text
    assert "The sample is the August prefix." in text
    assert "lowest SHA-256" in text
    assert "evaluable moves, not games" in text
    assert "Side" in text
    games = "\n".join(item.value for item in app.markdown if "cal-games" in item.value)
    hrefs = re.findall(r'href="([^"]+)"', games)
    assert hrefs
    for href in hrefs:
        parsed = urlsplit(href)
        assert parsed.scheme == "https"
        assert parsed.hostname == "lichess.org"
        assert re.fullmatch(r"/[A-Za-z0-9]{8}", parsed.path)
    assert "cal-wide" in games
    assert "overflow-x" not in games


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
