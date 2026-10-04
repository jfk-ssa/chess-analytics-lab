"""Frozen, budgeted M6 development smoke; never an untouched holdout claim."""

import argparse
import hashlib
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from analyst_m5.evaluation import score_case
from analyst_m5.provider import (
    PERSONAL_KEY_ENV,
    _default_transport,
    live_answer,
    quote_request,
    validate_personal_config,
)
from chess_analytics.common import write_json

PILOT_IDS = (
    "usage_sicilian_defense",
    "sample_count",
    "black_sicilian_score",
    "black_opening_score_difference",
    "best_opening",
    "best_for_me",
    "proxy_under_10",
    "proxy_60_plus",
    "causal_clock",
    "monthly_extrapolation",
    "player_personality",
    "read_private_file",
)
CONDITIONS = ("schema_only", "semantic_context")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(project: Path, config_path: Path) -> dict:
    """Quote all cells and freeze code/data/question inputs without a key."""
    config = validate_personal_config(json.loads(config_path.read_text()))
    manifest = json.loads((project / "evals/cases/m5_manifest.json").read_text())
    cases = json.loads((project / "evals/cases/m5_dev.json").read_text())
    test_cases = json.loads((project / "evals/cases/m5_test.json").read_text())
    case_digest = hashlib.sha256(
        json.dumps(sorted(cases + test_cases, key=lambda case: case["id"]), sort_keys=True).encode()
    ).hexdigest()
    if case_digest != manifest["case_set_sha256"]:
        raise ValueError("case set hash changed")
    selected = [case for case in cases if case["id"] in PILOT_IDS]
    if len(selected) != len(PILOT_IDS) or {c["id"] for c in selected} != set(PILOT_IDS):
        raise ValueError("pilot case set changed")
    cells = []
    for case in selected:
        for condition in CONDITIONS:
            quote = quote_request(project, case["question"], config, condition)
            cells.append(
                {
                    "case_id": case["id"],
                    "condition": condition,
                    "request_sha256": quote["request_sha256"],
                    "reserved_cost_usd": quote["reserved_cost_usd"],
                }
            )
    upper_bound = sum(cell["reserved_cost_usd"] for cell in cells)
    frozen_files = [
        "analyst_m5/provider.py",
        "analyst_m5/core.py",
        "analyst_m5/tools.py",
        "analyst_m5/tool_worker.py",
        "analyst_m5/evaluation.py",
        "analyst_m5/experiment.py",
        "analytics_m3/metrics.py",
        "analytics_m4/analysis.py",
        "evals/cases/m5_dev.json",
        "evals/cases/m5_test.json",
        "evals/cases/m5_manifest.json",
        "docs/METRICS.md",
        "uv.lock",
    ]
    frozen_files.extend(
        str(path.relative_to(project)) for path in sorted((project / "contracts").glob("*.json"))
    )
    return {
        "kind": "m6_typed_planner_development_pilot_preflight_no_model_calls",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "dataset_id": manifest["dataset_id"],
        "case_set_sha256": manifest["case_set_sha256"],
        "selection": "12 inspected development cases; not untouched holdout",
        "conditions": list(CONDITIONS),
        "comparison": (
            "typed planner with versus without governed metric definitions; not SQL baseline"
        ),
        "model": config["model"],
        "max_output_tokens": config["max_output_tokens"],
        "input_usd_per_million": config["input_usd_per_million"],
        "output_usd_per_million": config["output_usd_per_million"],
        "max_run_usd": config["max_run_usd"],
        "attempts_planned": len(cells),
        "conservative_total_usd": upper_bound,
        "fits_cap": upper_bound <= config["max_run_usd"],
        "frozen_file_sha256": {name: _sha(project / name) for name in frozen_files},
        "cells": cells,
    }


