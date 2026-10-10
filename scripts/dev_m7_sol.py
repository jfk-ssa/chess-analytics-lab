"""Frozen six-case Sol diagnostic on inspected January data; never a holdout claim."""

import argparse
import hashlib
import json
import os
from pathlib import Path

from chess_analytics.analyst.evaluation import score_case_m7
from chess_analytics.analyst.experiment import _load_named_key
from chess_analytics.analyst.provider import (
    KEY_ENV,
    _default_transport,
    live_answer,
    price_usage,
    quote_request,
)
from chess_analytics.common import write_json

CASE_IDS = (
    "m7k_usage_queens_gambit_declined",
    "m7k_white_queens_pawn_game_score",
    "m7k_compare_queens_pawn_game_sicilian_defense_win",
    "m7k_clock_60_plus_proxy",
    "m7k_boundary_private_file",
    "m7k_boundary_rating_unspecified",
)
PRIOR_GROSS_USD = 0.120814360
CAP_USD = 0.5
CONFIG = {
    "enabled": True,
    "personal_account_acknowledged": True,
    "model": "gpt-6-sol",
    "max_run_usd": CAP_USD,
    "input_usd_per_million": 2.0,
    "cached_input_usd_per_million": 0.2,
    "cache_write_usd_per_million": 2.5,
    "output_usd_per_million": 10.0,
    "max_output_tokens": 512,
    "api_key_env": KEY_ENV,
}
FROZEN_FILES = (
    "src/chess_analytics/analyst/provider.py",
    "src/chess_analytics/analyst/core.py",
    "src/chess_analytics/analyst/tools.py",
    "src/chess_analytics/analyst/evaluation.py",
    "evals/cases/m7_holdout_v11.json",
    "reports/M3-analytical-manifest.json",
    "scripts/dev_m7_sol.py",
)


def prepare(project: Path) -> dict:
    cases = {c["id"]: c for c in json.loads((project / FROZEN_FILES[4]).read_text())}
    cells = []
    for case_id in CASE_IDS:
        case = cases[case_id]
        quote = quote_request(project, case["question"], CONFIG, "semantic_context")
        cells.append(
            {
                "case_id": case_id,
                "request_sha256": quote["request_sha256"],
                "reserved_cost_usd": quote["reserved_cost_usd"],
            }
        )
    bound = sum(cell["reserved_cost_usd"] for cell in cells)
    return {
        "kind": "M7 inspected-case Sol development preflight; no model calls",
        "dataset_id": cases[CASE_IDS[0]]["dataset_id"],
        "model": CONFIG["model"],
        "price_source": "https://developers.openai.com/api/docs/models/gpt-6-sol",
        "price_checked_utc_date": "2026-10-04",
        "config": CONFIG,
        "prior_gross_accounted_usd": PRIOR_GROSS_USD,
        "approved_cumulative_cap_usd": CAP_USD,
        "conservative_total_usd": bound,
        "fits_cumulative_cap": PRIOR_GROSS_USD + bound <= CAP_USD,
        "frozen_file_sha256": {
            name: hashlib.sha256((project / name).read_bytes()).hexdigest() for name in FROZEN_FILES
        },
        "cells": cells,
    }


def run(project: Path, frozen_path: Path, env_file: Path, out: Path) -> dict:
    if out.exists():
        raise ValueError("existing development attempt must be preserved")
    frozen = json.loads(frozen_path.read_text())
    current = prepare(project)
    if frozen != current or not current["fits_cumulative_cap"]:
        raise ValueError("frozen development request or cap drift")
    _load_named_key(env_file)
    if not os.environ.get(KEY_ENV):
        raise ValueError("named personal key absent")
    cases = {c["id"]: c for c in json.loads((project / FROZEN_FILES[4]).read_text())}
    record = {
        "kind": "M7 Sol inspected-case development; actual model calls, not holdout",
        "preflight_sha256": hashlib.sha256(frozen_path.read_bytes()).hexdigest(),
        "prior_gross_accounted_usd": PRIOR_GROSS_USD,
        "approved_cumulative_cap_usd": CAP_USD,
        "state": "running",
        "attempts": [],
    }
    write_json(out, record)
    accounted = 0.0
    for cell in frozen["cells"]:
        case = cases[cell["case_id"]]
        captured = {}

        def capture(body, key, captured=captured, cell=cell):
            if hashlib.sha256(body).hexdigest() != cell["request_sha256"]:
                raise ValueError("outgoing request differs from frozen development cell")
            captured["response"] = _default_transport(body, key)
            return captured["response"]

        row = {"case_id": cell["case_id"], "request_sha256": cell["request_sha256"]}
        try:
            answer = live_answer(
                project,
                case["question"],
                None,
                config=CONFIG,
                transport=capture,
                condition="semantic_context",
                remaining_usd=CAP_USD - PRIOR_GROSS_USD - accounted,
            )
            row.update(status="completed", answer=answer, score=score_case_m7(case, answer))
        except Exception as exc:
            key = os.environ.get(KEY_ENV)
            message = str(exc).replace(key, "[redacted]") if key else str(exc)
            row.update(
                status="failed",
                error_type=type(exc).__name__,
                error=message,
                provider_response=captured.get("response"),
            )
        response = captured.get("response") or {}
        usage = response.get("usage")
        if usage:
            try:
                cost, basis = price_usage(CONFIG, usage)
            except ValueError as exc:
                row.update(status="failed", cost_error=str(exc))
                row["unknown_cost_reservation_usd"] = cell["reserved_cost_usd"]
                accounted += cell["reserved_cost_usd"]
            else:
                row.update(provider_usage=usage, gross_cost_usd=cost, cost_basis=basis)
                accounted += cost
                if cost > cell["reserved_cost_usd"] + 1e-12:
                    row.update(status="failed", error="provider cost exceeded frozen cell bound")
        else:
            row["unknown_cost_reservation_usd"] = cell["reserved_cost_usd"]
            accounted += cell["reserved_cost_usd"]
        record["attempts"].append(row)
        record["gross_cost_accounted_usd"] = accounted
        record["cumulative_gross_accounted_usd"] = PRIOR_GROSS_USD + accounted
        if row["status"] == "failed" or record["cumulative_gross_accounted_usd"] > CAP_USD:
            record["state"] = "stopped_failed_or_budget"
            write_json(out, record)
            break
        write_json(out, record)
    else:
        record["state"] = "complete"
        write_json(out, record)
    return record


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("prepare", "run"))
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.mode == "prepare":
        if args.env_file or args.out:
            parser.error("prepare only writes the offline preflight")
        result = prepare(args.project)
        write_json(args.preflight, result)
    else:
        if not args.env_file or not args.out:
            parser.error("run requires a named env file and output")
        result = run(args.project, args.preflight, args.env_file, args.out)
    print(
        json.dumps(
            {
                "kind": result["kind"],
                "state": result.get("state"),
                "attempted": len(result.get("attempts", [])),
                "conservative_total_usd": result.get("conservative_total_usd"),
                "gross_cost_accounted_usd": result.get("gross_cost_accounted_usd"),
            }
        )
    )


if __name__ == "__main__":
    main()
