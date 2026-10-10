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
from jinja2 import Environment, FileSystemLoader, StrictUndefined

TEMPLATES = Path(__file__).resolve().parent / "templates"
ENV = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=False, undefined=StrictUndefined)


def render(template_name: str, **context: object) -> str:
    text = ENV.get_template(template_name).render(**context)
    return text[:-1] if text.endswith("\n") else text


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
    ("Home", "index.html", ()),
    (
        "Openings",
        None,
        (
            ("opening-learning.html", "Opening learning"),
            ("transpositions.html", "Transpositions"),
        ),
    ),
    ("Analyze my games", "import-games.html", ()),
    (
        "The lab",
        None,
        (
            ("demo.html", "Run the demo"),
            ("metrics.html", "Metrics & data"),
            ("comparison.html", "AI comparison"),
            ("architecture.html", "Architecture"),
        ),
    ),
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
                render(
                    "research_card.html.j2",
                    source=source,
                    finding=finding,
                    interpretation=interpretation,
                )
            )
        return render("research_cards.html.j2", cards="".join(cards))

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
        return render("scroll_table.html.j2", table=aligned_table(match.group(0)))

    content = re.sub(r"<table>.*?</table>", table_layout, content, flags=re.DOTALL)
    content = re.sub(r"<(/?)h1([ >])", r"<\1h2\2", content)
    toc = re.sub(r'^<div class="toc">\s*|\s*</div>\s*$', "", engine.toc)
    contents = (
        render("toc.html.j2", toc=toc)
        if len(engine.toc_tokens) > 1 or any(t["children"] for t in engine.toc_tokens)
        else ""
    )
    return render("article.html.j2", contents=contents, content=content)


