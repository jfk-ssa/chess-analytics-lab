"""Publication checks: bounded output, preserved evidence and fail-closed source drift."""

import hashlib
import importlib.util
import json
import re
import shutil
from html.parser import HTMLParser
from pathlib import Path

import pytest

pytest.importorskip("markdown", reason="Documentation build uses the optional docs extra")
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("docs_site", ROOT / "scripts/build_docs_site.py")
site = importlib.util.module_from_spec(spec)
spec.loader.exec_module(site)


class NavigationParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_navigation = False
        self.links = []
        self.toggle = {}

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "nav" and attributes.get("id") == "site-navigation":
            self.in_navigation = True
        if tag == "button" and attributes.get("aria-controls") == "site-navigation":
            self.toggle = attributes
        if self.in_navigation and tag == "a":
            self.links.append(attributes)

    def handle_endtag(self, tag):
        if tag == "nav":
            self.in_navigation = False


def _header_nav_max_width(css: str) -> str:
    """Return the max-width of the media query that restyles the header navigation."""
    found = None
    for match in re.finditer(r"@media\s*\(\s*max-width:\s*(\d+)px\s*\)\s*\{", css):
        depth = 1
        index = match.end()
        while index < len(css) and depth:
            depth += (css[index] == "{") - (css[index] == "}")
            index += 1
        block = css[match.end() : index - 1]
        if ".nav-toggle" in block and ".site-nav" in block:
            assert found is None, "header navigation is restyled by more than one media query"
            found = match.group(1)
    assert found is not None, "header navigation media query not found"
    return found


def test_header_breakpoint_matches_between_css_and_javascript():
    css_width = _header_nav_max_width((ROOT / "site/assets/site.css").read_text())
    script = (ROOT / "site/assets/site.js").read_text()
    js_widths = re.findall(r"matchMedia\(\s*['\"]\(max-width:\s*(\d+)px\)['\"]\s*\)", script)
    assert js_widths == [css_width]


def test_materialized_positions_match_the_publication_checkpoint():
    checkpoint = json.loads((ROOT / "reports/opening-positions-checkpoint.json").read_text())
    target = ROOT / "reports/opening-positions.json"
    assert target.is_file(), "run scripts/materialize_opening_positions.py before docs tests"
    assert (
        hashlib.sha256(target.read_bytes()).hexdigest()
        == checkpoint["files"]["reports/opening-positions.json"]
    )


def test_site_publishes_guides_without_mutating_evidence(tmp_path):
    before = (ROOT / "reports/decisions-routing-comparison.html").read_bytes()
    result = site.build(ROOT, tmp_path / "output")
    assert len(result["pages"]) == 8
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
        navigation = NavigationParser()
        navigation.feed(text)
        destinations = [link["href"] for link in navigation.links]
        assert len(destinations) == len(result["pages"])
        assert set(destinations) == set(result["pages"])
        assert destinations.index("opening-learning.html") < destinations.index(
            "transpositions.html"
        )
        assert [
            link["href"] for link in navigation.links if link.get("aria-current") == "page"
        ] == [name]
        assert navigation.toggle["type"] == "button"
        assert navigation.toggle["aria-controls"] in parser.ids
        assert navigation.toggle["aria-expanded"] == "false"
        assert "hidden" not in navigation.toggle
        class_script = text.split('src="assets/js-class.js', 1)[0].rsplit("<script", 1)[1]
        assert "defer" not in class_script and "async" not in class_script
        if name == "import-games.html":
            assert "script-src 'self'" in text
            assert "unsafe-inline" not in text
        canonical = site.SITE_URL + ("" if name == "index.html" else name)
        assert f'<link rel="canonical" href="{canonical}">' in text
        assert f'<meta property="og:url" content="{canonical}">' in text
        assert f'content="{site.SITE_URL}assets/social-preview.png"' in text
        assert '<meta name="twitter:card" content="summary_large_image">' in text
        assert 'href="assets/favicon.svg"' in text and 'href="favicon.ico"' in text
        description = text.split('<meta name="description" content="', 1)[1].split('"', 1)[0]
        descriptions.add(description)
    assert len(descriptions) == len(result["pages"])
    css = (output / "assets/site.css").read_text()
    assert "html.js .nav-toggle" in css
    assert 'html.js .nav-toggle[aria-expanded="false"] + .site-nav' in css
    assert "classList.add('js')" in (output / "assets/js-class.js").read_text()
    assert (output / "favicon.ico").read_bytes() == (ROOT / "site/assets/favicon.ico").read_bytes()
    assert (output / "assets/opening-positions.json").read_bytes() == (
        ROOT / "reports/opening-positions.json"
    ).read_bytes()
    positions = site.checked_positions(ROOT)
    identifiers = {
        key
        for cohort in positions["cohorts"].values()
        for view in cohort["views"].values()
        for key in view["positions"]
    }
    assert {p.stem for p in (output / "assets/opening-positions").glob("*.svg")} == identifiers
    assert 'id="position-explorer"' in (output / "transpositions.html").read_text()
    analytics = (output / "transpositions.html").read_text()
    learning = (output / "opening-learning.html").read_text()
    assert 'id="position-coverage-chart"' in analytics
    assert 'id="position-depth-chart"' in analytics
    assert 'id="position-scatter-chart"' in analytics
    assert 'href="opening-learning.html#getting-more-games"' in analytics
    assert "opening-learning.html" in (output / "sitemap.xml").read_text()
    assert 'id="opening-data"' not in analytics
    assert 'id="opening-data"' in learning
    assert 'id="position-explorer"' not in learning
    metrics = (output / "metrics.html").read_text()
    assert "opening_positions.json" in metrics
    assert "Alternative-route share" in metrics
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
    page.write_text(f'<a href="{site.REPO_URL}src/chess_analytics/game_import.py#L1-L4">Code</a>')
    assert site.validate_site(output, ROOT) == 1
    page.write_text(f'<a href="{site.REPO_URL}src/chess_analytics/game_import.py#L99999">Code</a>')
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


