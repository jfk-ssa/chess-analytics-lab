"""Freeze 12 M3 development references; this does not evaluate model answers."""

import json
from pathlib import Path

from chess_analytics.common import write_json

PROJECT = Path(__file__).resolve().parents[1]


def ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def build(project=PROJECT):
    reference = json.loads((project / "reports/M3-independent-reference.json").read_text())
    manifest = json.loads((project / "reports/M3-analytical-manifest.json").read_text())
    dataset = manifest["analytical_id"]
    cohorts = reference["opening_player_cohorts"]
    sic_black = cohorts["Sicilian Defense|black|rating_1400_1599|60+0"]
    french_black = cohorts["French Defense|black|rating_1400_1599|60+0"]
    sic_white = cohorts["Sicilian Defense|white|rating_1400_1599|60+0"]
    under = reference["clock_buckets"]["under_10"]
    sixty = reference["clock_buckets"]["60_plus"]
    cases = [
        (
            "prefix_draw_rate",
            "basic_calculation",
            "What fraction of eligible games in this observed prefix were draws?",
            {
                "numerator": reference["drawn_eligible_games"],
                "denominator": reference["eligible_games"],
                "value": ratio(reference["drawn_eligible_games"], reference["eligible_games"]),
            },
            ["observed_prefix_only"],
            "drawn_eligible_games / eligible_games",
        ),
        (
            "sicilian_usage",
            "basic_calculation",
            "What share of known-opening eligible games had a Sicilian Defense tag?",
            {
                "numerator": reference["opening_families"]["Sicilian Defense"],
                "denominator": reference["known_opening_games"],
                "value": ratio(
                    reference["opening_families"]["Sicilian Defense"],
                    reference["known_opening_games"],
                ),
            },
            ["observed_prefix_only", "source_tags_only"],
            "opening_families.Sicilian Defense",
        ),
        (
            "french_usage",
            "basic_calculation",
            "What share of known-opening eligible games had a French Defense tag?",
            {
                "numerator": reference["opening_families"]["French Defense"],
                "denominator": reference["known_opening_games"],
                "value": ratio(
                    reference["opening_families"]["French Defense"],
                    reference["known_opening_games"],
                ),
            },
            ["observed_prefix_only", "source_tags_only"],
            "opening_families.French Defense",
        ),
        (
            "black_sicilian_win",
            "filtering_perspective",
            "For Black rated 1400–1599 at 60+0, what was the Sicilian win rate?",
            {
                "wins": sic_black["wins"],
                "games": sic_black["games"],
                "value": ratio(sic_black["wins"], sic_black["games"]),
            },
            ["observed_prefix_only", "association_not_causation"],
            "opening_player_cohorts.Sicilian Defense|black|rating_1400_1599|60+0",
        ),
        (
            "black_sicilian_score",
            "filtering_perspective",
            "For that Black Sicilian cohort, what was score rate, counting draws as half?",
            {
                "wins": sic_black["wins"],
                "draws": sic_black["draws"],
                "games": sic_black["games"],
                "value": ratio(sic_black["wins"] + 0.5 * sic_black["draws"], sic_black["games"]),
            },
            ["observed_prefix_only", "score_not_win_rate"],
            "opening_player_cohorts.Sicilian Defense|black|rating_1400_1599|60+0",
        ),
        (
            "black_french_score",
            "filtering_perspective",
            "For Black rated 1400–1599 at 60+0, what was French Defense score rate?",
            {
                "wins": french_black["wins"],
                "draws": french_black["draws"],
                "games": french_black["games"],
                "value": ratio(
                    french_black["wins"] + 0.5 * french_black["draws"], french_black["games"]
                ),
            },
            ["observed_prefix_only", "association_not_causation"],
            "opening_player_cohorts.French Defense|black|rating_1400_1599|60+0",
        ),
        (
            "white_sicilian_score",
            "filtering_perspective",
            "For White rated 1400–1599 at 60+0, what was Sicilian score rate?",
            {
                "wins": sic_white["wins"],
                "draws": sic_white["draws"],
                "games": sic_white["games"],
                "value": ratio(sic_white["wins"] + 0.5 * sic_white["draws"], sic_white["games"]),
            },
            ["observed_prefix_only", "white_perspective"],
            "opening_player_cohorts.Sicilian Defense|white|rating_1400_1599|60+0",
        ),
        (
            "under10_proxy",
            "missing_data",
            "Among evaluable sampled zero-increment moves starting under 10 seconds, "
            "what fraction met the 200 cp error proxy?",
            {
                "errors": under["errors"],
                "evaluable": under["evaluable"],
                "value": ratio(under["errors"], under["evaluable"]),
            },
            ["observed_prefix_only", "source_evaluation_selection", "exploratory_proxy"],
            "clock_buckets.under_10",
        ),
        (
            "under10_coverage",
            "missing_data",
            "What fraction of eligible under-10-second sampled moves had comparable "
            "source centipawn evaluations?",
            {
                "evaluable": under["evaluable"],
                "eligible": under["eligible"],
                "value": ratio(under["evaluable"], under["eligible"]),
            },
            ["missing_evaluation_not_zero", "observed_prefix_only"],
            "clock_buckets.under_10",
        ),
        (
            "sixtyplus_proxy",
            "missing_data",
            "What was the exploratory error-proxy rate for evaluable sampled moves "
            "starting at 60 seconds or more?",
            {
                "errors": sixty["errors"],
                "evaluable": sixty["evaluable"],
                "value": ratio(sixty["errors"], sixty["evaluable"]),
            },
            ["source_evaluation_selection", "exploratory_proxy"],
            "clock_buckets.60_plus",
        ),
    ]
    output = []
    for case_id, category, question, expected, caveats, reference_key in cases:
        output.append(
            {
                "id": case_id,
                "category": category,
                "question": question,
                "dataset_id": dataset,
                "expected_status": "answered",
                "reference_file": "reports/M3-independent-reference.json",
                "reference_key": reference_key,
                "expected_result": expected,
                "comparison": {"counts": "exact", "rates_absolute_tolerance": 0.000001},
                "required_caveats": caveats,
                "allowed_interpretations": ["descriptive_observed_prefix"],
                "severity": "medium",
                "rubric_version": "dev-1.0",
                "split": "dev",
            }
        )
    output.extend(
        [
            {
                "id": "best_opening_unspecified",
                "category": "ambiguity",
                "question": "What is the best opening?",
                "dataset_id": dataset,
                "expected_status": "needs_clarification",
                "expected_result": None,
                "reference_file": "contracts/opening_player_score.json",
                "reference_key": "filters",
                "comparison": None,
                "required_caveats": ["color_rating_time_control_needed"],
                "allowed_interpretations": ["ask_for_cohort_and_metric"],
                "severity": "medium",
                "rubric_version": "dev-1.0",
                "split": "dev",
            },
            {
                "id": "clock_causality",
                "category": "unsupported_inference",
                "question": "Does being under ten seconds cause players to make more mistakes?",
                "dataset_id": dataset,
                "expected_status": "unsupported",
                "expected_result": None,
                "reference_file": "contracts/clock_pressure_error_proxy.json",
                "reference_key": "caveats",
                "comparison": None,
                "required_caveats": [
                    "association_not_causation",
                    "source_evaluation_selection",
                    "observed_prefix_only",
                ],
                "allowed_interpretations": ["describe_proxy_and_limit"],
                "severity": "high",
                "rubric_version": "dev-1.0",
                "split": "dev",
            },
        ]
    )
    if len(output) != 12 or len({case["id"] for case in output}) != 12:
        raise ValueError("development case set must contain 12 distinct cases")
    return output


if __name__ == "__main__":
    output = build()
    path = PROJECT / "evals/cases/dev/m3_cases.json"
    write_json(path, output)
    print(
        json.dumps(
            {
                "kind": "development reference construction; no model responses",
                "cases": len(output),
                "dataset_id": output[0]["dataset_id"],
            },
            indent=2,
        )
    )