def shell(title, active, intro, body, commit):
    canonical = SITE_URL + ("" if active == "index.html" else active)
    page_title = title if active == "index.html" else title + " · Chess Analytics Lab"
    return render(
        "shell.html.j2",
        description=html.escape(intro, quote=True),
        page_title=html.escape(page_title),
        og_title=html.escape(page_title, quote=True),
        heading=html.escape(title),
        intro=intro,
        canonical=canonical,
        active=active,
        commit=commit,
        nav=NAV,
        body=body,
        site_url=SITE_URL,
        repo_url=REPO_URL,
    )


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
    return render(
        "architecture.html.j2",
        repo_url=REPO_URL,
        stages=[
            {"key": key, "name": name, "name_lower": name.lower(), "path": path, "desc": desc}
            for key, name, path, desc in stages
        ],
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
    stats = (
        ("Unique retained games", f"{counts['unique_retained_games']:,}", "Fixtures excluded"),
        (
            "Both players 1000+",
            f"{counts['both_at_least_1000']:,}",
            "Includes ratings exactly 1000",
        ),
        ("Opening corpus", f"{counts['training_games']:,}", "Completed games; at least ten moves"),
    )
    return render(
        "opening_corpus.html.j2",
        stats=stats,
        elite_games=f"{counts['elite_training_games']:,}",
        payload=payload,
    )


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
    if not source.is_file():
        raise ValueError(
            "reports/opening-positions.json is absent. Restore the pinned publication "
            "with scripts/materialize_opening_positions.py, or regenerate it from the "
            "local visit snapshot with scripts/summarize_opening_positions.py."
        )
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
        # The receipt keeps the lock hash from publication. Later documentation
        # dependencies may edit uv.lock without regenerating the rankings.
        if name == "uv.lock":
            continue
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
    preview = []
    for index, key in enumerate(ranked["ids"][:5], 1):
        position = elite["positions"][key]
        preview.append(
            {
                "index": index,
                "san": html.escape(position["routes"][0]["san"]),
                "games": f"{position['games']:,}",
                "frequency": f"{position['frequency']:.2%}",
                "routes": f"{position['acyclic_routes']:,}",
                "share": f"{position['alternative_route_share']:.2%}",
            }
        )
    coverage = ranked["top_20_game_coverage"]
    denominator = elite["denominator_games"]
    return render(
        "opening_positions.html.j2",
        repo_url=REPO_URL,
        preview=preview,
        denominator_games=f"{denominator:,}",
        coverage_games=f"{coverage:,}",
        coverage_share=f"{coverage / denominator:.1%}",
        first_id=first["id"],
        first_games=f"{first['games']:,}",
    )


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
    return render(
        "game_import.html.j2",
        position_counts=range(1, 21),
        reference=encoded_reference,
        example=encoded_example,
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
    return render(
        "transpositions.html.j2",
        board=example["routes"][0]["states"][-1]["svg"],
        data=data,
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
    thresholds = [
        {"value": f"{value}", "label": f"{value:.2f}", "selected": value == threshold}
        for value in (0.0, 0.5, 0.7, 0.85, 0.95)
    ]
    return render(
        "routing.html.j2",
        threshold=f"{threshold:.2f}",
        thresholds=thresholds,
        encoded=encoded,
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
            render(
                "contract_card.html.j2",
                repo_url=REPO_URL,
                name=name,
                title=html.escape(title),
                body=html.escape(json.dumps(obj, indent=2)),
            )
        )
    for name in ("tables.json", "m3_tables.json"):
        for key, fields in json.loads((repo / "contracts" / name).read_text()).items():
            if not isinstance(fields, dict):
                continue
            cards.append(
                render(
                    "schema_card.html.j2",
                    repo_url=REPO_URL,
                    name=name,
                    key=key,
                    fields=[
                        (html.escape(column), html.escape(kind)) for column, kind in fields.items()
                    ],
                )
            )
    return render("definitions.html.j2", count=len(cards), cards="".join(cards))


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
                fragment = unquote(url.fragment)
                line_anchor = re.fullmatch(r"L(\d+)(?:-L(\d+))?", fragment)
                if github and line_anchor:
                    start = int(line_anchor.group(1))
                    end = int(line_anchor.group(2) or start)
                    line_count = len(target.read_text().splitlines())
                    if not 1 <= start <= end <= line_count:
                        raise ValueError(f"Broken generated anchor in {path.name}: {ref}")
                else:
                    cache_key = (target, github)
                    if cache_key not in anchors:
                        anchors[cache_key] = target_anchors(target, github)
                    if fragment not in anchors[cache_key]:
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
    return render(
        "homepage_results.html.j2",
        repo_url=REPO_URL,
        training_games=f"{corpus['training_games']:,}",
        baseline_passed=baseline["passed"],
        baseline_total=baseline["total"],
        gated_passed=gated["passed"],
        gated_total=gated["total"],
        accepted=fixture["accepted"],
    )


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
    home = render(
        "home_cards.html.j2",
        cards=[
            {
                "page": "comparison.html",
                "title": "Read the measured results",
                "desc": (
                    "Rules, Jev and Decisions on shared questions; explore routing "
                    "errors and thresholds."
                ),
                "extra": "Actual classification runs + explicitly labeled replay",
            },
            {
                "page": "architecture.html",
                "title": "Follow the pipeline",
                "desc": (
                    "Inspect how source bytes become checked metrics and evidence-bound answers."
                ),
                "extra": "Six stages with code links",
            },
            {
                "page": "metrics.html",
                "title": "Understand the definitions",
                "desc": (
                    "Search versioned contracts and schemas; explore eligible versus "
                    "evaluable denominators."
                ),
                "extra": "Explicit missingness and coverage",
            },
            {
                "page": "transpositions.html",
                "title": "Explore positions across move orders",
                "desc": (
                    "Compare recurring boards, route balance and coverage across public cohorts."
                ),
                "extra": "Measured rankings, charts and fianchetto lenses",
            },
            {
                "page": "opening-learning.html",
                "title": "Design lessons around positions",
                "desc": "Replay an illustrative transposition and inspect the learning proposal.",
                "extra": "Lesson design and evaluation plan",
            },
            {
                "page": "demo.html",
                "title": "Run it yourself",
                "desc": (
                    "Build tiny synthetic data, explore the dashboard and replay a checked answer."
                ),
                "extra": "No API key; no real archive download",
            },
        ],
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
            demo_images += render("demo_figure.html.j2", name=name, caption=caption)
    bodies = {
        "index.html": (
            "Chess Analytics Lab",
            (
                "A reproducible chess data pipeline, explicit analytical metrics, "
                "and an AI analyst evaluated against checked evidence."
            ),
            render("index_links.html.j2") + homepage_results(repo) + home + md(repo, "HOME.md"),
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
            md(repo, "CLASSIFIER_COMPARISON.md") + routing(repo) + render("report_link.html.j2"),
        ),
        "transpositions.html": (
            "Opening positions, across move orders",
            "Explore recurring boards, route diversity and study-set coverage "
            "in two public cohorts.",
            render("transpositions_banner.html.j2")
            + opening_positions(repo, output)
            + opening_corpus(repo)
            + md(repo, "TRANSPOSITIONS.md")
            + render("moved_lab.html.j2"),
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
            render("learning_banner.html.j2")
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
        render(
            "legacy_anchor.html.j2",
            anchor=html.escape(anchor),
            label=html.escape(anchor.replace("-", " ")),
        )
        for anchor in sorted(legacy.ids - current.ids)
    )
    title, intro, body = bodies["transpositions.html"]
    bodies["transpositions.html"] = (
        title,
        intro,
        body + render("legacy_details.html.j2", aliases=aliases),
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
    source_files.update((repo / "scripts/templates").glob("*.html.j2"))
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
