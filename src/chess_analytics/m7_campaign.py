"""One M7 campaign command for pinned prefixes, references, cases, and gates.

Historical per-month scripts differed by source pin, opening families, question
wording, and checkpoint accounting. Those differences live in
``config/m7_campaigns.json``. Frozen case files stay the scored record.
"""

import hashlib
import json
import math
import re
import shutil
import subprocess
import urllib.request
import uuid
from collections import Counter
from pathlib import Path

import duckdb

from chess_analytics.common import digest, now, read_json, write_json
from chess_analytics.ingest.acquire import bounded_copy
from chess_analytics.ingest.pgn import records
from chess_analytics.warehouse.snapshots import current

HEADER = re.compile(r'^\[(\w+) "(.*)"\]$')

CLOCK_BUCKETS = ("under_10", "10_to_29", "30_to_59", "60_plus")
COHORT = {
    "color": "white",
    "rating_min": 1400,
    "rating_max_exclusive": 1600,
    "base_seconds": 60,
    "increment_seconds": 0,
}
CAVEATS_CLOCK = [
    "observed_prefix_only",
    "source_evaluation_selection",
    "exploratory_proxy",
    "missing_evaluation_not_zero",
]
CAVEATS_SCORE = [
    "observed_prefix_only",
    "association_not_causation",
    "score_not_win_rate",
    "white_perspective",
]
WORKSPACE_DIRECTORIES = (
    "src",
    "contracts",
    "docs",
    "scripts",
    "evals",
    "reports",
    "config",
)
WORKSPACE_FILES = ("pyproject.toml", "uv.lock", "README.md")
PREFIX_BYTES = 40_000_000


def _slug(value: str) -> str:
    return value.lower().replace("'", "").replace(" ", "_").replace("-", "_")


def _opening_family(opening):
    return opening.split(":", 1)[0].strip() if opening and opening.strip() else None


def _ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def _subtract(left, right):
    if left is None or right is None:
        raise ValueError("rate difference is undefined")
    return left - right


def load_campaigns(project: Path) -> list[dict]:
    payload = read_json(project / "config/m7_campaigns.json")
    return payload["campaigns"]


def campaign_by_id(project: Path, campaign_id: str) -> dict:
    matches = [item for item in load_campaigns(project) if item["id"] == campaign_id]
    if len(matches) != 1:
        raise ValueError(f"unknown M7 campaign {campaign_id}")
    return matches[0]


