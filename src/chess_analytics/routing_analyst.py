"""Same-question structured analyst comparator for the M8 routing study."""

import argparse
import hashlib
import json
import math
import os
import time
from pathlib import Path

from analyst_m5 import provider
from analyst_m5.experiment import _resolve_config
from analyst_m5.tools import CheckedTools
from chess_analytics.routing_study import _sha, _write, cases, score

KEY_NAME = provider.KEY_ENV


def route_from_answer(answer: dict) -> str:
    """Map the existing planner's checked action, not its prose, to one M8 route."""
    status = answer.get("status")
    if status == "needs_clarification":
        return "clarify"
    if status == "unsupported":
        return "unsupported"
    if status != "answered":
        return "fallback"
    evidence = answer.get("evidence") or []
    if not evidence:
        return "fallback"
    actions = [(item.get("tool"), item.get("args") or {}) for item in evidence]
    if any(tool == "compare_openings" for tool, _ in actions):
        return "opening_compare"
    if any(tool == "compare_clock_buckets" for tool, _ in actions):
        return "clock_compare"
    if any(tool == "get_dataset_coverage" for tool, _ in actions):
        return "coverage"
    if (
        len(actions) > 1
        and all(tool == "query_metric" for tool, _ in actions)
        and all(
            args.get("metric_id") in {"opening_player_score", "opening_adjusted_score"}
            for _, args in actions
        )
    ):
        return "opening_compare"
    tool, args = actions[-1]
    metric = args.get("metric_id")
    if metric == "opening_usage":
        return "opening_usage"
    if metric in {"opening_player_score", "opening_adjusted_score"}:
        return "opening_score"
    if tool == "analyze_clock_pressure" or metric in {
        "clock_pressure_error_proxy",
        "evaluation_coverage",
    }:
        return "clock_bucket"
    return "fallback"


def preflight(repo: Path, data_project: Path, split: str = "test") -> dict:
    selected, manifest = cases(repo, split)
    config = _resolve_config(None, 1.0)  # Quote only; this is not a run authorization.
    dataset_id = CheckedTools(data_project).dataset_id
    cells = []
    for row in selected:
        quote = provider.quote_request(data_project, row["question"], config)
        cells.append(
            {
                "id": row["id"],
                "request_sha256": quote["request_sha256"],
                "reserved_cost_usd": quote["reserved_cost_usd"],
            }
        )
    paths = ("analyst_m5/provider.py", "analyst_m5/core.py", "analyst_m5/tools.py")
    return {
        "kind": "m8_existing_analyst_preflight_no_model_calls",
        "split": split,
        "case_sha256": manifest["case_sha256"],
        "dataset_id": dataset_id,
        "model": config["model"],
        "prices": {
            name: config[name]
            for name in (
                "input_usd_per_million",
                "output_usd_per_million",
                "cache_write_usd_per_million",
                "cached_input_usd_per_million",
            )
        },
        "source_hashes": {name: _sha((repo / name).read_bytes()) for name in paths},
        "code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "cells": cells,
        "total_reserved_cost_usd": sum(cell["reserved_cost_usd"] for cell in cells),
        "pricing_source": "https://developers.openai.com/api/docs/models/gpt-6-luna",
    }


def _key_from_file(path: Path) -> str:
    if path.name not in {".env", ".env.openai"}:
        raise ValueError("use an explicit ignored work/.env or work/.env.openai")
    matches = []
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        name, separator, value = line.partition("=")
        if not separator or name != KEY_NAME or not value.strip():
            raise ValueError("env file may contain only the named project OpenAI key")
        token = value.strip().strip("\"'")
        if not token:
            raise ValueError("project OpenAI key value is blank")
        matches.append(token)
    if len(matches) != 1:
        raise ValueError("env file must contain exactly one project OpenAI key")
    return matches[0]


