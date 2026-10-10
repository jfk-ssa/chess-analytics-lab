"""Build a credential-free, allowlisted static documentation site from tracked sources."""

import argparse
import csv
import hashlib
import html
import json
import re
import shutil
import subprocess
from decimal import Decimal
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

import chess
import chess.svg
import markdown

REPO_URL = "https://github.com/jfk-ssa/chess-analytics-lab/blob/main/"
SITE_URL = "https://jfk-ssa.github.io/chess-analytics-lab/"
PAGES = {
    "HOME.md": "index.html",
    "CLASSIFIER_COMPARISON.md": "comparison.html",
    "ARCHITECTURE.md": "architecture.html",
    "METRICS.md": "metrics.html",
    "DATA_DICTIONARY.md": "metrics.html",
    "DEMO.md": "demo.html",
    "GAME_IMPORT.md": "import-games.html",
    "TRANSPOSITIONS.md": "transpositions.html",
    "TRANSPOSITION_LEARNING.md": "opening-learning.html",
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
    "game-import-core.mjs": "site/assets/game-import-core.mjs",
    "game-import-worker.mjs": "site/assets/game-import-worker.mjs",
    "game-import-ui.js": "site/assets/game-import-ui.js",
    "vendor/chess-1.4.0.mjs": "site/assets/vendor/chess-1.4.0.mjs",
    "vendor/LICENSE.chess-js.txt": "site/assets/vendor/LICENSE.chess-js.txt",
    "vendor/chess-js-provenance.json": "site/assets/vendor/chess-js-provenance.json",
    "import-example.pgn": "tests/fixtures/imports/authored-games.pgn",
    "site.css": "site/assets/site.css",
    "site.js": "site/assets/site.js",
    "position-explorer.js": "site/assets/position-explorer.js",
    "position-charts.js": "site/assets/position-charts.js",
    "favicon.svg": "site/assets/favicon.svg",
    "social-preview.png": "site/assets/social-preview.png",
    "demo-overview.png": "site/assets/demo-overview.png",
    "demo-analyst.png": "site/assets/demo-analyst.png",
    "fonts/inter-latin-wght-normal.woff2": (
        "src/chess_analytics/dashboard/static/fonts/inter-latin-wght-normal.woff2"
    ),
    "fonts/LICENSE.inter.txt": "src/chess_analytics/dashboard/static/fonts/LICENSE.inter.txt",
    "fonts/provenance.json": "site/assets/fonts/provenance.json",
}
NAV = (
    ("index.html", "Start here"),
    ("comparison.html", "Comparison"),
    ("architecture.html", "Architecture"),
    ("metrics.html", "Metrics & data"),
    ("transpositions.html", "Transpositions"),
    ("opening-learning.html", "Opening learning"),
    ("import-games.html", "Analyze my games"),
    ("demo.html", "Run the demo"),
)


def digest(data):
    return hashlib.sha256(data).hexdigest()


NUMERIC_COLUMNS = {
    "Correct routes": "number",
    "Correct final answers": "number",
    "Gross API cost per run": "currency",
    "Gross total": "currency",
    "Accepted games": "number",
    "Retained games": "number",
    "Training games": "number",
}


def aligned_table(table):
    """Declare alignment by column; annotations cannot change a cell's role."""
    headers = re.findall(r"<th(?:\s[^>]*)?>(.*?)</th>", table, re.DOTALL)
    roles = [NUMERIC_COLUMNS.get(re.sub(r"<[^>]+>", "", h), "text") for h in headers]

    def row_layout(match):
        index = 0

        def cell_layout(cell):
            nonlocal index
            tag, attrs, value = cell.groups()
            role = roles[index] if index < len(roles) else "text"
            index += 1
            if tag == "th":
                attrs += ' scope="col"'
            if role != "text":
                attrs += ' class="number"'
            if role == "currency" and tag == "td":
                amount = re.fullmatch(r"\$(\d+(?:\.\d+)?)(?:\s*\((simulated)\))?", value.strip())
                if amount is None:
                    raise ValueError(f"Unrecognized currency cell: {value}")
                decimal = Decimal(amount[1])
                precision = max(9, -decimal.as_tuple().exponent)
                value = f'<span class="cell-value">${decimal:.{precision}f}</span>'
                if amount[2]:
                    value += '<small class="cell-note">Simulated</small>'
            return f"<{tag}{attrs}>{value}</{tag}>"

        row = re.sub(r"<(th|td)([^>]*)>(.*?)</\1>", cell_layout, match[1], flags=re.DOTALL)
        return f"<tr>{row}</tr>"

    return re.sub(r"<tr>(.*?)</tr>", row_layout, table, flags=re.DOTALL)


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
        return '<div class="scroll">' + aligned_table(match.group(0)) + "</div>"

    content = re.sub(r"<table>.*?</table>", table_layout, content, flags=re.DOTALL)
    content = re.sub(r"<(/?)h1([ >])", r"<\1h2\2", content)
    toc = re.sub(r'^<div class="toc">\s*|\s*</div>\s*$', "", engine.toc)
    contents = (
        '<div class="toc" role="navigation" aria-label="On this page"><strong>On this page</strong>'
        + toc
        + "</div>"
        if len(engine.toc_tokens) > 1 or any(t["children"] for t in engine.toc_tokens)
        else ""
    )
    return contents + '<article class="article">' + content + "</article>"


