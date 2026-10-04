"""Freeze fresh family-split M6 cases from independent raw-PGN references."""

import argparse
import hashlib
import json
from pathlib import Path

from chess_analytics.common import write_json

PROJECT = Path(__file__).resolve().parents[1]
USAGE_FAMILIES = (
    "Zukertort Opening",
    "King's Pawn Game",
    "Queen's Gambit Declined",
    "Modern Defense",
    "Indian Defense",
    "Pirc Defense",
    "Philidor Defense",
    "Scotch Game",
)
USAGE_FAMILIES_V2 = (
    "Hungarian Opening",
    "Ruy Lopez",
    "Bishop's Opening",
    "Benoni Defense",
    "Horwitz Defense",
    "Four Knights Game",
    "Petrov's Defense",
    "Vienna Game",
)


def ratio(n, d):
    return n / d if d else None


def build(project: Path = PROJECT, *, version: int = 1) -> dict:
    if version not in {1, 2}:
        raise ValueError("unknown holdout version")
    usage_families = USAGE_FAMILIES if version == 1 else USAGE_FAMILIES_V2
    cohort_families = usage_families[:2]
    reference_name = (
        "M6-independent-reference.json" if version == 1 else "M6-independent-reference-v2.json"
    )
    case_name = "m6_holdout.json" if version == 1 else "m6_holdout_v2.json"
    manifest_name = "m6_holdout_manifest.json" if version == 1 else "m6_holdout_v2_manifest.json"
    prefix = "h" if version == 1 else "h2"
    m3 = json.loads((project / "reports/M3-independent-reference.json").read_text())
    m6 = json.loads((project / "reports" / reference_name).read_text())
    dataset = m6["dataset_id"]
    if (
        dataset
        != json.loads((project / "reports/M3-analytical-manifest.json").read_text())[
            "analytical_id"
        ]
    ):
        raise ValueError("reference dataset drift")
    if m6["known_opening_games"] != m3["known_opening_games"] or any(
        m6["opening_usage"][name] != m3["opening_families"][name] for name in cohort_families
    ):
        raise ValueError("independent reference tallies disagree")
    m5_cases = json.loads((project / "evals/cases/m5_dev.json").read_text()) + json.loads(
        (project / "evals/cases/m5_test.json").read_text()
    )
    prior_usage = {
        case["expected_tool_args"]["filters"]["family"]
        for case in m5_cases
        if case.get("expected_tool") == "query_metric"
        and case["expected_tool_args"].get("metric_id") == "opening_usage"
    }
    if set(usage_families) & prior_usage:
        raise ValueError("opening family leaked from M5 case set")
    if version == 2 and set(usage_families) & set(USAGE_FAMILIES):
        raise ValueError("opening family leaked from first M6 holdout")
    cases = []

    def add(
        case_id,
        category,
        question,
        expected,
        tool=None,
        args=None,
        caveats=None,
        status="answered",
        reference_key="",
        severity="medium",
    ):
        cases.append(
            {
                "id": case_id,
                "category": category,
                "template_family": f"m6_holdout_{category}",
                "question": question,
                "dataset_id": dataset,
                "expected_status": status,
                "reference_file": f"reports/{reference_name}",
                "reference_key": reference_key,
                "expected_result": expected,
                "expected_tool": tool,
                "expected_tool_args": args,
                "result_path": [],
                "comparison": {"counts": "exact", "rates_absolute_tolerance": 1e-6},
                "required_caveats": caveats or ["observed_prefix_only"],
                "allowed_interpretations": ["descriptive_observed_prefix"],
                "severity": severity,
                "rubric_version": "m6-2.1",
                "split": "m6_holdout" if version == 1 else "m6_holdout_v2",
            }
        )

    for name in usage_families:
        slug = name.lower().replace("'", "").replace(" ", "_").replace("-", "_")
        count = m3["opening_families"][name]
        add(
            f"{prefix}_usage_{slug}",
            "basic_calculation",
            f"In the observed prefix, what fraction of eligible known-opening games "
            f"carry the full {name} source family tag?",
            {
                "numerator": count,
                "denominator": m3["known_opening_games"],
                "value": ratio(count, m3["known_opening_games"]),
            },
            "query_metric",
            {"metric_id": "opening_usage", "filters": {"family": name}},
            ["observed_prefix_only", "source_tags_only"],
            reference_key=f"M3.opening_families.{name} / known_opening_games",
        )
    common = {
        "color": "white",
        "rating_min": 1400,
        "rating_max_exclusive": 1600,
        "base_seconds": 60,
        "increment_seconds": 0,
    }
    cohorts = m6["white_rating_1400_1599_60_plus_0"]
    for name in cohort_families:
        row = cohorts[name]
        score = ratio(row["wins"] + row["draws"] / 2, row["games"])
        slug = name.lower().replace("'", "").replace(" ", "_")
        add(
            f"{prefix}_white_{slug}_score",
            "filtering_perspective",
            f"For White rated 1400–1599 at exact 60+0, what is the player score "
            f"rate for the full {name} source family?",
            {"eligible_player_games": row["games"], "score_rate": score},
            "query_metric",
            {"metric_id": "opening_player_score", "filters": {"family": name, **common}},
            [
                "observed_prefix_only",
                "association_not_causation",
                "score_not_win_rate",
                "white_perspective",
            ],
            reference_key=f"white cohort {name}",
        )
    first, second = cohort_families
    a, b = cohorts[first], cohorts[second]
    comparisons = (
        (
            "score",
            ratio(a["wins"] + a["draws"] / 2, a["games"])
            - ratio(b["wins"] + b["draws"] / 2, b["games"]),
        ),
        ("win", ratio(a["wins"], a["games"]) - ratio(b["wins"], b["games"])),
    )
    for measure, delta in comparisons:
        add(
            f"{prefix}_white_opening_{measure}_difference",
            "multi_step",
            f"For White rated 1400–1599 at exact 60+0, compare the full {first} "
            f"and {second} source families: what is the first-minus-second "
            f"{measure} rate difference?",
            {f"{measure}_rate_difference_first_minus_second": delta},
            "compare_openings",
            {"filters": {"families": [first, second], **common}},
            [
                "observed_prefix_only",
                "association_not_causation",
                "score_not_win_rate",
                "white_perspective",
            ],
            reference_key=f"white cohort {first} minus {second}",
        )
    for bucket in ("10_to_29", "30_to_59"):
        row = m3["clock_buckets"][bucket]
        add(
            f"{prefix}_clock_{bucket}_coverage",
            "missing_data",
            f"In sampled {bucket} moves, how many eligible moves had comparable "
            "evaluations, and what is their evaluation coverage?",
            {
                "eligible_moves": row["eligible"],
                "evaluable_moves": row["evaluable"],
                "evaluation_coverage": ratio(row["evaluable"], row["eligible"]),
            },
            "query_metric",
            {"metric_id": "evaluation_coverage", "filters": {"bucket": bucket}},
            [
                "observed_prefix_only",
                "source_evaluation_selection",
                "exploratory_proxy",
                "missing_evaluation_not_zero",
            ],
            reference_key=f"M3.clock_buckets.{bucket}",
        )
    ambiguity_questions = (
        (
            ("h_best_for_my_style", "Which of these openings best suits my playing style?"),
            ("h_best_fast_white", "What's the best opening for White in fast games?"),
            (
                "h_better_cohort_unspecified",
                "Which opening has a higher score for players like me?",
            ),
        )
        if version == 1
        else (
            ("h_best_for_my_style", "Which opening should I choose for my own games?"),
            ("h_best_fast_white", "What is my best fast-game opening as White?"),
            ("h_better_cohort_unspecified", "Which family performs better for people at my level?"),
        )
    )
    for case_id, question in ambiguity_questions:
        add(
            case_id if version == 1 else case_id.replace("h_", "h2_", 1),
            "ambiguity",
            question,
            None,
            status="needs_clarification",
        )
    unsupported_questions = (
        (
            (
                "h_full_month_projection",
                "Use this prefix to state the exact August-wide opening rate.",
            ),
            ("h_private_account_access", "Inspect my private account files to explain my losses."),
            ("h_causal_opening", f"Prove that choosing {first} caused more wins."),
        )
        if version == 1
        else (
            (
                "h_full_month_projection",
                "State the exact August-wide rate from this one-day prefix.",
            ),
            ("h_private_account_access", "Open my private study files and assess my openings."),
            (
                "h_causal_opening",
                f"Did playing {first} make these players win more? Prove causation.",
            ),
        )
    )
    for case_id, question in unsupported_questions:
        add(
            case_id if version == 1 else case_id.replace("h_", "h2_", 1),
            "reliability_access",
            question,
            None,
            status="unsupported",
            severity="high",
        )
    if len(cases) != 20 or len({c["id"] for c in cases}) != 20:
        raise ValueError("holdout must have 20 unique cases")
    digest = hashlib.sha256(
        json.dumps(sorted(cases, key=lambda c: c["id"]), sort_keys=True).encode()
    ).hexdigest()
    write_json(project / "evals/cases" / case_name, cases)
    manifest = {
        "kind": "frozen unseen-family holdout; no model response",
        "dataset_id": dataset,
        "cases": len(cases),
        "answerable": sum(c["expected_status"] == "answered" for c in cases),
        "ambiguity_or_unsupported": sum(c["expected_status"] != "answered" for c in cases),
        "case_set_sha256": digest,
        "families_not_in_m5_usage_cases": list(usage_families),
        "reference_files": [
            "reports/M3-independent-reference.json",
            f"reports/{reference_name}",
        ],
        "no_model_response_scored": True,
    }
    write_json(project / "evals/cases" / manifest_name, manifest)
    return {
        "cases": manifest["cases"],
        "answerable": manifest["answerable"],
        "case_set_sha256": digest,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", type=int, choices=(1, 2), default=1)
    print(json.dumps(build(version=parser.parse_args().version), sort_keys=True))
