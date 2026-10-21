"""AppTest for the hosted read-only dashboard. Offline; no warehouse."""

import hashlib
import json

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
    _assert_section_origins(app)
    _assert_live_eval_link(app)
    _assert_build_table_omits_the_figure_id(app, extract)
    _assert_small_shares_are_below_a_tenth(app, extract)
    _assert_alt_text(app)
    for table in app.table:
        assert len(table.value.columns) <= 3


def _caption(app, fragment: str) -> str:
    matches = [item.value for item in app.caption if fragment in item.value]
    assert len(matches) == 1, matches
    return matches[0]


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
    assert len(charts) == 1
    assert isinstance(charts[0].proto.alt, str) and charts[0].proto.alt.strip()


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
