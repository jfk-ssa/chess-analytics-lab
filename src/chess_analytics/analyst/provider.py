"""Disabled-by-default personal Responses adapter; no implicit credential lookup."""

import hashlib
import json
import math
import os
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from chess_analytics.analyst.core import execute_plan
from chess_analytics.analyst.plan_recovery import (
    PLAN_SCHEMA,
    _extract_plan,
    _normalize_plan,
    _repair_opening_usage,
)
from chess_analytics.analyst.pricing import (
    KEY_ENV,
    cache_rates,
    price_usage,
    validate_personal_config,
)
from chess_analytics.analyst.tools import CheckedTools
from chess_analytics.common import write_json

ENDPOINT = "https://api.openai.com/v1/responses"


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
