"""Cross-check M4 figures against the independent M3 raw-PGN reference."""

import json
from pathlib import Path

from chess_analytics.common import write_json

PROJECT = Path(__file__).resolve().parents[1]


def check(project=PROJECT):
    figures = json.loads((project / "reports/M4-figures.json").read_text())
    reference = json.loads((project / "reports/M3-independent-reference.json").read_text())
    assert figures["analytical_id"] == figures["opening"]["analytical_id"]
    assert figures["analytical_id"] == figures["clock"]["analytical_id"]
    assert figures["coverage"]["source_counts"]["accepted"] == reference["accepted_games"]
    assert figures["coverage"]["selection"]["selected_games"] == reference["selected_games"]
    for family, result in figures["opening"]["families"].items():
        cohort = reference["opening_player_cohorts"][f"{family}|black|rating_1400_1599|60+0"]
        raw = result["raw"]
        assert (raw["wins"], raw["draws"], raw["losses"]) == (
            cohort["wins"],
            cohort["draws"],
            cohort["losses"],
        )
        assert raw["eligible_player_games"] == cohort["games"]
        assert raw["score_rate"] == (cohort["wins"] + 0.5 * cohort["draws"]) / cohort["games"]
        assert result["bootstrap_valid_repetitions"] == 400
    for bucket in figures["clock"]["buckets"]:
        row = reference["clock_buckets"][bucket["bucket"]]
        assert (
            bucket["eligible_moves"],
            bucket["evaluable_moves"],
            bucket["proxy_errors"],
            bucket["mate_transition_moves"],
        ) == (row["eligible"], row["evaluable"], row["errors"], row["mate"])
        assert bucket["evaluation_coverage"] == row["evaluable"] / row["eligible"]
        assert bucket["error_proxy_rate"] == row["errors"] / row["evaluable"]
    result = {
        "kind": "independent reference comparison; no model response",
        "status": "passed",
        "analytical_id": figures["analytical_id"],
        "opening_cohorts_checked": 2,
        "clock_buckets_checked": 4,
        "memo_count": 2,
    }
    write_json(project / "reports/M4-reference-check.json", result)
    return result


if __name__ == "__main__":
    print(json.dumps(check(), indent=2))
