import json
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

import analytics_m4.analysis as analysis
from chess_analytics.common import write_json

project = Path.cwd()
original = analysis.clock_analysis


def empty_bucket(*args, **kwargs):
    result = original(*args, **kwargs)
    result["buckets"][0].update(
        eligible_moves=0,
        evaluable_moves=0,
        proxy_errors=0,
        error_proxy_rate=None,
        evaluation_coverage=None,
    )
    return result


with patch.object(analysis, "clock_analysis", empty_bucket):
    app = AppTest.from_file(str(project / "analytics_m4/dashboard.py"), default_timeout=30).run()
    app.sidebar.radio[0].set_value("Clock pressure").run()
    errors = [x.message for x in app.exception]
write_json(
    project / "work/repository-review/ui-probe.json",
    {"kind": "AppTest with injected valid empty clock bucket", "exceptions": errors},
)
print(json.dumps(errors))
