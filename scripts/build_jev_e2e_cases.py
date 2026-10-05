"""Freeze new M8 answer cases from raw-PGN references, without model output."""

# Keep authored question strings readable as one line for label review.
# ruff: noqa: E501

import hashlib
import json
from pathlib import Path

from chess_analytics.common import digest, write_json

ROOT = Path(__file__).resolve().parents[1]
COHORT = {
    "color": "white",
    "rating_min": 1400,
    "rating_max_exclusive": 1600,
    "base_seconds": 60,
    "increment_seconds": 0,
}


def make_cases(root: Path = ROOT) -> list[dict]:
    reference = json.loads((root / "reports/M8-e2e-independent-reference.json").read_text())
    project = root / "work/m7-december-project"
    clocks = json.loads((project / "reports/M3-independent-reference.json").read_text())
    manifest = json.loads((project / "reports/M3-analytical-manifest.json").read_text())
    source = json.loads((project / "reports/M3-independent-reference.json").read_text())
    if reference["dataset_id"] != manifest["analytical_id"]:
        raise ValueError("reference and analytical snapshot differ")
    cases = []

    def add(identifier, route, question, expected_result, tool, args, caveats=()):
        status = (
            "answered" if tool else ("needs_clarification" if route == "clarify" else "unsupported")
        )
        cases.append(
            {
                "id": identifier,
                "split": "test",
                "category": route,
                "route": route,
                "question": question,
                "dataset_id": reference["dataset_id"],
                "expected_status": status,
                "expected_result": expected_result,
                "expected_tool": tool,
                "expected_tool_args": args,
                "comparison": {"rates_absolute_tolerance": 1e-6},
                "required_caveats": ["observed_prefix_only", *caveats],
                "allowed_interpretations": ["descriptive_observed_prefix"],
                "reference_file": "reports/M8-e2e-independent-reference.json"
                if route.startswith("opening")
                else "work/m7-december-project/reports/M3-independent-reference.json",
            }
        )

    usage_questions = (
        (
            "Vienna Game",
            "In this observed December 1 prefix, how many known-opening games carry the exact Vienna Game tag, and what fraction is that?",
        ),
        (
            "Owen Defense",
            "Give the raw count, known-opening denominator, and share for the Owen Defense source tag in this slice.",
        ),
        (
            "Nimzowitsch Defense",
            "For Nimzowitsch Defense, report its eligible tagged-game count and proportion of known-opening games.",
        ),
        (
            "Bird Opening",
            "What fraction of the observed known-opening games were labeled Bird Opening? Include count and denominator.",
        ),
        (
            "Slav Defense",
            "Count Slav Defense games under the source opening tag and give their share of tagged eligible games.",
        ),
        (
            "Alekhine Defense",
            "Within the bounded prefix, how frequent is the exact Alekhine Defense opening family? Give both numbers.",
        ),
        (
            "Mieses Opening",
            "Show the Mieses Opening source-family numerator, denominator and observed percentage.",
        ),
        (
            "King's Indian Defense",
            "How many eligible known-opening games were King's Indian Defense, and what share is that?",
        ),
    )
    for index, (family, question) in enumerate(usage_questions, 1):
        numerator = reference["opening_usage"][family]
        denominator = reference["known_opening_games"]
        add(
            f"e2e_u{index:02}",
            "opening_usage",
            question,
            {"numerator": numerator, "denominator": denominator, "value": numerator / denominator},
            "query_metric",
            {"metric_id": "opening_usage", "filters": {"family": family}},
            ("source_tags_only",),
        )
    score_families = (
        (
            "Vienna Game",
            "For White rated 1400–1599 at 60+0, report Vienna Game wins, draws, losses and points per game in the observed prefix.",
        ),
        (
            "Owen Defense",
            "In Owen Defense games at 60+0, how did White players rated [1400,1600) score? Include record and score rate.",
        ),
        (
            "Nimzowitsch Defense",
            "Give White's result counts and score fraction for Nimzowitsch Defense, rating 1400 to under 1600, 60+0.",
        ),
        (
            "Bird Opening",
            "What share of available points did White earn in Bird Opening for 1400–1599 players at 60+0? Give the W-D-L totals.",
        ),
        (
            "Slav Defense",
            "For the exact Slav Defense family, White 1400–1599 and 60+0, provide W-D-L and score per game.",
        ),
        (
            "Alekhine Defense",
            "Report White's wins, draws, losses and score rate in Alekhine Defense games for 1400–1599 at 60+0.",
        ),
    )
    for index, (family, question) in enumerate(score_families, 1):
        counts = reference["white_rating_1400_1599_60_plus_0"][family]
        games = counts["games"]
        add(
            f"e2e_s{index:02}",
            "opening_score",
            question,
            {
                "wins": counts["wins"],
                "draws": counts["draws"],
                "losses": counts["losses"],
                "eligible_player_games": games,
                "score_rate": (counts["wins"] + counts["draws"] / 2) / games,
            },
            "query_metric",
            {"metric_id": "opening_player_score", "filters": {"family": family, **COHORT}},
            ("association_not_causation", "score_not_win_rate", "white_perspective"),
        )
    comparisons = (
        (
            "Vienna Game",
            "Owen Defense",
            "For White 1400–1599 at 60+0, what is the Vienna Game minus Owen Defense observed score-rate difference?",
        ),
        (
            "Nimzowitsch Defense",
            "Bird Opening",
            "Compare White's 1400–1599, 60+0 score rates: Nimzowitsch Defense first, Bird Opening second. Give the first-minus-second difference.",
        ),
    )
    for index, (first, second, question) in enumerate(comparisons, 1):
        a = reference["white_rating_1400_1599_60_plus_0"][first]
        b = reference["white_rating_1400_1599_60_plus_0"][second]
        value = (a["wins"] + a["draws"] / 2) / a["games"] - (b["wins"] + b["draws"] / 2) / b[
            "games"
        ]
        add(
            f"e2e_o{index:02}",
            "opening_compare",
            question,
            {"score_rate_difference_first_minus_second": value},
            "compare_openings",
            {"filters": {"families": [first, second], **COHORT}},
            ("association_not_causation", "score_not_win_rate", "white_perspective"),
        )
    clock_questions = (
        (
            "under_10",
            "For the under_10 pre-turn clock bucket, give the exploratory proxy numerator, evaluable denominator and rate.",
        ),
        (
            "10_to_29",
            "In the 10_to_29 pre-turn clock bucket, how many selected moves were eligible and evaluable, and how many crossed the proxy threshold?",
        ),
        (
            "30_to_59",
            "Report eligible and evaluable selected moves plus the 200-centipawn proxy rate for 30_to_59.",
        ),
        (
            "60_plus",
            "For 60_plus seconds remaining before a turn, show proxy errors, evaluable moves and the observed proxy fraction.",
        ),
    )
    for index, (bucket, question) in enumerate(clock_questions, 1):
        values = clocks["clock_buckets"][bucket]
        add(
            f"e2e_b{index:02}",
            "clock_bucket",
            question,
            {
                "eligible_moves": values["eligible"],
                "evaluable_moves": values["evaluable"],
                "proxy_errors": values["errors"],
                "error_proxy_rate": values["errors"] / values["evaluable"],
                "evaluation_coverage": values["evaluable"] / values["eligible"],
            },
            "query_metric",
            {"metric_id": "clock_pressure_error_proxy", "filters": {"bucket": bucket}},
            ("source_evaluation_selection", "exploratory_proxy", "missing_evaluation_not_zero"),
        )
    clock_comparisons = (
        (
            "under_10",
            "30_to_59",
            "Compare the observed error-proxy rates for under_10 versus 30_to_59; report first minus second, without a causal claim.",
        ),
        (
            "10_to_29",
            "60_plus",
            "How much does evaluation coverage differ between 10_to_29 and 60_plus, first minus second, in selected moves?",
        ),
    )
    for index, (first, second, question) in enumerate(clock_comparisons, 1):
        a = clocks["clock_buckets"][first]
        b = clocks["clock_buckets"][second]
        add(
            f"e2e_c{index:02}",
            "clock_compare",
            question,
            {
                "error_proxy_rate_difference_first_minus_second": a["errors"] / a["evaluable"]
                - b["errors"] / b["evaluable"],
                "evaluation_coverage_difference_first_minus_second": a["evaluable"] / a["eligible"]
                - b["evaluable"] / b["eligible"],
            },
            "compare_clock_buckets",
            {"first": first, "second": second},
            ("source_evaluation_selection", "exploratory_proxy", "missing_evaluation_not_zero"),
        )
    add(
        "e2e_v01",
        "coverage",
        "Which UTC dates are actually represented in this December archive prefix? Give the first and last observed dates.",
        {"observed_dates": {"first_utc_date": "2025-12-01", "last_utc_date": "2025-12-01"}},
        "get_dataset_coverage",
        {},
        (),
    )
    add(
        "e2e_v02",
        "coverage",
        "How many games were selected for move replay, including selected zero-ply games, in this observed slice?",
        {
            "selection": {
                "selected_games": manifest["selection"]["selected_games"],
                "selected_zero_ply_games": manifest["selection"]["selected_zero_ply_games"],
            }
        },
        "get_dataset_coverage",
        {},
        (),
    )
    boundaries = (
        ("clarify", "How often did the opening I meant appear in this prefix?"),
        ("clarify", "Compare my two chosen opening families for White 1400–1599 at 60+0."),
        ("clarify", "What was the proxy rate in that clock bucket?"),
        (
            "clarify",
            "Give the score rate for a defense at 60+0, but I have not said whose result or rating range.",
        ),
        (
            "unsupported",
            "Prove that playing Vienna Game caused White to win more in this observed data.",
        ),
        (
            "unsupported",
            "Predict the winner of a live game using only this first-day archive prefix.",
        ),
        (
            "unsupported",
            "Identify individual cheaters from the selected moves and sparse evaluations.",
        ),
        (
            "unsupported",
            "Recommend my best opening based on private games in my account that are not in this dataset.",
        ),
    )
    for index, (route, question) in enumerate(boundaries, 1):
        add(f"e2e_x{index:02}", route, question, None, None, None)
    if len(cases) != 32 or len({case["id"] for case in cases}) != 32:
        raise ValueError("expected exactly 32 distinct end-to-end cases")
    if source["known_opening_games"] != reference["known_opening_games"]:
        raise ValueError("raw-PGN references disagree on denominator")
    return cases


if __name__ == "__main__":
    cases = make_cases()
    destination = ROOT / "evals/cases/jev_e2e_v1.json"
    write_json(destination, cases)
    write_json(
        ROOT / "evals/cases/jev_e2e_v1_manifest.json",
        {
            "kind": "m8_fresh_answer_holdout_frozen_before_live_inference",
            "case_file": str(destination.relative_to(ROOT)),
            "case_sha256": digest(destination),
            "cases": len(cases),
            "reference_sha256": digest(ROOT / "reports/M8-e2e-independent-reference.json"),
            "clock_reference_sha256": digest(
                ROOT / "work/m7-december-project/reports/M3-independent-reference.json"
            ),
            "question_author": "project agent; semantic boundary labels not human-adjudicated",
            "numerical_reference": "independent raw-PGN header/comment tallies, not checked metric code",
            "gate_policy": "Jev Choice at probability >= 0.70 can emit only clarify or unsupported; every other decision falls through to unchanged checked analyst",
        },
    )
    print(
        json.dumps(
            {"cases": len(cases), "sha256": hashlib.sha256(destination.read_bytes()).hexdigest()}
        )
    )
