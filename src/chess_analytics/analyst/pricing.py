"""Personal provider prices and configuration checks."""

import math
import re

KEY_ENV = "CHESSLAB_OPENAI_API_KEY"


def validate_personal_config(config: dict) -> dict:
    required = {
        "enabled",
        "personal_account_acknowledged",
        "model",
        "max_run_usd",
        "input_usd_per_million",
        "output_usd_per_million",
        "max_output_tokens",
        "api_key_env",
    }
    cache_prices = {"cache_write_usd_per_million", "cached_input_usd_per_million"}
    if (
        not isinstance(config, dict)
        or not required <= set(config)
        or set(config) - required - cache_prices
        or len(set(config) & cache_prices) not in {0, 2}
    ):
        raise ValueError("complete personal provider configuration required")
    if config["enabled"] is not True or config["personal_account_acknowledged"] is not True:
        raise ValueError("live provider explicitly disabled")
    if config["api_key_env"] != KEY_ENV:
        raise ValueError("only the named personal API key environment variable is allowed")
    if (
        not isinstance(config["model"], str)
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{3,100}", config["model"])
        or config["model"] == "SET_EXPLICIT_MODEL_ID"
    ):
        raise ValueError("explicit model ID required")
    for key in (
        "max_run_usd",
        "input_usd_per_million",
        "output_usd_per_million",
        *(cache_prices & set(config)),
    ):
        value = config[key]
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value <= 0
        ):
            raise ValueError(f"positive {key} required")
    if (
        type(config["max_output_tokens"]) is not int
        or not 64 <= config["max_output_tokens"] <= 2000
    ):
        raise ValueError("bounded max_output_tokens required")
    return config


def cache_rates(config: dict) -> tuple[float, float]:
    """Use explicit cache rates or conservative custom-model fallbacks."""
    input_rate = config["input_usd_per_million"]
    return (
        config.get("cache_write_usd_per_million", input_rate * 1.25),
        config.get("cached_input_usd_per_million", input_rate),
    )


def price_usage(config: dict, usage: dict) -> tuple[float, str]:
    """Price reported tokens; missing cache detail uses a conservative input bound."""
    if not isinstance(usage, dict) or not all(
        type(usage.get(key)) is int and usage[key] >= 0 for key in ("input_tokens", "output_tokens")
    ):
        raise ValueError("provider usage absent; cost cannot be established")
    write_rate, cached_rate = cache_rates(config)
    input_rate = config["input_usd_per_million"]
    details = usage.get("input_tokens_details")
    if (
        isinstance(details, dict)
        and all(
            type(details.get(key)) is int and details[key] >= 0
            for key in ("cache_write_tokens", "cached_tokens")
        )
        and details["cache_write_tokens"] + details["cached_tokens"] <= usage["input_tokens"]
    ):
        regular = usage["input_tokens"] - details["cache_write_tokens"] - details["cached_tokens"]
        input_cost = (
            regular * input_rate
            + details["cache_write_tokens"] * write_rate
            + details["cached_tokens"] * cached_rate
        )
        basis = "reported_cache_breakdown"
    else:
        input_cost = usage["input_tokens"] * max(input_rate, write_rate, cached_rate)
        basis = "conservative_missing_cache_breakdown"
    cost = (input_cost + usage["output_tokens"] * config["output_usd_per_million"]) / 1_000_000
    if not math.isfinite(cost):
        raise ValueError("provider cost cannot be established as a finite amount")
    return cost, basis
