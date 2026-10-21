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
        self.in_header = False
        self.nav_depth = 0
        self.links = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "header" and attributes.get("id") == "site-navigation":
            self.in_header = True
        if self.in_header and tag == "nav":
            self.nav_depth += 1
        if self.nav_depth and tag == "a":
            self.links.append(attributes)

    def handle_endtag(self, tag):
        if tag == "nav" and self.nav_depth:
            self.nav_depth -= 1
        if tag == "header" and self.in_header:
            self.in_header = False


def _media_block(css: str, header: str) -> str:
    match = re.search(header, css)
    assert match is not None, header
    depth = 1
    index = match.end()
    while index < len(css) and depth:
        depth += (css[index] == "{") - (css[index] == "}")
        index += 1
    return css[match.end() : index - 1]


def test_header_layouts_fit_without_a_horizontal_scroller():
    """390, 768 and 1280 stay in CSS: no JS breakpoint and no overflow scroller."""
    css = (ROOT / "site/assets/site.css").read_text()
    script = (ROOT / "site/assets/site.js").read_text()
    assert "matchMedia" not in script
    assert ".nav-compact {\n  display: none;" in css
    wide = _media_block(css, r"@media\s*\(\s*max-width:\s*960px\s*\)\s*\{")
    phone = _media_block(css, r"@media\s*\(\s*max-width:\s*600px\s*\)\s*\{")
    tablet = _media_block(
        css, r"@media\s*\(\s*min-width:\s*601px\s*\)\s*and\s*\(\s*max-width:\s*960px\s*\)\s*\{"
    )
    assert "position: static" in wide and "overflow-x: clip" in wide
    assert ".nav-primary" in wide and "display: none" in wide
    assert "flex-direction: column" in phone
    assert "min-height: 44px" in phone and "min-height: 24px" in phone
    assert "flex-wrap: wrap" in phone and "display: contents" in phone
    assert "repeat(5, minmax(0, 1fr))" in tablet
    assert "repeat(6, minmax(0, 1fr))" in tablet
    assert ".cards.preview-cards" in css
    assert "grid-template-columns: minmax(0, 1fr);" in css
    assert "Analyze games" in (ROOT / "scripts/build_docs_site.py").read_text()
    assert "Analyze my games" not in (ROOT / "scripts/build_docs_site.py").read_text()


def _scorecard_media(css: str) -> list[tuple[int, str, int]]:
    """Media blocks that style the scorecard row, in source order."""
    found = []
    pattern = r"@media\s*\(\s*max-width:\s*(\d+)px\s*\)\s*\{"
    for match in re.finditer(pattern, css):
        body = _media_block(css[match.start() :], pattern)
        if ".ev-cards" in body:
            found.append((match.start(), body, int(match.group(1))))
    return found


def _scorecard_columns(viewport: int, cards: int) -> int:
    """Column count implied by the scorecard caps. Five cards still use the four-up cap."""
    if viewport <= 600:
        return 1
    if cards >= 4 and viewport <= 1199:
        return 2
    if cards >= 3 and viewport <= 900:
        return 2
    return min(max(cards, 1), 4)