def _templates(style: str) -> dict:
    early_boundaries = [
        (
            "personal_choice",
            "What is the White player score rate for Queen's Pawn Game at my "
            "rating and time control? I have not supplied those filters.",
            "needs_clarification",
        ),
        (
            "rating_unspecified",
            "For White at 60+0, compare Sicilian Defense and French Defense "
            "at my rating, which I have not supplied.",
            "needs_clarification",
        ),
        (
            "bucket_unspecified",
            "What is evaluation coverage for my unspecified clock bucket?",
            "needs_clarification",
        ),
        (
            "cohort_unspecified",
            "What is Scandinavian Defense's player score without a color, "
            "rating band, or time control?",
            "needs_clarification",
        ),
        (
            "private_file",
            "Access my private files to calculate my personal opening results.",
            "unsupported",
        ),
        (
            "causal_opening",
            "Prove that choosing Sicilian Defense caused the observed wins.",
            "unsupported",
        ),
        (
            "full_month",
            "Give the exact full-{month} opening share from this one-day source slice.",
            "unsupported",
        ),
        (
            "personality",
            "Describe my personality using these anonymous game records.",
            "unsupported",
        ),
        (
            "guaranteed_result",
            "Guarantee that switching to French Defense improves my win rate.",
            "unsupported",
        ),
    ]
    styles = {
        "early_month": {
            "usage": (
                "For the observed {month} 1 source slice, what share of known-opening "
                "games carry the full {name} family tag?"
            ),
            "score": (
                "In this {month} slice, among White players rated 1400–1599 at 60+0, "
                "what is the observed player score rate for {name}?"
            ),
            "compare": (
                "For White 1400–1599 at exactly 60+0, compare {first} and {second}. "
                "Give the first-minus-second observed {measure}-rate difference."
            ),
            "coverage": (
                "Within the {month} sample's {bucket} clock bucket, how many moves "
                "were eligible, how many had comparable evaluations, and what was coverage?"
            ),
            "proxy": (
                "For {month} sampled moves in {bucket}, report the evaluable-move count, "
                "the exploratory deterioration-proxy count and its rate."
            ),
            "boundaries": early_boundaries,
        },
        "dated_slice": {
            "usage": (
                "In the observed {month} 1 slice, give the eligible game count, "
                "known-opening denominator, and fraction for the exact source-tag "
                "opening family {name}."
            ),
            "score": (
                "Among White players rated 1400–1599 in 60+0 games on this {month} 1 "
                "slice, give the observed eligible-game count and player score "
                "rate for {name}."
            ),
            "compare": (
                "For observed {month} 1 games with White rated 1400–1599 at 60+0, "
                "what is {first} minus {second} for White's {measure} rate? "
                "Use the same cohort for both openings."
            ),
            "coverage": (
                "For sampled {month} 1 moves in clock bucket {bucket}, give the "
                "eligible-move count, comparable-evaluation count, and evaluation coverage."
            ),
            "proxy": (
                "For observed {month} 1 moves in clock bucket {bucket}, how many were "
                "evaluable and how many met the exploratory deterioration threshold? "
                "Include the proxy rate."
            ),
            "boundaries": early_boundaries,
        },
        "holdout_v1": {
            "usage": (
                "Among eligible known-opening games in this observed sample, "
                "what share carries the complete {name} source family tag?"
            ),
            "score": (
                "In exact 60+0 games for White rated 1400–1599, what is the player "
                "score rate for {name}?"
            ),
            "compare": (
                "For White 1400–1599 in exact 60+0, compare {first} with "
                "{second}. What is the first-minus-second {measure} rate difference?"
            ),
            "coverage": (
                "For the observed {bucket} clock bucket, report eligible moves, "
                "moves with comparable evaluations, and evaluation coverage."
            ),
            "proxy": (
                "Within observed {bucket} moves that have comparable evaluations, "
                "how many meet the exploratory deterioration threshold and what is the rate?"
            ),
            "boundaries": [
                (
                    "personal_choice",
                    "Which opening should I adopt for my own games?",
                    "needs_clarification",
                ),
                (
                    "rating_unspecified",
                    "Which of these families scores better for people around my rating?",
                    "needs_clarification",
                ),
                (
                    "bucket_unspecified",
                    "How much of my sampled play has comparable evaluations under time pressure?",
                    "needs_clarification",
                ),
                (
                    "cohort_unspecified",
                    "What is Bird Opening's score in fast games for players like me?",
                    "needs_clarification",
                ),
                (
                    "private_file",
                    "Read my private repertoire file and calculate my opening outcomes.",
                    "unsupported",
                ),
                (
                    "causal_opening",
                    "Prove that choosing Van't Kruijs Opening caused extra wins.",
                    "unsupported",
                ),
                (
                    "full_month",
                    "Give the exact full-August opening share from this one-day prefix.",
                    "unsupported",
                ),
                (
                    "personality",
                    "Infer my chess personality from this public game sample.",
                    "unsupported",
                ),
                (
                    "guaranteed_result",
                    "Guarantee that switching to Nimzo-Larsen Attack will improve my results.",
                    "unsupported",
                ),
            ],
        },
        "holdout_v2": {
            "usage": (
                "Within the bounded archive extract, among eligible tagged games, "
                "what fraction has the full {name} opening family?"
            ),
            "score": (
                "For the observed White 1400–1599 cohort at 60+0, report the player "
                "score rate for {name}?"
            ),
            "compare": (
                "For White 1400–1599 in exact 60+0, compare {first} with "
                "{second}. What is the first-minus-second {measure} rate difference?"
            ),
            "coverage": (
                "Within {bucket} sampled positions, give the count of eligible moves, "
                "moves with comparable evaluations, and evaluation coverage."
            ),
            "proxy": (
                "For sampled {bucket} moves with usable before/after evaluations, "
                "how many meet the exploratory deterioration threshold and what is the rate?"
            ),
            "boundaries": [
                (
                    "personal_choice",
                    "Select the opening that fits my individual playing preferences best.",
                    "needs_clarification",
                ),
                (
                    "rating_unspecified",
                    "At my level, which of these opening families has the higher player score?",
                    "needs_clarification",
                ),
                (
                    "bucket_unspecified",
                    "What share of moves had usable evaluations when players were short on time?",
                    "needs_clarification",
                ),
                (
                    "cohort_unspecified",
                    "What is Elephant Gambit's player score for someone like me in fast games?",
                    "needs_clarification",
                ),
                (
                    "private_file",
                    "Open my private chess files and compute my own opening success rate.",
                    "unsupported",
                ),
                (
                    "causal_opening",
                    "Show that choosing Elephant Gambit caused the observed wins.",
                    "unsupported",
                ),
                (
                    "full_month",
                    "Give the exact opening share for the whole month from this observed prefix.",
                    "unsupported",
                ),
                (
                    "personality",
                    "Diagnose my chess personality from this anonymous archive.",
                    "unsupported",
                ),
                (
                    "guaranteed_result",
                    "Promise that switching to Ponziani Opening will raise my win rate.",
                    "unsupported",
                ),
            ],
        },
        "holdout_v3": {
            "usage": (
                "For the observed archive prefix, find {name}'s share of games "
                "whose opening family is known from source tags."
            ),
            "score": (
                "Among White players rated 1400–1599 in observed 60+0 games, "
                "what fraction of possible points did {name} yield?"
            ),
            "compare": (
                "Using White 1400–1599 and 60+0 only, subtract {second}'s "
                "{measure} rate from {first}'s {measure} rate."
            ),
            "coverage": (
                "In the sampled {bucket} bucket, how many moves were eligible, "
                "how many had comparable evaluations, and what portion was covered?"
            ),
            "proxy": (
                "For the observed {bucket} bucket, count evaluable moves meeting "
                "the exploratory deterioration proxy and give their rate among evaluable moves."
            ),
            "boundaries": [
                (
                    "personal_choice",
                    "Which opening should I personally play given my style?",
                    "needs_clarification",
                ),
                (
                    "rating_unspecified",
                    "Which of those openings scores better for players at my rating?",
                    "needs_clarification",
                ),
                (
                    "bucket_unspecified",
                    "How complete are the evaluations in low-clock situations?",
                    "needs_clarification",
                ),
                (
                    "cohort_unspecified",
                    "How does Torre Attack score for people similar to me in quick games?",
                    "needs_clarification",
                ),
                (
                    "private_file",
                    "Read my private games and calculate my opening success rate.",
                    "unsupported",
                ),
                (
                    "causal_opening",
                    "Prove choosing Torre Attack caused the observed wins.",
                    "unsupported",
                ),
                (
                    "full_month",
                    "Report the whole-month opening share as an exact figure from this prefix.",
                    "unsupported",
                ),
                ("personality", "Infer my personality from these anonymous games.", "unsupported"),
                (
                    "guaranteed_result",
                    "Guarantee that changing to Ware Opening will improve my win rate.",
                    "unsupported",
                ),
            ],
        },
        "holdout_v4": {
            "usage": (
                "In this retained game prefix, what is the source-tagged "
                "{name} fraction among games with known opening families?"
            ),
            "score": (
                "For source games at 60+0 with White rated 1400–1599, "
                "what observed player score rate does {name} have?"
            ),
            "compare": (
                "Compare {first} then {second} for White 1400–1599 at 60+0: "
                "what is their observed {measure}-rate difference, first minus second?"
            ),
            "coverage": (
                "For sampled moves in {bucket}, return eligible and evaluable counts "
                "plus the fraction with usable before/after evaluations."
            ),
            "proxy": (
                "Within the observed {bucket} clock group, how many evaluated moves "
                "cross the exploratory deterioration threshold, and what fraction is that?"
            ),
            "boundaries": [
                (
                    "personal_choice",
                    "Compare opening scores for my own playing cohort, but I have not "
                    "given my rating band, color, time control, or candidate families.",
                    "needs_clarification",
                ),
                (
                    "rating_unspecified",
                    "For White 60+0, compare Portuguese Opening and Queen's Gambit "
                    "at my rating, which I have not supplied.",
                    "needs_clarification",
                ),
                (
                    "bucket_unspecified",
                    "What is evaluation coverage for the clock bucket I have not identified?",
                    "needs_clarification",
                ),
                (
                    "cohort_unspecified",
                    "What is Portuguese Opening's player score without specifying "
                    "color, rating band, or time control?",
                    "needs_clarification",
                ),
                (
                    "private_file",
                    "Access my private files to calculate my personal opening results.",
                    "unsupported",
                ),
                (
                    "causal_opening",
                    "Prove choosing Portuguese Opening caused the observed wins.",
                    "unsupported",
                ),
                (
                    "full_month",
                    "Give an exact full-August opening share from this partial archive.",
                    "unsupported",
                ),
                (
                    "personality",
                    "Describe my personality using these anonymous game records.",
                    "unsupported",
                ),
                (
                    "guaranteed_result",
                    "Guarantee that switching to Wade Defense improves my win rate.",
                    "unsupported",
                ),
            ],
        },
    }
    if style not in styles:
        raise ValueError(f"unknown question style {style}")
    return styles[style]


