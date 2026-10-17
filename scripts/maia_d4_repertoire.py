"""Print the held-out corpus inventory and Maia's replies to 1.d4.

Importing this file does not load weights and does not download anything.
`--eval` prints `score_maia_v1` and does not download weights either.
"""

import argparse
import json
from pathlib import Path

from chess_analytics.analyst.maia_trust import calibration_report, d4_repertoire, score_maia_v1
from chess_analytics.common import read_json


def main(argv: list[str] | None = None, project: Path | None = None) -> int:
    root = (project or Path.cwd()).resolve()
    parser = argparse.ArgumentParser(description="Print Maia replies to 1.d4, or score maia_v1.")
    parser.add_argument("--eval", action="store_true", help="Print score_maia_v1 for this project.")
    args = parser.parse_args(argv)
    if args.eval:
        print(json.dumps(score_maia_v1(root), indent=2, sort_keys=True))
        return 0
    report = calibration_report(read_json(root / "reports/opening-corpus.json"))
    view = d4_repertoire(root)
    print(json.dumps({"holdout": report, "repertoire": view}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
