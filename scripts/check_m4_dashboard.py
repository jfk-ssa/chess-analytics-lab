"""Exercise every local dashboard view with Streamlit's app test runtime."""

import json
from pathlib import Path

from streamlit.testing.v1 import AppTest

from chess_analytics.common import write_json

PROJECT = Path(__file__).resolve().parents[1]
VIEWS = (
    "Overview and coverage",
    "Opening comparisons",
    "Clock pressure",
    "Data quality",
    "AI analyst",
    "Evaluation results",
)


def check(project=PROJECT):
    app = AppTest.from_file(
        str(project / "src/chess_analytics/dashboard/dashboard.py"), default_timeout=30
    ).run()
    observations = []
    for view in VIEWS:
        if view != VIEWS[0]:
            app.sidebar.radio[0].set_value(view).run()
        if view == "AI analyst":
            app.button[0].click().run()
        errors = [element.message for element in app.exception]
        if view == "AI analyst" and not app.json:
            errors.append("replay action did not render an evidence record")
        observations.append({"view": view, "exceptions": errors})
    result = {
        "kind": "local Streamlit AppTest smoke; no hosted deployment",
        "status": "passed" if all(not item["exceptions"] for item in observations) else "failed",
        "analytical_id": json.loads((project / "reports/M4-figures.json").read_text())[
            "analytical_id"
        ],
        "replay_action_checked": True,
        "views": observations,
    }
    write_json(project / "reports/M4-dashboard-smoke.json", result)
    if result["status"] != "passed":
        raise AssertionError("dashboard view exception; see saved report")
    return result


if __name__ == "__main__":
    print(json.dumps(check(), indent=2))
