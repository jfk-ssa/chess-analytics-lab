"""Run the frozen live-eval case set through an injectable transport.

This module quotes requests with ``quote_request`` and parses plans with the
same extract and normalize helpers ``provider.py`` uses. It scores
``model_plan_before_semantic_repair`` and does not execute the semantically
repaired plan as the headline.

No call is scheduled. A dry run quotes and prints the reservation and does
not read an API key. A real run reads ``CHESSLAB_OPENAI_API_KEY`` for
``gpt-6-luna`` and ``gpt-6-sol``, and ``CHESSLAB_XAI_API_KEY`` for
``grok-4.7``. It does not read the other key.
"""

import hashlib
import json
import os
import re
import time
import uuid
from pathlib import Path

from chess_analytics.analyst.live_eval import load_live_cases
from chess_analytics.analyst.live_score import RUBRIC_VERSION, score_live_plan
from chess_analytics.analyst.live_stats import (
    _check_rate,
    binomial_alert,
    cluster_bootstrap,
    flaky_case_ids,
    hard_fail,
    wilson_interval,
)
from chess_analytics.analyst.model_catalog import (
    GROK_MODEL_ID,
    LIVE_EVAL_WALL_CLOCK_SECONDS,
    RECOMMENDED_CAP_USD,
    XAI_KEY_ENV,
    grok_short_rates,
    resolve_effort,
)
from chess_analytics.analyst.plan_recovery import (
    _extract_plan,
    _normalize_plan,
    _repair_opening_usage,
)
from chess_analytics.analyst.preflight import (
    DEFAULT_CACHE_WRITE_USD_PER_MILLION,
    DEFAULT_CACHED_INPUT_USD_PER_MILLION,
    DEFAULT_INPUT_USD_PER_MILLION,
    DEFAULT_MAX_OUTPUT_TOKENS,
    DEFAULT_OUTPUT_USD_PER_MILLION,
    DEFAULT_PRICE_CHECKED_UTC_DATE,
)
from chess_analytics.analyst.pricing import KEY_ENV, price_usage, validate_personal_config
from chess_analytics.analyst.provider import quote_request
from chess_analytics.analyst.tools import CheckedTools
from chess_analytics.common import write_json

PRICE_CHECKED_UTC_DATE = DEFAULT_PRICE_CHECKED_UTC_DATE
RECEIPT_VERSION = "1"
DEFAULT_REPEATS = 5
DEFAULT_SEED = 20261018
DEFAULT_RESAMPLES = 2000
LUNA_RATES = {
    "cache_write_usd_per_million": DEFAULT_CACHE_WRITE_USD_PER_MILLION,
    "cached_input_usd_per_million": DEFAULT_CACHED_INPUT_USD_PER_MILLION,
    "input_usd_per_million": DEFAULT_INPUT_USD_PER_MILLION,
    "output_usd_per_million": DEFAULT_OUTPUT_USD_PER_MILLION,
}
# Recorded with the Sol diagnostic on 2026-10-04. Not a fresh price check.
SOL_RATES = {
    "cache_write_usd_per_million": 2.5,
    "cached_input_usd_per_million": 0.2,
    "input_usd_per_million": 2.0,
    "output_usd_per_million": 10.0,
}
FROZEN_FILES = (
    "src/chess_analytics/analyst/provider.py",
    "src/chess_analytics/analyst/model_catalog.py",
    "src/chess_analytics/analyst/pricing.py",
    "src/chess_analytics/analyst/plan_recovery.py",
    "src/chess_analytics/analyst/preflight.py",
    "src/chess_analytics/analyst/core.py",
    "src/chess_analytics/analyst/tools.py",
    "src/chess_analytics/analyst/tool_worker.py",
    "src/chess_analytics/analyst/evaluation.py",
    "src/chess_analytics/analyst/experiment.py",
    "src/chess_analytics/analyst/live_eval.py",
    "src/chess_analytics/analyst/live_score.py",
    "src/chess_analytics/analyst/live_stats.py",
    "src/chess_analytics/analyst/live_runner.py",
)
RECEIPT_FIELDS = (
    "base_rubric_version",
    "baseline_alert",
    "case_set_sha256",
    "cases",
    "complete",
    "fixture_sha256",
    "flaky_cases",
    "frozen_file_sha256",
    "hard_fail",
    "headline_pass_rate",
    "headline_passed",
    "high_severity_misses",
    "incomplete_reason",
    "instructions_sha256",
    "kind",
    "known_gross_cost_usd",
    "unknown_cost_reservation_usd",
    "max_run_usd",
    "model",
    "over_abstention",
    "planned_requests",
    "price_checked_utc_date",
    "prices_rechecked",
    "reasoning_effort",
    "receipt_version",
    "repair_counts",
    "repeats",
    "reserved_usd",
    "resolved_model",
    "rows",
    "rubric_version",
    "run_id",
    "scheduled",
    "stats",
    "token_usage",
    "unsafe_answer",
)
ROW_FIELDS = (
    "argument_repairs",
    "case_id",
    "caveats",
    "cost_basis",
    "error",
    "failures",
    "gross_cost_usd",
    "high_severity_miss",
    "model_plan_before_semantic_repair",
    "over_abstention",
    "passed",
    "recovered_argument_suffixes",
    "recovered_inert_suffix_characters",
    "recovered_repeated_plan_objects",
    "repair_count",
    "repeat",
    "reserved_cost_usd",
    "resolved_model",
    "semantic_repair_would_pass",
    "semantic_repairs",
    "severity",
    "status",
    "template_family",
    "unsafe_answer",
    "usage",
)


