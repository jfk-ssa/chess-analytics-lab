"""Frozen, budgeted M6 development smoke; never an untouched holdout claim."""

import argparse
import hashlib
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from analyst_m5.evaluation import score_case_m6, score_case_m6_holdout, score_case_m7
from analyst_m5.provider import (
    KEY_ENV,
    _default_transport,
    live_answer,
    price_usage,
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
DEFAULT_MODEL = "gpt-6-luna"
DEFAULT_INPUT_USD_PER_MILLION = 0.10
DEFAULT_OUTPUT_USD_PER_MILLION = 0.50
DEFAULT_CACHE_WRITE_USD_PER_MILLION = 0.125
DEFAULT_CACHED_INPUT_USD_PER_MILLION = 0.01
DEFAULT_MAX_OUTPUT_TOKENS = 512
DEFAULT_PRICE_SOURCE = "https://developers.openai.com/api/docs/models/gpt-6-luna"
DEFAULT_PRICE_CHECKED_UTC_DATE = "2026-10-04"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_named_key(env_file: Path) -> None:
    """Load only the named key from a local dotenv-style file, without a shell."""
    if os.environ.get(KEY_ENV):
        return
    matches = []
    for raw in env_file.read_text().splitlines():
        line = raw.strip()
        if line.startswith("export "):
            line = line[7:].strip()
        if line.startswith(f"{KEY_ENV}="):
            value = line.split("=", 1)[1].strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            matches.append(value)
    if len(matches) != 1 or not matches[0]:
        raise ValueError("env file must contain exactly one named personal API key")
    os.environ[KEY_ENV] = matches[0]


def _resolve_config(config_path: Path | None, max_run_usd: float | None) -> dict:
    if (config_path is None) == (max_run_usd is None):
        raise ValueError("provide exactly one of --config or --max-run-usd")
    if config_path is not None:
        return validate_personal_config(json.loads(config_path.read_text()))
    return validate_personal_config(
        {
            "enabled": True,
            "personal_account_acknowledged": True,
            "model": DEFAULT_MODEL,
            "max_run_usd": max_run_usd,
            "input_usd_per_million": DEFAULT_INPUT_USD_PER_MILLION,
            "output_usd_per_million": DEFAULT_OUTPUT_USD_PER_MILLION,
            "cache_write_usd_per_million": DEFAULT_CACHE_WRITE_USD_PER_MILLION,
            "cached_input_usd_per_million": DEFAULT_CACHED_INPUT_USD_PER_MILLION,
            "max_output_tokens": DEFAULT_MAX_OUTPUT_TOKENS,
            "api_key_env": KEY_ENV,
        }
    )


def prepare(
    project: Path,
    config_path: Path | None = None,
    *,
    max_run_usd=None,
    holdout=False,
    holdout_version=1,
    conditions=None,
) -> dict:
    """Quote all cells and freeze code/data/question inputs without a key."""
    config = _resolve_config(config_path, max_run_usd)
    selected_conditions = tuple(conditions or CONDITIONS)
    if not selected_conditions or any(c not in CONDITIONS for c in selected_conditions):
        raise ValueError("unknown or empty experiment condition")
    if holdout_version in {7, 8, 9, 10, 11, 12, 13, 14} and selected_conditions != (
        "semantic_context",
    ):
        raise ValueError("M7 new-data release gate uses the product semantic-context condition")
    if holdout:
        if holdout_version not in {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14}:
            raise ValueError("unknown holdout version")
        if holdout_version in {3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14}:
            suffix = "" if holdout_version == 3 else f"_v{holdout_version - 2}"
            case_file = f"evals/cases/m7_holdout{suffix}.json"
            manifest_file = f"evals/cases/m7_holdout{suffix}_manifest.json"
        else:
            suffix = "" if holdout_version == 1 else "_v2"
            case_file = f"evals/cases/m6_holdout{suffix}.json"
            manifest_file = f"evals/cases/m6_holdout{suffix}_manifest.json"
        cases = json.loads((project / case_file).read_text())
        selected = cases
        digest_cases = cases
    else:
        case_file = "evals/cases/m5_dev.json"
        manifest_file = "evals/cases/m5_manifest.json"
        cases = json.loads((project / case_file).read_text())
        test_cases = json.loads((project / "evals/cases/m5_test.json").read_text())
        digest_cases = cases + test_cases
        selected = [case for case in cases if case["id"] in PILOT_IDS]
        if len(selected) != len(PILOT_IDS) or {c["id"] for c in selected} != set(PILOT_IDS):
            raise ValueError("pilot case set changed")
    manifest = json.loads((project / manifest_file).read_text())
    case_digest = hashlib.sha256(
        json.dumps(sorted(digest_cases, key=lambda case: case["id"]), sort_keys=True).encode()
    ).hexdigest()
    if case_digest != manifest["case_set_sha256"]:
        raise ValueError("case set hash changed")
    if holdout and (
        len(selected) != manifest["cases"] or len({c["id"] for c in selected}) != len(selected)
    ):
        raise ValueError("holdout case count or identities changed")
    cells = []
    for case in selected:
        for condition in selected_conditions:
            quote = quote_request(project, case["question"], config, condition)
            cells.append(
                {
                    "case_id": case["id"],
                    "condition": condition,
                    "request_sha256": quote["request_sha256"],
                    "reserved_cost_usd": quote["reserved_cost_usd"],
                }
            )
    max_transport_retries_per_run = (
        3 if holdout_version in {12, 13} else 1 if holdout_version in {10, 11} else 0
    )
    retry_reservation = (
        max(cell["reserved_cost_usd"] for cell in cells) * max_transport_retries_per_run
        if max_transport_retries_per_run
        else 0.0
    )
    upper_bound = sum(cell["reserved_cost_usd"] for cell in cells) + retry_reservation
    frozen_files = [
        "analyst_m5/provider.py",
        "analyst_m5/core.py",
        "analyst_m5/tools.py",
        "analyst_m5/tool_worker.py",
        "analyst_m5/evaluation.py",
        "analyst_m5/experiment.py",
        "analytics_m3/metrics.py",
        "analytics_m4/analysis.py",
        case_file,
        manifest_file,
        "docs/METRICS.md",
        "uv.lock",
    ]
    if holdout:
        if holdout_version == 7:
            frozen_files.extend(
                (
                    "config/datasets.json",
                    "config/m7_campaigns.json",
                    "reports/M3-analytical-manifest.json",
                    "reports/M3-independent-reference.json",
                    "reports/M7-independent-reference-v5.json",
                    "src/chess_analytics/m7_campaign.py",
                )
            )
        elif holdout_version == 8:
            frozen_files.extend(
                (
                    "config/datasets.json",
                    "config/m7_campaigns.json",
                    "reports/M3-analytical-manifest.json",
                    "reports/M3-independent-reference.json",
                    "reports/M7-independent-reference-v6.json",
                    "src/chess_analytics/m7_campaign.py",
                )
            )
        elif holdout_version == 9:
            frozen_files.extend(
                (
                    "config/datasets.json",
                    "config/m7_campaigns.json",
                    "reports/M3-analytical-manifest.json",
                    "reports/M3-independent-reference.json",
                    "reports/M7-independent-reference-v7.json",
                    "src/chess_analytics/m7_campaign.py",
                )
            )
        elif holdout_version == 10:
            frozen_files.extend(
                (
                    "config/datasets.json",
                    "config/m7_campaigns.json",
                    "reports/M3-analytical-manifest.json",
                    "reports/M3-independent-reference.json",
                    "reports/M7-independent-reference-v8.json",
                    "src/chess_analytics/m7_campaign.py",
                )
            )
        elif holdout_version == 11:
            frozen_files.extend(
                (
                    "config/datasets.json",
                    "config/m7_campaigns.json",
                    "reports/M3-analytical-manifest.json",
                    "reports/M3-independent-reference.json",
                    "reports/M7-independent-reference-v9.json",
                    "src/chess_analytics/m7_campaign.py",
                )
            )
        elif holdout_version == 12:
            frozen_files.extend(
                (
                    "config/datasets.json",
                    "config/m7_campaigns.json",
                    "reports/M3-analytical-manifest.json",
                    "reports/M3-independent-reference.json",
                    "reports/M7-independent-reference-v10.json",
                    "src/chess_analytics/m7_campaign.py",
                )
            )
        elif holdout_version == 13:
            frozen_files.extend(
                (
                    "config/datasets.json",
                    "config/m7_campaigns.json",
                    "reports/M3-analytical-manifest.json",
                    "reports/M3-independent-reference.json",
                    "reports/M7-independent-reference-v11.json",
                    "src/chess_analytics/m7_campaign.py",
                )
            )
        elif holdout_version == 14:
            frozen_files.extend(
                (
                    "config/datasets.json",
                    "config/m7_campaigns.json",
                    "reports/M3-analytical-manifest.json",
                    "reports/M3-independent-reference.json",
                    "reports/M7-independent-reference-v12.json",
                    "src/chess_analytics/m7_campaign.py",
                )
            )
        elif holdout_version in {3, 4, 5, 6}:
            report_suffix = "" if holdout_version == 3 else f"-v{holdout_version - 2}"
            frozen_files.extend(
                (
                    "reports/M3-independent-reference.json",
                    f"reports/M7-independent-reference{report_suffix}.json",
                    "config/m7_campaigns.json",
                    "src/chess_analytics/m7_campaign.py",
                )
            )
        else:
            reference_file = (
                "reports/M6-independent-reference.json"
                if holdout_version == 1
                else "reports/M6-independent-reference-v2.json"
            )
            frozen_files.extend(
                (
                    "reports/M3-independent-reference.json",
                    reference_file,
                    "scripts/reference_m6_holdout.py",
                    "scripts/build_m6_holdout.py",
                )
            )
    else:
        frozen_files.append("evals/cases/m5_test.json")
    frozen_files.extend(
        str(path.relative_to(project)) for path in sorted((project / "contracts").glob("*.json"))
    )
    new_data_month = {
        7: "July",
        8: "June",
        9: "May",
        10: "April",
        11: "March",
        12: "February",
        13: "January",
        14: "December",
    }.get(holdout_version)
    return {
        "kind": (
            (
                "m7_typed_planner_holdout_preflight_no_model_calls"
                if holdout_version in {3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14}
                else "m6_typed_planner_holdout_preflight_no_model_calls"
            )
            if holdout
            else "m6_typed_planner_development_pilot_preflight_no_model_calls"
        ),
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "dataset_id": manifest["dataset_id"],
        "case_set_sha256": manifest["case_set_sha256"],
        "selection": (
            (
                (
                    f"50 new-dataset {new_data_month} "
                    f"M7 v{holdout_version - 2} cases; product semantic context; one shot per run"
                    if holdout_version in {7, 8, 9, 10, 11, 12, 13, 14}
                    else f"50 new-family M7 holdout v{holdout_version - 2} cases; one-shot"
                )
                if holdout_version in {3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14}
                else f"20 family-split holdout v{holdout_version} cases; one-shot"
            )
            if holdout
            else "12 inspected development cases; not untouched holdout"
        ),
        "case_file": case_file,
        "conditions": list(selected_conditions),
        "comparison": (
            "product semantic-context condition only; no paired baseline"
            if holdout_version in {7, 8, 9, 10, 11, 12, 13, 14}
            else "typed planner with versus without governed metric definitions; not SQL baseline"
        ),
        "model": config["model"],
        "max_output_tokens": config["max_output_tokens"],
        "input_usd_per_million": config["input_usd_per_million"],
        "output_usd_per_million": config["output_usd_per_million"],
        "cache_write_usd_per_million": config.get("cache_write_usd_per_million"),
        "cached_input_usd_per_million": config.get("cached_input_usd_per_million"),
        "max_run_usd": config["max_run_usd"],
        "price_source": DEFAULT_PRICE_SOURCE if config_path is None else "user_configured",
        "price_checked_utc_date": (DEFAULT_PRICE_CHECKED_UTC_DATE if config_path is None else None),
        "attempts_planned": len(cells),
        "max_transport_retries_per_run": max_transport_retries_per_run,
        "transport_retry_reservation_usd": retry_reservation,
        "conservative_total_usd": upper_bound,
        "fits_cap": upper_bound <= config["max_run_usd"],
        "frozen_file_sha256": {name: _sha(project / name) for name in frozen_files},
        "cells": cells,
    }


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
