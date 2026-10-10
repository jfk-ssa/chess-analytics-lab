"""Build a credential-free, allowlisted static documentation site from tracked sources."""

import argparse
import csv
import hashlib
import html
import json
import re
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

import chess
import chess.svg
import markdown

REPO_URL = "https://github.com/jfk-ssa/chess-analytics-lab/blob/main/"
PAGES = {
    "README.md": "index.html",
    "CLASSIFIER_COMPARISON.md": "comparison.html",
    "ARCHITECTURE.md": "architecture.html",
    "METRICS.md": "metrics.html",
    "DATA_DICTIONARY.md": "metrics.html",
    "DEMO.md": "demo.html",
    "TRANSPOSITION_LEARNING.md": "transpositions.html",
}
REPORTS = (
    "decisions-development.json",
    "decisions-historical-test.json",
    "decisions-historical-e2e.json",
    "decisions-fresh-pass-1.json",
    "decisions-fresh-pass-2.json",
    "decisions-fresh-pass-3.json",
    "decisions-fresh-rules.json",
    "decisions-development-policy.json",
    "decisions-checkpoint.json",
    "M8-routing-rules-test.json",
    "M8-jev-pass-1.json",
    "M8-jev-pass-2.json",
    "M8-analyst-pass-1.json",
    "M8-e2e-checkpoint.json",
)
ASSETS = {
    "site.css": "site/assets/site.css",
    "site.js": "site/assets/site.js",
    "demo-overview.png": "site/assets/demo-overview.png",
    "demo-analyst.png": "site/assets/demo-analyst.png",
    "fonts/inter-latin-wght-normal.woff2": (
        "analytics_m4/static/fonts/inter-latin-wght-normal.woff2"
    ),
    "fonts/LICENSE.inter.txt": "analytics_m4/static/fonts/LICENSE.inter.txt",
    "fonts/provenance.json": "site/assets/fonts/provenance.json",
}
NAV = (
    ("index.html", "Start here"),
    ("comparison.html", "Comparison"),
    ("architecture.html", "Architecture"),
    ("metrics.html", "Metrics & data"),
    ("transpositions.html", "Opening learning"),
    ("demo.html", "Run the demo"),
)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def research_cards(content):
    """Present the maintained research comparison as readable source cards."""

    def replace(match):
        table = match.group(0)
        headers = re.findall(r"<th(?:\s[^>]*)?>(.*?)</th>", table, re.DOTALL)
        if headers != [
            "Primary source",
            "Finding relevant to the design",
            "Interpretation for this project",
        ]:
            return table
        cards = []
        for row in re.findall(r"<tr>(.*?)</tr>", table, re.DOTALL):
            cells = re.findall(r"<td(?:\s[^>]*)?>(.*?)</td>", row, re.DOTALL)
            if not cells:
                continue
            if len(cells) != 3:
                raise ValueError("Research comparison must contain three cells per source")
            source, finding, interpretation = cells
            cards.append(
                f'<section class="research-card"><h3>{source}</h3><dl>'
                f"<dt>Research finding</dt><dd>{finding}</dd>"
                f"<dt>What this suggests for our lessons</dt><dd>{interpretation}</dd>"
                "</dl></section>"
            )
        return '<div class="research-cards">' + "".join(cards) + "</div>"

    return re.sub(r"<table>.*?</table>", replace, content, flags=re.DOTALL)


