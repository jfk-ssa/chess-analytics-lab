"""Offline grok-4.7 quote, usage pricing, and reservation tests.

No test in this module calls xAI or OpenAI. HTTP is mocked. The network
fixture in conftest blocks sockets.
"""

import io
import json
from decimal import Decimal

import pytest

from chess_analytics.analyst.live_runner import (
    RECOMMENDED_CAP_USD,
    ReservationError,
    build_config,
    run,
)
from chess_analytics.analyst.model_catalog import (
    GROK_MODEL_ID,
    LIVE_EVAL_DEFAULT_EFFORT,
    LIVE_EVAL_EFFORTS,
    LIVE_EVAL_JOB_TIMEOUT_MINUTES,
    LIVE_EVAL_WALL_CLOCK_SECONDS,
    LONG_CONTEXT_PROMPT_TOKENS,
    PROMPT_CACHE_KEY,
    REASONING_RESERVE_TOKENS,
    XAI_KEY_ENV,
    XAI_RESPONSES_URL,
    grok_reservation_usd,
    price_grok_usage,
    resolve_effort,
)
from chess_analytics.analyst.pricing import KEY_ENV
from chess_analytics.analyst.provider import ENDPOINT, _default_transport, quote_request


def _config(**overrides):
    config = build_config(model=GROK_MODEL_ID, max_run_usd=5, acknowledged=True)
    config.update(overrides)
    return config


def _usage(**overrides):
    usage = {
        "input_tokens": 32,
        "input_tokens_details": {"cached_tokens": 8},
        "output_tokens": 9,
        "output_tokens_details": {"reasoning_tokens": 110},
        "total_tokens": 151,
    }
    usage.update(overrides)
    return usage


def test_documented_usage_bills_cached_input_and_adds_reasoning_tokens():
    """The Responses example is 32 + 9 + 110 = 151, so reasoning is not inside output."""
    cost, basis = price_grok_usage(_config(), _usage())
    assert basis == "grok_reported_cached_short_reasoning_added"
    assert cost == pytest.approx((24 * 2 + 8 * 0.5 + 119 * 6) / 1_000_000)


def test_long_context_rates_apply_to_the_whole_request_at_200k_prompt_tokens():
    config = _config()
    short_usage = _usage(
        input_tokens=LONG_CONTEXT_PROMPT_TOKENS - 1,
        input_tokens_details={"cached_tokens": 0},
        output_tokens=1,
        output_tokens_details={"reasoning_tokens": 1},
        total_tokens=LONG_CONTEXT_PROMPT_TOKENS + 1,
    )
    long_usage = _usage(
        input_tokens=LONG_CONTEXT_PROMPT_TOKENS,
        input_tokens_details={"cached_tokens": 10_000},
        output_tokens=20,
        output_tokens_details={"reasoning_tokens": 100},
        total_tokens=LONG_CONTEXT_PROMPT_TOKENS + 120,
    )
    short, short_basis = price_grok_usage(config, short_usage)
    long, long_basis = price_grok_usage(config, long_usage)
    assert short_basis == "grok_reported_cached_short_reasoning_added"
    assert long_basis == "grok_reported_cached_long_reasoning_added"
    assert short == pytest.approx(((LONG_CONTEXT_PROMPT_TOKENS - 1) * 2 + 2 * 6) / 1_000_000)
    assert long == pytest.approx((190_000 * 4 + 10_000 * 1 + 120 * 12) / 1_000_000)
    assert long > short


def test_total_tokens_equal_to_input_plus_output_does_not_bill_reasoning_twice():
    usage = _usage(
        input_tokens=100,
        input_tokens_details={"cached_tokens": 0},
        output_tokens=50,
        output_tokens_details={"reasoning_tokens": 20},
        total_tokens=150,
    )
    cost, basis = price_grok_usage(_config(), usage)
    assert basis == "grok_reported_cached_short_reasoning_included"
    assert cost == pytest.approx((100 * 2 + 50 * 6) / 1_000_000)


