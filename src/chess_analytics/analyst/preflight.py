"""Frozen preflight for a budgeted analyst experiment; no model calls."""

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from chess_analytics.analyst.provider import (
    KEY_ENV,
    quote_request,
    validate_personal_config,
)

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
        "src/chess_analytics/analyst/provider.py",
        "src/chess_analytics/analyst/pricing.py",
        "src/chess_analytics/analyst/plan_recovery.py",
        "src/chess_analytics/analyst/preflight.py",
        "src/chess_analytics/analyst/core.py",
        "src/chess_analytics/analyst/tools.py",
        "src/chess_analytics/analyst/tool_worker.py",
        "src/chess_analytics/analyst/evaluation.py",
        "src/chess_analytics/analyst/experiment.py",
        "src/chess_analytics/corpus/metrics.py",
        "src/chess_analytics/dashboard/analysis.py",
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
        "created_utc": datetime.now(UTC).isoformat(),
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
