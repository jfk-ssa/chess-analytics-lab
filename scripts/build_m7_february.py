"""Freeze 50 independently referenced M7 February v10 cases before any model response."""

import hashlib
import json
from pathlib import Path

from analyst_m5.core import execute_plan
from analyst_m5.evaluation import score_case_m7
from chess_analytics.common import write_json
from scripts.reference_m7_february import COHORT_FAMILIES, USAGE_FAMILIES

PROJECT = Path(__file__).resolve().parents[1]
CLOCK_BUCKETS = ("under_10", "10_to_29", "30_to_59", "60_plus")


def _ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def _slug(value):
    return value.lower().replace("'", "").replace(" ", "_").replace("-", "_")


def build(project: Path = PROJECT) -> dict:
    m3 = json.loads((project / "reports/M3-independent-reference.json").read_text())
    ref = json.loads((project / "reports/M7-independent-reference-v10.json").read_text())
    dataset = ref["dataset_id"]
    manifest = json.loads((project / "reports/M3-analytical-manifest.json").read_text())
    if dataset != manifest["analytical_id"] or manifest["source_period"] != "2026-02":
        raise ValueError("reference dataset drift")
    previous = []
    for name in (
        "m5_dev",
        "m5_test",
        "m6_holdout",
        "m6_holdout_v2",
        "m7_holdout",
        "m7_holdout_v2",
        "m7_holdout_v3",
        "m7_holdout_v4",
        "m7_holdout_v5",
        "m7_holdout_v6",
        "m7_holdout_v7",
        "m7_holdout_v8",
        "m7_holdout_v9",
    ):
        previous.extend(json.loads((project / f"evals/cases/{name}.json").read_text()))
    if any(case["dataset_id"] == dataset for case in previous):
        raise ValueError("February dataset appeared in an inspected case set")
    if ref["families"] != list(USAGE_FAMILIES):
        raise ValueError("reference family selection drift")
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
        severity="medium",
        reference_key="",
    ):
        cases.append(
            {
                "id": case_id,
                "category": category,
                "template_family": f"m7j_{category}",
                "question": question,
                "dataset_id": dataset,
                "expected_status": status,
                "reference_file": "reports/M7-independent-reference-v10.json",
                "reference_key": reference_key,
                "expected_result": expected,
                "expected_tool": tool,
                "expected_tool_args": args,
                "result_path": [],
                "comparison": {"counts": "exact", "rates_absolute_tolerance": 1e-6},
                "required_caveats": caveats or ["observed_prefix_only"],
                "allowed_interpretations": ["descriptive_observed_prefix"],
                "severity": severity,
                "rubric_version": "m7-1.0",
                "split": "m7_holdout_v10",
            }
        )

    for name in USAGE_FAMILIES:
        add(
            f"m7j_usage_{_slug(name)}",
            "basic_calculation",
            f"In the observed February 1 slice, give the eligible game count, "
            f"known-opening denominator, and fraction for the exact source-tag "
            f"opening family {name}.",
            {
                "numerator": ref["opening_usage"][name],
                "denominator": ref["known_opening_games"],
                "value": _ratio(ref["opening_usage"][name], ref["known_opening_games"]),
            },
            "query_metric",
            {"metric_id": "opening_usage", "filters": {"family": name}},
            ["observed_prefix_only", "source_tags_only"],
            reference_key=f"opening_usage.{name}",
        )
    cohort = {
        "color": "white",
        "rating_min": 1400,
        "rating_max_exclusive": 1600,
        "base_seconds": 60,
        "increment_seconds": 0,
    }
    counts = ref["white_rating_1400_1599_60_plus_0"]
    for name in COHORT_FAMILIES:
        row = counts[name]
        add(
            f"m7j_white_{_slug(name)}_score",
            "filtering_perspective",
            f"Among White players rated 1400–1599 in 60+0 games on this February 1 "
            f"slice, give the observed eligible-game count and player score "
            f"rate for {name}.",
            {
                "eligible_player_games": row["games"],
                "score_rate": _ratio(row["wins"] + row["draws"] / 2, row["games"]),
            },
            "query_metric",
            {"metric_id": "opening_player_score", "filters": {"family": name, **cohort}},
            [
                "observed_prefix_only",
                "association_not_causation",
                "score_not_win_rate",
                "white_perspective",
            ],
            reference_key=f"white_rating_1400_1599_60_plus_0.{name}",
        )
    for first, second in (
        (COHORT_FAMILIES[0], COHORT_FAMILIES[1]),
        (COHORT_FAMILIES[2], COHORT_FAMILIES[3]),
    ):
        a, b = counts[first], counts[second]
        for measure in ("score", "win"):
            rate = (
                _ratio(a["wins"] + a["draws"] / 2, a["games"])
                - _ratio(b["wins"] + b["draws"] / 2, b["games"])
                if measure == "score"
                else _ratio(a["wins"], a["games"]) - _ratio(b["wins"], b["games"])
            )
            add(
                f"m7j_compare_{_slug(first)}_{_slug(second)}_{measure}",
                "multi_step",
                f"For observed February 1 games with White rated 1400–1599 at 60+0, "
                f"what is {first} minus {second} for White's {measure} rate? "
                "Use the same cohort for both openings.",
                {f"{measure}_rate_difference_first_minus_second": rate},
                "compare_openings",
                {"filters": {"families": [first, second], **cohort}},
                [
                    "observed_prefix_only",
                    "association_not_causation",
                    "score_not_win_rate",
                    "white_perspective",
                ],
                reference_key=f"cohort difference {first} minus {second}",
            )
    for bucket in CLOCK_BUCKETS:
        row = m3["clock_buckets"][bucket]
        caveats = [
            "observed_prefix_only",
            "source_evaluation_selection",
            "exploratory_proxy",
            "missing_evaluation_not_zero",
        ]
        add(
            f"m7j_clock_{bucket}_coverage",
            "missing_data",
            f"For sampled February 1 moves in clock bucket {bucket}, give the "
            "eligible-move count, comparable-evaluation count, and evaluation coverage.",
            {
                "eligible_moves": row["eligible"],
                "evaluable_moves": row["evaluable"],
                "evaluation_coverage": _ratio(row["evaluable"], row["eligible"]),
            },
            "query_metric",
            {"metric_id": "evaluation_coverage", "filters": {"bucket": bucket}},
            caveats,
            reference_key=f"M3.clock_buckets.{bucket}",
        )
        add(
            f"m7j_clock_{bucket}_proxy",
            "missing_data",
            f"For observed February 1 moves in clock bucket {bucket}, how many were "
            "evaluable and how many met the exploratory deterioration threshold? "
            "Include the proxy rate.",
            {
                "evaluable_moves": row["evaluable"],
                "proxy_errors": row["errors"],
                "error_proxy_rate": _ratio(row["errors"], row["evaluable"]),
            },
            "query_metric",
            {"metric_id": "clock_pressure_error_proxy", "filters": {"bucket": bucket}},
            caveats,
            reference_key=f"M3.clock_buckets.{bucket}",
        )
    boundaries = (
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
            "Give the exact full-February opening share from this one-day source slice.",
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
    )
    for name, question, status in boundaries:
        add(
            f"m7j_boundary_{name}",
            "ambiguity" if status == "needs_clarification" else "reliability_access",
            question,
            None,
            status=status,
            severity="high" if status == "unsupported" else "medium",
            reference_key="scope and access boundary",
        )
    if len(cases) != 50 or len({case["id"] for case in cases}) != 50:
        raise ValueError("M7 February v10 must have 50 unique cases")
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
    case_path = project / "evals/cases/m7_holdout_v10.json"
    write_json(case_path, cases)
    manifest = {
        "kind": "frozen M7 February v10 new-dataset opening holdout; no model response",
        "dataset_id": dataset,
        "cases": 50,
        "answerable": 41,
        "ambiguity_or_unsupported": 9,
        "high_severity": 5,
        "case_set_sha256": digest,
        "families": list(USAGE_FAMILIES),
        "new_dataset_id_disjoint_from_inspected_cases": True,
        "reference_files": [
            "reports/M3-independent-reference.json",
            "reports/M7-independent-reference-v10.json",
        ],
        "offline_oracle_passed": sum(score["passed"] for score in scores),
        "offline_oracle_failures": [score for score in scores if not score["passed"]],
        "no_model_response_scored": True,
    }
    write_json(project / "evals/cases/m7_holdout_v10_manifest.json", manifest)
    if manifest["offline_oracle_passed"] != 50:
        raise ValueError("M7 offline reference validation failed")
    return manifest


if __name__ == "__main__":
    print(json.dumps(build(), sort_keys=True))