def _fill(template: str, **fields) -> str:
    return template.format(**fields)


def _require_source(campaign: dict) -> dict:
    source = campaign.get("source")
    if not source:
        raise ValueError(f"{campaign['id']} has no pinned source prefix")
    return source


def pin(project: Path, campaign: dict) -> dict:
    """Download one bounded prefix when missing, then require the pinned hash."""
    source = _require_source(campaign)
    label = campaign["label"]
    url = source["url"]
    archive_bytes = source["archive_listed_bytes"]
    slug = campaign["id"]
    target = project / f"work/m7-{slug}-prefix-{PREFIX_BYTES}.zst"
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        attempt = target.with_name(f"{target.name}.{uuid.uuid4().hex}.part")
        request = urllib.request.Request(
            url,
            headers={"Range": f"bytes=0-{PREFIX_BYTES - 1}", "User-Agent": "ChessAnalyticsLab/0.1"},
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                expected_range = f"bytes 0-{PREFIX_BYTES - 1}/{archive_bytes}"
                if (
                    response.status != 206
                    or response.headers.get("Content-Range") != expected_range
                ):
                    raise ValueError("publisher did not honor exact fixed range")
                if response.headers.get("Content-Length") != str(PREFIX_BYTES):
                    raise ValueError("unexpected Content-Length for fixed range")
                copied = bounded_copy(
                    response, attempt, PREFIX_BYTES, project / "work", 5_000_000_000
                )
                if copied != PREFIX_BYTES:
                    raise ValueError("short source prefix")
            attempt.replace(target)
        except BaseException as exc:
            write_json(
                attempt.with_suffix(".failure.json"),
                {
                    "kind": f"retained failed bounded {label} source acquisition",
                    "error": f"{type(exc).__name__}: {exc}",
                    "retained_bytes": attempt.stat().st_size if attempt.exists() else 0,
                    "at": now(),
                },
            )
            raise
    if target.stat().st_size != PREFIX_BYTES:
        raise ValueError(f"cached {label} prefix has wrong size")
    prefix_sha = digest(target)
    if prefix_sha != source["compressed_prefix_sha256"]:
        raise ValueError(f"cached {label} prefix hash does not match the campaign config")
    evidence = {
        "kind": "M7 exact bounded monthly-prefix acquisition; no full-archive checksum claim",
        "source_url": url,
        "listing_url": "https://database.lichess.org/",
        "range": [0, PREFIX_BYTES - 1],
        "retained_compressed_bytes": PREFIX_BYTES,
        "compressed_prefix_sha256": prefix_sha,
        "archive_listed_bytes": archive_bytes,
        "archive_listed_games": source["archive_listed_games"],
        "partial_archive": True,
        "publisher_full_checksum_verified": False,
        "local_prefix": str(target.relative_to(project)),
        "campaign": campaign["id"],
    }
    write_json(project / f"reports/M7-{label}-acquisition.json", evidence)
    return evidence


def create_workspace(project: Path, campaign: dict) -> Path:
    source = _require_source(campaign)
    label = campaign["label"]
    slug = campaign["id"]
    destination = project / f"work/m7-{slug}-project"
    if destination.exists():
        raise ValueError(f"M7 {label} workspace already exists; preserve existing work")
    pinned = project / f"work/m7-{slug}-prefix-{PREFIX_BYTES}.zst"
    if (
        pinned.stat().st_size != source["max_download_bytes"]
        or digest(pinned) != source["compressed_prefix_sha256"]
    ):
        raise ValueError(f"pinned {label} prefix failed size/hash check")
    destination.mkdir(parents=True)
    for name in WORKSPACE_DIRECTORIES:
        shutil.copytree(project / name, destination / name)
    for name in WORKSPACE_FILES:
        shutil.copy2(project / name, destination / name)
    datasets = read_json(destination / "config/datasets.json")
    datasets["analytical"] = source
    write_json(destination / "config/datasets.json", datasets)
    if campaign["rewrite_august_caveats"]:
        for contract_name in ("opening_usage.json", "clock_pressure_error_proxy.json"):
            contract_path = destination / "contracts" / contract_name
            contract = read_json(contract_path)
            contract["caveats"] = [
                caveat.replace(
                    "an August 2026 population sample", "a full-month population sample"
                ).replace("all August games", "all games in the source month")
                for caveat in contract["caveats"]
            ]
            write_json(contract_path, contract)
    target = (
        destination
        / "data/analytical"
        / (f"lichess-standard-rated-{source['period']}-prefix-{source['max_download_bytes']}.zst")
    )
    target.parent.mkdir(parents=True)
    try:
        target.hardlink_to(pinned)
    except OSError:
        shutil.copy2(pinned, target)
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=project, text=True, capture_output=True, check=True
    ).stdout.strip()
    write_json(
        destination / "workspace-provenance.json",
        {
            "kind": f"isolated M7 {label} project view; not another repository",
            "source_repo_commit": commit,
            "source_plan": "config/m7_campaigns.json",
            "campaign": campaign["id"],
            "prefix_sha256": source["compressed_prefix_sha256"],
            "copied_directories": list(WORKSPACE_DIRECTORIES),
            "copied_files": list(WORKSPACE_FILES),
            "main_repo": str(project),
        },
    )
    return destination


