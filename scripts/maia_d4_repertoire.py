"""Print the held-out corpus inventory and Maia's replies to 1.d4.

Importing this file does not load weights and does not download anything.
"""

import json
from pathlib import Path

from chess_analytics.analyst.maia_trust import calibration_report, d4_repertoire
from chess_analytics.common import read_json


def main(project: Path | None = None) -> int:
    root = (project or Path.cwd()).resolve()
    report = calibration_report(read_json(root / "reports/opening-corpus.json"))
    view = d4_repertoire(root)
    print(json.dumps({"holdout": report, "repertoire": view}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
