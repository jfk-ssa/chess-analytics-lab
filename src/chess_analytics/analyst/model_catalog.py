"""Live-eval model catalog: efforts, endpoints, and grok-4.7 prices.

OpenAI rates stay in preflight.py and live_runner.py. This module adds the
xAI model without a new dependency. The price-check date stays the one
constant in preflight.py. pricing.py does not store that date.
"""

import math
from decimal import Decimal

GROK_MODEL_ID = "grok-4.7"
XAI_KEY_ENV = "CHESSLAB_XAI_API_KEY"
XAI_RESPONSES_URL = "https://api.x.ai/v1/responses"
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
PROMPT_CACHE_KEY = "chesslab-analyst-live-v1"
OPENAI_TIMEOUT_SECONDS = 30
XAI_TIMEOUT_SECONDS = 180
LONG_CONTEXT_PROMPT_TOKENS = 200_000
# Published 2026-10-20. The long-context rates bill the whole request.
GROK_LONG_INPUT_USD_PER_MILLION = 4.0
GROK_LONG_CACHED_USD_PER_MILLION = 1.0
GROK_LONG_OUTPUT_USD_PER_MILLION = 12.0
# Extra output tokens reserved for reasoning. grok-4.7 cannot set effort to
# none. The best-practices guide says these tokens do not count against
# max_output_tokens, and the docs publish no per-effort maximum. These
# ceilings are the harness reservation, not a measured usage and not an
# API-enforced cap. xhigh is accepted by the API and is outside the
# low/medium/high sensitivity sweep.
REASONING_RESERVE_TOKENS = {
    "low": 2_048,
    "medium": 8_192,
    "high": 16_384,
    "xhigh": 32_768,
}
LIVE_EVAL_EFFORTS = {
    "gpt-6-luna": ("none",),
    "gpt-6-sol": ("none",),
    GROK_MODEL_ID: ("low", "medium", "high", "xhigh"),
}
LIVE_EVAL_DEFAULT_EFFORT = {
    "gpt-6-luna": "none",
    "gpt-6-sol": "none",
    GROK_MODEL_ID: "low",
}
RECOMMENDED_CAP_USD = {
    "gpt-6-luna": 0.50,
    "gpt-6-sol": 10.0,
    GROK_MODEL_ID: 10.0,
}
# The live job stops at this wall clock. Measured OpenAI live steps on
# 2026-10-20 and 2026-10-21 were 413s (Luna) and 379s (Sol) for 240
# requests. 150 minutes allows about 37s average on that same request
# count, about 22 times the slower of those two, and it cuts a 180s hang
# off well before the 360-minute GitHub-hosted limit.
LIVE_EVAL_JOB_TIMEOUT_MINUTES = 150
# The runner writes the receipt before the job timeout. One in-flight
# request can still use the 180s socket timeout after this clock trips.
LIVE_EVAL_WALL_CLOCK_SECONDS = 140 * 60
# xAI cost_in_usd_ticks. One dollar is 10^10 ticks.
USD_TICKS = 10_000_000_000


def grok_short_rates() -> dict:
    """Short-context token prices. xAI publishes no cache-write premium."""
    return {
        "cached_input_usd_per_million": 0.5,
        "input_usd_per_million": 2.0,
        "output_usd_per_million": 6.0,
    }


def resolve_effort(model: str, effort: str | None) -> str:
    """Map a missing effort to the model default and reject other combinations."""
    allowed = LIVE_EVAL_EFFORTS.get(model)
    if effort in (None, "", "model-default"):
        chosen = LIVE_EVAL_DEFAULT_EFFORT.get(model, "none")
    else:
        chosen = effort
    if allowed is None:
        if chosen != "none":
            raise ValueError(
                "reasoning effort none is the only value this harness sends for this model"
            )
        return "none"
    if chosen not in allowed:
        names = ", ".join(allowed)
        raise ValueError(f"{model} does not accept reasoning effort {chosen}; allowed: {names}")
    return chosen


def endpoint_for(model: str) -> str:
    if model == GROK_MODEL_ID:
        return XAI_RESPONSES_URL
    return OPENAI_RESPONSES_URL


def timeout_for(model: str) -> int:
    if model == GROK_MODEL_ID:
        return XAI_TIMEOUT_SECONDS
    return OPENAI_TIMEOUT_SECONDS


def prompt_token_ceiling(body: bytes) -> int:
    """ASCII JSON bytes plus the same 1,000-token envelope the OpenAI quote uses.

    A token is at least one ASCII byte, so this is a ceiling, not a tokenizer
    count. The long-context tier applies when the ceiling reaches 200k.
    """
    return len(body) + 1000


def grok_tier_rates(prompt_tokens: int, config: dict) -> tuple[float, float, float, str]:
    """Return input, cached-input, and output rates, plus the tier name.

    At or above 200k prompt tokens the published long-context rates replace
    the short rates for every token in the request. Below that, the config
    rates are the short-context prices (or an explicit override).
    """
    if prompt_tokens >= LONG_CONTEXT_PROMPT_TOKENS:
        return (
            GROK_LONG_INPUT_USD_PER_MILLION,
            GROK_LONG_CACHED_USD_PER_MILLION,
            GROK_LONG_OUTPUT_USD_PER_MILLION,
            "long",
        )
    return (
        config["input_usd_per_million"],
        config["cached_input_usd_per_million"],
        config["output_usd_per_million"],
        "short",
    )