def shell(title, active, intro, body, commit):
    canonical = SITE_URL + ("" if active == "index.html" else active)
    page_title = title if active == "index.html" else title + " · Chess Analytics Lab"
    description = html.escape(intro, quote=True)
    csp = (
        '<meta http-equiv="Content-Security-Policy" content="default-src \'self\'; '
        "script-src 'self'; connect-src 'none'; worker-src 'self'; "
        "img-src 'self'; style-src 'self'; font-src 'self'; object-src 'none'; "
        "base-uri 'none'; form-action 'none'\">"
        if active == "import-games.html"
        else ""
    )
    source_note = (
        '<p class="source-note">Generated from maintained Markdown, contracts and '
        f'recorded evidence. <a href="{REPO_URL}docs/README.md">Repository guides</a></p>'
        if active != "index.html"
        else ""
    )
    revision = html.escape(commit)
    if commit != "local export":
        revision = (
            f'<a href="https://github.com/jfk-ssa/chess-analytics-lab/commit/{commit}">'
            f"{revision}</a>"
        )
    nav = "".join(
        f'<a href="{path}"' + (' aria-current="page"' if path == active else "") + f">{name}</a>"
        for path, name in NAV
    )
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="{description}">
<title>{html.escape(page_title)}</title>
{csp}
<link rel="canonical" href="{canonical}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="Chess Analytics Lab">
<meta property="og:title" content="{html.escape(page_title, quote=True)}">
<meta property="og:description" content="{description}">
<meta property="og:url" content="{canonical}">
<meta property="og:image" content="{SITE_URL}assets/social-preview.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="Chess Analytics Lab: data, analytics and evaluated AI">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{html.escape(page_title, quote=True)}">
<meta name="twitter:description" content="{description}">
<meta name="twitter:image" content="{SITE_URL}assets/social-preview.png">
<meta name="twitter:image:alt" content="Chess Analytics Lab: data, analytics and evaluated AI">
<link rel="icon" href="assets/favicon.svg" type="image/svg+xml">
<link rel="icon" href="favicon.ico" sizes="16x16 32x32 48x48">
<link rel="stylesheet" href="assets/site.css?v={commit}">
<script defer src="assets/site.js?v={commit}"></script></head>
<body><a class="skip" href="#main">Skip to content</a><header class="topbar"><div class="nav-inner">
<a class="brand" href="index.html">Chess Analytics Lab <span class="badge">Learning lab</span></a>
<nav aria-label="Main navigation">{nav}</nav></div></header><main id="main">
<div class="hero"><div class="eyebrow">Data • Analytics • Evaluated AI</div>
<h1>{html.escape(title)}</h1>
<p class="lead">{intro}</p>{source_note}</div>{body}</main>
<footer>Source revision {revision} · Static documentation ·
No runtime model calls or account downloads.
<a href="{REPO_URL}docs/SITE.md">Build and publishing runbook</a></footer></body></html>'''


def architecture():
    stages = (
        (
            "ingest",
            "Bounded ingestion",
            "src/chess_analytics/ingest/pipeline.py",
            "Read a pinned archive or fixture; preserve exclusions, quarantine and source hashes.",
        ),
        (
            "publish",
            "Checked snapshots",
            "src/chess_analytics/warehouse/snapshots.py",
            "Validate immutable Parquet/DuckDB output before replacing its current pointer.",
        ),
        (
            "marts",
            "Optional marts",
            "src/chess_analytics/marts/pipeline.py",
            "Transform a copy through dbt; record lineage, validation and recovery.",
        ),
        (
            "metrics",
            "Opening & clock metrics",
            "src/chess_analytics/dashboard/analysis.py",
            "Apply explicit cohorts, denominators, missingness and observed-prefix caveats.",
        ),
        (
            "analyst",
            "Checked analyst",
            "src/chess_analytics/analyst/tools.py",
            "Allowlisted read-only actions compute values and bind evidence IDs to the snapshot.",
        ),
        (
            "evaluate",
            "Independent scoring",
            "src/chess_analytics/analyst/evaluation.py",
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
        f'<a href="{REPO_URL}{path}">Inspect {name.lower()} code</a></details>'
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
<th class="number" scope="col">Games</th><th>Observed dates</th>
<th class="number" scope="col">Minimum player rating</th></tr></thead>
<tbody id="opening-cohort-rows"></tbody></table></div>
<p class="source-note">Counts come from a checked local game index. The full PGNs remain
local; this page downloads no database. Measured position rankings appear above;
learning drills remain proposed. <a href="#getting-more-games">Sources, exclusions and costs</a></p>
<noscript>The default Elite cohort contains {counts["elite_training_games"]:,} games.
Enable JavaScript to switch the cohort summary.</noscript></section>
<script type="application/json" id="opening-corpus-data">{payload}</script>"""


def validate_position(identifier, position, expected):
    key = position["position_key"]
    if not re.fullmatch(r"[0-9a-f]{24}", identifier) or digest(key.encode())[:24] != identifier:
        raise ValueError("Opening position identifier changed")
    board = chess.Board(key + " 0 1")
    if not board.is_valid() or board.turn != chess.WHITE:
        raise ValueError("Opening position is not a valid White decision")
    if " ".join(board.fen(en_passant="legal").split()[:4]) != key:
        raise ValueError("Opening position is not canonical")
    games = position["games"]
    if not 1 <= games <= expected or position["frequency"] != games / expected:
        raise ValueError("Opening position frequency does not reconcile")
    if not 0 <= position["acyclic_routes"] <= games:
        raise ValueError("Opening route count exceeds position games")
    if not 0 <= position["loop_prefix_games"] <= games:
        raise ValueError("Opening loop count exceeds position games")
    if not 0 <= position["next_move_games"] <= games:
        raise ValueError("Opening continuation denominator exceeds position games")
    acyclic = games - position["loop_prefix_games"]
    dominant = max((route["games"] for route in position["routes"]), default=0)
    alternative = 1 - dominant / acyclic if acyclic else None
    if (
        position["acyclic_games"] != acyclic
        or position["dominant_route_games"] != dominant
        or position["alternative_route_share"] != alternative
        or position["other_acyclic_route_games"]
        != acyclic - sum(route["games"] for route in position["routes"])
    ):
        raise ValueError("Opening alternative-route denominator differs")
    if not 0 <= position["other_acyclic_route_games"] <= acyclic:
        raise ValueError("Opening route remainder differs")
    for field in (
        "distinct_recorded_families",
        "distinct_recorded_ecos",
        "unknown_family_games",
        "white_g3_played_games",
    ):
        if not 0 <= position[field] <= games:
            raise ValueError("Opening label or g3 count exceeds games")
    for route in position["routes"]:
        replay = chess.Board()
        for uci in route["uci"].split():
            move = chess.Move.from_uci(uci)
            if move not in replay.legal_moves:
                raise ValueError("Opening route is illegal")
            replay.push(move)
        if " ".join(replay.fen(en_passant="legal").split()[:4]) != key:
            raise ValueError("Opening route endpoint differs")
        if route["share"] != route["games"] / games:
            raise ValueError("Opening route share differs")
    for move in position["continuations"]:
        parsed = chess.Move.from_uci(move["uci"])
        if parsed not in board.legal_moves or board.san(parsed) != move["san"]:
            raise ValueError("Opening continuation is illegal or mislabeled")
        if move["share_of_position_games"] != move["games"] / games:
            raise ValueError("Opening continuation share differs")


def validate_ranking(kind, ranking, view, expected, limit):
    ranked = [view["positions"][key] for key in ranking["ids"]]
    if len(ranked) > limit or len(set(ranking["ids"])) != len(ranked):
        raise ValueError("Opening ranking is unbounded or duplicated")
    if any(p["games"] < 2 or (kind == "transposing" and p["acyclic_routes"] < 2) for p in ranked):
        raise ValueError("Opening ranking contains an ineligible position")
    if [p["games"] for p in ranked] != sorted((p["games"] for p in ranked), reverse=True):
        raise ValueError("Opening ranking is not ordered by game frequency")
    c10, c20 = ranking["top_10_game_coverage"], ranking["top_20_game_coverage"]
    if not 0 <= c10 <= c20 <= expected:
        raise ValueError("Opening union coverage exceeds denominator")
    for count, rows in ((c10, ranked[:10]), (c20, ranked)):
        if rows and not max(p["games"] for p in rows) <= count <= sum(p["games"] for p in rows):
            raise ValueError("Opening union coverage is inconsistent")
    curve = ranking["coverage_curve"]
    if len(curve) != len(ranked):
        raise ValueError("Opening coverage curve length differs")
    previous = 0
    for n, (point, position) in enumerate(zip(curve, ranked, strict=True), 1):
        if (
            point["n"] != n
            or not previous <= point["games"] <= expected
            or point["additional_games"] != point["games"] - previous
            or not 0 <= point["additional_games"] <= position["games"]
            or point["share"] != point["games"] / expected
            or point["games"] < max(p["games"] for p in ranked[:n])
        ):
            raise ValueError("Opening coverage curve does not reconcile")
        previous = point["games"]
    if curve and (c10 != curve[min(10, len(curve)) - 1]["games"] or c20 != previous):
        raise ValueError("Opening coverage endpoints differ")


def checked_positions(repo):
    """Validate compact publication against its checked corpus and build receipt."""
    source = repo / "reports/opening-positions.json"
    data = json.loads(source.read_text())
    corpus = json.loads((repo / "reports/opening-corpus.json").read_text())
    contract = json.loads((repo / "contracts/opening_positions.json").read_text())
    plan = json.loads((repo / "config/opening-positions.json").read_text())
    checkpoint = json.loads((repo / "reports/opening-positions-checkpoint.json").read_text())
    if data["kind"] != "observed_white_opening_positions" or data["plan"] != plan:
        raise ValueError("Opening position kind or plan changed")
    if data["corpus_snapshot_id"] != corpus["snapshot_id"]:
        raise ValueError("Opening position corpus identity changed")
    if data["training_sources"] != corpus["training_sources"]:
        raise ValueError("Opening position sources differ from checked corpus")
    if set(data["cohorts"]) != set(plan["cohorts"]):
        raise ValueError("Opening position cohorts differ from plan")
    for cohort, details in data["cohorts"].items():
        denominator = sum(s["games"] for s in corpus["training_sources"] if s["cohort"] == cohort)
        families = {row["family"]: row["games"] for row in details["opening_families"]}
        if details["denominator_games"] != denominator or sum(families.values()) != denominator:
            raise ValueError("Opening position denominator does not reconcile")
        for name, view in details["views"].items():
            lens = view.get("lens")
            expected = (
                view["denominator_games"]
                if lens
                else denominator
                if name == "all"
                else families[name]
            )
            if lens and (
                name not in {"d4-g3", "d4-g3-catalan", "d4-g3-kings-indian"}
                or not 1 <= expected <= denominator
                or view["family"] is not None
            ):
                raise ValueError("Opening lens definition or denominator differs")
            if lens and any(
                lens[field] != value for field, value in contract["public_lenses"][name].items()
            ):
                raise ValueError("Opening lens moves differ from contract")
            if view["denominator_games"] != expected:
                raise ValueError("Opening family denominator does not reconcile")
            for identifier, position in view["positions"].items():
                validate_position(identifier, position, expected)
            for kind, ranking in view["rankings"].items():
                validate_ranking(
                    kind, ranking, view, expected, plan["published_positions_per_view"]
                )
    for name, expected_hash in checkpoint["files"].items():
        if digest((repo / name).read_bytes()) != expected_hash:
            raise ValueError("Opening position publication hash changed: " + name)
    return data


def opening_positions(repo, output):
    data = checked_positions(repo)
    directory = output / "assets/opening-positions"
    directory.mkdir()
    positions = {
        identifier: position
        for cohort in data["cohorts"].values()
        for view in cohort["views"].values()
        for identifier, position in view["positions"].items()
    }
    for identifier, position in positions.items():
        board = chess.Board(position["position_key"] + " 0 1")
        (directory / (identifier + ".svg")).write_text(
            chess.svg.board(
                board, size=420, colors={"square light": "#eaf1eb", "square dark": "#789b8d"}
            )
        )
    shutil.copy2(repo / "reports/opening-positions.json", output / "assets/opening-positions.json")
    elite = data["cohorts"]["elite_reference"]["views"]["all"]
    ranked = elite["rankings"]["transposing"]
    first = elite["positions"][ranked["ids"][0]]
    rows = "".join(
        f"<tr><td>{index}</td><td>{html.escape(elite['positions'][key]['routes'][0]['san'])}</td>"
        f'<td class="number">{elite["positions"][key]["games"]:,}</td>'
        f'<td class="number">{elite["positions"][key]["frequency"]:.2%}</td>'
        f'<td class="number">{elite["positions"][key]["acyclic_routes"]:,}</td>'
        f'<td class="number">{elite["positions"][key]["alternative_route_share"]:.2%}</td></tr>'
        for index, key in enumerate(ranked["ids"][:5], 1)
    )
    return f'''<section id="position-explorer" class="position-explorer"
