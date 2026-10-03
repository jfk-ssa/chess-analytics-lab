"""Concise coverage artifact for the observed, bounded analytical prefix."""

import json
from pathlib import Path

from chess_analytics.common import write_json

PROJECT = Path(__file__).resolve().parents[1]


def coverage(project=PROJECT):
    def load(name):
        return json.loads((project / "reports" / name).read_text())

    acquisition = load("M3-acquisition.json")
    extraction = load("M3-extraction.json")
    source = load("M3-source-manifest.json")
    analytical = load("M3-analytical-manifest.json")
    return {
        "kind": "observed bounded-prefix coverage; not a monthly population estimate",
        "archive_period": acquisition["period"],
        "archive_listed_games": acquisition["archive_listed_games"],
        "archive_listed_bytes": acquisition["archive_listed_bytes"],
        "compressed_range": [acquisition["range_start"], acquisition["range_end_inclusive"]],
        "retained_compressed_bytes": acquisition["retained_compressed_bytes"],
        "compressed_prefix_sha256": acquisition["compressed_prefix_sha256"],
        "publisher_full_checksum_verified": False,
        "complete_pgns_extracted": extraction["complete_games"],
        "extracted_source_sha256": extraction["source_sha256"],
        "source_snapshot_id": source["snapshot_id"],
        "partial_archive": source["partial"],
        "observed_first_utc_date": source["coverage"]["first_utc_date"],
        "observed_last_utc_date": source["coverage"]["last_utc_date"],
        "source_counts": source["counts"],
        "source_exclusion_reasons": source["reasons"],
        "missing_fields": source["coverage"]["missing"],
        "analytical_id": analytical["analytical_id"],
        "selected_games": analytical["selection"]["selected_games"],
        "selected_zero_ply_games": analytical["selection"]["selected_zero_ply_games"],
        "sampled_move_coverage": analytical["summary"]["move_coverage"],
        "opening_coverage": analytical["summary"]["opening_coverage"],
        "clock_buckets": analytical["summary"]["clock_buckets"],
        "limits": [
            "First 100,000 complete games from a fixed 40 MB compressed prefix; "
            "observed dates only.",
            "The SHA256 identifies retained prefix bytes, not the publisher's full archive.",
            "Move games are selected by game-ID hash within the prefix, "
            "independent of annotations.",
            "Clock error proxy covers only zero-increment moves with prior clocks "
            "and comparable source cp evaluations.",
        ],
    }


if __name__ == "__main__":
    result = coverage()
    write_json(PROJECT / "reports/M3-coverage.json", result)
    print(
        json.dumps(
            {
                "analytical_id": result["analytical_id"],
                "accepted": result["source_counts"]["accepted"],
                "observed_dates": [
                    result["observed_first_utc_date"],
                    result["observed_last_utc_date"],
                ],
            },
            indent=2,
        )
    )