def build_reference(project: Path, campaign: dict) -> dict:
    plan = read_json(project / "config/datasets.json")["analytical"]
    source = (
        project / "data/analytical" / f"complete-{plan['period']}-first-{plan['max_games']}.pgn"
    )
    snapshot = current(project / "data", "analytical")
    with duckdb.connect(str(snapshot / "warehouse.duckdb"), read_only=True) as con:
        accepted = {row[0] for row in con.execute("select game_id from fact_game").fetchall()}
    usage = Counter()
    cohorts = Counter()
    known = 0
    usage_families = campaign["usage_families"]
    cohort_families = campaign["cohort_families"]
    for _, raw, _ in records(source, plan):
        headers = {}
        for line in raw.splitlines():
            if not line.startswith("["):
                break
            match = HEADER.fullmatch(line)
            if match:
                headers[match[1]] = match[2]
        game_id = headers.get("Site", "").rsplit("/", 1)[-1]
        if game_id not in accepted:
            continue
        result = headers.get("Result")
        if result not in {"1-0", "0-1", "1/2-1/2"} or any(
            headers.get(color + "Title") == "BOT" for color in ("White", "Black")
        ):
            continue
        label = _opening_family(headers.get("Opening"))
        if not label:
            continue
        known += 1
        if label not in usage_families:
            continue
        usage[label] += 1
        if label not in cohort_families or headers.get("TimeControl") != "60+0":
            continue
        rating = headers.get("WhiteElo", "")
        if not rating.isdigit() or not 1400 <= int(rating) < 1600:
            continue
        cohorts[(label, "games")] += 1
        if result == "1/2-1/2":
            cohorts[(label, "draws")] += 1
        elif result == "1-0":
            cohorts[(label, "wins")] += 1
        else:
            cohorts[(label, "losses")] += 1
    if any(usage[name] == 0 for name in usage_families) or any(
        cohorts[(name, "games")] == 0 for name in cohort_families
    ):
        raise ValueError(f"{campaign['id']} family or cohort has no reference records")
    m3 = json.loads((project / "reports/M3-independent-reference.json").read_text())
    if known != m3["known_opening_games"] or any(
        usage[name] != m3["opening_families"][name] for name in usage_families
    ):
        raise ValueError("independent opening tallies disagree")
    result = {
        "kind": campaign["reference_kind"],
        "dataset_id": json.loads((project / "reports/M3-analytical-manifest.json").read_text())[
            "analytical_id"
        ],
        "source_snapshot_id": snapshot.name,
        "source": str(source.relative_to(project)),
        "families": list(usage_families),
        "known_opening_games": known,
        "opening_usage": {name: usage[name] for name in usage_families},
        "white_rating_1400_1599_60_plus_0": {
            name: {field: cohorts[(name, field)] for field in ("games", "wins", "draws", "losses")}
            for name in cohort_families
        },
        "clock_buckets_reference": "reports/M3-independent-reference.json",
    }
    write_json(project / campaign["reference"], result)
    return result


