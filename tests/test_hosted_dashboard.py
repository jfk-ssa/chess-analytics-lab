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


def test_hosted_streamlit_pin_matches_the_lock(project):
    requirements = [
        line.strip()
        for line in (project / "hosted" / "requirements.txt").read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]
    assert requirements == ["streamlit==1.65.0"]
    assert "streamlit==1.65.0" in (project / "pyproject.toml").read_text()
    assert "1.65.0" in (project / "THIRD_PARTY_NOTICES.md").read_text()
    version = None
    saw_name = False
    for line in (project / "uv.lock").read_text().splitlines():
        if line == 'name = "streamlit"':
            saw_name = True
            continue
        if saw_name and line.startswith("version = "):
            version = line.split("=", 1)[1].strip().strip('"')
            break
    assert version == "1.65.0"


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
        "Query origin: metricflow",
        "Query origin: reviewed_sql",
        "Query origin: committed_report",
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
        "84a38a404815ed2729917d76",
        "nikonoel",
        "under_10",
        "10_to_29",
        "30_to_59",
        "60_plus",
    )
    missing = [item for item in expected if item not in text]
    assert not missing, missing
    for table in app.table:
        assert len(table.value.columns) <= 3


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