aria-labelledby="positions-title">
<div class="eyebrow">Measured from retained games</div>
<h2 id="positions-title">Find positions worth studying together</h2>
<p>Rank White decisions after Black's moves 3–10. A recurring position appears in
at least two games; a transposing position has at least two distinct arrival move
orders without repetition loops. A game counts once per position.</p>
<div class="toolbar" id="position-controls" hidden>
<div><label for="position-cohort">Reference cohort</label>
<select id="position-cohort"><option value="elite_reference">Elite · 240,086 games</option>
<option value="rated_public">Public 1000+ · 802,260 games</option></select></div>
<div><label for="position-family">Opening family or public lens</label>
<select id="position-family"></select></div>
<div><label for="position-kind">Position ranking</label><select id="position-kind">
<option value="transposing">Multiple move orders</option>
<option value="recurring">All recurring positions</option>
</select></div></div>
<p id="position-status" class="stats" aria-live="polite">Elite reference ·
{elite["denominator_games"]:,} eligible games.
Top 20 transposing positions reach {ranked["top_20_game_coverage"]:,} distinct games
({ranked["top_20_game_coverage"] / elite["denominator_games"]:.1%}).</p>
<p id="position-scope" class="source-note">Opening names/ECO are recorded game labels,
not definitions of the board position. The filter includes the twelve largest eligible
labeled families per cohort; complete family counts are available below.</p>
<div class="position-layout"><div class="scroll position-ranking" tabindex="0"
role="region" aria-label="Ranked positions; scroll horizontally on smaller screens">
<table><caption id="position-caption">Most frequent transposing positions · Elite</caption>
<thead><tr><th scope="col">Rank</th><th scope="col">Position</th>
<th scope="col" class="number">Games</th><th scope="col" class="number">Frequency</th>
<th scope="col" class="number">Move orders</th>
<th scope="col" class="number">Alternative-route share</th></tr></thead>
<tbody id="position-rows">{rows}</tbody></table></div>
<div id="position-detail" class="position-detail" tabindex="-1"
role="region" aria-labelledby="position-selected-title">
<h3 id="position-selected-title">Most frequent transposing position</h3>
<img id="position-image" width="420" height="420" src="assets/opening-positions/{first["id"]}.svg"
alt="Most frequent Elite transposing position, White to move">
<p id="position-selected-note" class="source-note" aria-live="polite">
{first["games"]:,} games · White to move.</p>
<div id="position-selected-content"></div></div></div>
<section aria-labelledby="position-coverage-title" class="position-chart-panel">
<h3 id="position-coverage-title">How much does a study set cover?</h3>
<p>Positions ranked by frequency. Each game counts
once across the set. The next position can overlap games already covered.</p>
<div id="position-coverage-chart" class="scroll" tabindex="0"
role="region" aria-label="Coverage chart; scroll horizontally if needed"></div><details>
<summary>Coverage and marginal gains table</summary>
<div id="position-coverage-table"></div></details></section>
<section aria-labelledby="position-depth-title" class="position-chart-panel">
<h3 id="position-depth-title">Different routes, fewer endpoints</h3>
<p>Endpoint compression at each depth: 1 − distinct positions / distinct acyclic
routes. Both cohorts include all openings; this chart does not follow family or lens filters.</p>
<div id="position-depth-chart" class="scroll" tabindex="0"
role="region" aria-label="Depth chart; scroll horizontally if needed"></div>
<div id="position-depth-legend"></div>
<details><summary>Depth observations and included visits</summary>
<div id="position-depth-table"></div></details></section>
<section aria-labelledby="position-scatter-title" class="position-chart-panel">
<h3 id="position-scatter-title">Frequency and route variety</h3>
<p>Published ranked positions in this view, rather than the whole corpus.
Axes use logarithmic scales. Select a point or a table row to inspect its board.
Darker green indicates more games arriving through alternatives to the leading route.</p>
<div id="position-scatter-chart" class="scroll" tabindex="0"
role="region" aria-label="Frequency and routes chart; scroll horizontally if needed"></div>
</section>
<details class="definition"><summary>Opening-family counts and convergence by depth</summary>
<div id="position-inventory"></div>
<p>At one depth, endpoint compression is 1 − distinct positions / distinct move orders.
Repeated-position prefixes are excluded. This describes convergence in the observed
corpus; it does not measure time saved or learning improvement.</p>
<div id="position-compression"></div></details>
<p class="source-note">Elite covers the curated November 2025 month. Public games are
nine ordered first-day archive prefixes. Compare cohorts separately; these are not
estimates of your personal encounter rate. Continuations show observed choices,
not best moves. Drills and strategic lesson explanations remain future work.</p>
<p><a href="assets/opening-positions.json" download>Download measured rankings (JSON)</a> ·
<a href="{REPO_URL}contracts/opening_positions.json">Metric definitions</a> ·
<a href="{REPO_URL}reports/opening-positions-checkpoint.json">Build evidence</a></p>
<noscript>The table shows the five leading Elite transposing positions. Enable JavaScript
to explore both cohorts, opening families, boards, routes and continuations.</noscript>
<p id="position-load-note" class="source-note" aria-live="polite"></p>
</section><script defer src="assets/position-charts.js"></script>
<script defer src="assets/position-explorer.js"></script>'''


def game_import(repo, output):
    """Publish only checked public reference examples; imported records stay on the device."""
    vendor = repo / "site/assets/vendor"
    provenance = json.loads((vendor / "chess-js-provenance.json").read_text())
    if set(provenance["files"]) != {"chess-1.4.0.mjs", "LICENSE.chess-js.txt"}:
        raise ValueError("Unexpected vendored chess assets")
    for name, expected in provenance["files"].items():
        if digest((vendor / name).read_bytes()) != expected:
            raise ValueError("Vendored chess library hash changed")
    data = checked_positions(repo)
    reference = {"corpus_snapshot_id": data["corpus_snapshot_id"], "cohorts": {}}
    for name, cohort in data["cohorts"].items():
        reference["cohorts"][name] = {
            "views": {
                key: {
                    "label": (
                        view["lens"]["label"]
                        if view.get("lens")
                        else "All openings"
                        if key == "all"
                        else key
                    ),
                    "rankings": {kind: rank["ids"] for kind, rank in view["rankings"].items()},
                    "positions": {
                        identifier: {
                            "position_key": position["position_key"],
                            "routes": [{"uci": route["uci"]} for route in position["routes"]],
                        }
                        for identifier, position in view["positions"].items()
                    },
                }
                for key, view in cohort["views"].items()
            }
        }
    pieces = output / "assets/pieces"
    pieces.mkdir()
    for symbol in "PNBRQKpnbrqk":
        name = ("w" if symbol.isupper() else "b") + symbol.upper() + ".svg"
        (pieces / name).write_text(chess.svg.piece(chess.Piece.from_symbol(symbol), size=45))
    example = {
        "name": "authored-games.pgn",
        "text": (repo / "tests/fixtures/imports/authored-games.pgn").read_text(),
    }
    encoded_reference = json.dumps(reference, separators=(",", ":")).replace("<", "\\u003c")
    encoded_example = json.dumps(example).replace("<", "\\u003c")
    return (
        """<section class="game-import" aria-labelledby="import-title">
<h2 id="import-title">Analyze your exported games</h2>
<p>Choose plain PGN files exported from Chess.com or Lichess. Your files stay on this
device; legal replay and analysis run in a browser worker.
Each import replaces the current session.</p>
<label for="import-files">Choose PGN files</label>
<input type="file" id="import-files" accept=".pgn,text/plain,application/x-chess-pgn" multiple>
<p class="source-note">Up to 20 files, 10 MiB total, 5,000 games and 1,000 plies per game.
Standard chess from the initial board, completed games only. Invalid records and
unsupported games receive visible dispositions. No account connection is needed.</p>
<div class="import-actions"><button type="button" id="import-example">Try authored example</button>
<button type="button" id="import-cancel" hidden>Cancel processing</button>
<button type="button" id="import-clear" disabled>Clear session</button>
<button type="button" id="import-download" disabled>Download analysis JSON</button></div>
<p id="import-status" class="stats" role="status" aria-live="polite">
Choose PGN files or try the authored example.</p>
<div id="import-summary"></div>
<div id="import-selection" hidden><fieldset id="import-filters">
<legend>Choose your player and comparison scope</legend>
<p>Select the player separately for each provider. Matching usernames are not
linked automatically. This release analyzes your White games and reports Black games separately.</p>
<div id="import-players" class="toolbar"></div>
<div class="toolbar"><div><label for="import-since">Start date (optional)</label>
<input type="date" id="import-since"></div>
<div><label for="import-until">End date (optional)</label>
<input type="date" id="import-until"></div>
<div><label for="import-time-control">Time control</label><select id="import-time-control">
<option value="all">All time controls</option></select></div>
<div><label for="import-rated">Rated status</label><select id="import-rated">
<option value="all">All / include unknown</option><option value="true">Known rated</option>
<option value="false">Known casual / unrated</option><option value="unknown">Unknown status</option>
</select></div></div>
<p class="source-note">Missing ratings do not exclude games.
Date filters visibly exclude undated games;
platform ratings and reference cohorts are not interchangeable.
Exported rated status may be unknown.</p>
<label class="import-check"><input type="checkbox" id="import-minimum20">
Require at least 20 plies for comparison with the public eligibility policy</label>
<h3>Choose a bounded public study set</h3>
<div class="toolbar"><div><label for="import-cohort">Reference cohort</label>
<select id="import-cohort"><option value="elite_reference">Elite reference</option>
<option value="rated_public">Public 1000+</option></select></div>
<div><label for="import-view">Reference opening family or lens</label>
<select id="import-view"></select></div>
<div><label for="import-kind">Reference ranking</label><select id="import-kind">
<option value="transposing">Multiple move orders</option>
<option value="recurring">All recurring positions</option></select></div>
<div><label for="import-n">Number of reference positions</label>
<select id="import-n">"""
        + "".join(
            f'<option value="{n}"' + (" selected" if n == 20 else "") + f">{n}</option>"
            for n in range(1, 21)
        )
        + """</select></div></div>
<p>The comparison uses selected published boards and up to three recorded route examples
per board. A position outside this set has not been checked against the full corpus.
A route departure is not a mistake; comparison stops when an example ends.</p>
</fieldset><button type="button" id="import-analyze" disabled>
Analyze selected White games</button></div>
<div id="import-results" aria-live="polite"></div>
<noscript>Local game import needs JavaScript and browser workers. The public
<a href="transpositions.html">Transposition analysis</a>
remains available without an import.</noscript>
<p class="source-note">No persistent browser storage, server upload, username download,
engine scoring or model call. Clearing/reloading removes the session; explicitly downloaded
reports remain on your device. <a href="assets/import-example.pgn" download>
Download authored PGN example</a></p>
</section><script type="application/json" id="import-reference-data">"""
        + encoded_reference
        + """</script>
<script type="application/json" id="import-example-data">"""
        + encoded_example
        + """</script>
<script defer src="assets/position-charts.js"></script>
<script type="module" src="assets/game-import-ui.js"></script>"""
    )


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
<details class="routing-details"><summary>Inspect all saved question-level routes</summary>
<p>Scroll the table sideways to compare every method. Route names are task labels;
agreement here does not establish a correct final answer.</p>
<div class="scroll" tabindex="0" role="region" aria-label="Saved routing comparisons">
<table class="routing-table">
<caption>Saved route choices; colored cells show agreement with reviewed labels.</caption>
<thead><tr><th>ID</th><th>Question</th><th>Expected route</th>
<th>Rules</th><th>Jev run 1</th><th>Jev run 2</th>
<th>Decisions</th><th class="number" scope="col">Chosen-option probability</th>
<th>Explored gate</th></tr></thead>
<tbody id="routing-rows"></tbody></table></div>
<script type="application/json" id="routing-data">"""
        + encoded
        + "</script></details></section>"
    )


def definitions(repo):
    cards = []
    contract_files = (
        "game_draw_rate.json",
        "opening_usage.json",
        "opening_player_score.json",
        "opening_adjusted_score.json",
        "opening_positions.json",
        "imported_games.json",
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
<p id="search-status" aria-live="polite">"""
        + str(len(cards))
        + " definitions or schemas shown</p>"
        + "".join(cards)
        + """
<section class="example-panel" aria-labelledby="denominator-title">
<h2 id="denominator-title">Why the denominator matters</h2>
<p>This worked illustration starts with the authored demo:
3 proxy errors among 6 evaluable moves. Change the number of moves with missing evaluations;
they change coverage, while the proxy rate stays tied to evaluable moves.</p>
<div class="toolbar"><div><label for="missing-moves">
Missing evaluations: <span id="missing-value">2</span></label>
<input id="missing-moves" type="range" min="0" max="14" value="2"></div></div>
<div class="fraction"><div>Proxy rate<br><strong id="proxy-rate">3 / 6 = 50.0%</strong></div>
<div>Evaluation coverage<br><strong id="coverage-rate">6 / 8 = 75.0%</strong></div></div>
<p class="source-note">Other slider values are hypothetical examples,
not new observations or model results.</p></section>"""
    )


class SiteLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.refs = []
        self.ids = set()

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key in ("href", "src") and value:
                self.refs.append(value)
            if key == "id" and value:
                self.ids.add(value)


def target_anchors(path, github=False):
    text = path.read_text()
    if path.suffix == ".md":
        text = markdown.markdown(text, extensions=["fenced_code", "tables", "toc"])
    parser = SiteLinks()
    parser.feed(text)
    if github and path.suffix == ".md":
        # GitHub removes punctuation from heading anchors; repeated headings get suffixes.
        used = set()
        for heading in re.findall(r"<h[1-6][^>]*>(.*?)</h[1-6]>", text, re.DOTALL):
            plain = html.unescape(re.sub(r"<[^>]+>", "", heading)).lower()
            slug = re.sub(r"[^\w\- ]", "", plain).replace(" ", "-")
            anchor, index = slug, 0
            while anchor in used:
                index += 1
                anchor = f"{slug}-{index}"
            used.add(anchor)
        return used | parser.ids
    return parser.ids


def validate_site(output, repo=None):
    checked = 0
    anchors = {}
    for path in output.rglob("*.html"):
        parser = SiteLinks()
        parser.feed(path.read_text())
        for ref in parser.refs:
            url = urlsplit(ref)
            github = repo is not None and ref.startswith(REPO_URL)
            if github:
                target = (repo / unquote(url.path.split("/blob/main/", 1)[1])).resolve()
                root = repo.resolve()
            elif ref.startswith(SITE_URL):
                relative = unquote(url.path.removeprefix("/chess-analytics-lab/"))
                target = (output / relative).resolve()
                root = output.resolve()
            elif not url.scheme and not url.netloc:
                target = (path.parent / unquote(url.path)).resolve() if url.path else path
                root = output.resolve()
            else:
                continue
            if not target.is_relative_to(root) or not target.exists():
                raise ValueError(f"Broken generated link in {path.name}: {ref}")
            if target.is_dir() and not github:
                target /= "index.html"
                if not target.exists():
                    raise ValueError(f"Broken generated link in {path.name}: {ref}")
            if url.fragment:
                cache_key = (target, github)
                if cache_key not in anchors:
                    anchors[cache_key] = target_anchors(target, github)
                if unquote(url.fragment) not in anchors[cache_key]:
                    raise ValueError(f"Broken generated anchor in {path.name}: {ref}")
            checked += 1
    return checked


def homepage_results(repo):
    # Reuse corpus reconciliation and frozen report checks before promoting values to the hero.
    opening_corpus(repo)
    routing(repo)
    corpus = json.loads((repo / "reports/opening-corpus.json").read_text())["counts"]
    paired = json.loads((repo / "reports/M8-e2e-checkpoint.json").read_text())
    checkpoint = json.loads((repo / "reports/decisions-checkpoint.json").read_text())
    if paired["arms"] != checkpoint["retained_final_answer_comparison"]["arms"]:
        raise ValueError("Final-answer checkpoints do not reconcile")
    baseline, gated = paired["arms"]["baseline"], paired["arms"]["gated"]
    fixture = json.loads((repo / "tests/fixtures/portfolio_expected.json").read_text())
    return f'''<section aria-labelledby="results-title">
