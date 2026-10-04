"""Disabled-by-default personal Responses adapter; no implicit credential lookup."""

import hashlib
import json
import os
import re
import urllib.request
import uuid
from pathlib import Path

from analyst_m5.core import execute_plan
from analyst_m5.tools import CheckedTools
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
    if not isinstance(config, dict) or set(config) != required:
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
    for key in ("max_run_usd", "input_usd_per_million", "output_usd_per_million"):
        value = config[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            raise ValueError(f"positive {key} required")
    if (
        type(config["max_output_tokens"]) is not int
        or not 64 <= config["max_output_tokens"] <= 2000
    ):
        raise ValueError("bounded max_output_tokens required")
    return config


def _default_transport(body: bytes, key: str) -> dict:
    request = urllib.request.Request(
        ENDPOINT,
        body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def _extract_text(response: dict) -> str:
    chunks = [
        part.get("text")
        for item in response.get("output", [])
        for part in item.get("content", [])
        if part.get("type") == "output_text"
    ]
    if len(chunks) != 1 or not isinstance(chunks[0], str):
        raise ValueError("provider returned no single structured plan")
    return chunks[0]


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
        "Eligibility is built into metrics; never invent extra filter keys. "
        "Use lowercase color values white or black, never title case. "
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
        (len(body) + 1000) * config["input_usd_per_million"]
        + config["max_output_tokens"] * config["output_usd_per_million"]
    ) / 1_000_000
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
    config = validate_personal_config(
        config if config is not None else json.loads(config_path.read_text())
    )
    quote = quote_request(project, question, config, condition)
    reserved_usd = quote["reserved_cost_usd"]
    if reserved_usd > config["max_run_usd"] or (
        remaining_usd is not None and reserved_usd > remaining_usd
    ):
        raise ValueError("explicit run spending cap below conservative request bound")
    key = os.environ.get(KEY_ENV)
    if not key:
        raise ValueError("explicit personal API key is absent")
    response = (transport or _default_transport)(quote["body"], key)
    usage = response.get("usage")
    if not isinstance(usage, dict) or not all(
        type(usage.get(name)) is int for name in ("input_tokens", "output_tokens")
    ):
        raise ValueError("provider usage absent; cost cannot be established")
    actual_cost = (
        usage["input_tokens"] * config["input_usd_per_million"]
        + usage["output_tokens"] * config["output_usd_per_million"]
    ) / 1_000_000
    if actual_cost > config["max_run_usd"]:
        raise ValueError("provider usage exceeded configured run spending cap")
    raw_plan = json.loads(_extract_text(response))
    if set(raw_plan) != {"status", "interpretation", "actions"}:
        raise ValueError("provider plan schema mismatch")
    plan = {
        "status": raw_plan["status"],
        "interpretation": raw_plan["interpretation"],
        "actions": [
            {"tool": item["tool"], "args": json.loads(item["args_json"])}
            for item in raw_plan["actions"]
        ],
    }
    answer = execute_plan(project, question, plan, source="live_provider")
    answer["provider"] = {
        "response_id": response.get("id"),
        "resolved_model": response.get("model"),
        "usage": usage,
        "gross_cost_usd": actual_cost,
        "reserved_cost_usd": reserved_usd,
        "request_sha256": quote["request_sha256"],
        "condition": condition,
        "max_run_usd": config["max_run_usd"],
        "input_usd_per_million": config["input_usd_per_million"],
        "output_usd_per_million": config["output_usd_per_million"],
        "raw_response": response,
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