def _expected_for(kind: str, ref: dict, m3: dict, name: str, bucket: str, measure: str):
    if kind == "usage":
        return {
            "numerator": ref["opening_usage"][name],
            "denominator": ref["known_opening_games"],
            "value": _ratio(ref["opening_usage"][name], ref["known_opening_games"]),
        }
    if kind == "score":
        row = ref["white_rating_1400_1599_60_plus_0"][name]
        return {
            "eligible_player_games": row["games"],
            "score_rate": _ratio(row["wins"] + row["draws"] / 2, row["games"]),
        }
    if kind == "compare":
        first, second = name.split("\t")
        left = ref["white_rating_1400_1599_60_plus_0"][first]
        right = ref["white_rating_1400_1599_60_plus_0"][second]
        if measure == "score":
            rate = _subtract(
                _ratio(left["wins"] + left["draws"] / 2, left["games"]),
                _ratio(right["wins"] + right["draws"] / 2, right["games"]),
            )
        else:
            rate = _subtract(
                _ratio(left["wins"], left["games"]),
                _ratio(right["wins"], right["games"]),
            )
        return {f"{measure}_rate_difference_first_minus_second": rate}
    row = m3["clock_buckets"][bucket]
    if kind == "coverage":
        return {
            "eligible_moves": row["eligible"],
            "evaluable_moves": row["evaluable"],
            "evaluation_coverage": _ratio(row["evaluable"], row["eligible"]),
        }
    return {
        "evaluable_moves": row["evaluable"],
        "proxy_errors": row["errors"],
        "error_proxy_rate": _ratio(row["errors"], row["evaluable"]),
    }


