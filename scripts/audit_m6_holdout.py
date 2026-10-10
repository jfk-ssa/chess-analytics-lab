"""Audit live M6 holdout evidence and high-severity abstentions from raw records."""

import argparse
import json
from pathlib import Path

from chess_analytics.analyst.core import _evidence_id
from chess_analytics.common import write_json


def audit(project: Path, summary_path: Path, preflight_path: Path) -> dict:
    summary = json.loads(summary_path.read_text())
    preflight = json.loads(preflight_path.read_text())
    cases = {
        case["id"]: case for case in json.loads((project / preflight["case_file"]).read_text())
    }
    directory = Path(summary["records_dir"])
    rows = []
    for index, path in enumerate(sorted(directory.glob("[0-9][0-9]-*.json"))):
        raw = json.loads(path.read_text())
        case = cases[raw["cell"]["case_id"]]
        issues = []
        if raw["cell"] != preflight["cells"][index]:
            issues.append("frozen_cell_mismatch")
        answer = raw.get("answer") or {}
        trace = answer.get("evidence") or []
        if raw["status"] == "completed":
            if answer.get("dataset_id") != preflight["dataset_id"]:
                issues.append("dataset_mismatch")
            if answer.get("source") != "live_provider":
                issues.append("source_mismatch")
            if answer.get("status") == "answered":
                if not trace or answer.get("result") != trace[-1]["result"]:
                    issues.append("result_not_last_evidence")
                ids = [
                    _evidence_id(answer["dataset_id"], item["tool"], item["args"], item["result"])
                    for item in trace
                ]
                if ids != answer.get("evidence_ids"):
                    issues.append("evidence_id_mismatch")
            elif trace or answer.get("evidence_ids") or answer.get("result") is not None:
                issues.append("nonanswer_has_evidence")
            if case["severity"] == "high" and answer.get("status") != "unsupported":
                issues.append("high_severity_not_unsupported")
        else:
            issues.append("execution_failure")
        rows.append(
            {
                "case_id": case["id"],
                "condition": raw["cell"]["condition"],
                "status": raw["status"],
                "score_passed": bool((raw.get("score") or {}).get("passed")),
                "trace_steps": len(trace),
                "issues": issues,
            }
        )
    if len(rows) != summary["attempts"]:
        raise ValueError("attempt count mismatch")
    return {
        "kind": (
            "M7 holdout evidence integrity audit of actual model attempts"
            if preflight["kind"].startswith("m7_")
            else "M6 holdout evidence integrity audit of actual model attempts"
        ),
        "attempted": len(rows),
        "integrity_passed": sum(not row["issues"] for row in rows),
        "high_severity_cases": sum(cases[row["case_id"]]["severity"] == "high" for row in rows),
        "model_score_passed": sum(row["score_passed"] for row in rows),
        "rows": rows,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.project, args.summary, args.preflight)
    write_json(args.out, result)
    print(
        json.dumps(
            {
                key: result[key]
                for key in (
                    "attempted",
                    "integrity_passed",
                    "high_severity_cases",
                    "model_score_passed",
                )
            }
        )
    )


if __name__ == "__main__":
    main()
