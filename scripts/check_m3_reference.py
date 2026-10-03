"""Assert the published M3 metric cells against an independent raw-PGN tally."""

import json
from pathlib import Path

from analytics_m3.metrics import opening_player_score
from chess_analytics.common import write_json
from chess_analytics.warehouse.snapshots import current, report

PROJECT = Path(__file__).resolve().parents[1]


def check(project=PROJECT):
    manifest = json.loads((project / "reports/M3-analytical-manifest.json").read_text())
    reference = json.loads((project / "reports/M3-independent-reference.json").read_text())
    summary = manifest["summary"]
    selection = manifest["selection"]
    snapshot = project / "data/analytical/published" / manifest["analytical_id"]
    source_report = report(project, current(project / "data", "analytical"))
    assert source_report["metric"]["numerator"] == reference["drawn_eligible_games"]
    assert source_report["metric"]["denominator"] == reference["eligible_games"]
    assert manifest["source_snapshot_id"] == reference["source_snapshot_id"]
    assert selection["selected_games"] == reference["selected_games"]
    assert selection["move_rows"] == reference["selected_moves"]
    assert summary["opening_coverage"]["eligible_games"] == reference["eligible_games"]
    assert summary["opening_coverage"]["known_opening_games"] == reference["known_opening_games"]
    assert (
        summary["opening_coverage"]["missing_source_opening"] == reference["missing_source_opening"]
    )
    for row in summary["top_opening_families"]:
        assert row["eligible_games"] == reference["opening_families"][row["family"]]
    for row in summary["clock_buckets"]:
        expected = reference["clock_buckets"][row["bucket"]]
        assert row["eligible_moves"] == expected["eligible"]
        assert row["evaluable_moves"] == expected["evaluable"]
        assert row["proxy_errors"] == expected["errors"]
        assert row["mate_transition_moves"] == expected["mate"]
    for family in ("Sicilian Defense", "French Defense"):
        for color in ("white", "black"):
            key = f"{family}|{color}|rating_1400_1599|60+0"
            expected = reference["opening_player_cohorts"][key]
            observed = opening_player_score(
                project,
                snapshot,
                family=family,
                color=color,
                rating_min=1400,
                rating_max_exclusive=1600,
                base_seconds=60,
                increment_seconds=0,
            )
            for field in ("wins", "draws", "losses"):
                assert observed[field] == expected[field]
            assert observed["eligible_player_games"] == expected["games"]
            assert observed["win_rate"] == expected["wins"] / expected["games"]
            assert (
                observed["score_rate"]
                == (expected["wins"] + 0.5 * expected["draws"]) / expected["games"]
            )
    return {
        "kind": "offline raw-PGN reference comparison; no model response",
        "status": "passed",
        "analytical_id": manifest["analytical_id"],
        "source_snapshot_id": manifest["source_snapshot_id"],
        "selected_games": selection["selected_games"],
        "selected_move_rows": selection["move_rows"],
        "opening_families_checked": len(summary["top_opening_families"]),
        "clock_buckets_checked": len(summary["clock_buckets"]),
        "opening_player_cohorts_checked": 4,
    }


if __name__ == "__main__":
    result = check()
    write_json(PROJECT / "reports/M3-reference-check.json", result)
    print(json.dumps(result, indent=2, sort_keys=True))
