"""Disabled-by-default personal Responses adapter; no implicit credential lookup."""

import hashlib
import json
import math
import os
import re
import unicodedata
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from chess_analytics.analyst.core import execute_plan
from chess_analytics.analyst.tools import CheckedTools
from chess_analytics.common import write_json

KEY_ENV = "CHESSLAB_OPENAI_API_KEY"
ENDPOINT = "https://api.openai.com/v1/responses"
PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["answered", "needs_clarification", "unsupported"]},
        "interpretation": {"type": "string", "enum": ["descriptive_observed_prefix"]},
        "actions": {
            "type": "array",
            "maxItems": 4,
            "items": {
                "type": "object",
                "properties": {
                    "tool": {
                        "type": "string",
                        "enum": [
                            "list_metrics",
                            "get_metric_definition",
                            "get_dataset_coverage",
                            "query_metric",
                            "compare_openings",
                            "analyze_clock_pressure",
                            "compare_clock_buckets",
                        ],
                    },
                    "args_json": {"type": "string"},
                },
                "required": ["tool", "args_json"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["status", "interpretation", "actions"],
    "additionalProperties": False,
}


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


def price_usage(config: dict, usage: object) -> tuple[float, str]:
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


def _default_transport(body: bytes, key: str) -> dict:
    request = urllib.request.Request(
        ENDPOINT,
        body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        try:
            payload = json.loads(exc.read(8192))
            error = payload.get("error", {})
            detail = f"{error.get('type', 'unknown')}: {str(error.get('message', ''))[:500]}"
        except (ValueError, AttributeError):
            detail = "unavailable"
        raise RuntimeError(f"provider HTTP {exc.code}: {detail}") from exc


def _recover_repeated_plan_chunk(chunk: str, response: dict) -> tuple[dict, dict]:
    """Accept only identical repeated objects, with an optional duplicate truncation."""
    if len(chunk) > 8192:
        raise ValueError("repeated plan chunk too long")
    decoder = json.JSONDecoder()
    objects = []
    snippets = []
    remaining = chunk.strip()
    truncated = 0
    while remaining:
        if len(objects) >= 16:
            raise ValueError("too many repeated plan objects")
        try:
            value, end = decoder.raw_decode(remaining)
        except json.JSONDecodeError:
            if (
                response.get("status") == "incomplete"
                and len(objects) >= 2
                and len(remaining) >= 64
                and any(snippet.startswith(remaining) for snippet in snippets)
            ):
                truncated = len(remaining)
                break
            raise ValueError("unrecognized repeated-plan suffix") from None
        if not isinstance(value, dict) or (objects and value != objects[0]):
            raise ValueError("conflicting repeated-plan object")
        objects.append(value)
        snippets.append(remaining[:end])
        remaining = remaining[end:].strip()
        if remaining.startswith("1 final"):
            remaining = remaining[len("1 final") :].strip()
    if len(objects) < 2:
        raise ValueError("not a repeated plan")
    return objects[0], {
        "identical_complete_objects": len(objects),
        "truncated_duplicate_suffix_characters": truncated,
    }


def _recover_inert_suffix(chunk: str, response: dict) -> tuple[dict, int]:
    """Keep one complete plan before bounded non-ASCII repeated punctuation."""
    if response.get("status") != "incomplete" or len(chunk) > 8192:
        raise ValueError("not an incomplete bounded response")
    text = chunk.lstrip()
    raw, end = json.JSONDecoder().raw_decode(text)
    trailing = text[end:].strip()
    if (
        not isinstance(raw, dict)
        or not 64 <= len(trailing) <= 4096
        or len(set(trailing)) != 1
        or trailing[0].isascii()
        or unicodedata.category(trailing[0])[0] not in {"P", "S"}
    ):
        raise ValueError("not an inert repeated suffix")
    return raw, len(trailing)


def _extract_plan(response: dict) -> tuple[dict, dict]:
    """Accept one unambiguous structured plan; log invalid and duplicate chunks."""
    chunks = [
        part.get("text")
        for item in response.get("output", [])
        for part in item.get("content", [])
        if part.get("type") == "output_text"
    ]
    valid = []
    decoder = json.JSONDecoder()
    tools = set(PLAN_SCHEMA["properties"]["actions"]["items"]["properties"]["tool"]["enum"])
    for index, chunk in enumerate(chunks):
        if not isinstance(chunk, str):
            continue
        try:
            repeated = None
            inert_suffix = 0
            try:
                raw = json.loads(chunk)
            except json.JSONDecodeError:
                try:
                    raw, repeated = _recover_repeated_plan_chunk(chunk, response)
                except ValueError:
                    raw, inert_suffix = _recover_inert_suffix(chunk, response)
            if (
                not isinstance(raw, dict)
                or set(raw) != {"status", "interpretation", "actions"}
                or raw["status"] not in {"answered", "needs_clarification", "unsupported"}
                or raw["interpretation"] != "descriptive_observed_prefix"
                or not isinstance(raw["actions"], list)
                or len(raw["actions"]) > 4
            ):
                continue
            actions = []
            recovered_arguments = []
            for item in raw["actions"]:
                if not isinstance(item, dict) or set(item) != {"tool", "args_json"}:
                    raise ValueError("invalid action schema")
                if item["tool"] not in tools or not isinstance(item["args_json"], str):
                    raise ValueError("invalid action tool")
                argument_text = item["args_json"]
                try:
                    args = json.loads(argument_text)
                except json.JSONDecodeError:
                    # Some provider responses put a complete argument object first,
                    # then stray prose inside args_json. Keep the raw response,
                    # accept only that unique leading object, and log the repair.
                    args, end = decoder.raw_decode(argument_text.lstrip())
                    trailing = argument_text.lstrip()[end:]
                    if not trailing or len(trailing) > 4096:
                        raise ValueError("unbounded or absent argument suffix") from None
                    for match in re.finditer(r"[\[{]", trailing):
                        try:
                            extra, _ = decoder.raw_decode(trailing[match.start() :])
                        except json.JSONDecodeError:
                            continue
                        if isinstance(extra, (dict, list)):
                            raise ValueError("conflicting structured argument suffix") from None
                    recovered_arguments.append(
                        {"action_index": len(actions), "ignored_trailing_characters": len(trailing)}
                    )
                if not isinstance(args, dict):
                    raise ValueError("tool args must be an object")
                actions.append({"tool": item["tool"], "args": args})
            valid.append(
                (
                    index,
                    {
                        "status": raw["status"],
                        "interpretation": raw["interpretation"],
                        "actions": actions,
                    },
                    chunk,
                    recovered_arguments,
                    repeated,
                    inert_suffix,
                )
            )
        except (ValueError, TypeError, KeyError):
            continue
    if not valid or any(candidate[1] != valid[0][1] for candidate in valid[1:]):
        raise ValueError("provider returned no unique structured plan")
    index, plan, selected, recovered_arguments, repeated, inert_suffix = valid[0]
    return plan, {
        "output_text_chunks": len(chunks),
        "selected_chunk_index": index,
        "selected_chunk_sha256": hashlib.sha256(selected.encode()).hexdigest(),
        "discarded_invalid_chunks": len(chunks) - len(valid),
        "duplicate_valid_chunks": len(valid) - 1,
        "recovered_argument_suffixes": recovered_arguments,
        "recovered_repeated_plan_objects": repeated,
        "recovered_inert_suffix_characters": inert_suffix,
    }


def _normalize_plan(plan: dict) -> tuple[dict, list[str]]:
    """Wrap one known flat tool signature; preserve the raw plan in the response."""
    repairs = []
    normalized = {**plan, "actions": []}
    opening_keys = {
        "families",
        "color",
        "rating_min",
        "rating_max_exclusive",
        "base_seconds",
        "increment_seconds",
    }
    for index, action in enumerate(plan["actions"]):
        args = action["args"]
        if action["tool"] == "compare_openings" and set(args) == opening_keys:
            args = {"filters": args}
            repairs.append(f"action_{index}:wrapped_compare_openings_filters")
        normalized["actions"].append({"tool": action["tool"], "args": args})
    return normalized, repairs


def _repair_opening_usage(question: str, plan: dict, tools: CheckedTools) -> tuple[dict, list[str]]:
    """Route one clearly specified source-family fraction through the checked metric."""
    lower = question.lower()
    if not (
        ("fraction" in lower or "share" in lower)
        and ("known-opening" in lower or "source-tag" in lower or "opening usage" in lower)
    ) or any(
        word in lower
        for word in (
            "full-month",
            "full april",
            "full march",
            "full february",
            "full january",
            "full december",
            "full may",
            "full june",
            "full july",
            "caus",
            "guarantee",
            "personal",
            "my rating",
        )
    ):
        return plan, []
    rows = tools.query_metric("opening_usage", {}, ["opening_family"])["rows"]
    matches = [
        row["family"]
        for row in rows
        if re.search(r"(?<!\w)" + re.escape(row["family"]) + r"(?!\w)", question, re.I)
    ]
    matches.sort(key=len, reverse=True)
    if not matches or any(name.lower() not in matches[0].lower() for name in matches[1:]):
        return plan, []
    intended = {
        "status": "answered",
        "interpretation": "descriptive_observed_prefix",
        "actions": [
            {
                "tool": "query_metric",
                "args": {"metric_id": "opening_usage", "filters": {"family": matches[0]}},
            }
        ],
    }
    if plan == intended:
        return plan, []
    return intended, ["one_exact_source_family_fraction:checked_opening_usage"]


CONDITIONS = {"schema_only", "semantic_context"}


def quote_request(project: Path, question: str, config: dict, condition="semantic_context") -> dict:
    """Build and price an exact planner request without reading any credential."""
    config = validate_personal_config(config)
    if condition not in CONDITIONS:
        raise ValueError("unknown experiment condition")
    tools = CheckedTools(project)
    if not isinstance(question, str) or not 1 <= len(question) <= 2000:
        raise ValueError("invalid question length")
    prompt = (
        "Select at most four reviewed metric tool actions. Use only the observed bounded prefix. "
        "If essential filters are absent, request clarification. Reject causal or unsupported "
        "claims. Return tool arguments as JSON in args_json. Do not calculate numeric answers. "
        "Use needs_clarification only when the user can supply missing cohort filters "
        "for a supported descriptive query. Use unsupported for inaccessible data, "
        "causal effects, full-month extrapolation from this prefix, personality or "
        "other claims this dataset or tools cannot answer. Both statuses use no actions. "
        "A personalized opening-choice request without the player's cohort and "
        "outcome preference needs clarification; do not recommend an opening. "
        "If a descriptive opening question gives an exact family and cohort, "
        "a small but nonzero observed cohort is answerable with a sample-size "
        "caveat; do not turn sparse counts into unsupported. A comparison of "
        "two exact families in that cohort is also answerable. "
        "If a question supplies color, opening family, rating band, and time control, "
        "it is fully specified: answer with checked evidence, not clarification. "
        "A 1400–1599 band means rating_min 1400 and rating_max_exclusive 1600; "
        "60+0 means base_seconds 60 and increment_seconds 0. "
        "Exact action args: list_metrics {}; get_metric_definition {metric_id}; "
        "get_dataset_coverage {}; query_metric {metric_id, filters, optional group_by}; "
        "compare_openings {filters}; analyze_clock_pressure {bucket}; "
        "compare_clock_buckets {first, second}. Never put dataset_id in args_json. "
        "For numerical questions, use query_metric or a specialized numerical tool; "
        "a metric definition alone is not numerical evidence. "
        "Exact query_metric filters: opening_usage {family}; game_draw_rate {}; "
        "opening_player_score {family,color,rating_min,rating_max_exclusive,"
        "base_seconds,increment_seconds}; opening_adjusted_score uses families "
        "(two-name array) instead of family with the same cohort keys; "
        "clock_pressure_error_proxy and evaluation_coverage {bucket}. "
        "A specified clock-bucket evaluation-coverage question is answerable: "
        "query evaluation_coverage and report eligible and evaluable move counts "
        "with the missing-evaluation caveat. Sparse evaluation availability "
        "does not itself make coverage unsupported. Never infer a missing "
        "evaluation is zero error or that clock pressure caused an error. "
        "A specified clock-bucket question asking how many evaluable moves "
        "meet the exploratory deterioration threshold or asks for its rate "
        "is answerable with clock_pressure_error_proxy. Query that metric "
        "for the named bucket; sparse source evaluations do not make the "
        "observed proxy count unsupported. Do not request clarification or "
        "call evaluation_coverage unless coverage itself is requested. "
        "Eligibility is built into metrics; never invent extra filter keys. "
        "Use lowercase color values white or black, never title case. "
        "For differences between two opening families, use compare_openings with "
        "filters {families:[full first family name, full second family name],color,"
        "rating_min,rating_max_exclusive,base_seconds,increment_seconds}. "
        "For a first-minus-second opening difference, compare_openings is mandatory: "
        "two query_metric calls return components, not the requested difference. "
        "For compare_openings, args_json must have one outer filters key, never flat fields. "
        "Opening usage is fully specified by the source family alone; do not ask for "
        "color, rating, or time control for opening_usage. For an exact opening-usage "
        "fraction, use one query_metric action, without a coverage action. "
        "For any exact source-tag family named in a usage question, call opening_usage; "
        "the checked tool determines whether it occurs, so do not infer unsupported "
        "from the family name or absence from a preview list. "
        "Copy full provider family names from the question; never abbreviate "
        "Sicilian Defense to Sicilian or French Defense to French. "
        "For Black's Sicilian versus French comparison, use full source names "
        "Sicilian Defense and French Defense with color black. "
        "get_dataset_coverage returns selection.selected_games, the number of games "
        "selected for move replay including selected zero-ply games. "
        f"Dataset: {tools.dataset_id}. Available metric IDs: "
        f"{json.dumps(tools.list_metrics()['metric_ids'])}. "
        "Opening player-score filters require family, color, rating_min, "
        "rating_max_exclusive, base_seconds, increment_seconds. "
        "Adjusted opening score uses the same filters with families as two names. "
        "Clock bucket is under_10, 10_to_29, 30_to_59, or 60_plus."
    )
    if condition == "semantic_context":
        definitions = [
            tools.get_metric_definition(metric_id)["definition"]
            for metric_id in tools.list_metrics()["metric_ids"]
        ]
        prompt += " Governed metric definitions: " + json.dumps(definitions, sort_keys=True)
    payload = {
        "model": config["model"],
        "instructions": prompt,
        "input": question,
        "max_output_tokens": config["max_output_tokens"],
        "reasoning": {"effort": "none"},
        "store": False,
        "text": {
            "format": {
                "type": "json_schema",
                "name": "chess_analyst_plan",
                "strict": True,
                "schema": PLAN_SCHEMA,
            }
        },
    }
    body = json.dumps(payload, ensure_ascii=True).encode()
    # JSON ASCII bytes plus a fixed envelope allowance; verify billed usage afterward.
    reserved_usd = (
        (len(body) + 1000) * max(config["input_usd_per_million"], *cache_rates(config))
        + config["max_output_tokens"] * config["output_usd_per_million"]
    ) / 1_000_000
    if not math.isfinite(reserved_usd):
        raise ValueError("request cost bound is not finite")
    return {
        "body": body,
        "request_sha256": hashlib.sha256(body).hexdigest(),
        "reserved_cost_usd": reserved_usd,
        "condition": condition,
    }


def live_answer(
    project: Path,
    question: str,
    config_path: Path | None,
    *,
    config: dict | None = None,
    transport=None,
    condition="semantic_context",
    remaining_usd=None,
) -> dict:
    """One capped planning request; all numerical answers come from checked tools."""
    if (config_path is None) == (config is None):
        raise ValueError("provide either personal config path or explicit config")
    if config is None:
        assert config_path is not None
        config = validate_personal_config(json.loads(config_path.read_text()))
    else:
        config = validate_personal_config(config)
    quote = quote_request(project, question, config, condition)
    reserved_usd = quote["reserved_cost_usd"]
    if remaining_usd is not None and (
        isinstance(remaining_usd, bool)
        or not isinstance(remaining_usd, (int, float))
        or not math.isfinite(remaining_usd)
        or remaining_usd < 0
    ):
        raise ValueError("finite remaining run budget required")
    if reserved_usd > config["max_run_usd"] or (
        remaining_usd is not None and reserved_usd > remaining_usd
    ):
        raise ValueError("explicit run spending cap below conservative request bound")
    key = os.environ.get(KEY_ENV)
    if not key:
        raise ValueError("explicit personal API key is absent")
    response = (transport or _default_transport)(quote["body"], key)
    usage = response.get("usage")
    actual_cost, cost_basis = price_usage(config, usage)
    if actual_cost > config["max_run_usd"]:
        raise ValueError("provider usage exceeded configured run spending cap")
    parsed_plan, selection = _extract_plan(response)
    plan, repairs = _normalize_plan(parsed_plan)
    model_plan = plan
    plan, semantic_repairs = _repair_opening_usage(question, plan, CheckedTools(project))
    answer = execute_plan(project, question, plan, source="live_provider")
    answer["provider"] = {
        "response_id": response.get("id"),
        "resolved_model": response.get("model"),
        "usage": usage,
        "gross_cost_usd": actual_cost,
        "cost_basis": cost_basis,
        "reserved_cost_usd": reserved_usd,
        "request_sha256": quote["request_sha256"],
        "condition": condition,
        "max_run_usd": config["max_run_usd"],
        "input_usd_per_million": config["input_usd_per_million"],
        "output_usd_per_million": config["output_usd_per_million"],
        "raw_response": response,
        "response_selection": selection,
        "argument_repairs": repairs,
        "model_plan_before_semantic_repair": model_plan,
        "semantic_repairs": semantic_repairs,
        "attempts": 1,
    }
    return answer


def recorded_live_answer(project: Path, question: str, config_path: Path) -> dict:
    """Retain successful and failed attempts without copying API keys."""
    attempt_id = uuid.uuid4().hex
    path = project / "data/analyst_attempts" / f"{attempt_id}.json"
    captured = {}

    def capture_transport(body, key):
        response = _default_transport(body, key)
        captured["response"] = response
        return response

    try:
        answer = live_answer(project, question, config_path, transport=capture_transport)
        write_json(
            path,
            {
                "kind": "live_provider_attempt",
                "status": "completed",
                "question": question,
                "answer": answer,
            },
        )
        return answer
    except Exception as exc:
        key = os.environ.get(KEY_ENV)
        message = str(exc).replace(key, "[redacted]") if key else str(exc)
        write_json(
            path,
            {
                "kind": "live_provider_attempt",
                "status": "failed",
                "question": question,
                "error_type": type(exc).__name__,
                "error": message,
                "provider_response": captured.get("response"),
            },
        )
        raise
