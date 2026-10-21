"""Checks and the job summary for the manual live-eval workflow.

The workflow calls this before any provider request. It does not probe the
API, does not read an API key, and does not write a receipt.
"""

import argparse
import json
import os
import re
import sys
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

PRICE_CHECK_MAX_AGE_DAYS = 14
MAX_REPEATS = 20
CAPS_USD = {
    "gpt-6-luna": Decimal("0.50"),
    "gpt-6-sol": Decimal("10"),
    "grok-4.7": Decimal("10"),
}
EFFORTS = {
    "gpt-6-luna": ("none",),
    "gpt-6-sol": ("none",),
    "grok-4.7": ("low", "medium", "high", "xhigh"),
}
DEFAULT_EFFORT = {
    "gpt-6-luna": "none",
    "gpt-6-sol": "none",
    "grok-4.7": "low",
}
PRICE_DATE_PATH = Path("src/chess_analytics/analyst/preflight.py")
_DATE_LINE = re.compile(r'^DEFAULT_PRICE_CHECKED_UTC_DATE = "(\d{4}-\d{2}-\d{2})"$', re.MULTILINE)
_REPEATS = re.compile(r"^[1-9][0-9]*$")
_DECIMAL = re.compile(r"^(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")
CHECKLIST_LINES = (
    "### Pre-run checklist",
    "",
    "Before this job reads a key or calls the provider:",
    "",
    "1. Recheck the provider model page. Past Sol runs use gpt-6-sol. "
    "The approved plan records that OpenAI's page has listed gpt-6.1-sol. "
    "The xAI id is grok-4.7.",
    "2. Confirm the reasoning effort. OpenAI ids in this harness accept "
    "reasoning.effort none, and the quote sends none. grok-4.7 cannot disable "
    "reasoning. Allowed efforts are low, medium, high, and xhigh. The headline "
    "comparison is low at 5 repeats. medium and high are a 1-repeat sensitivity "
    "check and are not a second 5-repeat headline. This job does not probe the API.",
    "3. Recheck prices. The recorded date is DEFAULT_PRICE_CHECKED_UTC_DATE in "
    "src/chess_analytics/analyst/preflight.py. pricing.py does not store that date. "
    f"This job stops when the date is older than {PRICE_CHECK_MAX_AGE_DAYS} days "
    "unless allow_stale_price_check is true. The receipt keeps prices_rechecked false. "
    "grok-4.7 below 200k prompt tokens is $2 input, $0.50 cached input, and $6 output "
    "per 1M tokens. At 200k prompt tokens the whole request uses $4, $1, and $12. "
    "Reasoning tokens bill as output.",
)


class DispatchError(ValueError):
    """A dispatch input or the recorded price-check date refuses the run."""


def checklist_text() -> str:
    return "\n".join(CHECKLIST_LINES) + "\n"


def price_check_date(text: str) -> date:
    """The one recorded date. pricing.py does not store it."""
    found = _DATE_LINE.findall(text)
    if len(found) != 1:
        raise DispatchError("preflight.py must contain one DEFAULT_PRICE_CHECKED_UTC_DATE")
    return date.fromisoformat(found[0])


def enforce_price_check(checked: date, today: date, *, allow_stale: bool) -> int:
    """Return the age in days. Refuse a stale date unless the operator overrode it."""
    if today < checked:
        raise DispatchError("price-check date is in the future")
    age = (today - checked).days
    if age > PRICE_CHECK_MAX_AGE_DAYS and not allow_stale:
        raise DispatchError(
            f"recorded price check {checked.isoformat()} is {age} days old "
            f"(limit {PRICE_CHECK_MAX_AGE_DAYS}). Recheck the Sol model id, "
            "reasoning.effort for the chosen model, grok-4.7 prices including the "
            "200k tier, and the OpenAI prices, then set allow_stale_price_check. "
            "This command does not probe the API."
        )
    return age


def validate_dispatch(
    model: str,
    repeats: str,
    max_run_usd: str,
    acknowledge: str,
    reasoning_effort: str = "model-default",
) -> dict:
    """Refuse a model, effort, repeat count, cap, or acknowledgement outside the contract."""
    if model not in CAPS_USD:
        raise DispatchError("model must be gpt-6-luna, gpt-6-sol, or grok-4.7")
    effort = resolve_effort(model, reasoning_effort)
    if acknowledge != "true":
        raise DispatchError("acknowledge_personal_account must be true")
    if not _REPEATS.fullmatch(repeats):
        raise DispatchError("repeats must be an integer from 1 to 20")
    count = int(repeats)
    if count > MAX_REPEATS:
        raise DispatchError("repeats must be an integer from 1 to 20")
    if not _DECIMAL.fullmatch(max_run_usd):
        raise DispatchError("max_run_usd must be a positive decimal")
    amount = Decimal(max_run_usd)
    ceiling = CAPS_USD[model]
    if amount <= 0:
        raise DispatchError("max_run_usd must be a positive decimal")
    if amount > ceiling:
        raise DispatchError(f"max_run_usd {amount} is above the {model} 5-repeat cap {ceiling}")
    return {
        "cap_usd": ceiling,
        "max_run_usd": amount,
        "model": model,
        "reasoning_effort": effort,
        "repeats": count,
    }


def resolve_effort(model: str, effort: str) -> str:
    """model-default keeps OpenAI on none and grok-4.7 on low."""
    chosen = DEFAULT_EFFORT[model] if effort in ("", "model-default") else effort
    allowed = EFFORTS[model]
    if chosen not in allowed:
        raise DispatchError(
            f"{model} does not accept reasoning effort {chosen}; allowed: {', '.join(allowed)}"
        )
    return chosen