def md(repo, name):
    source = repo / "docs" / name
    text = source.read_text()
    text = re.sub(r"^\*\*HTML version:\*\*.*\n", "", text, flags=re.MULTILINE)

    def link(match):
        label, dest = match.groups()
        parsed = urlsplit(dest)
        if parsed.scheme or dest.startswith("#"):
            return match.group(0)
        target = (source.parent / unquote(parsed.path)).resolve()
        if not target.is_relative_to(repo.resolve()) or not target.exists():
            raise ValueError(f"Missing or outside-repository Markdown target in {name}: {dest}")
        relative = target.relative_to(repo.resolve()).as_posix()
        page = PAGES.get(target.name) if target.parent == repo.resolve() / "docs" else None
        if relative == "reports/decisions-routing-comparison.html":
            page = "reports/decisions-routing-comparison.html"
        url = page or REPO_URL + relative
        if parsed.fragment:
            url += "#" + parsed.fragment
        return f"[{label}]({url})"

    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", link, text)
    engine = markdown.Markdown(extensions=["fenced_code", "tables", "toc"])
    content = engine.convert(text)
    if name == "TRANSPOSITION_LEARNING.md":
        content = research_cards(content)

    def table_layout(match):
        table = match.group(0)
        headers = re.findall(r"<th(?:\s[^>]*)?>(.*?)</th>", table, re.DOTALL)
        wide = (
            name == "CLASSIFIER_COMPARISON.md"
            or len(headers) >= 4
            or "Proposed relation" in headers
        )
        css = "scroll article-table-wide" if wide else "scroll"
        return f'<div class="{css}">{table}</div>'

    content = re.sub(r"<table>.*?</table>", table_layout, content, flags=re.DOTALL)
    content = re.sub(r"<(/?)h1([ >])", r"<\1h2\2", content)
    toc = re.sub(r'^<div class="toc">\s*|\s*</div>\s*$', "", engine.toc)
    return (
        '<div class="toc" role="navigation" aria-label="On this page"><strong>On this page</strong>'
        + toc
        + '</div><article class="article">'
        + content
        + "</article>"
    )