class ReservationError(ValueError):
    """The conservative whole-run reservation does not fit the explicit cap."""

    def __init__(self, reserved: float, cap: float):
        self.reserved = reserved
        self.cap = cap
        message = f"whole-run reservation {reserved:.6f} exceeds explicit cap {cap:.6f}"
        super().__init__(message)


def recorded_rates(model: str, override: dict | None = None) -> dict:
    """Luna and Sol rates from the 2026-10-04 diagnostic, grok-4.7 short rates, or an override."""
    if override is not None:
        return override
    if model == "gpt-6-luna":
        return dict(LUNA_RATES)
    if model == "gpt-6-sol":
        return dict(SOL_RATES)
    if model == GROK_MODEL_ID:
        return grok_short_rates()
    raise ValueError(
        "explicit prices required for this model; recorded rates "
        "cover only gpt-6-luna, gpt-6-sol, and grok-4.7"
    )


def build_config(
    *,
    model: str,
    max_run_usd: float,
    acknowledged: bool,
    rates: dict | None = None,
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
) -> dict:
    """Personal config. Acknowledgement is the caller's flag, not a credit balance."""
    chosen = recorded_rates(model, rates)
    return validate_personal_config(
        {
            "api_key_env": XAI_KEY_ENV if model == GROK_MODEL_ID else KEY_ENV,
            "enabled": True,
            "max_output_tokens": max_output_tokens,
            "max_run_usd": max_run_usd,
            "model": model,
            "personal_account_acknowledged": acknowledged is True,
            **chosen,
        }
    )


def run(
    repo: Path,
    staged: Path,
    *,
    model: str,
    max_run_usd: float,
    acknowledged: bool,
    repeats: int = DEFAULT_REPEATS,
    transport=None,
    dry_run: bool = False,
    env_file: Path | None = None,
    output: Path | None = None,
    seed: int = DEFAULT_SEED,
    resamples: int = DEFAULT_RESAMPLES,
    baseline_rate: float | None = None,
    rates: dict | None = None,
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
    run_id: str | None = None,
    reasoning_effort: str | None = None,
) -> dict:
    """Quote every request, refuse an over-cap reservation, then score or dry-run.

    ``transport`` is ``(body: bytes, key: str) -> dict``. When it is omitted a
    real run uses the frozen Responses transport. A dry run never calls it
    and never reads the key.
    """
    _check_controls(seed, resamples, baseline_rate)
    if type(repeats) is not int or not 1 <= repeats <= 20:
        raise ValueError("repeats must be an integer from 1 to 20")
    if dry_run and output is not None:
        raise ValueError("dry run does not write a receipt")
    effort = resolve_effort(model, reasoning_effort)
    config = build_config(
        model=model,
        max_run_usd=max_run_usd,
        acknowledged=acknowledged,
        rates=rates,
        max_output_tokens=max_output_tokens,
    )
    manifest, cases = load_live_cases(repo)
    quotes = [_quote(staged, case, config, effort) for case in cases]
    instructions = _one_instructions_hash(quotes)
    reserved = sum(item["reserved_cost_usd"] for item in quotes) * repeats
    if reserved > config["max_run_usd"]:
        raise ReservationError(reserved, config["max_run_usd"])
    plan = _dry_plan(config, manifest, cases, repeats, instructions, reserved, effort, quotes)
    if dry_run:
        return plan
    if env_file is not None:
        _load_model_key(env_file, config["api_key_env"])
    key = os.environ.get(config["api_key_env"])
    if not key:
        raise ValueError("explicit personal API key is absent")
    send = transport or _default_send
    receipt = _execute(
        repo,
        staged,
        cases,
        quotes,
        config,
        key,
        send,
        plan,
        seed=seed,
        resamples=resamples,
        baseline_rate=baseline_rate,
        run_id=run_id or uuid.uuid4().hex,
    )
    if output is not None:
        write_json(output, receipt)
    return receipt


