"""Single checked tool in a disposable, credential-free local process."""

import json
import sys
from pathlib import Path

from analyst_m5.tools import CheckedTools


def main():
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict) or set(request) != {"project", "tool", "args"}:
            raise ValueError("invalid worker request")
        project = Path(request["project"]).resolve()
        if not isinstance(request["tool"], str) or not isinstance(request["args"], dict):
            raise ValueError("invalid worker tool arguments")
        tools = CheckedTools(project)
        result = tools.execute(request["tool"], request["args"])
        print(json.dumps({"ok": True, "dataset_id": tools.dataset_id, "result": result}))
    except Exception as exc:
        print(json.dumps({"ok": False, "error_type": type(exc).__name__, "error": str(exc)}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