def shell(title, active, intro, body, commit):
    nav = "".join(
        f'<a href="{path}"' + (' aria-current="page"' if path == active else "") + f">{name}</a>"
        for path, name in NAV
    )
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description"
content="Local chess analytics, reproducible evidence and learning guides.">
<title>{html.escape(title)} · Chess Analytics Lab</title>
<link rel="stylesheet" href="assets/site.css?v={commit}">
<script defer src="assets/site.js?v={commit}"></script></head>
<body><a class="skip" href="#main">Skip to content</a><header class="topbar"><div class="nav-inner">
<a class="brand" href="index.html">Chess Analytics Lab <span class="badge">Learning lab</span></a>
<nav aria-label="Main navigation">{nav}</nav></div></header><main id="main">
<div class="hero"><div class="eyebrow">Data • Analytics • Evaluated AI</div>
<h1>{html.escape(title)}</h1>
<p class="lead">{intro}</p><p class="source-note">Generated from maintained Markdown, contracts and
recorded evidence. <a href="{REPO_URL}docs/README.md">Repository guides</a></p></div>{body}</main>
<footer>Source revision {html.escape(commit)} · Static documentation ·
No runtime model calls or game downloads.
<a href="{REPO_URL}docs/SITE.md">Build and publishing runbook</a></footer></body></html>'''


def architecture():
    stages = (
        (
            "ingest",
            "Bounded ingestion",
            "src/chess_analytics/ingest.py",
            "Read a pinned archive or fixture; preserve exclusions, quarantine and source hashes.",
        ),
        (
            "publish",
            "Checked snapshots",
            "src/chess_analytics/warehouse.py",
            "Validate immutable Parquet/DuckDB output before replacing its current pointer.",
        ),
        (
            "marts",
            "Optional marts",
            "platform_m2/pipeline.py",
            "Transform a copy through dbt; record lineage, validation and recovery.",
        ),
        (
            "metrics",
            "Opening & clock metrics",
            "analytics_m4/analysis.py",
            "Apply explicit cohorts, denominators, missingness and observed-prefix caveats.",
        ),
        (
            "analyst",
            "Checked analyst",
            "analyst_m5/tools.py",
            "Allowlisted read-only actions compute values and bind evidence IDs to the snapshot.",
        ),
        (
            "evaluate",
            "Independent scoring",
            "analyst_m5/evaluation.py",
            "Compare responses with frozen references and retain failures, repetitions and costs.",
        ),
    )
    flow = (
        '<ol class="pipeline" aria-label="Pipeline stages">'
        + "".join(
            f'<li><a href="#stage-{key}"><strong>{name}</strong><small>{desc}</small></a></li>'
            for key, name, _, desc in stages
        )
        + "</ol>"
    )
    details = "".join(
        f'<details class="definition" id="stage-{key}"><summary>{name}</summary><p>{desc}</p>'
        f'<a href="{REPO_URL}{path}">Inspect the implementation</a></details>'
        for key, name, path, desc in stages
    )
    return (
        (
            "<h2>Follow a question through the system</h2><p>Select a stage to"
            " inspect its role and code.</p>"
        )
        + flow
        + details
    )


def opening_corpus(repo):
    report = json.loads((repo / "reports/opening-corpus.json").read_text())
    counts = report["counts"]
    if sum(report["rating_bands"].values()) != counts["training_games"]:
        raise ValueError("opening corpus rating bands do not reconcile")
    if sum(source["games"] for source in report["training_sources"]) != counts["training_games"]:
        raise ValueError("opening corpus source summaries do not reconcile")
    data = {
        "counts": counts,
        "sources": report["training_sources"],
        "snapshot_id": report["snapshot_id"],
    }
    payload = json.dumps(data).replace("<", "\\u003c")
    cards = "".join(
        f'<div class="corpus-stat"><span>{label}</span><strong>{value:,}</strong>'
        f"<small>{detail}</small></div>"
        for label, value, detail in (
            ("Unique retained games", counts["unique_retained_games"], "Fixtures excluded"),
            ("Both players 1000+", counts["both_at_least_1000"], "Includes ratings exactly 1000"),
            ("Opening corpus", counts["training_games"], "Completed games; at least ten moves"),
        )
    )
    return f"""<section class="corpus-panel" aria-labelledby="corpus-title">
<div class="eyebrow">Public games · White first</div>
<h2 id="corpus-title">A stronger reference corpus</h2>
<p>The default reference is Lichess Elite: both players rated 2300+, with at least
one rated 2500+, and bullet excluded. The broader comparison corpus enforces a
1000 rating floor for both players. Each cohort keeps its own denominator.</p>
<div class="corpus-stats">{cards}</div>
<div class="toolbar"><div><label for="opening-cohort">Explore a training cohort</label>
<select id="opening-cohort"><option value="elite_reference">Elite reference · default</option>
<option value="rated_public">Public games · both players 1000+</option>
<option value="all">All eligible games · combined inventory</option></select></div>
<div><strong id="opening-cohort-count">{counts["elite_training_games"]:,}</strong>
<span>eligible games</span></div></div>
<p id="opening-cohort-note" aria-live="polite">Full curated November 2025 file;
stronger play is useful for reference study, but ratings do not certify every move.</p>
<div class="scroll"><table><thead><tr><th>Source period</th><th>Cohort</th>
<th>Games</th><th>Observed dates</th><th>Minimum player rating</th></tr></thead>
<tbody id="opening-cohort-rows"></tbody></table></div>
<p class="source-note">Counts come from a checked local game index. The full PGNs remain
local; this page downloads no database. Opening-position analysis and drills are the
next milestone. <a href="#getting-more-games">Sources, exclusions and costs</a></p>
<noscript>The default Elite cohort contains {counts["elite_training_games"]:,} games.
Enable JavaScript to switch the cohort summary.</noscript></section>
<script type="application/json" id="opening-corpus-data">{payload}</script>"""


def transposition_example():
    """Replay two legal illustrative routes; retain full FEN and opening identity."""
    routes = []
    for name, line, moves in (
        ("Knight first", "1.d4 Nf6 2.c4 e6 3.Nf3 d5", "d4 Nf6 c4 e6 Nf3 d5"),
        ("Center first", "1.d4 d5 2.c4 e6 3.Nf3 Nf6", "d4 d5 c4 e6 Nf3 Nf6"),
    ):
        board = chess.Board()
        states = []
        for ply, san in enumerate([None, *moves.split()]):
            lastmove = board.push_san(san) if san is not None else None
            states.append(
                {
                    "ply": ply,
                    "san": san,
                    "full_fen": board.fen(),
                    "position_key": " ".join(board.fen(en_passant="legal").split()[:4]),
                    "to_move": "White" if board.turn == chess.WHITE else "Black",
                    "svg": chess.svg.board(
                        board,
                        lastmove=lastmove,
                        size=400,
                        colors={"square light": "#eaf1eb", "square dark": "#789b8d"},
                    ),
                }
            )
        routes.append({"name": name, "line": line, "states": states})
    if routes[0]["states"][-1]["position_key"] != routes[1]["states"][-1]["position_key"]:
        raise ValueError("Illustrative routes no longer transpose")
    return {"kind": "illustrative_legal_routes_not_observed_training_results", "routes": routes}


def transpositions():
    example = transposition_example()
    data = json.dumps(example).replace("<", "\\u003c")
    return (
        """<section class="opening-lab" aria-labelledby="opening-lab-title">
<div class="opening-lab-header"><span class="badge">Illustrative legal example</span>
<h2 id="opening-lab-title">Two routes. One position to recognize.</h2>
<p>Replay either move order, then compare the shared position after Black's third move.
The board example is verified by legal replay; it is not a measured learning result.</p></div>
<div class="opening-grid"><div>
<label for="opening-route">Choose an arrival route</label>
<select id="opening-route"><option value="0">Knight first</option>
<option value="1">Center first</option></select>
<div id="opening-board" class="opening-board" role="img"
aria-label="Opening board after six half-moves, White to move">"""
        + (example["routes"][0]["states"][-1]["svg"])
        + """</div><div class="opening-controls">
<button type="button" id="opening-back" aria-label="Previous half-move">Previous</button>
<label for="opening-ply">Half-move <output id="opening-ply-value">6 / 6</output></label>
<input id="opening-ply" type="range" min="0" max="6" value="6" step="1">
<button type="button" id="opening-next" aria-label="Next half-move">Next</button></div>
<p id="opening-board-status" class="source-note" aria-live="polite">White to move.</p>
</div><div class="opening-explanation">
<div class="route-card"><h3>Knight first</h3><p><code>1.d4 Nf6 2.c4 e6 3.Nf3 d5</code></p></div>
<div class="route-card"><h3>Center first</h3><p><code>1.d4 d5 2.c4 e6 3.Nf3 Nf6</code></p></div>
<div class="callout"><strong id="opening-match-title">Shared opening position</strong>
<p id="opening-match-note" aria-live="polite">The board, side to move, castling rights,
and legal en passant availability match after both routes.</p></div>
<h3>Attach knowledge to the position</h3><ol>
<li>Recognize the arrangement and the opponent's threats.</li>
<li>Recall candidate moves, pawn breaks, and their reasons.</li>
<li>Check tactics and differences before choosing a move.</li></ol>
<p class="source-note">Earlier deviations need their own lessons. A move order can
leave this route before the shared position is reached.</p></div></div>
<noscript>The two printed routes transpose after six half-moves. Enable JavaScript
to step through their intermediate positions.</noscript></section>
<script type="application/json" id="opening-data">"""
        + data
        + "</script>"
    )


def routing(repo):
    records = {n: json.loads((repo / "reports" / n).read_text()) for n in REPORTS}
    for name, expected in records["decisions-checkpoint.json"]["files"].items():
        if digest((repo / "reports" / name).read_bytes()) != expected:
            raise ValueError("Frozen comparison report hash changed: " + name)
    old_manifest = json.loads((repo / "evals/cases/jev_routing_v1_manifest.json").read_text())
    old = repo / "evals/cases/jev_routing_v1.tsv"
    fresh_manifest = json.loads(
        (repo / "evals/cases/decisions_routing_v1_manifest.json").read_text()
    )
    fresh = repo / "evals/cases/decisions_routing_v1.json"
    for path, manifest in ((old, old_manifest), (fresh, fresh_manifest)):
        if digest(path.read_bytes()) != manifest["case_sha256"]:
            raise ValueError("Frozen route case hash changed")
    with old.open() as handle:
        historical = [r for r in csv.DictReader(handle, delimiter="\t") if r["split"] == "test"]
    cohorts = {"historical": historical, "fresh": json.loads(fresh.read_text())}
    data = {}
    for cohort, rows in cohorts.items():
        report = records[
            "decisions-historical-test.json"
            if cohort == "historical"
            else "decisions-fresh-pass-1.json"
        ]
        decisions = {r["id"]: r for r in report["predictions"]}
        rules_report = records[
            "M8-routing-rules-test.json" if cohort == "historical" else "decisions-fresh-rules.json"
        ]
        rules = {
            r["id"]: r["route"] for r in rules_report.get("scoring", rules_report)["predictions"]
        }
        jev = [
            {r["id"]: r["route"] for r in records[f"M8-jev-pass-{i}.json"]["predictions"]}
            for i in (1, 2)
        ]
        if set(decisions) != {r["id"] for r in rows}:
            raise ValueError("Comparison question identities differ")
        data[cohort] = [
            dict(
                id=r["id"],
                question=r["question"],
                expected=r["label"],
                rules=rules[r["id"]],
                jev1=jev[0].get(r["id"]) if cohort == "historical" else None,
                jev2=jev[1].get(r["id"]) if cohort == "historical" else None,
                decisions=decisions[r["id"]]["route"],
                probability=decisions[r["id"]]["probabilities"].get(decisions[r["id"]]["route"], 0),
            )
            for r in rows
        ]
    threshold = records["decisions-development-policy.json"]["threshold"]
    encoded = json.dumps(data).replace("<", "\\u003c")
    return (
        f"""<section><h2>Explore routing and fallback</h2><p>These controls recompute acceptance
from saved classifications. They make no requests.
The frozen development threshold is {threshold:.2f};
changing it here is descriptive exploration, not a newly validated production policy.</p>
<noscript>The complete summary and recorded report below remain readable
with JavaScript disabled.</noscript>
<div class="toolbar"><div><label for="cohort">Question set</label><select id="cohort">
<option value="historical">40 historical questions — shared comparison</option>
<option value="fresh">24 fresh questions — Decisions and rules</option></select></div>
<div><label for="threshold">Minimum chosen-option probability</label><select id="threshold">"""
        + "".join(
            f'<option value="{v}"' + (" selected" if v == threshold else "") + f">{v:.2f}</option>"
            for v in (0.0, 0.5, 0.7, 0.85, 0.95)
        )
        + """</select></div></div><p id="routing-status" class="stats" aria-live="polite"></p>
<div class="scroll"><table>
<caption>Saved route choices; colored cells show agreement with reviewed labels.</caption>
<thead><tr><th>ID</th><th>Question</th><th>Expected route</th>
<th>Rules</th><th>Jev run 1</th><th>Jev run 2</th>
<th>Decisions</th><th>Chosen-option probability</th><th>Explored gate</th></tr></thead>
<tbody id="routing-rows"></tbody></table></div>
<script type="application/json" id="routing-data">"""
        + encoded
        + "</script></section>"
    )


def definitions(repo):
    cards = []
    contract_files = (
        "game_draw_rate.json",
        "opening_usage.json",
        "opening_player_score.json",
        "opening_adjusted_score.json",
        "clock_pressure_error_proxy.json",
        "evaluation_coverage.json",
    )
    for name in contract_files:
        obj = json.loads((repo / "contracts" / name).read_text())
        title = obj.get("id", name.removesuffix(".json"))
        cards.append(
            f'<details class="definition" data-definition><summary>{html.escape(title)}</summary>'
            f'<a href="{REPO_URL}contracts/{name}">Versioned contract</a>'
            "<pre>" + html.escape(json.dumps(obj, indent=2)) + "</pre></details>"
        )
    for name in ("tables.json", "m3_tables.json"):
        for key, fields in json.loads((repo / "contracts" / name).read_text()).items():
            if not isinstance(fields, dict):
                continue
            rows = "".join(
                f"<tr><td>{html.escape(k)}</td><td>{html.escape(v)}</td></tr>"
                for k, v in fields.items()
            )
            cards.append(
                f'<details class="definition" data-definition><summary>{key} schema</summary>'
                f'<a href="{REPO_URL}contracts/{name}">Storage contract</a>'
                "<table><tr><th>Column</th><th>Type</th></tr>" + rows + "</table></details>"
            )
    return (
        """<h2>Find a definition or column</h2>
<label for="definition-search">Search names, definitions and schemas</label>
<input id="definition-search" class="search" type="search"
placeholder="Try denominator, rating, clock or missing">
<p id="search-status" aria-live="polite">9 definitions or schemas shown</p>"""
        + "".join(cards)
        + """
<h2>Why the denominator matters</h2><p>This worked illustration starts with the authored demo:
3 proxy errors among 6 evaluable moves. Change the number of moves with missing evaluations;
they change coverage, while the proxy rate stays tied to evaluable moves.</p>
<div class="toolbar"><div><label for="missing-moves">
Missing evaluations: <span id="missing-value">2</span></label>
<input id="missing-moves" type="range" min="0" max="14" value="2"></div></div>
<div class="fraction"><div>Proxy rate<br><strong id="proxy-rate">3 / 6 = 50.0%</strong></div>
<div>Evaluation coverage<br><strong id="coverage-rate">6 / 8 = 75.0%</strong></div></div>
<p class="source-note">Other slider values are hypothetical examples,
not new observations or model results.</p>"""
    )


def validate_site(output):
    class Links(HTMLParser):
        def __init__(self):
            super().__init__()
            self.refs = []

        def handle_starttag(self, tag, attrs):
            for k, value in attrs:
                if k in ("href", "src") and value:
                    self.refs.append(value)

    checked = 0
    for path in output.rglob("*.html"):
        parser = Links()
        parser.feed(path.read_text())
        for ref in parser.refs:
            url = urlsplit(ref)
            if url.scheme or ref.startswith("#"):
                continue
            target = (path.parent / unquote(url.path)).resolve()
            if not target.is_relative_to(output.resolve()) or not target.exists():
                raise ValueError(f"Broken generated link in {path.name}: {ref}")
            checked += 1
    return checked


def build(repo, output):
    repo, output = repo.resolve(), output.resolve()
    if output == repo or (output.is_relative_to(repo) and not output.is_relative_to(repo / "work")):
        raise ValueError("Use an ignored work output directory or a separate temporary directory")
    if output.exists() and any(output.iterdir()):
        if not (output / ".site-output").is_file():
            raise ValueError("Refusing to replace a directory that is not a generated site")
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / ".site-output").write_text("Generated static site; safe to rebuild.\n")
    (output / ".nojekyll").touch()
    (output / "assets").mkdir()
    for name, source in ASSETS.items():
        asset = repo / source
        if not asset.exists() and name not in ("demo-overview.png", "demo-analyst.png"):
            raise ValueError(f"Missing required public asset: {name}")
        if asset.exists():
            if asset.is_symlink():
                raise ValueError(f"Refusing symlink asset: {name}")
            (output / "assets" / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(asset, output / "assets" / name)
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=repo, text=True
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        commit = "local export"
    home = (
        '<div class="cards">'
        + "".join(
            f'<a class="card" href="{page}"><strong>{title}</strong>'
            f"<p>{desc}</p><small>{extra}</small></a>"
            for page, title, desc, extra in (
                (
                    "comparison.html",
                    "Read the measured results",
                    (
                        "Rules, Jev and Decisions on shared questions; explore routing err"
                        "ors and thresholds."
                    ),
                    "Actual classification runs + explicitly labeled replay",
                ),
                (
                    "architecture.html",
                    "Follow the pipeline",
                    "Inspect how source bytes become checked metrics and evidence-bound answers.",
                    "Six stages with code links",
                ),
                (
                    "metrics.html",
                    "Understand the definitions",
                    (
                        "Search versioned contracts and schemas; explore eligible versus e"
                        "valuable denominators."
                    ),
                    "Explicit missingness and coverage",
                ),
                (
                    "transpositions.html",
                    "Learn positions across move orders",
                    "Explore shared opening positions, the learning rationale, "
                    "and a White-first plan.",
                    "Legal board walkthrough + research design",
                ),
                (
                    "demo.html",
                    "Run it yourself",
                    "Build tiny synthetic data, explore the dashboard and replay a checked answer.",
                    "No API key; no real archive download",
                ),
            )
        )
        + "</div>"
    )
    demo_images = ""
    for name, caption in (
        (
            "demo-overview.png",
            "Actual local dashboard on the authored synthetic fixture: four accepted games.",
        ),
        (
            "demo-analyst.png",
            "Actual fixture replay in the local analyst view; the plan was authored in advance.",
        ),
    ):
        if (repo / "site/assets" / name).exists():
            demo_images += (
                f'<figure><a href="assets/{name}"><img src="assets/{name}" '
                f'alt="{caption}" loading="lazy"></a><figcaption>{caption}</figcaption>'
                f'<a class="full-size" href="assets/{name}">View full-size screenshot</a></figure>'
            )
    bodies = {
        "index.html": (
            "Start with evidence. Learn by doing.",
            (
                "A local chess data platform, descriptive analytics and an evaluat"
                "ed AI analyst—one reproducible learning project."
            ),
            home + md(repo, "README.md"),
        ),
        "architecture.html": (
            "From game records to checked answers",
            "Explore the pipeline, its boundaries, and the code responsible for each stage.",
            architecture() + md(repo, "ARCHITECTURE.md"),
        ),
        "metrics.html": (
            "Make every denominator explicit",
            (
                "Search contracts and table schemas, then inspect how definitions "
                "handle missing values."
            ),
            definitions(repo) + md(repo, "METRICS.md") + md(repo, "DATA_DICTIONARY.md"),
        ),
        "demo.html": (
            "Run the lab on tiny synthetic games",
            (
                "A step-by-step local walkthrough with known answers and fixture r"
                "eplay. Installation may download dependencies once."
            ),
            demo_images + md(repo, "DEMO.md"),
        ),
        "comparison.html": (
            "Compare routes. Then compare answers.",
            (
                "Shared questions, recorded costs and clear evidence boundaries fo"
                "r rules, Jev and OpenAI Decisions."
            ),
            md(repo, "CLASSIFIER_COMPARISON.md")
            + routing(repo)
            + (
                '<h2>Full recorded comparison report</h2><p><a href="reports/decis'
                'ions-routing-comparison.html">Open the full report in its own pag'
                'e</a></p><iframe class="report-frame" title="Recorded Decisions c'
                'omparison report" src="reports/decisions-routing-comparison.html"'
                ' loading="lazy"></iframe>'
            ),
        ),
        "transpositions.html": (
            "Learn the position. Recognize every route.",
            "Explore how opening sequences converge, why familiar positions may help decisions, "
            "and how we can evaluate the learning method.",
            opening_corpus(repo) + transpositions() + md(repo, "TRANSPOSITION_LEARNING.md"),
        ),
    }
    for name, (title, intro, body) in bodies.items():
        (output / name).write_text(shell(title, name, intro, body, commit))
    (output / "reports").mkdir()
    shutil.copy2(
        repo / "reports/decisions-routing-comparison.html",
        output / "reports/decisions-routing-comparison.html",
    )
    source_files = {
        repo / "scripts/build_docs_site.py",
        repo / "pyproject.toml",
        repo / "uv.lock",
        repo / "reports/decisions-routing-comparison.html",
        repo / "evals/cases/jev_routing_v1.tsv",
        repo / "evals/cases/jev_routing_v1_manifest.json",
        repo / "evals/cases/decisions_routing_v1.json",
        repo / "evals/cases/decisions_routing_v1_manifest.json",
    }
    source_files.update(repo / "docs" / name for name in PAGES)
    source_files.update(repo / "reports" / name for name in REPORTS)
    source_files.add(repo / "reports/opening-corpus.json")
    source_files.update((repo / "contracts").glob("*.json"))
    source_files.update(
        repo / source for name, source in ASSETS.items() if (output / "assets" / name).is_file()
    )
    manifest = {
        "kind": "static_documentation_build_no_live_requests",
        "source_revision": commit,
        "pages": sorted(bodies),
        "local_links_checked": validate_site(output),
        "sources": {
            p.relative_to(repo).as_posix(): digest(p.read_bytes()) for p in sorted(source_files)
        },
        "outputs": {
            p.relative_to(output).as_posix(): digest(p.read_bytes())
            for p in sorted(output.rglob("*"))
            if p.is_file()
        },
        "live_requests": 0,
        "data_downloads": 0,
    }
    (output / "site-build.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, default=Path("work/docs-site"))
    args = parser.parse_args()
    manifest = build(args.project, args.output)
    print(
        json.dumps(
            {k: manifest[k] for k in ("kind", "pages", "local_links_checked", "live_requests")}
        )
    )


if __name__ == "__main__":
    main()
