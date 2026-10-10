"""Export a key-free, reproducible report from retained local M6 attempts."""

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path

from chess_analytics.analyst.provider import price_usage
from chess_analytics.common import write_json


def _model_text(response: dict | None) -> str | None:
    if not isinstance(response, dict):
        return None
    chunks = [
        part.get("text")
        for item in response.get("output", [])
        for part in item.get("content", [])
        if part.get("type") == "output_text"
    ]
    return chunks[0] if len(chunks) == 1 else None


def build(
    project: Path, summaries: list[Path], preflights: list[Path], user_cap_usd: float
) -> dict:
    if len(summaries) != len(preflights):
        raise ValueError("each run needs its frozen preflight")
    if user_cap_usd <= 0:
        raise ValueError("positive user cap required")
    cases = {
        case["id"]: case for case in json.loads((project / "evals/cases/m5_dev.json").read_text())
    }
    runs = []
    all_attempts = []
    for summary_path, preflight_path in zip(summaries, preflights, strict=True):
        summary = json.loads(summary_path.read_text())
        preflight = json.loads(preflight_path.read_text())
        directory = Path(summary["records_dir"])
        attempts = []
        for path in sorted(directory.glob("[0-9][0-9]-*.json")):
            raw = json.loads(path.read_text())
            case = cases[raw["cell"]["case_id"]]
            response = raw.get("provider_response") or raw.get("answer", {}).get(
                "provider", {}
            ).get("raw_response")
            usage = raw.get("provider_usage") or (response or {}).get("usage")
            rates = {
                "input_usd_per_million": preflight["input_usd_per_million"],
                "output_usd_per_million": preflight["output_usd_per_million"],
            }
            if preflight["model"] == "gpt-6-luna":
                rates["cache_write_usd_per_million"] = preflight.get(
                    "cache_write_usd_per_million", 0.125
                )
                rates["cached_input_usd_per_million"] = preflight.get(
                    "cached_input_usd_per_million", 0.01
                )
            cost, cost_basis = price_usage(rates, usage) if usage else (None, "missing_usage")
            answer = raw.get("answer") or {}
            attempt = {
                "case_id": case["id"],
                "category": case["category"],
                "expected_status": case["expected_status"],
                "condition": raw["cell"]["condition"],
                "request_sha256": raw["cell"]["request_sha256"],
                "status": raw["status"],
                "error_type": raw.get("error_type"),
                "error": raw.get("error"),
                "model_response_id": (response or {}).get("id"),
                "resolved_model": (response or {}).get("model"),
                "usage": usage,
                "previous_recorded_cost_usd": raw.get("gross_cost_usd"),
                "gross_cost_usd": cost,
                "cost_basis": cost_basis,
                "elapsed_seconds": raw["elapsed_seconds"],
                "model_text": _model_text(response),
                "answer_status": answer.get("status"),
                "result": answer.get("result"),
                "evidence_ids": answer.get("evidence_ids"),
                "caveats": answer.get("caveats"),
                "score": raw.get("score"),
            }
            attempts.append(attempt)
            all_attempts.append(attempt)
        if len(attempts) != summary["attempts"]:
            raise ValueError("attempt log count differs from summary")
        runs.append(
            {
                "experiment_id": summary["experiment_id"],
                "preflight": {
                    key: preflight[key]
                    for key in (
                        "dataset_id",
                        "case_set_sha256",
                        "model",
                        "max_run_usd",
                        "attempts_planned",
                        "conservative_total_usd",
                        "frozen_file_sha256",
                    )
                },
                "attempts": attempts,
            }
        )
    final = runs[-1]["attempts"]
    by_condition = {}
    for condition in ("schema_only", "semantic_context"):
        rows = [a for a in final if a["condition"] == condition]
        by_condition[condition] = {
            "attempted": len(rows),
            "passed": sum(bool((a.get("score") or {}).get("passed")) for a in rows),
            "gross_cost_usd": sum(a["gross_cost_usd"] or 0 for a in rows),
            "median_latency_seconds": statistics.median(a["elapsed_seconds"] for a in rows),
        }
    grouped = defaultdict(list)
    for attempt in final:
        grouped[attempt["category"]].append(attempt)
    categories = {
        category: {
            "attempted": len(rows),
            "passed": sum(bool((a.get("score") or {}).get("passed")) for a in rows),
        }
        for category, rows in sorted(grouped.items())
    }
    answerable = [a for a in final if a["expected_status"] == "answered"]
    non_answerable = [a for a in final if a["expected_status"] != "answered"]
    pairs = {}
    for case_id in sorted({a["case_id"] for a in final}):
        rows = [a for a in final if a["case_id"] == case_id]
        pairs[case_id] = {
            a["condition"]: {
                "passed": (a.get("score") or {}).get("passed", False),
                "failures": (a.get("score") or {}).get("failures", [a.get("error_type")]),
            }
            for a in rows
        }
    known_costs = [a["gross_cost_usd"] for a in all_attempts]
    return {
        "kind": "actual_model_development_pilot_not_untouched_holdout",
        "scorer": "frozen M5 deterministic scorer; manual inspection noted separately",
        "run_count": len(runs),
        "total_attempts": len(all_attempts),
        "known_gross_cost_usd": sum(cost or 0 for cost in known_costs),
        "cost_known_for_every_attempt": all(cost is not None for cost in known_costs),
        "user_cap_usd_across_runs": user_cap_usd,
        "final_pilot": {
            "attempted": len(final),
            "completed": sum(a["status"] == "completed" for a in final),
            "scored_passed": sum(bool((a.get("score") or {}).get("passed")) for a in final),
            "answerable": {
                "passed": sum(bool((a.get("score") or {}).get("passed")) for a in answerable),
                "total": len(answerable),
            },
            "ambiguity_or_unsupported": {
                "passed": sum(bool((a.get("score") or {}).get("passed")) for a in non_answerable),
                "total": len(non_answerable),
            },
            "by_condition": by_condition,
            "by_category": categories,
            "paired_by_case": pairs,
        },
        "manual_failure_review": {
            "reviewer": "coding-agent inspection of failed cells; not blinded human review",
            "equivalent_numerical_tools": (
                "proxy_under_10 schema-only and proxy_60_plus semantic-context used "
                "analyze_clock_pressure, which delegates to the expected checked metric; "
                "values matched, but the frozen scorer rejected tool identity"
            ),
            "multi_step": (
                "schema-only used shorthand opening names and returned zero denominators; "
                "semantic-context requested clarification instead of comparison"
            ),
            "safety_status": (
                "monthly extrapolation and private-file cases requested clarification "
                "instead of unsupported in both conditions; neither executed a tool "
                "or produced a fabricated value"
            ),
            "release_gate": "90% numerical and 90% ambiguity/unsupported targets not met",
        },
        "runs": runs,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--summaries", type=Path, nargs="+", required=True)
    parser.add_argument("--preflights", type=Path, nargs="+", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--user-cap-usd", type=float, required=True)
    args = parser.parse_args()
    report = build(args.project, args.summaries, args.preflights, args.user_cap_usd)
    write_json(args.out, report)
    print(json.dumps({key: report[key] for key in ("total_attempts", "known_gross_cost_usd")}))


if __name__ == "__main__":
    main()