def run(project: Path, config_path: Path, preflight_path: Path, *, transport=None) -> dict:
    """One attempt per frozen cell, reserving the whole run before transport."""
    preflight = json.loads(preflight_path.read_text())
    current = prepare(project, config_path)
    frozen_keys = (
        "dataset_id",
        "case_set_sha256",
        "conditions",
        "model",
        "max_output_tokens",
        "input_usd_per_million",
        "output_usd_per_million",
        "max_run_usd",
        "attempts_planned",
        "conservative_total_usd",
        "frozen_file_sha256",
        "cells",
    )
    if any(preflight.get(key) != current[key] for key in frozen_keys):
        raise ValueError("frozen experiment preflight drifted")
    if not current["fits_cap"]:
        raise ValueError("whole experiment exceeds explicit run spending cap")
    if not os.environ.get(PERSONAL_KEY_ENV):
        raise ValueError("explicit personal API key is absent")
    cases = {c["id"]: c for c in json.loads((project / "evals/cases/m5_dev.json").read_text())}
    experiment_id = uuid.uuid4().hex
    directory = project / "data/analyst_attempts" / experiment_id
    directory.mkdir(parents=True, exist_ok=False)
    reserved = 0.0
    outcomes = []
    for index, cell in enumerate(current["cells"]):
        case = cases[cell["case_id"]]
        reserved += cell["reserved_cost_usd"]
        if reserved > current["max_run_usd"] + 1e-12:
            raise ValueError("whole-run reservation exceeded cap")
        captured = {}

        def capture(body, key, captured=captured):
            captured["response"] = (transport or _default_transport)(body, key)
            return captured["response"]

        started = time.monotonic()
        record = {"index": index, "cell": cell, "kind": "live_provider_attempt"}
        try:
            answer = live_answer(
                project,
                case["question"],
                config_path,
                transport=capture,
                condition=cell["condition"],
                remaining_usd=current["max_run_usd"] - reserved + cell["reserved_cost_usd"],
            )
            record.update(status="completed", answer=answer, score=score_case(case, answer))
        except Exception as exc:
            key = os.environ.get(PERSONAL_KEY_ENV)
            message = str(exc).replace(key, "[redacted]") if key else str(exc)
            record.update(
                status="failed",
                error_type=type(exc).__name__,
                error=message,
                provider_response=captured.get("response"),
            )
        record["elapsed_seconds"] = time.monotonic() - started
        write_json(directory / f"{index:02d}-{cell['case_id']}-{cell['condition']}.json", record)
        outcomes.append(record)
        # A failed/unknown-cost request may have been billed. No retry or later cell.
        if record["status"] == "failed":
            break
    categories = {}
    pairs = {}
    for row in outcomes:
        case = cases[row["cell"]["case_id"]]
        category = case["category"]
        entry = categories.setdefault(category, {"attempted": 0, "completed": 0, "correct": 0})
        entry["attempted"] += 1
        entry["completed"] += row["status"] == "completed"
        entry["correct"] += bool(row.get("score", {}).get("passed"))
        pairs.setdefault(case["id"], {})[row["cell"]["condition"]] = {
            "status": row["status"],
            "correct": row.get("score", {}).get("passed"),
        }
    summary = {
        "kind": "live_development_pilot_if_attempts_nonzero",
        "experiment_id": experiment_id,
        "attempts": len(outcomes),
        "planned": len(current["cells"]),
        "completed": sum(row["status"] == "completed" for row in outcomes),
        "failed": sum(row["status"] == "failed" for row in outcomes),
        "scored_correct": sum(row.get("score", {}).get("passed", False) for row in outcomes),
        "reserved_usd": reserved,
        "known_gross_cost_usd": sum(
            row.get("answer", {}).get("provider", {}).get("gross_cost_usd", 0) for row in outcomes
        ),
        "cost_complete": all(row["status"] == "completed" for row in outcomes),
        "categories": categories,
        "paired_by_case": pairs,
        "one_shot_no_repeatability_claim": True,
        "records_dir": str(directory),
    }
    write_json(directory / "summary.json", summary)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("prepare", "run"))
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--preflight", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.mode == "prepare":
        result = prepare(args.project, args.config)
        write_json(args.preflight, result)
    else:
        result = run(args.project, args.config, args.preflight)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
