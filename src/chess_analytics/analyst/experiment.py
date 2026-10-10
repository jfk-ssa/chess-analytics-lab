"""Frozen, budgeted analyst runs; never an untouched holdout claim."""

import argparse
import json
import os
import time
import uuid
from pathlib import Path

from chess_analytics.analyst.evaluation import score_case_m6, score_case_m6_holdout, score_case_m7
from chess_analytics.analyst.preflight import (
    CONDITIONS,
    _load_named_key,
    _resolve_config,
    prepare,
)
from chess_analytics.analyst.provider import (
    KEY_ENV,
    _default_transport,
    live_answer,
    price_usage,
)
from chess_analytics.common import write_json


def run(
    project: Path,
    config_path: Path | None,
    preflight_path: Path,
    *,
    max_run_usd=None,
    env_file: Path | None = None,
    transport=None,
    holdout=False,
    holdout_version=1,
    conditions=None,
) -> dict:
    """One attempt per frozen cell, reserving the whole run before transport."""
    preflight = json.loads(preflight_path.read_text())
    config = _resolve_config(config_path, max_run_usd)
    current = prepare(
        project,
        config_path,
        max_run_usd=max_run_usd,
        holdout=holdout,
        holdout_version=holdout_version,
        conditions=conditions,
    )
    frozen_keys = (
        "dataset_id",
        "case_set_sha256",
        "selection",
        "case_file",
        "conditions",
        "model",
        "max_output_tokens",
        "input_usd_per_million",
        "output_usd_per_million",
        "cache_write_usd_per_million",
        "cached_input_usd_per_million",
        "max_run_usd",
        "price_source",
        "price_checked_utc_date",
        "attempts_planned",
        "max_transport_retries_per_run",
        "transport_retry_reservation_usd",
        "conservative_total_usd",
        "frozen_file_sha256",
        "cells",
    )
    if any(preflight.get(key) != current[key] for key in frozen_keys):
        raise ValueError("frozen experiment preflight drifted")
    if not current["fits_cap"]:
        raise ValueError("whole experiment exceeds explicit run spending cap")
    if env_file is not None:
        _load_named_key(env_file)
    if not os.environ.get(KEY_ENV):
        raise ValueError("explicit personal API key is absent")
    cases = {c["id"]: c for c in json.loads((project / current["case_file"]).read_text())}
    experiment_id = uuid.uuid4().hex
    directory = project / "data/analyst_attempts" / experiment_id
    directory.mkdir(parents=True, exist_ok=False)
    reserved = 0.0
    spent = 0.0
    unknown_reservations = 0.0
    transport_retries_used = 0
    outcomes = []
    for index, cell in enumerate(current["cells"]):
        case = cases[cell["case_id"]]
        reserved += cell["reserved_cost_usd"]
        if reserved > current["max_run_usd"] + 1e-12:
            raise ValueError("whole-run reservation exceeded cap")
        captured = {}

        def capture(body, key, captured=captured, cell=cell):
            nonlocal reserved, unknown_reservations, transport_retries_used
            try:
                captured["response"] = (transport or _default_transport)(body, key)
            except RuntimeError as exc:
                message = str(exc)
                retryable = message.startswith(
                    "provider HTTP 400: invalid_request_error: Invalid prompt"
                )
                if (
                    not retryable
                    or transport_retries_used >= current["max_transport_retries_per_run"]
                ):
                    raise
                extra = cell["reserved_cost_usd"]
                if reserved + extra > current["max_run_usd"] + 1e-12:
                    raise ValueError("transport retry reservation exceeds run cap") from exc
                captured["transport_retries"] = [
                    {
                        "error_type": type(exc).__name__,
                        "error": message.replace(key, "[redacted]"),
                        "reserved_cost_usd": extra,
                    }
                ]
                reserved += extra
                unknown_reservations += extra
                transport_retries_used += 1
                captured["response"] = (transport or _default_transport)(body, key)
            return captured["response"]

        started = time.monotonic()
        record = {"index": index, "cell": cell, "kind": "live_provider_attempt"}
        try:
            answer = live_answer(
                project,
                case["question"],
                config_path,
                config=config if config_path is None else None,
                transport=capture,
                condition=cell["condition"],
                remaining_usd=current["max_run_usd"] - reserved + cell["reserved_cost_usd"],
            )
            scorer = (
                (
                    score_case_m7
                    if holdout_version in {3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14}
                    else score_case_m6_holdout
                )
                if holdout
                else score_case_m6
            )
            record.update(status="completed", answer=answer, score=scorer(case, answer))
        except Exception as exc:
            key = os.environ.get(KEY_ENV)
            message = str(exc).replace(key, "[redacted]") if key else str(exc)
            record.update(
                status="failed",
                error_type=type(exc).__name__,
                error=message,
                provider_response=captured.get("response"),
            )
        record["elapsed_seconds"] = time.monotonic() - started
        record["transport_retries"] = captured.get("transport_retries", [])
        response = captured.get("response")
        usage = response.get("usage") if isinstance(response, dict) else None
        if usage is not None:
            try:
                cost, basis = price_usage(config, usage)
            except ValueError:
                cost = basis = None
        else:
            cost = basis = None
        if cost is not None:
            record["provider_usage"] = usage
            record["gross_cost_usd"] = cost
            record["cost_basis"] = basis
            spent += cost
            if (
                cost > cell["reserved_cost_usd"] + 1e-12
                or spent + unknown_reservations > current["max_run_usd"] + 1e-12
            ):
                record["budget_bound_exceeded"] = True
        elif holdout_version in {10, 11, 12, 13, 14}:
            unknown_reservations += cell["reserved_cost_usd"]
            record["unknown_cost_reservation_usd"] = cell["reserved_cost_usd"]
        write_json(directory / f"{index:02d}-{cell['case_id']}-{cell['condition']}.json", record)
        outcomes.append(record)
        # A failed/unknown-cost request may have been billed. No retry or later cell.
        if record["status"] == "failed" or record.get("budget_bound_exceeded"):
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
        "kind": (
            "live_holdout_if_attempts_nonzero"
            if holdout
            else "live_development_pilot_if_attempts_nonzero"
        ),
        "experiment_id": experiment_id,
        "attempts": len(outcomes),
        "planned": len(current["cells"]),
        "completed": sum(row["status"] == "completed" for row in outcomes),
        "failed": sum(row["status"] == "failed" for row in outcomes),
        "scored_correct": sum(row.get("score", {}).get("passed", False) for row in outcomes),
        "reserved_usd": reserved,
        "known_gross_cost_usd": sum(row.get("gross_cost_usd", 0) for row in outcomes),
        "unknown_cost_reservations_usd": unknown_reservations,
        "gross_cost_accounted_usd": spent + unknown_reservations,
        "transport_retries": transport_retries_used,
        "cost_complete": all("gross_cost_usd" in row for row in outcomes),
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
    config_group = parser.add_mutually_exclusive_group(required=True)
    config_group.add_argument("--config", type=Path)
    config_group.add_argument("--max-run-usd", type=float)
    parser.add_argument("--env-file", type=Path, help="run mode only; reads only the named key")
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--holdout", action="store_true", help="use frozen M6/M7 family split")
    parser.add_argument(
        "--holdout-version",
        type=int,
        choices=(1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14),
        default=1,
    )
    parser.add_argument("--condition", choices=CONDITIONS, action="append")
    args = parser.parse_args(argv)
    if args.mode == "prepare":
        if args.env_file is not None:
            parser.error("--env-file applies only to run mode")
        result = prepare(
            args.project,
            args.config,
            max_run_usd=args.max_run_usd,
            holdout=args.holdout,
            holdout_version=args.holdout_version,
            conditions=args.condition,
        )
        write_json(args.preflight, result)
    else:
        result = run(
            args.project,
            args.config,
            args.preflight,
            max_run_usd=args.max_run_usd,
            env_file=args.env_file,
            holdout=args.holdout,
            holdout_version=args.holdout_version,
            conditions=args.condition,
        )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