def test_missing_cached_tokens_uses_the_uncached_input_rate():
    usage = {
        "input_tokens": 1_000,
        "output_tokens": 10,
        "output_tokens_details": {"reasoning_tokens": 5},
    }
    cost, basis = price_grok_usage(_config(), usage)
    assert basis == "grok_conservative_input_short_reasoning_added"
    assert cost == pytest.approx((1_000 * 2 + 15 * 6) / 1_000_000)


def test_reservation_uses_uncached_short_rates_until_the_prompt_ceiling_reaches_200k():
    config = _config()
    short_body = b"x" * (LONG_CONTEXT_PROMPT_TOKENS - 1000 - 1)
    long_body = b"x" * (LONG_CONTEXT_PROMPT_TOKENS - 1000)
    short, short_tier = grok_reservation_usd(short_body, config, "low")
    long, long_tier = grok_reservation_usd(long_body, config, "low")
    visible = config["max_output_tokens"]
    low_out = visible + REASONING_RESERVE_TOKENS["low"]
    assert short_tier == "short"
    assert long_tier == "long"
    assert short == pytest.approx(((LONG_CONTEXT_PROMPT_TOKENS - 1) * 2 + low_out * 6) / 1_000_000)
    assert long == pytest.approx((LONG_CONTEXT_PROMPT_TOKENS * 4 + low_out * 12) / 1_000_000)
    medium, _ = grok_reservation_usd(b"x" * 1000, config, "medium")
    high, _ = grok_reservation_usd(b"x" * 1000, config, "high")
    low, _ = grok_reservation_usd(b"x" * 1000, config, "low")
    assert low < medium < high


def test_grok_quote_is_strict_json_schema_on_the_xai_shape(live_eval_stage):
    from chess_analytics.analyst.live_eval import load_live_cases

    _manifest, cases = load_live_cases(_repo())
    question = cases[0]["question"]
    quote = quote_request(live_eval_stage, question, _config(), "semantic_context", "low")
    payload = json.loads(quote["body"])
    assert payload["model"] == GROK_MODEL_ID
    assert payload["reasoning"] == {"effort": "low"}
    assert payload["store"] is False
    assert payload["prompt_cache_key"] == PROMPT_CACHE_KEY
    assert payload["max_output_tokens"] == 512
    assert payload["input"] == question
    assert payload["instructions"]
    text_format = payload["text"]["format"]
    assert text_format["type"] == "json_schema"
    assert text_format["name"] == "chess_analyst_plan"
    assert text_format["strict"] is True
    assert text_format["schema"]["type"] == "object"
    assert quote["price_tier"] == "short"
    assert quote["reasoning_effort"] == "low"
    luna = build_config(model="gpt-6-luna", max_run_usd=1, acknowledged=True)
    luna_payload = json.loads(
        quote_request(live_eval_stage, question, luna, "semantic_context")["body"]
    )
    assert luna_payload["reasoning"] == {"effort": "none"}
    assert "prompt_cache_key" not in luna_payload