@pytest.mark.parametrize("damage", ["denominator", "coverage", "route", "hash"])
def test_position_publication_rejects_inconsistent_evidence(tmp_path, damage):
    checkpoint = json.loads((ROOT / "reports/opening-positions-checkpoint.json").read_text())
    for name in {
        *checkpoint["files"],
        "reports/opening-corpus.json",
        "reports/opening-positions-checkpoint.json",
    }:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
    path = tmp_path / "reports/opening-positions.json"
    data = json.loads(path.read_text())
    cohort = data["cohorts"]["elite_reference"]
    if damage == "denominator":
        cohort["denominator_games"] += 1
    elif damage == "coverage":
        cohort["views"]["all"]["rankings"]["transposing"]["top_20_game_coverage"] = (
            cohort["denominator_games"] + 1
        )
    elif damage == "route":
        next(iter(cohort["views"]["all"]["positions"].values()))["routes"][0]["uci"] = "e2e5"
    if damage == "hash":
        path.write_text(path.read_text() + "\n")
    else:
        path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        site.checked_positions(tmp_path)


def test_import_page_has_bounded_checked_reference_and_local_runtime(tmp_path):
    site.build(ROOT, tmp_path / "output")
    output = tmp_path / "output"
    text = (output / "import-games.html").read_text()
    assert "connect-src 'none'" in text and "worker-src 'self'" in text
    assert 'type="file"' in text and "game-import-ui.js" in text
    encoded = text.split('id="import-reference-data">', 1)[1].split("</script>", 1)[0]
    reference = json.loads(encoded)
    checked = site.checked_positions(ROOT)
    assert reference["corpus_snapshot_id"] == checked["corpus_snapshot_id"]
    for cohort, payload in reference["cohorts"].items():
        for view, data in payload["views"].items():
            expected = checked["cohorts"][cohort]["views"][view]
            for kind, ids in data["rankings"].items():
                assert ids == expected["rankings"][kind]["ids"] and len(ids) <= 20
            for identifier, position in data["positions"].items():
                original = expected["positions"][identifier]
                assert position["position_key"] == original["position_key"]
                assert position["routes"] == [{"uci": r["uci"]} for r in original["routes"]]
                assert len(position["routes"]) <= 3
    assert len(list((output / "assets/pieces").glob("*.svg"))) == 12
    assert (output / "assets/vendor/chess-1.4.0.mjs").read_bytes() == (
        ROOT / "site/assets/vendor/chess-1.4.0.mjs"
    ).read_bytes()
    assert (output / "assets/import-example.pgn").read_bytes() == (
        ROOT / "tests/fixtures/imports/authored-games.pgn"
    ).read_bytes()
    assert "local_user_opening_analysis" in (output / "metrics.html").read_text()


def test_import_publication_rejects_changed_vendor(tmp_path):
    vendor = tmp_path / "site/assets/vendor"
    shutil.copytree(ROOT / "site/assets/vendor", vendor)
    (vendor / "chess-1.4.0.mjs").write_text("modified dependency")
    with pytest.raises(ValueError, match="Vendored chess library hash changed"):
        site.game_import(tmp_path, tmp_path / "output")