def grok_reservation_usd(body: bytes, config: dict, effort: str) -> tuple[float, str]:
    """Worst-case quote: uncached input, visible output, and the reasoning ceiling.

    Cached input is cheaper, and xAI publishes no cache-write premium, so the
    input rate is the uncached one. The long-context tier is used only when
    the prompt ceiling can reach it.
    """
    prompt_tokens = prompt_token_ceiling(body)
    input_rate, cached_rate, output_rate, tier = grok_tier_rates(prompt_tokens, config)
    output_tokens = config["max_output_tokens"] + REASONING_RESERVE_TOKENS[effort]
    cost = (prompt_tokens * max(input_rate, cached_rate) + output_tokens * output_rate) / 1_000_000
    if not math.isfinite(cost):
        raise ValueError("request cost bound is not finite")
    return cost, tier


def price_grok_usage(config: dict, usage: object) -> tuple[float, str]:
    """Price one grok-4.7 usage object without going below the reported bill.

    Billed output is max(output + reasoning, total - input) unless reasoning
    is contained in output. Contained means reasoning_tokens is at most
    output_tokens and total_tokens equals input plus output. The documented
    32 / 9 / 110 / 151 split is not contained, so reasoning is added. A total
    larger than input plus output plus reasoning bills that gap. A
    non-negative cost_in_usd_ticks converts at 10^10 ticks per dollar, and
    the price is the max of that charge and the token reconstruction.
    num_server_side_tools_used above zero requires ticks. Inconsistent or
    ambiguous usage raises so the runner charges the quote and stops.
    """
    if (
        not isinstance(usage, dict)
        or not _count(usage.get("input_tokens"))
        or not _count(usage.get("output_tokens"))
    ):
        raise ValueError("provider usage absent; cost cannot be established")
    input_tokens = usage["input_tokens"]
    output_tokens = usage["output_tokens"]
    cached, cache_basis = _cached_tokens(usage, input_tokens)
    billed_output, reasoning_basis = _billed_output(usage, input_tokens, output_tokens)
    ticks = _present_count(usage, "cost_in_usd_ticks")
    _require_ticks_for_tools(usage, ticks)
    input_rate, cached_rate, output_rate, tier = grok_tier_rates(input_tokens, config)
    regular = input_tokens - cached
    reconstruction = (
        regular * input_rate + cached * cached_rate + billed_output * output_rate
    ) / 1_000_000
    if not math.isfinite(reconstruction):
        raise ValueError("provider cost cannot be established as a finite amount")
    cost, reasoning_basis = _with_ticks(reconstruction, ticks, reasoning_basis)
    return cost, f"grok_{cache_basis}_{tier}_{reasoning_basis}"


def grok_billed_output(usage: dict) -> int:
    """Billed output tokens for one grok usage object, using the same rule as pricing."""
    return _billed_output(usage, usage["input_tokens"], usage["output_tokens"])[0]


def _cached_tokens(usage: dict, input_tokens: int) -> tuple[int, str]:
    details = usage.get("input_tokens_details")
    if not isinstance(details, dict) or "cached_tokens" not in details:
        return 0, "conservative_input"
    cached = details["cached_tokens"]
    if not _count(cached) or cached > input_tokens:
        raise ValueError("provider usage absent; cost cannot be established")
    return cached, "reported_cached"


def _billed_output(usage: dict, input_tokens: int, output_tokens: int) -> tuple[int, str]:
    """Return billed output tokens and the basis name.

    Contained reasoning is not added. Every other known reading contributes
    through max(output + reasoning, total - input). A total below the input,
    or a usage object with neither reasoning nor a total, cannot be priced.
    """
    reasoning = _reasoning_count(usage)
    total = _present_count(usage, "total_tokens")
    if total is not None and total < input_tokens:
        raise ValueError("provider usage absent; cost cannot be established")
    contained = (
        reasoning is not None
        and total is not None
        and reasoning <= output_tokens
        and total == input_tokens + output_tokens
    )
    if contained:
        return output_tokens, "reasoning_included"
    if reasoning is None and total is None:
        raise ValueError("provider usage absent; cost cannot be established")
    extra = 0 if reasoning is None else reasoning
    from_parts = output_tokens + extra
    if total is None:
        return from_parts, "reasoning_added" if extra else "no_reasoning_detail"
    from_total = total - input_tokens
    billed = max(from_parts, from_total)
    if from_total > from_parts:
        return billed, "total_gap"
    if extra:
        return billed, "reasoning_added"
    return billed, "no_reasoning_detail"


def _reasoning_count(usage: dict) -> int | None:
    if "output_tokens_details" not in usage:
        return None
    details = usage["output_tokens_details"]
    if not isinstance(details, dict):
        raise ValueError("provider usage absent; cost cannot be established")
    return _present_count(details, "reasoning_tokens")


def _require_ticks_for_tools(usage: dict, ticks: int | None) -> None:
    tools = _present_count(usage, "num_server_side_tools_used")
    if tools and ticks is None:
        raise ValueError("server-side tool usage needs cost_in_usd_ticks")


def _with_ticks(reconstruction: float, ticks: int | None, basis: str) -> tuple[float, str]:
    """Keep the higher of the token reconstruction and the provider tick charge."""
    if ticks is None:
        return reconstruction, basis
    tick_cost = Decimal(ticks) / Decimal(USD_TICKS)
    if tick_cost <= Decimal(reconstruction):
        return reconstruction, basis
    rendered = float(tick_cost)
    while Decimal(rendered) < tick_cost:
        rendered = math.nextafter(rendered, math.inf)
    if not math.isfinite(rendered):
        raise ValueError("provider cost cannot be established as a finite amount")
    return rendered, "provider_ticks"


def _present_count(mapping: dict, key: str) -> int | None:
    if key not in mapping:
        return None
    value = mapping[key]
    if not _count(value):
        raise ValueError("provider usage absent; cost cannot be established")
    return value


def _count(value: object) -> bool:
    return type(value) is int and value >= 0