def test_scorecard_rows_use_equal_tracks():
    """Model cards share fr tracks. Caps keep a 56px rate inside the card."""
    css = (ROOT / "site/assets/site.css").read_text()
    template = (ROOT / "scripts/templates/live_eval.html.j2").read_text()
    assert template.count('class="ev-cards"') == 2
    cards = css[css.index(".ev-cards {") : css.index("}", css.index(".ev-cards {"))]
    assert "--ev-card-columns: 1;" in cards
    assert "grid-template-columns: repeat(var(--ev-card-columns), minmax(0, 1fr));" in cards
    assert "gap: 20px;" in cards
    for count in (2, 3, 4):
        marker = f".ev-cards:has(> .ev-card:nth-child({count})) {{"
        rule = css[css.index(marker) : css.index("}", css.index(marker))]
        assert f"--ev-card-columns: {count};" in rule
    media = _scorecard_media(css)
    assert [width for _, _, width in media] == [1199, 900, 600]
    wide, mid, phone = (body for _, body, _ in media)
    assert ".ev-cards:has(> .ev-card:nth-child(4))" in wide
    assert "--ev-card-columns: 2;" in wide
    assert "nth-child(3)" not in wide
    assert ".ev-cards:has(> .ev-card:nth-child(3))" in mid
    assert ".ev-cards:has(> .ev-card:nth-child(4))" in mid
    assert "--ev-card-columns: 2;" in mid
    assert ".ev-cards," in phone
    assert "--ev-card-columns: 1;" in phone
    for count in (2, 3, 4):
        assert f":has(> .ev-card:nth-child({count}))" in phone
    # 205px of 56px ink, 52px of card padding and the 1px border, on each side of the rate.
    minimum_track = 260
    big = css[css.index(".ev-big {") : css.index("}", css.index(".ev-big {"))]
    assert "font-size: 56px;" in big
    assert ".page-live-eval main {\n  max-width: 1200px;" in css
    narrow_page = _media_block(css, r"@media\s*\(\s*max-width:\s*750px\s*\)\s*\{")
    assert "padding: 28px 18px;" in narrow_page
    for viewport in (390, 601, 700, 800, 900, 1024, 1199, 1280):
        pad = 18 if viewport <= 750 else 28
        content = min(viewport, 1200) - 2 * pad
        for count in (1, 2, 3, 4, 5):
            columns = _scorecard_columns(viewport, count)
            track = (content - 20 * (columns - 1)) / columns
            assert track >= minimum_track, (viewport, count, columns, track)
    card = css[css.index(".ev-card {") : css.index("}", css.index(".ev-card {"))]
    assert "min-width: 0;" in card
    name = css[css.index(".ev-name {") : css.index("}", css.index(".ev-name {"))]
    stat = css[css.index(".ev-stat {") : css.index("}", css.index(".ev-stat {"))]
    assert "overflow-wrap: anywhere;" in name
    assert "display: block;" in stat and "width: 100%;" in stat
    assert "min-width: 0;" in stat and "overflow-wrap: anywhere;" in stat
    assert "text-wrap: pretty;" in stat
    assert ".ev-big small" not in css


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
    assert len(result["pages"]) == 9
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
    architecture = (output / "architecture.html").read_text()
    assert 'href="https://jfk-ssa.github.io/chess-analytics-lab/dbt-docs/"' in architecture
    assert "tiny fixture" in architecture
    placeholder = (output / "dbt-docs" / "index.html").read_text()
    assert "dbt docs generate" in placeholder
    assert site.PRIMARY_NAV == (
        ("Home", "index.html"),
        ("Data pipeline", "architecture.html"),
        ("Transpositions", "transpositions.html"),
        ("Analyze games", "import-games.html"),
        ("AI analyst", "comparison.html"),
    )
    assert site.LAB_NAV == (
        ("Metrics & data", "metrics.html"),
        ("Architecture", "architecture.html"),
        ("Run the demo", "demo.html"),
        ("AI comparison", "comparison.html"),
        ("Opening learning", "opening-learning.html"),
        ("Live eval", "live-eval.html"),
    )
    descriptions = set()
    for name in result["pages"]:
        parser = site.SiteLinks()
        text = (output / name).read_text()
        parser.feed(text)
        navigation = NavigationParser()
        navigation.feed(text)
        destinations = [link["href"] for link in navigation.links]
        expected = [path for _, path in site.PRIMARY_NAV + site.LAB_NAV]
        assert destinations == expected + expected
        assert set(destinations) == set(result["pages"])
        current = [link["href"] for link in navigation.links if link.get("aria-current") == "page"]
        assert current == [href for href in destinations if href == name]
        assert "nav-toggle" not in text and "js-class.js" not in text and "nav-group" not in text
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
    assert ".nav-compact" in css and "nav-toggle" not in css and "html.js" not in css
    assert not (output / "assets/js-class.js").exists()
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
    index = (output / "index.html").read_text()
    assert 'class="cards preview-cards"' in index
    assert "Drop in a PGN" in index
    report = (output / "live-eval.html").read_text()
    assert 'class="page-live-eval"' in report
    assert 'href="live-eval.html" aria-current="page"' in report
    assert "86.25%" in report and "97.50%" in report and "97.08%" in report
    assert "same pass-rate" not in report
    assert "does not separate" not in report
    assert "3,810.5" in report
    assert "same frozen inputs" in report
    assert "left out of the test" in report
    assert "boundary_budget" in report
    assert "needs_clarification" in report
    assert "public_extract.py" in report
    assert "implementation_sha256" in report
    assert "unexplained" not in report.lower()
    assert "under investigation" not in report.lower()
    assert "fonts.googleapis.com" not in report
    assert "data:font/woff2" not in report
    assert 'id="ev-heatmap-title"' in report and 'id="ev-heatmap-desc"' in report
    assert "were not re-run" not in report
    assert "recomputed from the rows" in report
    assert "GitHub run-id order" in report
    luna_at = report.index("live-eval-receipt-39494372489.json")
    sol_at = report.index("live-eval-receipt-39519293762.json")
    grok_at = report.index("live-eval-receipt-grok-4.7-low-r5-39541049632.json")
    assert luna_at < sol_at < grok_at
    assert 'rel="preload"' in report
    assert "inter-latin-wght-normal.woff2" in report
    assert "live-eval.html" in (output / "sitemap.xml").read_text()
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


def test_homepage_preview_reads_checked_reports():
    html = site.homepage_preview(ROOT)
    corpus = json.loads((ROOT / "reports/opening-corpus.json").read_text())
    positions = json.loads((ROOT / "reports/opening-positions.json").read_text())
    elite = positions["cohorts"]["elite_reference"]["views"]["all"]
    checkpoint = json.loads((ROOT / "reports/decisions-checkpoint.json").read_text())
    run = next(
        item
        for item in checkpoint["runs"]
        if item["report"] == "decisions-historical-test.json" and item["split"] == "test"
    )
    assert f"{corpus['counts']['training_games']:,}" in html
    assert f"{elite['transposing_positions']:,}" in html
    assert f"{elite['denominator_games']:,}" in html
    assert f"{run['correct']}/{run['cases']}" in html
    assert "This is route choice, not a correct chess answer." in html
    assert "Drop in a PGN" in html
    assert "Analyze games" in html
    analyze = html.split('href="import-games.html"', 1)[1]
    assert "preview-stat" not in analyze
    assert 'role="img"' in html
    assert "vertical axis runs from 0 to 0.50" in html
    for href in (
        "architecture.html",
        "transpositions.html",
        "comparison.html",
        "import-games.html",
    ):
        assert f'class="card preview-card" href="{href}"' in html


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