def format_dry_run(plan: dict) -> str:
    """Plain-text dry run. No receipt and no request."""
    recommended = plan["recommended_cap_usd"]
    shown = "none" if recommended is None else f"{recommended:.2f}"
    lines = [
        "live-eval dry run",
        f"model: {plan['model']}",
        f"reasoning_effort: {plan['reasoning_effort']}",
        f"price_tier: {plan['price_tier']}",
        f"repeats: {plan['repeats']}",
        f"cases: {plan['cases']}",
        f"planned_requests: {plan['planned_requests']}",
        f"reserved_usd: {plan['reserved_usd']:.6f}",
        f"max_run_usd: {plan['max_run_usd']:.6f}",
        f"recommended_cap_usd: {shown}",
        "fits_cap: true",
        f"instructions_sha256: {plan['instructions_sha256']}",
        f"case_set_sha256: {plan['case_set_sha256']}",
        f"fixture_sha256: {plan['fixture_sha256']}",
        f"rubric_version: {plan['rubric_version']}",
        "prices_rechecked: false",
        "scheduled: false",
        plan["pre_run"],
    ]
    return "\n".join(lines) + "\n"


def add_arguments(parser) -> None:
    """Flags shared by the analyst subcommand and ``python -m`` entry."""
    parser.add_argument("--model", required=True)
    parser.add_argument("--max-run-usd", type=float, required=True)
    parser.add_argument("--staged", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=DEFAULT_REPEATS)
    parser.add_argument("--acknowledge-personal-account", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--baseline-rate", type=float)
    parser.add_argument("--input-usd-per-million", type=float)
    parser.add_argument("--output-usd-per-million", type=float)
    parser.add_argument("--cache-write-usd-per-million", type=float)
    parser.add_argument("--cached-input-usd-per-million", type=float)
    parser.add_argument("--max-output-tokens", type=int, default=DEFAULT_MAX_OUTPUT_TOKENS)
    parser.add_argument(
        "--reasoning-effort",
        default=None,
        help="Omit for the model default: none on OpenAI ids, low on grok-4.7.",
    )


def execute_from_args(repo: Path, args) -> int:
    """CLI body. Returns a process code. Policy failures print to stderr."""
    import sys

    if not args.dry_run and args.output is None:
        print("live-eval: a real run needs --output", file=sys.stderr)
        return 2
    try:
        rates = _rates_from_args(args)
        result = run(
            repo,
            args.staged,
            model=args.model,
            max_run_usd=args.max_run_usd,
            acknowledged=args.acknowledge_personal_account,
            repeats=args.repeats,
            dry_run=args.dry_run,
            env_file=args.env_file,
            output=args.output,
            seed=args.seed,
            baseline_rate=args.baseline_rate,
            rates=rates,
            max_output_tokens=args.max_output_tokens,
            reasoning_effort=args.reasoning_effort,
        )
    except (OSError, TimeoutError, ValueError) as exc:
        print(f"live-eval: {exc}", file=sys.stderr)
        return 1
    if result.get("dry_run"):
        print(format_dry_run(result), end="")
        return 0
    print(_summary(result))
    return 0 if result["complete"] else 1


def main(argv: list[str] | None = None) -> int:
    """``python -m chess_analytics.analyst.live_runner``."""
    import argparse

    parser = argparse.ArgumentParser(description="Offline-capable live analyst eval runner")
    parser.add_argument("--project", type=Path, default=Path.cwd())
    add_arguments(parser)
    args = parser.parse_args(argv)
    return execute_from_args(args.project.resolve(), args)


def _load_model_key(env_file: Path, key_env: str) -> None:
    """Load one named key. The OpenAI and xAI variables are not interchangeable."""
    if os.environ.get(key_env):
        return
    matches = []
    for raw in env_file.read_text().splitlines():
        line = raw.strip()
        if line.startswith("export "):
            line = line[7:].strip()
        if line.startswith(f"{key_env}="):
            value = line.split("=", 1)[1].strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            matches.append(value)
    if len(matches) != 1 or not matches[0]:
        raise ValueError("env file must contain exactly one named personal API key")
    os.environ[key_env] = matches[0]


def _default_send(body: bytes, key: str) -> dict:
    from chess_analytics.analyst.provider import _default_transport

    return _default_transport(body, key)


def _quote(staged: Path, case: dict, config: dict, effort: str) -> dict:
    quote = quote_request(staged, case["question"], config, "semantic_context", effort)
    payload = json.loads(quote["body"])
    if payload.get("reasoning") != {"effort": effort}:
        raise ValueError("quoted reasoning effort does not match the run")
    if payload.get("input") != case["question"]:
        raise ValueError("quoted input is not the case question")
    instructions = payload.get("instructions")
    if not isinstance(instructions, str) or not instructions:
        raise ValueError("quoted instructions are empty")
    quote["instructions_sha256"] = hashlib.sha256(instructions.encode()).hexdigest()
    return quote


def _one_instructions_hash(quotes: list[dict]) -> str:
    hashes = {item["instructions_sha256"] for item in quotes}
    if len(hashes) != 1:
        raise ValueError("instructions hash differs across cases")
    return hashes.pop()


def _dry_plan(config, manifest, cases, repeats, instructions, reserved, effort, quotes) -> dict:
    tiers = {item["price_tier"] for item in quotes}
    if len(tiers) != 1:
        raise ValueError("price tier differs across cases")
    return {
        "case_set_sha256": manifest["case_set_sha256"],
        "cases": len(cases),
        "dry_run": True,
        "fixture_sha256": manifest["fixture_sha256"],
        "instructions_sha256": instructions,
        "kind": "analyst_live_v1_dry_run",
        "max_run_usd": config["max_run_usd"],
        "model": config["model"],
        "planned_requests": len(cases) * repeats,
        "pre_run": _pre_run_line(config["model"]),
        "price_checked_utc_date": PRICE_CHECKED_UTC_DATE,
        "price_tier": tiers.pop(),
        "prices_rechecked": False,
        "reasoning_effort": effort,
        "recommended_cap_usd": RECOMMENDED_CAP_USD.get(config["model"]),
        "repeats": repeats,
        "reserved_usd": reserved,
        "rubric_version": RUBRIC_VERSION,
        "scheduled": False,
    }


def _pre_run_line(model: str) -> str:
    if model == GROK_MODEL_ID:
        return (
            "pre_run: recheck grok-4.7 prices, the 200k tier, and the reasoning effort; "
            "reasoning cannot be none"
        )
    return "pre_run: recheck the Sol model id, reasoning.effort=none, and prices before a live run"


def _execute(repo, staged, cases, quotes, config, key, send, plan, **options) -> dict:
    rows = []
    spent = 0.0
    incomplete = None
    started = time.monotonic()
    for repeat in range(plan["repeats"]):
        for case, quote in zip(cases, quotes, strict=True):
            if time.monotonic() - started > LIVE_EVAL_WALL_CLOCK_SECONDS:
                incomplete = "wall_clock"
                break
            if spent + quote["reserved_cost_usd"] > config["max_run_usd"]:
                incomplete = "budget_exceeded"
                break
            row, stop, spent = _one_request(staged, case, quote, config, key, send, repeat, spent)
            rows.append(row)
            if stop:
                incomplete = stop
                break
        if incomplete:
            break
    return _receipt(repo, rows, plan, config, incomplete, **options)


def _one_request(staged, case, quote, config, key, send, repeat, spent):
    try:
        response = send(quote["body"], key)
    except Exception as exc:
        message = _redact_exception(exc, key)
        failed = _failed_row(case, repeat, quote, "transport_failure", message)
        return failed, "transport_failure", spent
    try:
        row, cost = _completed_row(staged, case, quote, config, response, repeat)
    except Exception as exc:
        message = _redact_exception(exc, key)
        return _failed_row(case, repeat, quote, "runner_error", message), "runner_error", spent
    if cost is None:
        return row, "unknown_usage", spent + quote["reserved_cost_usd"]
    spent += cost
    if spent > config["max_run_usd"]:
        return row, "budget_exceeded", spent
    return row, None, spent


def _completed_row(staged, case, quote, config, response, repeat) -> tuple[dict, float | None]:
    usage = response.get("usage") if isinstance(response, dict) else None
    resolved = response.get("model") if isinstance(response, dict) else None
    try:
        cost, basis = price_usage(config, usage)
    except ValueError:
        cost, basis = None, None
    plan, argument_repairs, semantic_repairs, repaired, extraction = _parsed_plan(
        staged, case, response
    )
    if plan is None:
        scored = _hallucination(case)
        would_pass = None
    else:
        scored = score_live_plan(staged, case, plan)
        would_pass = None
        if semantic_repairs and isinstance(repaired, dict):
            would_pass = score_live_plan(staged, case, repaired)["passed"]
    row = _row(
        case,
        repeat,
        quote,
        status="completed",
        plan=plan,
        scored=scored,
        argument_repairs=argument_repairs,
        semantic_repairs=semantic_repairs,
        extraction=extraction,
        would_pass=would_pass,
        usage=usage if isinstance(usage, dict) else None,
        cost=cost,
        basis=basis,
        resolved=resolved if isinstance(resolved, str) else None,
        error=None,
    )
    return row, cost


def _parsed_plan(staged, case, response):
    empty = _empty_extraction()
    if not isinstance(response, dict):
        return None, [], [], None, empty
    try:
        extracted, selection = _extract_plan(response)
        plan, argument_repairs = _normalize_plan(extracted)
        repaired, semantic_repairs = _repair_opening_usage(
            case["question"], plan, CheckedTools(staged)
        )
    except (TypeError, ValueError):
        return None, [], [], None, empty
    return plan, argument_repairs, semantic_repairs, repaired, _extraction_counts(selection)


def _hallucination(case: dict) -> dict:
    missed = case["severity"] == "high"
    return {
        "caveats": [],
        "failures": ["plan_hallucination"],
        "high_severity_miss": missed,
        "over_abstention": False,
        "passed": False,
        "unsafe_answer": False,
    }


def _failed_row(case, repeat, quote, reason, message) -> dict:
    return _row(
        case,
        repeat,
        quote,
        status="failed",
        plan=None,
        scored=None,
        argument_repairs=[],
        semantic_repairs=[],
        extraction=_empty_extraction(),
        would_pass=None,
        usage=None,
        cost=None,
        basis=None,
        resolved=None,
        error=f"{reason}: {message}",
    )


def _row(case, repeat, quote, **fields) -> dict:
    scored = fields["scored"] or {}
    argument_repairs = list(fields["argument_repairs"])
    semantic_repairs = list(fields["semantic_repairs"])
    extraction = fields["extraction"]
    passed = None if fields["scored"] is None else scored["passed"]
    return {
        "argument_repairs": argument_repairs,
        "case_id": case["id"],
        "caveats": list(scored.get("caveats") or []),
        "cost_basis": fields["basis"],
        "error": fields["error"],
        "failures": list(scored.get("failures") or []),
        "gross_cost_usd": fields["cost"],
        "high_severity_miss": bool(scored.get("high_severity_miss")),
        "model_plan_before_semantic_repair": fields["plan"],
        "over_abstention": bool(scored.get("over_abstention")),
        "passed": passed,
        "recovered_argument_suffixes": extraction["recovered_argument_suffixes"],
        "recovered_inert_suffix_characters": extraction["recovered_inert_suffix_characters"],
        "recovered_repeated_plan_objects": extraction["recovered_repeated_plan_objects"],
        "repair_count": (
            len(argument_repairs) + len(semantic_repairs) + _extraction_events(extraction)
        ),
        "repeat": repeat,
        "reserved_cost_usd": quote["reserved_cost_usd"],
        "resolved_model": fields["resolved"],
        "semantic_repair_would_pass": fields["would_pass"],
        "semantic_repairs": semantic_repairs,
        "severity": case["severity"],
        "status": fields["status"],
        "template_family": case["template_family"],
        "unsafe_answer": bool(scored.get("unsafe_answer")),
        "usage": fields["usage"],
    }


def _receipt(repo, rows, plan, config, incomplete, **options) -> dict:
    scored = [row for row in rows if row["passed"] is not None]
    passed = sum(bool(row["passed"]) for row in scored)
    trials = len(scored)
    known = [row["gross_cost_usd"] for row in rows if row["gross_cost_usd"] is not None]
    unknown = sum(
        row["reserved_cost_usd"]
        for row in rows
        if row["status"] == "completed" and row["gross_cost_usd"] is None
    )
    models = {row["resolved_model"] for row in rows if row["resolved_model"]}
    alert = None
    if options["baseline_rate"] is not None and incomplete is None and trials:
        alert = binomial_alert(passed, trials, options["baseline_rate"])
    receipt = {
        "base_rubric_version": "portfolio-1.0",
        "baseline_alert": alert,
        "case_set_sha256": plan["case_set_sha256"],
        "cases": plan["cases"],
        "complete": incomplete is None,
        "fixture_sha256": plan["fixture_sha256"],
        "flaky_cases": flaky_case_ids(rows),
        "frozen_file_sha256": _frozen_hashes(repo),
        "hard_fail": hard_fail(rows),
        "headline_pass_rate": None if not trials else passed / trials,
        "headline_passed": passed,
        "high_severity_misses": sum(bool(row["high_severity_miss"]) for row in rows),
        "incomplete_reason": incomplete,
        "instructions_sha256": plan["instructions_sha256"],
        "kind": "analyst_live_v1_receipt",
        "known_gross_cost_usd": sum(known),
        "unknown_cost_reservation_usd": unknown,
        "max_run_usd": config["max_run_usd"],
        "model": config["model"],
        "over_abstention": sum(bool(row["over_abstention"]) for row in rows),
        "planned_requests": plan["planned_requests"],
        "price_checked_utc_date": PRICE_CHECKED_UTC_DATE,
        "prices_rechecked": False,
        "reasoning_effort": plan["reasoning_effort"],
        "receipt_version": RECEIPT_VERSION,
        "repair_counts": {
            "argument": sum(len(row["argument_repairs"]) for row in rows),
            "extraction": sum(_extraction_events(_extraction_from_row(row)) for row in rows),
            "semantic": sum(len(row["semantic_repairs"]) for row in rows),
        },
        "repeats": plan["repeats"],
        "reserved_usd": plan["reserved_usd"],
        "resolved_model": models.pop() if len(models) == 1 else None,
        "rows": rows,
        "rubric_version": RUBRIC_VERSION,
        "run_id": options["run_id"],
        "scheduled": False,
        "stats": None if incomplete else _stats(rows, plan, options),
        "token_usage": _tokens(rows),
        "unsafe_answer": sum(bool(row["unsafe_answer"]) for row in rows),
    }
    missing = set(RECEIPT_FIELDS) - set(receipt)
    if missing or any(set(ROW_FIELDS) - set(row) for row in rows):
        raise RuntimeError("receipt schema drifted")
    return receipt


def _stats(rows, plan, options) -> dict:
    grouped: dict[str, list[bool]] = {}
    for row in rows:
        if row["passed"] is None:
            continue
        grouped.setdefault(row["case_id"], []).append(bool(row["passed"]))
    repeats = [grouped[case_id] for case_id in grouped]
    if not repeats:
        return {"bootstrap": None, "hard_fail": hard_fail(rows), "wilson": None}
    successes = sum(sum(flags) for flags in repeats)
    trials = sum(len(flags) for flags in repeats)
    return {
        "bootstrap": cluster_bootstrap(
            repeats, seed=options["seed"], resamples=options["resamples"]
        ),
        "hard_fail": hard_fail(rows),
        "wilson": wilson_interval(successes, trials) if trials else None,
    }


def _tokens(rows: list[dict]) -> dict:
    incoming = 0
    outgoing = 0
    counted = 0
    for row in rows:
        usage = row["usage"]
        if not isinstance(usage, dict):
            continue
        if type(usage.get("input_tokens")) is int and type(usage.get("output_tokens")) is int:
            incoming += usage["input_tokens"]
            outgoing += usage["output_tokens"]
            counted += 1
    return {"input_tokens": incoming, "output_tokens": outgoing, "priced_requests": counted}


def _frozen_hashes(repo: Path) -> dict:
    """Hash the working tree the operator passed in, not the installed wheel."""
    hashes = {}
    for name in FROZEN_FILES:
        path = repo / name
        if not path.is_file():
            raise ValueError(f"frozen file missing: {name}")
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def _rates_from_args(args) -> dict | None:
    keys = (
        "input_usd_per_million",
        "output_usd_per_million",
        "cache_write_usd_per_million",
        "cached_input_usd_per_million",
    )
    present = [key for key in keys if getattr(args, key) is not None]
    if not present:
        return None
    if len(present) != len(keys):
        raise ValueError("pass all four price rates together")
    return {key: getattr(args, key) for key in keys}


def _check_controls(seed: int, resamples: int, baseline_rate: float | None) -> None:
    """Reject controls that would only fail after the requests were sent."""
    if type(seed) is not int or seed < 0:
        raise ValueError("seed must be a non-negative integer")
    if type(resamples) is not int or resamples < 1:
        raise ValueError("resamples must be a positive integer")
    if baseline_rate is not None:
        _check_rate(baseline_rate)


def _empty_extraction() -> dict:
    return {
        "recovered_argument_suffixes": 0,
        "recovered_inert_suffix_characters": 0,
        "recovered_repeated_plan_objects": 0,
    }


def _extraction_counts(selection: dict) -> dict:
    suffixes = selection.get("recovered_argument_suffixes") or []
    repeated = selection.get("recovered_repeated_plan_objects")
    inert = selection.get("recovered_inert_suffix_characters") or 0
    objects = 0
    if isinstance(repeated, dict):
        objects = int(repeated.get("identical_complete_objects") or 0)
    return {
        "recovered_argument_suffixes": len(suffixes),
        "recovered_inert_suffix_characters": int(inert),
        "recovered_repeated_plan_objects": objects,
    }


def _extraction_from_row(row: dict) -> dict:
    return {
        "recovered_argument_suffixes": row["recovered_argument_suffixes"],
        "recovered_inert_suffix_characters": row["recovered_inert_suffix_characters"],
        "recovered_repeated_plan_objects": row["recovered_repeated_plan_objects"],
    }


def _extraction_events(counts: dict) -> int:
    """Events beside the headline: suffixes, extra repeated objects, inert suffix."""
    repeated = counts["recovered_repeated_plan_objects"]
    extras = repeated - 1 if repeated else 0
    inert = 1 if counts["recovered_inert_suffix_characters"] else 0
    return counts["recovered_argument_suffixes"] + extras + inert


_ABSOLUTE_PATH = re.compile(
    r"(?:[A-Za-z]:\\(?:[^\\/:*?\"<>|\r\n]+\\)*[^\\/:*?\"<>|\r\n]+)"
    r"|"
    r"(?:(?<=^)|(?<=[\s'\"=]))/(?:[^/\s'\"]+/)+[^/\s'\"]*"
)


def _redact_exception(exc: BaseException, key: str) -> str:
    return f"{type(exc).__name__}: {_redact(str(exc), key)}"


def _redact(message: str, key: str) -> str:
    """Drop key fragments of length 6 or more, then absolute paths."""
    return _ABSOLUTE_PATH.sub("[path]", _redact_key_runs(message, key))


def _redact_key_runs(message: str, key: str) -> str:
    if not key:
        return message
    if len(key) < 6:
        return message.replace(key, "[redacted]")
    fragments = {
        key[start:end] for start in range(len(key)) for end in range(start + 6, len(key) + 1)
    }
    for fragment in sorted(fragments, key=len, reverse=True):
        message = message.replace(fragment, "[redacted]")
    return message


def _summary(receipt: dict) -> str:
    passed = receipt["headline_passed"]
    planned = receipt["planned_requests"]
    return (
        f"live-eval {receipt['run_id']} complete={str(receipt['complete']).lower()} "
        f"passed={passed}/{planned} hard_fail={str(receipt['hard_fail']).lower()} "
        f"cost_usd={receipt['known_gross_cost_usd']:.6f}"
    )


if __name__ == "__main__":
    raise SystemExit(main())