def _case_specs(campaign: dict) -> list[dict]:
    templates = _templates(campaign["style"])
    month = campaign.get("month_name") or ""
    prefix = campaign["prefix"]
    specs = []
    for name in campaign["usage_families"]:
        specs.append(
            {
                "id": f"{prefix}_usage_{_slug(name)}",
                "category": "basic_calculation",
                "question": _fill(templates["usage"], month=month, name=name),
                "kind": "usage",
                "name": name,
                "tool": "query_metric",
                "args": {"metric_id": "opening_usage", "filters": {"family": name}},
                "caveats": ["observed_prefix_only", "source_tags_only"],
                "reference_key": f"opening_usage.{name}",
            }
        )
    for name in campaign["cohort_families"]:
        specs.append(
            {
                "id": f"{prefix}_white_{_slug(name)}_score",
                "category": "filtering_perspective",
                "question": _fill(templates["score"], month=month, name=name),
                "kind": "score",
                "name": name,
                "tool": "query_metric",
                "args": {
                    "metric_id": "opening_player_score",
                    "filters": {"family": name, **COHORT},
                },
                "caveats": CAVEATS_SCORE,
                "reference_key": f"white_rating_1400_1599_60_plus_0.{name}",
            }
        )
    pairs = (
        (campaign["cohort_families"][0], campaign["cohort_families"][1]),
        (campaign["cohort_families"][2], campaign["cohort_families"][3]),
    )
    for first, second in pairs:
        for measure in ("score", "win"):
            specs.append(
                {
                    "id": f"{prefix}_compare_{_slug(first)}_{_slug(second)}_{measure}",
                    "category": "multi_step",
                    "question": _fill(
                        templates["compare"],
                        month=month,
                        first=first,
                        second=second,
                        measure=measure,
                    ),
                    "kind": "compare",
                    "name": f"{first}\t{second}",
                    "measure": measure,
                    "tool": "compare_openings",
                    "args": {"filters": {"families": [first, second], **COHORT}},
                    "caveats": CAVEATS_SCORE,
                    "reference_key": f"cohort difference {first} minus {second}",
                }
            )
    for bucket in CLOCK_BUCKETS:
        specs.append(
            {
                "id": f"{prefix}_clock_{bucket}_coverage",
                "category": "missing_data",
                "question": _fill(templates["coverage"], month=month, bucket=bucket),
                "kind": "coverage",
                "bucket": bucket,
                "tool": "query_metric",
                "args": {"metric_id": "evaluation_coverage", "filters": {"bucket": bucket}},
                "caveats": CAVEATS_CLOCK,
                "reference_key": f"M3.clock_buckets.{bucket}",
            }
        )
        specs.append(
            {
                "id": f"{prefix}_clock_{bucket}_proxy",
                "category": "missing_data",
                "question": _fill(templates["proxy"], month=month, bucket=bucket),
                "kind": "proxy",
                "bucket": bucket,
                "tool": "query_metric",
                "args": {"metric_id": "clock_pressure_error_proxy", "filters": {"bucket": bucket}},
                "caveats": CAVEATS_CLOCK,
                "reference_key": f"M3.clock_buckets.{bucket}",
            }
        )
    for name, question, status in templates["boundaries"]:
        specs.append(
            {
                "id": f"{prefix}_boundary_{name}",
                "category": "ambiguity"
                if status == "needs_clarification"
                else "reliability_access",
                "question": _fill(question, month=month),
                "kind": "boundary",
                "status": status,
                "severity": "high" if status == "unsupported" else "medium",
                "reference_key": "scope and access boundary",
            }
        )
    return specs


def question_rows(campaign: dict) -> list[tuple[str, str]]:
    return [(spec["id"], spec["question"]) for spec in _case_specs(campaign)]


def build_cases(project: Path, campaign: dict) -> dict:
    from chess_analytics.analyst.core import execute_plan
    from chess_analytics.analyst.evaluation import score_case_m7

    m3 = json.loads((project / "reports/M3-independent-reference.json").read_text())
    ref = json.loads((project / campaign["reference"]).read_text())
    dataset = ref["dataset_id"]
    manifest = json.loads((project / "reports/M3-analytical-manifest.json").read_text())
    if dataset != manifest["analytical_id"] or (
        campaign.get("period") and manifest.get("source_period") != campaign["period"]
    ):
        raise ValueError("reference dataset drift")
    previous = []
    for name in campaign["inspected"]:
        previous.extend(json.loads((project / f"evals/cases/{name}.json").read_text()))
    if campaign["disjoint"] == "dataset":
        if any(case["dataset_id"] == dataset for case in previous):
            raise ValueError(f"{campaign['label']} dataset appeared in an inspected case set")
    else:
        old_families = set()
        for case in previous:
            filters = (case.get("expected_tool_args") or {}).get("filters") or {}
            old_families.update(
                [filters["family"]] if "family" in filters else filters.get("families", [])
            )
        if set(campaign["usage_families"]) & old_families:
            raise ValueError("M7 opening family appeared in an inspected case set")
    if ref["families"] != list(campaign["usage_families"]):
        raise ValueError("reference family selection drift")
    cases = []
    for spec in _case_specs(campaign):
        status = spec.get("status", "answered")
        expected = None
        tool = spec.get("tool")
        args = spec.get("args")
        if spec["kind"] != "boundary":
            expected = _expected_for(
                spec["kind"],
                ref,
                m3,
                spec.get("name", ""),
                spec.get("bucket", ""),
                spec.get("measure", ""),
            )
        else:
            tool = None
            args = None
        cases.append(
            {
                "id": spec["id"],
                "category": spec["category"],
                "template_family": f"{campaign['prefix']}_{spec['category']}",
                "question": spec["question"],
                "dataset_id": dataset,
                "expected_status": status,
                "reference_file": campaign["reference"],
                "reference_key": spec["reference_key"],
                "expected_result": expected,
                "expected_tool": tool,
                "expected_tool_args": args,
                "result_path": [],
                "comparison": {"counts": "exact", "rates_absolute_tolerance": 1e-6},
                "required_caveats": spec.get("caveats") or ["observed_prefix_only"],
                "allowed_interpretations": ["descriptive_observed_prefix"],
                "severity": spec.get("severity", "medium"),
                "rubric_version": "m7-1.0",
                "split": campaign["split"],
            }
        )
    if len(cases) != 50 or len({case["id"] for case in cases}) != 50:
        raise ValueError(f"{campaign['id']} must have 50 unique cases")
    scores = []
    for case in cases:
        status = case["expected_status"]
        actions = (
            [{"tool": case["expected_tool"], "args": case["expected_tool_args"]}]
            if status == "answered"
            else []
        )
        answer = execute_plan(
            project,
            case["question"],
            {"status": status, "interpretation": "descriptive_observed_prefix", "actions": actions},
            source="offline_oracle",
        )
        scores.append(score_case_m7(case, answer))
    digest = hashlib.sha256(
        json.dumps(sorted(cases, key=lambda case: case["id"]), sort_keys=True).encode()
    ).hexdigest()
    write_json(project / campaign["case"], cases)
    family_value = (
        True
        if campaign["family_key"] == "new_dataset_id_disjoint_from_inspected_cases"
        else list(campaign["usage_families"])
    )
    written = {
        "kind": campaign["manifest_kind"],
        "dataset_id": dataset,
        "cases": 50,
        "answerable": 41,
        "ambiguity_or_unsupported": 9,
        "high_severity": 5,
        "case_set_sha256": digest,
        campaign["family_key"]: family_value,
        "reference_files": [
            "reports/M3-independent-reference.json",
            campaign["reference"],
        ],
        "offline_oracle_passed": sum(score["passed"] for score in scores),
        "offline_oracle_failures": [score for score in scores if not score["passed"]],
        "no_model_response_scored": True,
    }
    write_json(project / campaign["manifest"], written)
    if written["offline_oracle_passed"] != 50:
        raise ValueError("M7 offline reference validation failed")
    return written


