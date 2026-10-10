"""Publication checks: bounded output, preserved evidence and fail-closed source drift."""

import importlib.util
import json
import shutil
from pathlib import Path

import pytest

pytest.importorskip("markdown", reason="Documentation build uses the optional docs extra")
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("docs_site", ROOT / "scripts/build_docs_site.py")
site = importlib.util.module_from_spec(spec)
spec.loader.exec_module(site)


def test_site_publishes_guides_without_mutating_evidence(tmp_path):
    before = (ROOT / "reports/decisions-routing-comparison.html").read_bytes()
    result = site.build(ROOT, tmp_path / "output")
    assert len(result["pages"]) == 6
    assert result["local_links_checked"] > 50
    assert result["live_requests"] == result["data_downloads"] == 0
    output = tmp_path / "output"
    assert (output / "reports/decisions-routing-comparison.html").read_bytes() == before
    assert (ROOT / "reports/decisions-routing-comparison.html").read_bytes() == before
    assert set(p.name for p in (output / "reports").iterdir()) == {
        "decisions-routing-comparison.html"
    }
    assert not any(".env" in str(p) for p in output.rglob("*"))
    comparison = (output / "comparison.html").read_text()
    assert "24 fresh questions" in comparison and 'id="routing-data"' in comparison
    assert "Known-opening" in (output / "metrics.html").read_text() or (
        "nonempty source opening family" in (output / "metrics.html").read_text()
    )
    assert "uv sync --locked" in (output / "demo.html").read_text()
    descriptions = set()
    for name in result["pages"]:
        parser = site.SiteLinks()
        text = (output / name).read_text()
        parser.feed(text)
        canonical = site.SITE_URL + ("" if name == "index.html" else name)
        assert f'<link rel="canonical" href="{canonical}">' in text
        assert f'<meta property="og:url" content="{canonical}">' in text
        assert f'content="{site.SITE_URL}assets/social-preview.png"' in text
        assert '<meta name="twitter:card" content="summary_large_image">' in text
        assert 'href="assets/favicon.svg"' in text and 'href="favicon.ico"' in text
        description = text.split('<meta name="description" content="', 1)[1].split('"', 1)[0]
        descriptions.add(description)
    assert len(descriptions) == len(result["pages"])
    assert (output / "favicon.ico").read_bytes() == (ROOT / "site/assets/favicon.ico").read_bytes()
    site.build(ROOT, output)  # A generated output is safely rebuildable.


def test_publication_rejects_changed_frozen_run(tmp_path):
    for folder in ("reports", "evals/cases"):
        (tmp_path / folder).mkdir(parents=True)
    for name in site.REPORTS:
        shutil.copy2(ROOT / "reports" / name, tmp_path / "reports" / name)
    for name in (
        "jev_routing_v1.tsv",
        "jev_routing_v1_manifest.json",
        "decisions_routing_v1.json",
        "decisions_routing_v1_manifest.json",
    ):
        shutil.copy2(ROOT / "evals/cases" / name, tmp_path / "evals/cases" / name)
    site.routing(tmp_path)
    frozen = tmp_path / "reports/decisions-fresh-pass-1.json"
    obj = json.loads(frozen.read_text())
    obj["predictions"][0]["route"] = "unsupported"
    frozen.write_text(json.dumps(obj))
    with pytest.raises(ValueError, match="Frozen comparison report hash changed"):
        site.routing(tmp_path)


def test_transposition_routes_share_one_legal_position():
    example = site.transposition_example()
    assert example["kind"] == "illustrative_legal_routes_not_observed_training_results"
    routes = example["routes"]
    assert routes[0]["states"][-1]["position_key"] == routes[1]["states"][-1]["position_key"]
    assert routes[0]["states"][-1]["to_move"] == "White"
    assert len(routes[0]["states"]) == 7


def test_opening_corpus_panel_matches_the_checked_report():
    report = json.loads((ROOT / "reports/opening-corpus.json").read_text())
    html = site.opening_corpus(ROOT)
    assert f"{report['counts']['elite_training_games']:,}" in html
    assert 'id="opening-corpus-data"' in html


def test_opening_corpus_rejects_inconsistent_bands(tmp_path):
    report = json.loads((ROOT / "reports/opening-corpus.json").read_text())
    report["rating_bands"] = {"1000-1599": 1}
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports/opening-corpus.json").write_text(json.dumps(report))
    with pytest.raises(ValueError, match="rating bands do not reconcile"):
        site.opening_corpus(tmp_path)


def test_unrelated_output_and_missing_links_are_rejected(tmp_path):
    output = tmp_path / "unrelated"
    output.mkdir()
    note = output / "keep.txt"
    note.write_text("Owner content")
    with pytest.raises(ValueError, match="not a generated site"):
        site.build(ROOT, output)
    assert note.read_text() == "Owner content"
    (output / "index.html").write_text('<a href="missing.html">Missing</a>')
    with pytest.raises(ValueError, match="Broken generated link"):
        site.validate_site(output)


def test_link_checker_catches_moved_github_modules_and_missing_anchors(tmp_path):
    output = tmp_path / "site"
    output.mkdir()
    page = output / "index.html"
    page.write_text(f'<a href="{site.REPO_URL}src/chess_analytics/ingest.py">Code</a>')
    with pytest.raises(ValueError, match="Broken generated link"):
        site.validate_site(output, ROOT)
    page.write_text('<h1 id="main">Home</h1><a href="#missing">Section</a>')
    with pytest.raises(ValueError, match="Broken generated anchor"):
        site.validate_site(output, ROOT)
    page.write_text(
        '<h1 id="main">Home</h1><a href="#main">Section</a>'
        f'<a href="{site.REPO_URL}src/chess_analytics/ingest/pipeline.py">Code</a>'
        f'<a href="{site.REPO_URL}docs/DEMO.md#2-build-and-check-the-synthetic-snapshots">Demo</a>'
    )
    assert site.validate_site(output, ROOT) == 3
    page.write_text(f'<a href="{site.REPO_URL}docs/DEMO.md#missing">Demo</a>')
    with pytest.raises(ValueError, match="Broken generated anchor"):
        site.validate_site(output, ROOT)


def test_homepage_rejects_disagreeing_final_answer_checkpoints(tmp_path):
    (tmp_path / "reports").mkdir()
    for name in {*site.REPORTS, "opening-corpus.json"}:
        shutil.copy2(ROOT / "reports" / name, tmp_path / "reports" / name)
    shutil.copytree(ROOT / "evals/cases", tmp_path / "evals/cases")
    checkpoint = tmp_path / "reports/M8-e2e-checkpoint.json"
    data = json.loads(checkpoint.read_text())
    data["arms"]["baseline"]["passed"] = 32
    checkpoint.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="Final-answer checkpoints do not reconcile"):
        site.homepage_results(tmp_path)