def run(
    repo: Path,
    data_project: Path,
    frozen: dict,
    env_file: Path,
    max_run_usd: float,
    output: Path,
    *,
    transport=None,
) -> dict:
    if (
        isinstance(max_run_usd, bool)
        or not isinstance(max_run_usd, (int, float))
        or not math.isfinite(max_run_usd)
        or max_run_usd <= 0
    ):
        raise ValueError("explicit finite positive run cap required")
    if frozen != preflight(repo, data_project, frozen["split"]):
        raise ValueError("frozen structured-analyst preflight drifted")
    if frozen["total_reserved_cost_usd"] > max_run_usd:
        raise ValueError("whole structured-analyst run exceeds cap")
    work = (repo / "work").resolve()
    if not env_file.resolve().is_relative_to(work) or not output.resolve().is_relative_to(work):
        raise ValueError("key and raw attempts must stay in this project's ignored work/")
    if output.exists() and any(output.iterdir()):
        raise ValueError("use a fresh attempt directory")
    key = _key_from_file(env_file)
    output.mkdir(parents=True, exist_ok=True)
    selected, manifest = cases(repo, frozen["split"])
    config = _resolve_config(None, max_run_usd)
    predictions = []
    known = 0.0
    unknown = 0.0
    previous = os.environ.get(KEY_NAME)
    try:
        os.environ[KEY_NAME] = key
        for row, cell in zip(selected, frozen["cells"], strict=True):
            quote = provider.quote_request(data_project, row["question"], config)
            if cell["id"] != row["id"] or cell["request_sha256"] != quote["request_sha256"]:
                raise ValueError("frozen analyst request drifted")
            if known + unknown + cell["reserved_cost_usd"] > max_run_usd:
                raise ValueError("next analyst request exceeds remaining cap")
            started = time.monotonic()
            record = {"id": row["id"], "request_sha256": cell["request_sha256"]}

            def capture(body, supplied_key, current_record=record, case_id=row["id"]):
                raw = (transport or provider._default_transport)(body, supplied_key)
                current_record["raw_response"] = raw
                _write(output / f"{case_id}.json", current_record)
                return raw

            try:
                answer = provider.live_answer(
                    data_project,
                    row["question"],
                    None,
                    config=config,
                    transport=capture,
                    remaining_usd=max_run_usd - known - unknown,
                )
                cost = answer["provider"]["gross_cost_usd"]
                known += cost
                route = route_from_answer(answer)
                record["answer"] = answer
                predictions.append(
                    {
                        "id": row["id"],
                        "route": route,
                        "gross_cost_usd": cost,
                        "elapsed_seconds": time.monotonic() - started,
                    }
                )
            except (OSError, ValueError, TimeoutError, RuntimeError) as exc:
                usage = record.get("raw_response", {}).get("usage")
                try:
                    cost, _ = provider.price_usage(config, usage)
                except (ValueError, TypeError, KeyError):
                    unknown += cell["reserved_cost_usd"]
                    record["unknown_cost_reservation_usd"] = cell["reserved_cost_usd"]
                else:
                    known += cost
                    record["gross_cost_usd"] = cost
                record["failure"] = {"type": type(exc).__name__, "message": str(exc)[:300]}
                record["elapsed_seconds"] = time.monotonic() - started
                _write(output / f"{row['id']}.json", record)
                break
            _write(output / f"{row['id']}.json", record)
    finally:
        if previous is None:
            os.environ.pop(KEY_NAME, None)
        else:
            os.environ[KEY_NAME] = previous
    complete = len(predictions) == len(selected)
    report = {
        "kind": "m8_existing_structured_analyst_attempt",
        "transport_kind": "injected_mock" if transport is not None else "openai_api",
        "split": frozen["split"],
        "case_sha256": manifest["case_sha256"],
        "dataset_id": frozen["dataset_id"],
        "model": frozen["model"],
        "max_run_usd": max_run_usd,
        "known_gross_cost_usd": known,
        "unknown_cost_reservation_usd": unknown,
        "accounted_gross_usd": known + unknown,
        "complete": complete,
        "completed_cases": len(predictions),
        "total_cases": len(selected),
        "predictions": predictions,
    }
    if complete:
        report["scoring"] = score(selected, predictions, "analyst")
    _write(output / "report.json", report)
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="M8 existing analyst comparator")
    parser.add_argument("mode", choices=("prepare", "run"))
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--data-project", type=Path, required=True)
    parser.add_argument("--split", choices=("dev", "test"), default="test")
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--max-run-usd", type=float)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.mode == "prepare":
            result = preflight(args.repo, args.data_project, args.split)
            _write(args.preflight, result)
        else:
            if args.env_file is None or args.output is None:
                raise ValueError("run requires --env-file and --output")
            result = run(
                args.repo,
                args.data_project,
                json.loads(args.preflight.read_text()),
                args.env_file,
                args.max_run_usd,
                args.output,
            )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (OSError, ValueError) as exc:
        parser.exit(1, f"analyst routing comparator: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