def test_transport_posts_only_the_selected_provider(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["auth"] = request.get_header("Authorization")
        captured["type"] = request.get_header("Content-type")
        captured["data"] = request.data
        return io.BytesIO(b'{"id":"resp_test","output":[]}')

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    grok_body = json.dumps({"model": GROK_MODEL_ID}).encode()
    _default_transport(grok_body, "xai-test-key")
    assert captured["url"] == XAI_RESPONSES_URL
    assert captured["timeout"] == 180
    assert captured["auth"] == "Bearer xai-test-key"
    assert captured["type"] == "application/json"
    assert captured["data"] == grok_body
    luna_body = json.dumps({"model": "gpt-6-luna"}).encode()
    _default_transport(luna_body, "openai-test-key")
    assert captured["url"] == ENDPOINT
    assert captured["timeout"] == 30
    assert captured["auth"] == "Bearer openai-test-key"


def test_invalid_effort_is_rejected_before_a_request(live_eval_stage, monkeypatch):
    calls = []

    def transport(_body, _key):
        calls.append(1)
        raise AssertionError("request sent")

    monkeypatch.delenv(XAI_KEY_ENV, raising=False)
    with pytest.raises(ValueError, match="does not accept reasoning effort none"):
        run(
            _repo(),
            live_eval_stage,
            acknowledged=True,
            dry_run=True,
            max_run_usd=5,
            model=GROK_MODEL_ID,
            reasoning_effort="none",
            transport=transport,
        )
    with pytest.raises(ValueError, match="does not accept reasoning effort low"):
        run(
            _repo(),
            live_eval_stage,
            acknowledged=True,
            dry_run=True,
            max_run_usd=1,
            model="gpt-6-luna",
            reasoning_effort="low",
            transport=transport,
        )
    assert calls == []
    assert resolve_effort(GROK_MODEL_ID, "model-default") == "low"
    assert resolve_effort("gpt-6-sol", None) == "none"


def test_planned_grok_runs_fit_the_ten_dollar_cap(live_eval_stage, monkeypatch):
    monkeypatch.delenv(XAI_KEY_ENV, raising=False)
    monkeypatch.delenv(KEY_ENV, raising=False)
    reserved = {}

    def transport(_body, _key):
        raise AssertionError("dry run sent a request")

    for effort in ("low", "medium", "high"):
        plan = run(
            _repo(),
            live_eval_stage,
            acknowledged=True,
            dry_run=True,
            max_run_usd=100,
            model=GROK_MODEL_ID,
            reasoning_effort=effort,
            repeats=5,
            transport=transport,
        )
        reserved[effort] = plan["reserved_usd"]
        assert plan["reasoning_effort"] == effort
        assert plan["price_tier"] == "short"
        assert plan["planned_requests"] == 240
        assert plan["recommended_cap_usd"] == 10.0
    assert reserved["low"] < reserved["medium"] < reserved["high"]
    assert f"{reserved['low']:.6f}" == "9.822470"
    assert f"{reserved['medium']:.6f}" == "18.671270"
    assert f"{reserved['high']:.6f}" == "30.466790"
    headline = run(
        _repo(),
        live_eval_stage,
        acknowledged=True,
        dry_run=True,
        max_run_usd=10,
        model=GROK_MODEL_ID,
        reasoning_effort="low",
        repeats=5,
        transport=transport,
    )
    assert headline["repeats"] == 5
    assert f"{headline['reserved_usd']:.6f}" == "9.822470"
    for effort, expected in (("medium", "3.734254"), ("high", "6.093358")):
        once = run(
            _repo(),
            live_eval_stage,
            acknowledged=True,
            dry_run=True,
            max_run_usd=10,
            model=GROK_MODEL_ID,
            reasoning_effort=effort,
            repeats=1,
            transport=transport,
        )
        assert once["repeats"] == 1
        assert once["reasoning_effort"] == effort
        assert once["planned_requests"] == 48
        assert f"{once['reserved_usd']:.6f}" == expected
        with pytest.raises(ReservationError, match="exceeds explicit cap"):
            run(
                _repo(),
                live_eval_stage,
                acknowledged=True,
                dry_run=True,
                max_run_usd=10,
                model=GROK_MODEL_ID,
                reasoning_effort=effort,
                repeats=5,
                transport=transport,
            )


def test_runner_reads_only_the_xai_key_and_records_the_effort(live_eval_stage, monkeypatch):
    from chess_analytics.analyst.live_eval import load_live_cases, oracle_plan

    monkeypatch.setenv(KEY_ENV, "openai-secret")
    monkeypatch.setenv(XAI_KEY_ENV, "xai-secret")
    _manifest, cases = load_live_cases(_repo())
    by_question = {case["question"]: case for case in cases}
    seen = []

    def transport(body, key):
        seen.append(key)
        payload = json.loads(body)
        assert payload["model"] == GROK_MODEL_ID
        assert payload["text"]["format"]["strict"] is True
        plan = oracle_plan(by_question[payload["input"]])
        encoded = {
            "actions": [
                {"args_json": json.dumps(step["args"], sort_keys=True), "tool": step["tool"]}
                for step in plan["actions"]
            ],
            "interpretation": plan["interpretation"],
            "status": plan["status"],
        }
        return {
            "id": "resp_test",
            "model": GROK_MODEL_ID,
            "output": [
                {"type": "reasoning", "encrypted_content": "ciphertext"},
                {
                    "content": [{"text": json.dumps(encoded), "type": "output_text"}],
                    "type": "message",
                },
            ],
            "usage": _usage(),
        }

    receipt = run(
        _repo(),
        live_eval_stage,
        acknowledged=True,
        max_run_usd=100,
        model=GROK_MODEL_ID,
        reasoning_effort="low",
        repeats=1,
        resamples=20,
        run_id="grok-low",
        transport=transport,
    )
    assert seen == ["xai-secret"] * 48
    assert "openai-secret" not in seen
    assert receipt["model"] == GROK_MODEL_ID
    assert receipt["reasoning_effort"] == "low"
    assert receipt["headline_passed"] == 48
    assert receipt["rows"][0]["cost_basis"] == "grok_reported_cached_short_reasoning_added"
    one_call = (24 * 2 + 8 * 0.5 + 119 * 6) / 1_000_000
    assert receipt["known_gross_cost_usd"] == pytest.approx(48 * one_call)
    medium = run(
        _repo(),
        live_eval_stage,
        acknowledged=True,
        max_run_usd=100,
        model=GROK_MODEL_ID,
        reasoning_effort="medium",
        repeats=1,
        resamples=20,
        run_id="grok-medium",
        transport=transport,
    )
    assert medium["reasoning_effort"] == "medium"
    assert medium["model"] == receipt["model"]
    assert medium["run_id"] != receipt["run_id"]
    high = run(
        _repo(),
        live_eval_stage,
        acknowledged=True,
        dry_run=True,
        max_run_usd=100,
        model=GROK_MODEL_ID,
        reasoning_effort="high",
        repeats=5,
        transport=transport,
    )
    assert high["reasoning_effort"] == "high"


def test_wall_clock_stops_before_another_request(live_eval_stage, monkeypatch):
    monkeypatch.setenv(XAI_KEY_ENV, "xai-secret")
    monkeypatch.setattr(
        "chess_analytics.analyst.live_runner.LIVE_EVAL_WALL_CLOCK_SECONDS",
        -1,
    )
    calls = []

    def transport(_body, _key):
        calls.append(_key)
        raise AssertionError("wall clock sent a request")

    receipt = run(
        _repo(),
        live_eval_stage,
        acknowledged=True,
        max_run_usd=10,
        model=GROK_MODEL_ID,
        reasoning_effort="medium",
        repeats=1,
        run_id="grok-medium-clock",
        transport=transport,
    )
    assert calls == []
    assert receipt["complete"] is False
    assert receipt["incomplete_reason"] == "wall_clock"
    assert receipt["repeats"] == 1
    assert receipt["reasoning_effort"] == "medium"
    assert receipt["rows"] == []
    assert LIVE_EVAL_JOB_TIMEOUT_MINUTES == 150
    assert LIVE_EVAL_WALL_CLOCK_SECONDS == 140 * 60
    assert LIVE_EVAL_WALL_CLOCK_SECONDS < LIVE_EVAL_JOB_TIMEOUT_MINUTES * 60


def test_dispatch_tables_match_the_catalog():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "scripts" / "live_eval_dispatch.py"
    spec = importlib.util.spec_from_file_location("live_eval_dispatch_grok", path)
    assert spec is not None and spec.loader is not None
    dispatch = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dispatch)
    assert set(dispatch.CAPS_USD) == set(RECOMMENDED_CAP_USD)
    for model, cap in RECOMMENDED_CAP_USD.items():
        assert dispatch.CAPS_USD[model] == Decimal(str(cap))
        assert dispatch.EFFORTS[model] == LIVE_EVAL_EFFORTS[model]
        assert dispatch.DEFAULT_EFFORT[model] == LIVE_EVAL_DEFAULT_EFFORT[model]


def _repo():
    from pathlib import Path

    return Path(__file__).resolve().parents[1]
