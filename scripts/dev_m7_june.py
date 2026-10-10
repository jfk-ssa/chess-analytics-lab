"""Labeled June development smoke using already inspected July case templates."""

import argparse
import json
import os
from pathlib import Path

from analyst_m5.core import execute_plan
from analyst_m5.evaluation import score_case_m7
from analyst_m5.experiment import _load_named_key, _resolve_config
from analyst_m5.provider import KEY_ENV, _default_transport, live_answer, price_usage, quote_request
from chess_analytics.common import write_json
from chess_analytics.dashboard.analysis import current_snapshot

DEV_IDS = (
    "m7e_usage_scandinavian_defense",
    "m7e_usage_ruy_lopez",
    "m7e_clock_10_to_29_coverage",
    "m7e_clock_60_plus_proxy",
    "m7e_white_french_defense_score",
    "m7e_boundary_full_month",
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--prior-gross-usd", type=float, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise ValueError("development attempt file already exists")
    project = args.project
    dataset = current_snapshot(project).name
    config = _resolve_config(None, 0.5)
    prior = args.prior_gross_usd
    if not 0 <= prior < 0.5:
        raise ValueError("invalid prior gross")
    source_cases = json.loads((project / "evals/cases/m7_holdout_v5.json").read_text())
    by_id = {case["id"]: case for case in source_cases}
    cases = []
    for case_id in DEV_IDS:
        case = {**by_id[case_id]}
        case["question"] = case["question"].replace("July", "June")
        case["dataset_id"] = dataset
        plan = {
            "status": case["expected_status"],
            "interpretation": "descriptive_observed_prefix",
            "actions": (
                [{"tool": case["expected_tool"], "args": case["expected_tool_args"]}]
                if case["expected_status"] == "answered"
                else []
            ),
        }
        oracle = execute_plan(project, case["question"], plan, source="offline_oracle")
        case["expected_result"] = oracle["result"]
        if not score_case_m7(case, oracle)["passed"]:
            raise ValueError(f"offline development oracle failed: {case_id}")
        cases.append(case)
    quotes = [quote_request(project, case["question"], config) for case in cases]
    bound = sum(quote["reserved_cost_usd"] for quote in quotes)
    if prior + bound > 0.5:
        raise ValueError("development smoke exceeds cumulative cap")
    record = {
        "kind": "M7 June development smoke on inspected July templates; actual model attempts",
        "dataset_id": dataset,
        "prior_accounted_gross_usd": prior,
        "conservative_reservation_usd": bound,
        "cases": [],
    }
    write_json(args.out, record)
    _load_named_key(args.env_file)
    spent = 0.0
    for case, quote in zip(cases, quotes, strict=True):
        captured = {}

        def capture(body, key, captured=captured):
            captured["response"] = _default_transport(body, key)
            return captured["response"]

        row = {
            "case_id": case["id"],
            "question": case["question"],
            "request_sha256": quote["request_sha256"],
            "reserved_cost_usd": quote["reserved_cost_usd"],
        }
        try:
            answer = live_answer(
                project,
                case["question"],
                None,
                config=config,
                transport=capture,
                condition="semantic_context",
                remaining_usd=0.5 - prior - spent,
            )
            row["answer"] = answer
            row["score"] = score_case_m7(case, answer)
            row["status"] = "completed"
        except Exception as exc:
            key = os.environ.get(KEY_ENV)
            row["status"] = "failed"
            row["error_type"] = type(exc).__name__
            row["error"] = str(exc).replace(key, "[redacted]") if key else str(exc)
            row["provider_response"] = captured.get("response")
        usage = (captured.get("response") or {}).get("usage")
        if usage:
            cost, basis = price_usage(config, usage)
            row["gross_cost_usd"] = cost
            row["cost_basis"] = basis
            spent += cost
        else:
            row["gross_cost_usd"] = None
            spent += quote["reserved_cost_usd"]
        record["cases"].append(row)
        record["gross_accounted_this_smoke_usd"] = spent
        write_json(args.out, record)
        if row["status"] == "failed" or prior + spent > 0.5:
            break
    print(
        json.dumps(
            {
                "attempted": len(record["cases"]),
                "passed": sum(row.get("score", {}).get("passed", False) for row in record["cases"]),
                "gross_accounted_usd": spent,
            }
        )
    )


if __name__ == "__main__":
    main()