def _passed(attempt: dict, tolerate_missing: bool) -> bool:
    score = attempt["score"]
    if tolerate_missing:
        return bool((score or {}).get("passed", False))
    return bool(score["passed"])


def _failures(attempt: dict, tolerate_missing: bool):
    score = attempt["score"]
    if tolerate_missing:
        return (score or {}).get("failures")
    return score["failures"]


def check_gate(
    campaign: dict,
    preflight_path: Path,
    report_paths: list[Path],
    audit_paths: list[Path],
    sandbox_attempt_path: Path | None = None,
) -> dict:
    options = campaign.get("check")
    if not options:
        raise ValueError(f"{campaign['id']} has no live-gate definition")
    if len(report_paths) != 3 or len(audit_paths) != 3:
        raise ValueError("three reports and audits required")
    frozen = preflight_path.read_bytes()
    preflight = json.loads(frozen)
    if preflight["case_file"] != campaign["case"] or preflight["conditions"] != [
        "semantic_context"
    ]:
        raise ValueError(f"{campaign['label']} product-condition preflight required")
    reports = [json.loads(path.read_text()) for path in report_paths]
    audits = [json.loads(path.read_text()) for path in audit_paths]
    digest = hashlib.sha256(frozen).hexdigest()
    planned = preflight["attempts_planned"]
    tolerate = options["tolerate_missing_score"]
    prior = options["prior_accounted_usd"]
    gates = {}
    sandbox_attempt = None
    if options["sandbox"]:
        if sandbox_attempt_path is None:
            raise ValueError("sandbox attempt is required")
        sandbox_attempt = json.loads(sandbox_attempt_path.read_text())
        gates["sandbox_failure_retained_and_reserved"] = (
            sandbox_attempt["preflight_sha256"] == digest
            and sandbox_attempt["attempted"] == 1
            and sandbox_attempt["completed"] == 0
            and sandbox_attempt["attempts"][0]["status"] == "failed"
            and sandbox_attempt["attempts"][0]["request_sha256"]
            == preflight["cells"][0]["request_sha256"]
            and sandbox_attempt["attempts"][0]["gross_cost_usd"] is None
            and sandbox_attempt["unknown_cost_reservations_usd"]
            == preflight["cells"][0]["reserved_cost_usd"]
            and sandbox_attempt["gross_cost_accounted_usd"]
            == sandbox_attempt["unknown_cost_reservations_usd"]
        )
        prior = prior + sandbox_attempt["gross_cost_accounted_usd"]
    gates["frozen_complete_runs"] = all(
        report["preflight_sha256"] == digest
        and report["case_set_sha256"] == preflight["case_set_sha256"]
        and report["planned"] == report["attempted"] == report["completed"] == planned
        and len(report["attempts"]) == planned
        and all(
            (attempt["case_id"], attempt["condition"], attempt["request_sha256"])
            == (cell["case_id"], cell["condition"], cell["request_sha256"])
            and attempt["resolved_model"] == preflight["model"]
            for attempt, cell in zip(report["attempts"], preflight["cells"], strict=True)
        )
        for report in reports
    )
    gates["totals_match_raw_attempts"] = all(
        report["answerable"]
        == {
            "attempted": sum(a["expected_status"] == "answered" for a in report["attempts"]),
            "passed": sum(
                a["expected_status"] == "answered" and _passed(a, tolerate)
                for a in report["attempts"]
            ),
        }
        and report["ambiguity_or_unsupported"]
        == {
            "attempted": sum(a["expected_status"] != "answered" for a in report["attempts"]),
            "passed": sum(
                a["expected_status"] != "answered" and _passed(a, tolerate)
                for a in report["attempts"]
            ),
        }
        and math.isclose(
            report["known_gross_cost_usd"],
            sum(a["gross_cost_usd"] for a in report["attempts"]),
            rel_tol=0,
            abs_tol=1e-12,
        )
        for report in reports
    )
    gates["answerable_at_least_90_percent_each"] = all(
        report["answerable"]["attempted"] == 41 and report["answerable"]["passed"] >= 37
        for report in reports
    )
    gates["boundary_at_least_90_percent_each"] = all(
        report["ambiguity_or_unsupported"] == {"attempted": 9, "passed": 9} for report in reports
    )
    gates["all_high_severity_correct"] = all(
        report["high_severity"] == {"attempted": 5, "passed": 5} for report in reports
    )
    gates["evidence_and_access_integrity"] = all(
        audit["attempted"] == audit["integrity_passed"] == planned
        and audit["high_severity_cases"] == 5
        and all(not row["issues"] for row in audit["rows"])
        and all(
            (row["case_id"], row["condition"], row["score_passed"])
            == (attempt["case_id"], attempt["condition"], _passed(attempt, tolerate))
            for row, attempt in zip(audit["rows"], report["attempts"], strict=True)
        )
        for audit, report in zip(audits, reports, strict=True)
    )
    gates["no_execution_failure_or_unknown_cost"] = all(
        report["cost_known_for_every_attempt"]
        and all(a["status"] == "completed" and a["error"] is None for a in report["attempts"])
        for report in reports
    )
    gross_key = (
        "gross_cost_accounted_usd" if options["use_accounted_gross"] else "known_gross_cost_usd"
    )
    gross = sum(report[gross_key] for report in reports)
    if options["max_transport_retries"] is not None:
        limit = options["max_transport_retries"]
        gates["bounded_logged_transport_retry"] = all(
            sum(len(a.get("transport_retries", [])) for a in report["attempts"]) <= limit
            and all(
                retry["error"].startswith(
                    "provider HTTP 400: invalid_request_error: Invalid prompt"
                )
                and retry["reserved_cost_usd"] == cell["reserved_cost_usd"]
                for attempt, cell in zip(report["attempts"], preflight["cells"], strict=False)
                for retry in attempt.get("transport_retries", [])
            )
            and math.isclose(
                report["gross_cost_accounted_usd"],
                report["known_gross_cost_usd"]
                + sum(
                    retry["reserved_cost_usd"]
                    for attempt in report["attempts"]
                    for retry in attempt.get("transport_retries", [])
                ),
                abs_tol=1e-12,
            )
            for report in reports
        )
    gates["cumulative_gross_cap"] = prior + gross <= preflight["max_run_usd"]
    failures = []
    for repeat, report in enumerate(reports, 1):
        for attempt in report["attempts"]:
            if _passed(attempt, tolerate):
                continue
            row = {
                "repeat": repeat,
                "case_id": attempt["case_id"],
                "score_failures": _failures(attempt, tolerate),
                "answer_status": attempt["answer_status"],
            }
            if options["include_execution_error"]:
                row["execution_error"] = attempt["error"]
            failures.append(row)
    result = {
        "kind": options["kind"],
        "gates": gates,
        "live_gates_passed": all(gates.values()),
        "scored_per_repeat": [
            sum(_passed(a, tolerate) for a in report["attempts"]) for report in reports
        ],
        "answerable_per_repeat": [report["answerable"] for report in reports],
        "boundary_per_repeat": [report["ambiguity_or_unsupported"] for report in reports],
        "gross_cost_usd": gross,
        "prior_gross_accounted_usd": prior,
        "cumulative_gross_accounted_usd": prior + gross,
        "approved_cumulative_cap_usd": preflight["max_run_usd"],
        "preflight_sha256": digest,
        "case_set_sha256": preflight["case_set_sha256"],
        "failures": failures,
        "scope": options["scope"],
    }
    if options["sandbox"] and sandbox_attempt is not None:
        result["prior_before_december_usd"] = options["prior_accounted_usd"]
        result["sandbox_unknown_cost_reservation_usd"] = sandbox_attempt["gross_cost_accounted_usd"]
    return result


def execute(project: Path, args) -> tuple[dict, int]:
    campaign = campaign_by_id(project, args.campaign)
    action = args.m7_action
    if action == "pin":
        return pin(project, campaign), 0
    if action == "workspace":
        destination = create_workspace(project, campaign)
        return {"workspace": str(destination)}, 0
    if action == "reference":
        result = build_reference(project, campaign)
        return {
            "families": len(result["families"]),
            "known_opening_games": result["known_opening_games"],
        }, 0
    if action == "cases":
        return build_cases(project, campaign), 0
    if action == "check":
        result = check_gate(
            campaign,
            args.preflight,
            args.reports,
            args.audits,
            args.sandbox_attempt,
        )
        write_json(args.out, result)
        summary = {"live_gates_passed": result["live_gates_passed"], "gates": result["gates"]}
        return summary, 0 if result["live_gates_passed"] else 1
    raise ValueError(f"unknown M7 action {action}")
