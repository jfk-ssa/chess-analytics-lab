"""Rescore retained actual answers without changing their original run record."""

import argparse
import copy
import json
from pathlib import Path

from chess_analytics.jev_e2e import CASE_FILE, score_answer
from chess_analytics.routing_study import _sha, _write


def replay(repo: Path, attempt: Path) -> dict:
    original_file = attempt / "report.json"
    original = json.loads(original_file.read_text())
    if original["kind"] != "m8_paired_e2e_actual_attempt" or not original["complete"]:
        raise ValueError("complete actual attempt required")
    source = repo / CASE_FILE
    if _sha(source.read_bytes()) != original["case_sha256"]:
        raise ValueError("frozen case file differs from attempt")
    selected = {row["id"]: row for row in json.loads(source.read_text())}
    report = copy.deepcopy(original)
    report["kind"] = "m8_paired_e2e_offline_rescore"
    report["source_report_sha256"] = _sha(original_file.read_bytes())
    report["rescore_rubric"] = "m8-e2e-1.1"
    for phase in ("baseline", "gated"):
        for row in report["outcomes"][phase]:
            if not row["used_analyst"]:
                # The rubric change concerns extra checked evidence only.
                # Jev boundary answers have no evidence and retain their score.
                continue
            case = selected[row["id"]]
            record = json.loads((attempt / f"{phase}-{row['id']}.json").read_text())
            score = score_answer(case, record["answer"])
            row["passed"] = score["passed"]
            row["failures"] = score["failures"]
        rows = report["outcomes"][phase]
        gross = sum(sum(row["gross_cost_usd"].values()) for row in rows)
        passed = sum(row["passed"] for row in rows)
        report["scores"][phase] = {
            "passed": passed,
            "total": len(rows),
            "gross_usd": gross,
            "correct_answer_cost_usd": gross / passed if passed else None,
        }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--attempt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.resolve().is_relative_to(args.attempt.resolve()) or args.output.exists():
        parser.error("rescore output must be a fresh path outside the original attempt")
    result = replay(args.repo, args.attempt)
    _write(args.output, result)
    print(json.dumps({"kind": result["kind"], "scores": result["scores"]}, indent=2))


if __name__ == "__main__":
    main()
