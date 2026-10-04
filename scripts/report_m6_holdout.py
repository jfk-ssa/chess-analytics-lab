"""Export the frozen M6 holdout run with every attempt and exact denominators."""

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

from analyst_m5.provider import price_usage
from chess_analytics.common import write_json
from scripts.report_m6_live import _model_text


def _selected_model_text(response: dict | None, selection: dict | None):
    if not response or not selection:
        return _model_text(response)
    chunks = [
        part.get("text")
        for item in response.get("output", [])
        for part in item.get("content", [])
        if part.get("type") == "output_text"
    ]
    index = selection.get("selected_chunk_index")
    return chunks[index] if type(index) is int and 0 <= index < len(chunks) else None


def build(project: Path, summary_path: Path, preflight_path: Path) -> dict:
    summary = json.loads(summary_path.read_text())
    preflight = json.loads(preflight_path.read_text())
    if preflight["kind"] not in {
        "m6_typed_planner_holdout_preflight_no_model_calls",
        "m7_typed_planner_holdout_preflight_no_model_calls",
    }:
        raise ValueError("not a frozen holdout preflight")
    cases = json.loads((project / preflight["case_file"]).read_text())
    digest = hashlib.sha256(
        json.dumps(sorted(cases, key=lambda c: c["id"]), sort_keys=True).encode()
    ).hexdigest()
    if digest != preflight["case_set_sha256"]:
        raise ValueError("holdout case hash changed")
    by_id = {case["id"]: case for case in cases}
    directory = Path(summary["records_dir"])
    attempts = []
    rates = {
        key: preflight[key]
        for key in (
            "input_usd_per_million",
            "output_usd_per_million",
            "cache_write_usd_per_million",
            "cached_input_usd_per_million",
        )
    }
    for index, path in enumerate(sorted(directory.glob("[0-9][0-9]-*.json"))):
        raw = json.loads(path.read_text())
        cell = preflight["cells"][index]
        if raw["cell"] != cell or raw["index"] != index:
            raise ValueError("attempt order or frozen request hash changed")
        case = by_id[cell["case_id"]]
        response = raw.get("provider_response") or (raw.get("answer") or {}).get(
            "provider", {}
        ).get("raw_response")
        usage = raw.get("provider_usage") or (response or {}).get("usage")
        cost, basis = price_usage(rates, usage) if usage else (None, "missing_usage")
        answer = raw.get("answer") or {}
        selection = answer.get("provider", {}).get("response_selection")
        attempts.append(
            {
                "case_id": case["id"],
                "category": case["category"],
                "severity": case["severity"],
                "expected_status": case["expected_status"],
                "condition": cell["condition"],
                "request_sha256": cell["request_sha256"],
                "status": raw["status"],
                "error_type": raw.get("error_type"),
                "error": raw.get("error"),
                "model_response_id": (response or {}).get("id"),
                "resolved_model": (response or {}).get("model"),
                "usage": usage,
                "gross_cost_usd": cost,
                "cost_basis": basis,
                "elapsed_seconds": raw["elapsed_seconds"],
                "model_text": _selected_model_text(response, selection),
                "response_selection": selection,
                "argument_repairs": answer.get("provider", {}).get("argument_repairs", []),
                "semantic_repairs": answer.get("provider", {}).get("semantic_repairs", []),
                "model_plan_before_semantic_repair": answer.get("provider", {}).get(
                    "model_plan_before_semantic_repair"
                ),
                "transport_retries": raw.get("transport_retries", []),
                "unknown_cost_reservation_usd": raw.get("unknown_cost_reservation_usd", 0),
                "tool_steps": answer.get("tool_steps"),
                "answer_status": answer.get("status"),
                "result": answer.get("result"),
                "evidence_ids": answer.get("evidence_ids"),
                "caveats": answer.get("caveats"),
                "score": raw.get("score"),
            }
        )
    if len(attempts) != summary["attempts"]:
        raise ValueError("attempt log count differs from summary")
    groups = defaultdict(list)
    for item in attempts:
        groups[item["condition"]].append(item)

    def tally(rows):
        return {
            "attempted": len(rows),
            "passed": sum(bool((r["score"] or {}).get("passed")) for r in rows),
        }

    answerable = [a for a in attempts if a["expected_status"] == "answered"]
    abstention = [a for a in attempts if a["expected_status"] != "answered"]
    return {
        "kind": "one_shot_frozen_family_split_holdout_actual_model_responses",
        "scorer": (
            "m7-1.0 frozen before model calls"
            if preflight["kind"].startswith("m7_")
            else "m6-2.1 frozen before model calls"
        ),
        "preflight_sha256": hashlib.sha256(preflight_path.read_bytes()).hexdigest(),
        "case_set_sha256": digest,
        "model": preflight["model"],
        "attempted": len(attempts),
        "planned": preflight["attempts_planned"],
        "completed": sum(a["status"] == "completed" for a in attempts),
        "answerable": tally(answerable),
        "ambiguity_or_unsupported": tally(abstention),
        "high_severity": tally([a for a in attempts if a["severity"] == "high"]),
        "by_condition": {name: tally(rows) for name, rows in sorted(groups.items())},
        "by_category": {
            name: tally([a for a in attempts if a["category"] == name])
            for name in sorted({a["category"] for a in attempts})
        },
        "known_gross_cost_usd": sum(a["gross_cost_usd"] or 0 for a in attempts),
        "unknown_cost_reservations_usd": summary.get("unknown_cost_reservations_usd", 0),
        "gross_cost_accounted_usd": summary.get(
            "gross_cost_accounted_usd", summary["known_gross_cost_usd"]
        ),
        "cost_known_for_every_attempt": all(a["gross_cost_usd"] is not None for a in attempts),
        "max_run_usd": preflight["max_run_usd"],
        "one_shot_no_repeatability_claim": True,
        "attempts": attempts,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = build(args.project, args.summary, args.preflight)
    write_json(args.out, report)
    print(
        json.dumps({key: report[key] for key in ("attempted", "completed", "known_gross_cost_usd")})
    )


if __name__ == "__main__":
    main()
