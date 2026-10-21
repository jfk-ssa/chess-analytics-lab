"""Live-eval model catalog: efforts, endpoints, and grok-4.7 prices.

OpenAI rates stay in preflight.py and live_runner.py. This module adds the
xAI model without a new dependency. The price-check date stays the one
constant in preflight.py. pricing.py does not store that date.
"""

import math

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
    GROK_MODEL_ID: 5.0,
}


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
    """Price one grok-4.7 usage object. Reasoning tokens bill as output.

    The documented Responses usage split reports reasoning_tokens outside
    output_tokens: total_tokens = input + output + reasoning. When total_tokens
    equals input + output, reasoning is already inside output_tokens and is
    not added again. A missing total adds reasoning_tokens, which matches
    that documented split and over-bills if a response folds them in without
    saying so.
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
    extra, reasoning_basis = _reasoning_extra(usage, input_tokens, output_tokens)
    input_rate, cached_rate, output_rate, tier = grok_tier_rates(input_tokens, config)
    regular = input_tokens - cached
    billed_output = output_tokens + extra
    cost = (regular * input_rate + cached * cached_rate + billed_output * output_rate) / 1_000_000
    if not math.isfinite(cost):
        raise ValueError("provider cost cannot be established as a finite amount")
    return cost, f"grok_{cache_basis}_{tier}_{reasoning_basis}"


def _cached_tokens(usage: dict, input_tokens: int) -> tuple[int, str]:
    details = usage.get("input_tokens_details")
    if not isinstance(details, dict) or "cached_tokens" not in details:
        return 0, "conservative_input"
    cached = details["cached_tokens"]
    if not _count(cached) or cached > input_tokens:
        raise ValueError("provider usage absent; cost cannot be established")
    return cached, "reported_cached"


def _reasoning_extra(usage: dict, input_tokens: int, output_tokens: int) -> tuple[int, str]:
    details = usage.get("output_tokens_details")
    reasoning = 0
    if isinstance(details, dict) and "reasoning_tokens" in details:
        reasoning = details["reasoning_tokens"]
        if not _count(reasoning):
            raise ValueError("provider usage absent; cost cannot be established")
    total = usage.get("total_tokens")
    if type(total) is int and total == input_tokens + output_tokens:
        return 0, "reasoning_included"
    if reasoning:
        return reasoning, "reasoning_added"
    return 0, "no_reasoning_detail"


def _count(value: object) -> bool:
    return type(value) is int and value >= 0