<h2 id="results-title">What the lab demonstrates</h2>
<div class="result-grid">
<div class="result-card"><strong>{corpus["training_games"]:,}</strong>
<h3>Selected public games</h3><p>A checked opening-training game index, with Elite and
broader cohorts kept separate. Opening-position rankings are measured; drills remain proposed.</p>
<a href="{REPO_URL}reports/opening-corpus.json">Inspect corpus evidence</a></div>
<div class="result-card"><strong>{baseline["passed"]}/{baseline["total"]} ·
{gated["passed"]}/{gated["total"]}</strong>
<h3>Final-answer comparison</h3><p>The direct analyst and Jev gate tied in one small
paired Luna experiment under a versioned offline rescore. The gate cost more;
it remains optional.</p><a href="comparison.html">See results and limitations</a></div>
<div class="result-card"><strong>{fixture["accepted"]} games · offline</strong>
<h3>Reproducible demo</h3><p>Authored synthetic games exercise ingestion, metrics and
checked answer replay. Fixture checks are separate from live model results.</p>
<a href="demo.html">Run the walkthrough</a></div>
</div></section>'''


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
    shutil.copy2(repo / "site/assets/favicon.ico", output / "favicon.ico")
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
                    "Explore positions across move orders",
                    "Compare recurring boards, route balance and coverage across public cohorts.",
                    "Measured rankings, charts and fianchetto lenses",
                ),
                (
                    "opening-learning.html",
                    "Design lessons around positions",
                    "Replay an illustrative transposition and inspect the learning proposal.",
                    "Lesson design and evaluation plan",
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
            "Chess Analytics Lab",
            (
                "A reproducible chess data pipeline, explicit analytical metrics, "
                "and an AI analyst evaluated against checked evidence."
            ),
            '<p class="home-links">A portfolio project by '
            '<a href="https://github.com/jfk-ssa">jfk-ssa</a> · '
            '<a href="https://github.com/jfk-ssa/chess-analytics-lab">Explore the source</a>'
            '</p><p class="stack">Python · SQL · DuckDB · Parquet · dbt · Streamlit · '
            "AI evaluation</p>" + homepage_results(repo) + home + md(repo, "HOME.md"),
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
                '<a class="card report-link" href="reports/decisions-routing-comparison.html">'
                "<strong>Open the original comparison report</strong><p>Confusion matrices, "
                "latency and coverage plots. Preserved as the historical report.</p></a>"
            ),
        ),
        "transpositions.html": (
            "Opening positions, across move orders",
            "Explore recurring boards, route diversity and study-set coverage "
            "in two public cohorts.",
            '<div class="callout"><span class="badge">Measured public-corpus analysis</span>'
            "<p>Different routes can lead to one board. Explore which boards recur and how much "
            'a small study set covers. <a href="opening-learning.html">Learning rationale and '
            'illustrative walkthrough</a> · <a href="metrics.html#opening-position-metrics">'
            "Metric definitions</a></p></div>"
            + opening_positions(repo, output)
            + opening_corpus(repo)
            + md(repo, "TRANSPOSITIONS.md")
            + '<p id="opening-lab-title">The illustrative board has moved to '
            '<a href="opening-learning.html#opening-lab-title">Opening learning</a>.</p>',
        ),
        "import-games.html": (
            "Bring your games. Find familiar positions.",
            "Import Chess.com or Lichess PGN files locally and compare your White games "
            "with a bounded public study set.",
            game_import(repo, output) + md(repo, "GAME_IMPORT.md"),
        ),
        "opening-learning.html": (
            "Learn the position. Recognize every route.",
            "An illustrative walkthrough, lesson design and evaluation plan "
            "for learning through transpositions.",
            '<div class="callout"><span class="badge">Learning design · benefits unmeasured</span>'
            "<p>The public analysis is available on "
            '<a href="transpositions.html#position-explorer">'
            "Transpositions</a>. This page explains the learning proposal; drills and a "
            "learning experiment remain future work.</p></div>"
            + transpositions()
            + md(repo, "TRANSPOSITION_LEARNING.md"),
        ),
    }
    # Keep previously published learning-guide fragments useful after the page split.
    legacy = SiteLinks()
    legacy.feed(md(repo, "TRANSPOSITION_LEARNING.md"))
    current = SiteLinks()
    current.feed(bodies["transpositions.html"][2])
    aliases = "".join(
        f'<p id="{html.escape(anchor)}"><a href="opening-learning.html#{html.escape(anchor)}">'
        f"{html.escape(anchor.replace('-', ' '))}</a></p>"
        for anchor in sorted(legacy.ids - current.ids)
    )
    title, intro, body = bodies["transpositions.html"]
    bodies["transpositions.html"] = (
        title,
        intro,
        body + "<details><summary>Earlier learning-guide links</summary>" + aliases + "</details>",
    )
    (output / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        + "".join(
            "<url><loc>" + SITE_URL + ("" if name == "index.html" else name) + "</loc></url>"
            for name in sorted(bodies)
        )
        + "</urlset>\n"
    )
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
    source_files.update(
        repo / name
        for name in (
            "reports/opening-positions.json",
            "reports/opening-positions-checkpoint.json",
            "config/opening-positions.json",
            "scripts/build_opening_positions.py",
            "scripts/summarize_opening_positions.py",
        )
    )
    source_files.add(repo / "tests/fixtures/portfolio_expected.json")
    source_files.add(repo / "site/assets/favicon.ico")
    source_files.update((repo / "contracts").glob("*.json"))
    source_files.update(
        repo / source for name, source in ASSETS.items() if (output / "assets" / name).is_file()
    )
    manifest = {
        "kind": "static_documentation_build_no_live_requests",
        "source_revision": commit,
        "pages": sorted(bodies),
        "local_links_checked": validate_site(output, repo),
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