def format_summary(receipt: dict) -> str:
    """Job-summary markdown from one receipt. Repair counts sit beside the raw rate."""
    try:
        return _format_summary(receipt)
    except (KeyError, TypeError, ValueError) as exc:
        raise DispatchError(f"receipt is missing a summary field: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    """CLI used by the workflow. Returns 1 on a policy refusal."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("checklist")
    price = sub.add_parser("check-price")
    price.add_argument("--today", help="YYYY-MM-DD test clock. The workflow does not pass this.")
    sub.add_parser("check-inputs")
    summary = sub.add_parser("summarize")
    summary.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "checklist":
            emit(checklist_text())
        elif args.command == "check-price":
            today = date.fromisoformat(args.today) if args.today else datetime.now(UTC).date()
            report_price_check(args.repo, today)
        elif args.command == "check-inputs":
            report_inputs()
        else:
            write_summary(args.receipt)
    except DispatchError as exc:
        print(f"live-eval dispatch: {exc}", file=sys.stderr)
        return 1
    return 0


def report_price_check(repo: Path, today: date) -> None:
    text = (repo / PRICE_DATE_PATH).read_text(encoding="utf-8")
    checked = price_check_date(text)
    allow = _allow_stale()
    age = enforce_price_check(checked, today, allow_stale=allow)
    print(
        f"price_checked_utc_date: {checked.isoformat()}\n"
        f"age_days: {age}\n"
        f"limit_days: {PRICE_CHECK_MAX_AGE_DAYS}\n"
        f"allow_stale_price_check: {str(allow).lower()}\n"
    )


def report_inputs() -> None:
    chosen = validate_dispatch(
        _required("LIVE_EVAL_MODEL"),
        _required("LIVE_EVAL_REPEATS"),
        _required("LIVE_EVAL_MAX_RUN_USD"),
        _required("LIVE_EVAL_ACKNOWLEDGE"),
        os.environ.get("LIVE_EVAL_REASONING_EFFORT", "model-default"),
    )
    _publish_effort(chosen["reasoning_effort"])
    print(
        f"model: {chosen['model']}\n"
        f"reasoning_effort: {chosen['reasoning_effort']}\n"
        f"repeats: {chosen['repeats']}\n"
        f"max_run_usd: {chosen['max_run_usd']}\n"
        f"cap_usd: {chosen['cap_usd']}\n"
        "acknowledge_personal_account: true\n"
    )


def write_summary(path: Path) -> None:
    if not path.is_file():
        emit("### Live eval receipt\n\nNo receipt was written.\n")
        return
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DispatchError(f"receipt is not json: {exc}") from exc
    if not isinstance(receipt, dict):
        raise DispatchError("receipt is not an object")
    emit(format_summary(receipt))


def emit(text: str) -> None:
    if not text.endswith("\n"):
        text += "\n"
    sys.stdout.write(text)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with Path(summary).open("a", encoding="utf-8") as handle:
            handle.write(text)


def _format_summary(receipt: dict) -> str:
    rate = receipt["headline_pass_rate"]
    if rate is None:
        rate_text = "unavailable"
    else:
        passed = receipt["headline_passed"]
        planned = receipt["planned_requests"]
        rate_text = f"{float(rate):.6f} ({passed}/{planned})"
    stats = receipt["stats"]
    wilson = None if stats is None else stats["wilson"]
    if wilson is None:
        interval = "unavailable"
    else:
        interval = (
            f"[{float(wilson['lower']):.6f}, {float(wilson['upper']):.6f}] "
            f"({wilson['successes']}/{wilson['trials']})"
        )
    repairs = receipt["repair_counts"]
    repair_text = (
        f"argument {repairs['argument']}, "
        f"extraction {repairs['extraction']}, "
        f"semantic {repairs['semantic']}"
    )
    repeat_label = "1 repeat" if receipt["repeats"] == 1 else f"{receipt['repeats']} repeats"
    lines = [
        "### Live eval receipt",
        f"- model: {receipt['model']}",
        f"- reasoning effort: {receipt['reasoning_effort']}",
        f"- repeats: {receipt['repeats']}",
        f"- headline raw pass rate for {repeat_label}: {rate_text}; repair counts: {repair_text}",
        f"- Wilson interval: {interval}",
        f"- hard_fail: {str(receipt['hard_fail']).lower()}",
        f"- gross cost USD: {float(receipt['known_gross_cost_usd']):.6f}",
        f"- complete: {str(receipt['complete']).lower()}",
    ]
    if receipt["repeats"] != 5:
        lines.append(
            f"- note: this pass rate is for {repeat_label} "
            "and is not a 5-repeat headline comparison"
        )
    reason = receipt.get("incomplete_reason")
    if reason:
        lines.append(f"- incomplete reason: {reason}")
    unknown = receipt["unknown_cost_reservation_usd"]
    if unknown:
        lines.append(f"- unknown cost reservation USD: {float(unknown):.6f}")
    return "\n".join(lines) + "\n"


def _publish_effort(effort: str) -> None:
    """Later steps, including the artifact name, read the resolved effort."""
    path = os.environ.get("GITHUB_ENV")
    if not path:
        return
    with Path(path).open("a", encoding="utf-8") as handle:
        handle.write(f"LIVE_EVAL_REASONING_EFFORT={effort}\n")
        handle.write(f"LIVE_EVAL_RESOLVED_EFFORT={effort}\n")


def _allow_stale() -> bool:
    raw = os.environ.get("LIVE_EVAL_ALLOW_STALE", "false")
    if raw == "true":
        return True
    if raw == "false":
        return False
    raise DispatchError("allow_stale_price_check must be true or false")


def _required(name: str) -> str:
    if name not in os.environ:
        raise DispatchError(f"missing {name}")
    return os.environ[name]


if __name__ == "__main__":
    raise SystemExit(main())
