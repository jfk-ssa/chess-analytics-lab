"""Frozen paired end-to-end comparison of the analyst and a narrow Jev gate."""

import argparse
import json
import math
import os
import tempfile
import time
from pathlib import Path

from chess_analytics.analyst import provider
from chess_analytics.analyst.core import _evidence_id, execute_plan
from chess_analytics.analyst.evaluation import score_case_m7, score_case_portfolio
from chess_analytics.analyst.experiment import _resolve_config
from chess_analytics.analyst.tools import CheckedTools
from chess_analytics.routing_analyst import _key_from_file
from chess_analytics.routing_study import (
    MODEL,
    PRICE_USD_PER_MILLION_INPUT,
    _personal_key,
    _sha,
    _write,
    jev_request,
    parse_jev_response,
)
from chess_analytics.routing_study import (
    _transport as jev_transport,
)
from chess_analytics.routing_study import (
    quote as jev_quote,
)

CASE_FILE = Path("evals/cases/jev_e2e_v1.json")
MANIFEST_FILE = Path("evals/cases/jev_e2e_v1_manifest.json")
THRESHOLD = 0.70
POLICY = "jev-boundary-gate-v1"


def _durable_write(path: Path, value: dict) -> None:
    """Write the pre-transport reservation before a provider can charge us."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def reconcile_attempt_costs(attempt: Path) -> dict[str, dict[str, float]]:
    """Count settled usage and reserve every interrupted or uncertain request."""
    total = {"jev": 0.0, "openai": 0.0}
    unknown = {"jev": 0.0, "openai": 0.0}
    for path in attempt.glob("*.json"):
        if path.name == "report.json":
            continue
        record = json.loads(path.read_text())
        if not isinstance(record, dict) or "request_sha256" not in record:
            continue
        kind = "jev" if path.name.startswith("jev-") else "openai"
        if record.get("state") == "pending":
            cost = _finite_cap(record["reserved_cost_usd"], "pending reservation")
            uncertain = True
        elif "accounted_cost_usd" in record:
            cost = _finite_cap(record["accounted_cost_usd"], "accounted cost")
            uncertain = bool(record.get("unknown_cost_reservation"))
        elif "gross_cost_usd" in record:
            cost = _finite_cap(record["gross_cost_usd"], "gross cost")
            uncertain = False
        elif "parsed" in record:  # Historical Jev success records.
            cost = _finite_cap(record["parsed"]["gross_cost_usd"], "Jev gross cost")
            uncertain = False
        else:
            raise ValueError(f"attempt record has no cost: {path.name}")
        total[kind] += cost
        if uncertain:
            unknown[kind] += cost
    return {"gross_usd": total, "unknown_usd": unknown}


def cases(repo: Path, data_project: Path) -> tuple[list[dict], dict]:
    source = repo / CASE_FILE
    manifest = json.loads((repo / MANIFEST_FILE).read_text())
    if _sha(source.read_bytes()) != manifest["case_sha256"]:
        raise ValueError("frozen end-to-end cases changed")
    if (
        _sha((repo / "reports/M8-e2e-independent-reference.json").read_bytes())
        != manifest["reference_sha256"]
    ):
        raise ValueError("raw-PGN reference changed")
    if (
        _sha((data_project / "reports/M3-independent-reference.json").read_bytes())
        != manifest["clock_reference_sha256"]
    ):
        raise ValueError("clock reference changed")
    selected = json.loads(source.read_text())
    if len(selected) != manifest["cases"] or len({row["id"] for row in selected}) != len(selected):
        raise ValueError("frozen case count or identity changed")
    active_dataset_id = CheckedTools(data_project).dataset_id
    if any(row["dataset_id"] != active_dataset_id for row in selected):
        raise ValueError("answer reference and active dataset differ")
    return selected, manifest


def score_answer(case: dict, answer: dict) -> dict:
    scored = score_case_m7(case, answer)
    strict = score_case_portfolio(case, answer)
    trace = answer.get("evidence") or []
    if (
        "tool_or_filters" in scored["failures"]
        and case.get("expected_tool") is not None
        and any(
            item.get("tool") == case["expected_tool"]
            and item.get("args") == case["expected_tool_args"]
            for item in trace
        )
    ):
        scored["failures"].remove("tool_or_filters")
    if "result_values" in strict["failures"] and "result_values" not in scored["failures"]:
        scored["failures"].append("result_values")
    ids = answer.get("evidence_ids") or []
    if len(trace) != len(ids) or any(
        item.get("evidence_id") != identifier
        or _evidence_id(answer["dataset_id"], item["tool"], item["args"], item["result"])
        != identifier
        for item, identifier in zip(trace, ids, strict=True)
    ):
        scored["failures"].append("evidence_integrity")
    scored["passed"] = not scored["failures"]
    scored["rubric_version"] = "m8-e2e-1.1"
    return scored


def preflight(repo: Path, data_project: Path) -> dict:
    selected, manifest = cases(repo, data_project)
    config = _resolve_config(None, 1.0)  # Quote only, never authorization.
    cells = []
    for row in selected:
        openai_quote = provider.quote_request(data_project, row["question"], config)
        choice_quote = jev_quote(jev_request(row["question"]))
        cells.append(
            {
                "id": row["id"],
                "openai_request_sha256": openai_quote["request_sha256"],
                "openai_reserved_cost_usd": openai_quote["reserved_cost_usd"],
                "jev_request_sha256": choice_quote["request_sha256"],
                "jev_reserved_cost_usd": choice_quote["reserved_cost_usd"],
            }
        )
    source_paths = (
        "src/chess_analytics/analyst/provider.py",
        "src/chess_analytics/analyst/core.py",
        "src/chess_analytics/analyst/tools.py",
        "src/chess_analytics/analyst/evaluation.py",
        "src/chess_analytics/routing_study.py",
    )
    return {
        "kind": "m8_e2e_paired_preflight_no_model_calls",
        "case_sha256": manifest["case_sha256"],
        "reference_sha256": manifest["reference_sha256"],
        "dataset_id": selected[0]["dataset_id"],
        "policy": POLICY,
        "threshold": THRESHOLD,
        "jev_model": MODEL,
        "jev_price_usd_per_million_input": PRICE_USD_PER_MILLION_INPUT,
        "openai_model": config["model"],
        "openai_prices": {
            key: config[key]
            for key in (
                "input_usd_per_million",
                "output_usd_per_million",
                "cache_write_usd_per_million",
                "cached_input_usd_per_million",
            )
        },
        "source_hashes": {name: _sha((repo / name).read_bytes()) for name in source_paths},
        "code_sha256": _sha(Path(__file__).read_bytes()),
        "cells": cells,
        "openai_whole_run_reservation_usd": 2
        * sum(cell["openai_reserved_cost_usd"] for cell in cells),
        "jev_whole_run_reservation_usd": sum(cell["jev_reserved_cost_usd"] for cell in cells),
        "reservation_limit": (
            "OpenAI reserves baseline plus every possible gated fallback. Jev reserves "
            "4× request bytes + 1024 tokens per case; these are conservative quotes, "
            "not contractual tokenizer bounds."
        ),
    }


def _finite_cap(value, name: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
    ):
        raise ValueError(f"finite nonnegative {name} required")
    return float(value)


def _cost_from_raw(raw, config: dict, reserved: float, kind: str) -> tuple[float, bool]:
    """Return accounted gross and whether a reservation replaced unknown usage."""
    if kind == "jev":
        usage = raw.get("usage") if isinstance(raw, dict) else None
        count = usage.get("input_tokens") if isinstance(usage, dict) else None
        if isinstance(count, int) and not isinstance(count, bool) and count >= 0:
            return count * PRICE_USD_PER_MILLION_INPUT / 1_000_000, False
    else:
        usage = raw.get("usage") if isinstance(raw, dict) else None
        try:
            cost, _ = provider.price_usage(config, usage)
            return cost, False
        except (ValueError, TypeError, KeyError):
            pass
    return reserved, True


def _openai_answer(
    row: dict,
    cell: dict,
    phase: str,
    prior_openai_usd,
    accounted,
    unknown,
    openai_cap,
    output,
    openai_call,
    data_project,
    config,
):
    reserved = cell["openai_reserved_cost_usd"]
    if prior_openai_usd + accounted["openai"] + reserved > openai_cap:
        raise ValueError("next OpenAI call exceeds remaining cumulative cap")
    record = {
        "case_id": row["id"],
        "phase": phase,
        "request_sha256": cell["openai_request_sha256"],
    }
    path = output / f"{phase}-{row['id']}.json"

    def capture(body, key):
        if _sha(body) != cell["openai_request_sha256"]:
            raise ValueError("OpenAI request changed after frozen preflight")
        record.update(
            state="pending",
            transport_started=True,
            reserved_cost_usd=reserved,
        )
        _durable_write(path, record)
        raw = (openai_call or provider._default_transport)(body, key)
        record["raw_response"] = raw
        _durable_write(path, record)
        return raw

    try:
        answer = provider.live_answer(
            data_project,
            row["question"],
            None,
            config=config,
            transport=capture,
            remaining_usd=openai_cap - prior_openai_usd - accounted["openai"],
        )
        cost = answer["provider"]["gross_cost_usd"]
        accounted["openai"] += cost
        record["cost_accounted"] = True
        record["answer"] = answer
        record["gross_cost_usd"] = cost
        record["state"] = "settled"
        _durable_write(path, record)
        return answer, cost
    except (OSError, ValueError, RuntimeError, TimeoutError) as exc:
        cost, reserved_unknown = (
            _cost_from_raw(record.get("raw_response"), config, reserved, "openai")
            if record.get("transport_started")
            else (0.0, False)
        )
        if not record.get("cost_accounted"):
            accounted["openai"] += cost
        if reserved_unknown:
            unknown["openai"] += cost
        record["failure"] = {"type": type(exc).__name__, "message": str(exc)[:300]}
        record["accounted_cost_usd"] = cost
        record["unknown_cost_reservation"] = reserved_unknown
        record["state"] = "failed"
        _durable_write(path, record)
        raise


def _jev_choice(
    row: dict,
    cell: dict,
    prior_jev_usd,
    accounted,
    unknown,
    jev_cap,
    output,
    jev_call,
    jev_key,
    config,
):
    reserved = cell["jev_reserved_cost_usd"]
    if prior_jev_usd + accounted["jev"] + reserved > jev_cap:
        raise ValueError("next Jev call exceeds remaining cumulative cap")
    record = {"case_id": row["id"], "request_sha256": cell["jev_request_sha256"]}
    path = output / f"jev-{row['id']}.json"
    try:
        body = jev_request(row["question"])
        if _sha(body) != cell["jev_request_sha256"]:
            raise ValueError("Jev request changed after frozen preflight")
        record.update(
            state="pending",
            transport_started=True,
            reserved_cost_usd=reserved,
        )
        _durable_write(path, record)
        raw = (jev_call or jev_transport)(body, jev_key)
        record["raw_response"] = raw
        _durable_write(path, record)
        parsed = parse_jev_response(raw)
        if parsed["gross_cost_usd"] > reserved:
            raise ValueError("Jev usage exceeded request reservation")
        accounted["jev"] += parsed["gross_cost_usd"]
        record["cost_accounted"] = True
        record["parsed"] = parsed
        record["gross_cost_usd"] = parsed["gross_cost_usd"]
        record["state"] = "settled"
        _durable_write(path, record)
        return parsed
    except (OSError, ValueError, RuntimeError, TimeoutError) as exc:
        cost, reserved_unknown = (
            _cost_from_raw(record.get("raw_response"), config, reserved, "jev")
            if record.get("transport_started")
            else (0.0, False)
        )
        if not record.get("cost_accounted"):
            accounted["jev"] += cost
        if reserved_unknown:
            unknown["jev"] += cost
        record["failure"] = {"type": type(exc).__name__, "message": str(exc)[:300]}
        record["accounted_cost_usd"] = cost
        record["unknown_cost_reservation"] = reserved_unknown
        record["state"] = "failed"
        _durable_write(path, record)
        raise


def run(
    repo: Path,
    data_project: Path,
    frozen: dict,
    jev_env: Path,
    openai_env: Path,
    jev_cap: float,
    openai_cap: float,
    output: Path,
    *,
    prior_jev_usd: float = 0.0,
    prior_openai_usd: float = 0.0,
    prior_attempts: tuple[Path, ...] = (),
    jev_call=None,
    openai_call=None,
) -> dict:
    jev_cap, openai_cap = _finite_cap(jev_cap, "Jev cap"), _finite_cap(openai_cap, "OpenAI cap")
    prior_jev_usd = _finite_cap(prior_jev_usd, "prior Jev gross")
    prior_openai_usd = _finite_cap(prior_openai_usd, "prior OpenAI gross")
    work = (repo / "work").resolve()
    if prior_attempts and (prior_jev_usd or prior_openai_usd):
        raise ValueError("use prior attempt directories or manual prior totals, not both")
    if len({path.resolve() for path in prior_attempts}) != len(prior_attempts):
        raise ValueError("duplicate prior attempt directory")
    for prior in prior_attempts:
        if not prior.resolve().is_relative_to(work) or not prior.is_dir():
            raise ValueError("prior attempts must be existing ignored work/ directories")
        recovered = reconcile_attempt_costs(prior)["gross_usd"]
        prior_jev_usd += recovered["jev"]
        prior_openai_usd += recovered["openai"]
    if jev_cap <= 0 or openai_cap <= 0:
        raise ValueError("two explicit positive provider caps required")
    if frozen != preflight(repo, data_project):
        raise ValueError("frozen end-to-end preflight drifted")
    if prior_jev_usd + frozen["jev_whole_run_reservation_usd"] > jev_cap or (
        prior_openai_usd + frozen["openai_whole_run_reservation_usd"] > openai_cap
    ):
        raise ValueError("whole paired run does not fit remaining provider caps")
    if not all(path.resolve().is_relative_to(work) for path in (jev_env, openai_env, output)):
        raise ValueError("keys and raw attempts must stay in ignored project work/")
    if output.exists() and any(output.iterdir()):
        raise ValueError("use a fresh end-to-end attempt directory")
    jev_key = _personal_key(jev_env)
    openai_key = _key_from_file(openai_env)
    selected, manifest = cases(repo, data_project)
    config = _resolve_config(None, openai_cap - prior_openai_usd)
    output.mkdir(parents=True, exist_ok=True)
    accounted = {"jev": 0.0, "openai": 0.0}
    unknown = {"jev": 0.0, "openai": 0.0}
    outcomes = {"baseline": [], "gated": []}
    failure = None
    previous = os.environ.get(provider.KEY_ENV)

    try:
        os.environ[provider.KEY_ENV] = openai_key
        for phase in ("baseline", "gated"):
            for row, cell in zip(selected, frozen["cells"], strict=True):
                started = time.monotonic()
                try:
                    route = None
                    confidence = None
                    used_analyst = True
                    cost = {"jev": 0.0, "openai": 0.0}
                    if phase == "gated":
                        parsed = _jev_choice(
                            row,
                            cell,
                            prior_jev_usd,
                            accounted,
                            unknown,
                            jev_cap,
                            output,
                            jev_call,
                            jev_key,
                            config,
                        )
                        cost["jev"] = parsed["gross_cost_usd"]
                        route = parsed["choice"]
                        confidence = parsed["probabilities"][route]
                        used_analyst = not (
                            route in {"clarify", "unsupported"} and confidence >= THRESHOLD
                        )
                    if used_analyst:
                        answer, cost["openai"] = _openai_answer(
                            row,
                            cell,
                            phase,
                            prior_openai_usd,
                            accounted,
                            unknown,
                            openai_cap,
                            output,
                            openai_call,
                            data_project,
                            config,
                        )
                    else:
                        status = "needs_clarification" if route == "clarify" else "unsupported"
                        answer = execute_plan(
                            data_project,
                            row["question"],
                            {
                                "status": status,
                                "interpretation": "descriptive_observed_prefix",
                                "actions": [],
                            },
                            source="jev_boundary_gate",
                        )
                    scored = score_answer(row, answer)
                    outcomes[phase].append(
                        {
                            "id": row["id"],
                            "passed": scored["passed"],
                            "failures": scored["failures"],
                            "expected_status": row["expected_status"],
                            "observed_status": answer["status"],
                            "jev_route": route,
                            "jev_probability": confidence,
                            "used_analyst": used_analyst,
                            "gross_cost_usd": cost,
                            "elapsed_seconds": time.monotonic() - started,
                        }
                    )
                except (OSError, ValueError, RuntimeError, TimeoutError) as exc:
                    failure = {
                        "phase": phase,
                        "case_id": row["id"],
                        "type": type(exc).__name__,
                        "message": str(exc)[:300],
                    }
                    break
                except KeyboardInterrupt:
                    failure = {
                        "phase": phase,
                        "case_id": row["id"],
                        "type": "KeyboardInterrupt",
                        "message": "operator interrupted the attempt",
                    }
                    break
            if failure:
                break
    finally:
        if previous is None:
            os.environ.pop(provider.KEY_ENV, None)
        else:
            os.environ[provider.KEY_ENV] = previous
    recovered = reconcile_attempt_costs(output)
    accounted = recovered["gross_usd"]
    unknown = recovered["unknown_usd"]
    complete = not failure and all(len(outcomes[phase]) == len(selected) for phase in outcomes)
    report = {
        "kind": "m8_paired_e2e_actual_attempt"
        if jev_call is None and openai_call is None
        else "m8_paired_e2e_mock_attempt",
        "complete": complete,
        "failure": failure,
        "case_sha256": manifest["case_sha256"],
        "dataset_id": frozen["dataset_id"],
        "policy": POLICY,
        "threshold": THRESHOLD,
        "models": {"jev": MODEL, "openai": config["model"]},
        "caps_usd": {"jev": jev_cap, "openai": openai_cap},
        "prior_gross_usd": {"jev": prior_jev_usd, "openai": prior_openai_usd},
        "attempt_gross_usd": accounted,
        "unknown_cost_reservation_usd": unknown,
        "cumulative_accounted_gross_usd": {
            "jev": prior_jev_usd + accounted["jev"],
            "openai": prior_openai_usd + accounted["openai"],
        },
        "planned_cases_per_arm": len(selected),
        "outcomes": outcomes,
    }
    if complete:
        report["scores"] = {}
        for phase, results in outcomes.items():
            gross = sum(sum(item["gross_cost_usd"].values()) for item in results)
            passed = sum(item["passed"] for item in results)
            report["scores"][phase] = {
                "passed": passed,
                "total": len(results),
                "gross_usd": gross,
                "correct_answer_cost_usd": gross / passed if passed else None,
            }
    _write(output / "report.json", report)
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="M8 frozen end-to-end analyst comparison")
    parser.add_argument("mode", choices=("prepare", "run"))
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--data-project", type=Path, required=True)
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--jev-env", type=Path)
    parser.add_argument("--openai-env", type=Path)
    parser.add_argument("--jev-cap", type=float)
    parser.add_argument("--openai-cap", type=float)
    parser.add_argument("--prior-jev-usd", type=float, default=0.0)
    parser.add_argument("--prior-openai-usd", type=float, default=0.0)
    parser.add_argument("--prior-attempt", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.mode == "prepare":
            result = preflight(args.repo, args.data_project)
            _write(args.preflight, result)
        else:
            if args.jev_env is None or args.openai_env is None or args.output is None:
                raise ValueError("run requires both env files and a fresh output directory")
            result = run(
                args.repo,
                args.data_project,
                json.loads(args.preflight.read_text()),
                args.jev_env,
                args.openai_env,
                args.jev_cap,
                args.openai_cap,
                args.output,
                prior_jev_usd=args.prior_jev_usd,
                prior_openai_usd=args.prior_openai_usd,
                prior_attempts=tuple(args.prior_attempt),
            )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if args.mode == "prepare" or result["complete"] else 1
    except (OSError, ValueError) as exc:
        parser.exit(1, f"end-to-end study: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
