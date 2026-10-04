"""Record measured local depth costs and explicit deferral decisions."""

import json
import shutil
from pathlib import Path

from chess_analytics.common import write_json

PROJECT = Path(__file__).resolve().parents[1]


def build(project: Path = PROJECT) -> dict:
    coverage = json.loads((project / "reports/M3-coverage.json").read_text())
    manifest = json.loads((project / "reports/M3-source-manifest.json").read_text())
    analytical = project / "data/analytical"
    extracted = analytical / manifest["source_file"]
    prefix = analytical / "lichess-standard-rated-2026-08-prefix-40000000.zst"
    source_snapshot = project / "data/published" / coverage["source_snapshot_id"]

    def tree_bytes(path: Path) -> int:
        return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())

    return {
        "kind": "M7 bounded depth feasibility; measured local state, no new acquisition",
        "measured": {
            "retained_compressed_bytes": prefix.stat().st_size,
            "extracted_source_bytes": extracted.stat().st_size,
            "source_ingest_elapsed_seconds": manifest["elapsed_seconds"],
            "complete_pgns_extracted": coverage["complete_pgns_extracted"],
            "accepted_games": coverage["source_counts"]["accepted"],
            "observed_first_utc_date": coverage["observed_first_utc_date"],
            "observed_last_utc_date": coverage["observed_last_utc_date"],
            "source_snapshot_disk_bytes": tree_bytes(source_snapshot),
            "analytical_published_disk_bytes": tree_bytes(analytical / "published"),
            "analytical_staging_disk_bytes": tree_bytes(analytical / "staging"),
            "stockfish_on_path": shutil.which("stockfish") is not None,
        },
        "publisher_metadata": {
            "archive_listed_bytes": coverage["archive_listed_bytes"],
            "archive_listed_games": coverage["archive_listed_games"],
        },
        "decision": {
            "next_day_not_observed": True,
            "increase_byte_cap_alone_adds_no_games_with_current_100000_game_cap": True,
            "sequential_extension": (
                "defer pending a bounded date-targeted acquisition method; "
                "the archive prefix has no established seek index"
            ),
            "engine_enrichment": (
                "defer pending a fixed version/sample/budget and measured "
                "value test; no engine benchmark claimed"
            ),
            "provider_comparison": "defer while direct inference remains cents per evaluation",
        },
        "limits": [
            "Archive byte/game averages are not a measured per-day resource forecast.",
            "Staging disk includes retained failed and previous attempts.",
            "No new source day, engine analysis, or causal inference is claimed.",
        ],
    }


if __name__ == "__main__":
    result = build()
    write_json(PROJECT / "reports/M7-depth-feasibility.json", result)
    print(json.dumps(result["measured"], sort_keys=True))
