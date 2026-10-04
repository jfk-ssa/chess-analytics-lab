"""Freeze 50 independently referenced M7 v2 cases before any model response."""

import hashlib
import json
from pathlib import Path

from analyst_m5.core import execute_plan
from analyst_m5.evaluation import score_case_m7
from chess_analytics.common import write_json
from scripts.reference_m7_holdout_v2 import COHORT_FAMILIES, USAGE_FAMILIES

PROJECT = Path(__file__).resolve().parents[1]
CLOCK_BUCKETS = ("under_10", "10_to_29", "30_to_59", "60_plus")


def _ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def _slug(value):
    return value.lower().replace("'", "").replace(" ", "_").replace("-", "_")


def build(project: Path = PROJECT) -> dict:
    m3 = json.loads((project / "reports/M3-independent-reference.json").read_text())
    ref = json.loads((project / "reports/M7-independent-reference-v2.json").read_text())
    dataset = ref["dataset_id"]
    if (
        dataset
        != json.loads((project / "reports/M3-analytical-manifest.json").read_text())[
            "analytical_id"
        ]
    ):
        raise ValueError("reference dataset drift")
    previous = []
    for name in ("m5_dev", "m5_test", "m6_holdout", "m6_holdout_v2", "m7_holdout"):
        previous.extend(json.loads((project / f"evals/cases/{name}.json").read_text()))
    old_families = set()
    for case in previous:
        filters = (case.get("expected_tool_args") or {}).get("filters") or {}
        old_families.update(
            [filters["family"]] if "family" in filters else filters.get("families", [])
        )
    if set(USAGE_FAMILIES) & old_families:
        raise ValueError("M7 opening family appeared in an inspected case set")
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
                "template_family": f"m7b_{category}",
                "question": question,
                "dataset_id": dataset,
                "expected_status": status,
                "reference_file": "reports/M7-independent-reference-v2.json",
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
                "split": "m7_holdout_v2",
            }
        )

    for name in USAGE_FAMILIES:
        add(
            f"m7b_usage_{_slug(name)}",
            "basic_calculation",
            f"Within the bounded archive extract, among eligible tagged games, "
            f"what fraction has the full {name} opening family?",
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
            f"m7b_white_{_slug(name)}_score",
            "filtering_perspective",
            f"For the observed White 1400–1599 cohort at 60+0, report the player "
            f"score rate for {name}?",
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
                f"m7b_compare_{_slug(first)}_{_slug(second)}_{measure}",
                "multi_step",
                f"For White 1400–1599 in exact 60+0, compare {first} with "
                f"{second}. What is the first-minus-second {measure} rate difference?",
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
            f"m7b_clock_{bucket}_coverage",
            "missing_data",
            f"Within {bucket} sampled positions, give the count of eligible moves, "
            "moves with comparable evaluations, and evaluation coverage.",
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
            f"m7b_clock_{bucket}_proxy",
            "missing_data",
            f"For sampled {bucket} moves with usable before/after evaluations, "
            "how many meet the exploratory deterioration threshold and what is the rate?",
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
    )
    for name, question, status in boundaries:
        add(
            f"m7b_boundary_{name}",
            "ambiguity" if status == "needs_clarification" else "reliability_access",
            question,
            None,
            status=status,
            severity="high" if status == "unsupported" else "medium",
            reference_key="scope and access boundary",
        )
    if len(cases) != 50 or len({case["id"] for case in cases}) != 50:
        raise ValueError("M7 v2 must have 50 unique cases")
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
    case_path = project / "evals/cases/m7_holdout_v2.json"
    write_json(case_path, cases)
    manifest = {
        "kind": "frozen M7 v2 family-disjoint opening holdout; no model response",
        "dataset_id": dataset,
        "cases": 50,
        "answerable": 41,
        "ambiguity_or_unsupported": 9,
        "high_severity": 5,
        "case_set_sha256": digest,
        "families_not_in_inspected_cases": list(USAGE_FAMILIES),
        "reference_files": [
            "reports/M3-independent-reference.json",
            "reports/M7-independent-reference-v2.json",
        ],
        "offline_oracle_passed": sum(score["passed"] for score in scores),
        "offline_oracle_failures": [score for score in scores if not score["passed"]],
        "no_model_response_scored": True,
    }
    write_json(project / "evals/cases/m7_holdout_v2_manifest.json", manifest)
    if manifest["offline_oracle_passed"] != 50:
        raise ValueError("M7 offline reference validation failed")
    return manifest


if __name__ == "__main__":
    print(json.dumps(build(), sort_keys=True))
