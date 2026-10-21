"""Fake-transport tests for the live eval scorer and runner.

Nothing in this module calls a provider. The network fixture in conftest
blocks sockets. Plans are scored with the checked tools on the staged
100-game fixture.
"""

import importlib.util
import json
from pathlib import Path

import pytest

from chess_analytics.analyst.live_eval import load_live_cases, oracle_plan
from chess_analytics.analyst.live_runner import (
    RECEIPT_FIELDS,
    RECOMMENDED_CAP_USD,
    ROW_FIELDS,
    ReservationError,
    format_dry_run,
    recorded_rates,
    run,
)
from chess_analytics.analyst.live_score import score_live_plan
from chess_analytics.analyst.plan_recovery import _normalize_plan
from chess_analytics.analyst.pricing import KEY_ENV
from chess_analytics.analyst.tools import CheckedTools

ROOT = Path(__file__).resolve().parents[1]
_USAGE = {
    "input_tokens": 100,
    "input_tokens_details": {"cache_write_tokens": 0, "cached_tokens": 0},
    "output_tokens": 20,
}
_UNSUPPORTED = {
    "actions": [],
    "interpretation": "descriptive_observed_prefix",
    "status": "unsupported",
}
_DRAW = {
    "actions": [
        {
            "args": {"filters": {}, "metric_id": "game_draw_rate"},
            "tool": "query_metric",
        }
    ],
    "interpretation": "descriptive_observed_prefix",
    "status": "answered",
}
_CLARIFY = {
    "actions": [],
    "interpretation": "descriptive_observed_prefix",
    "status": "needs_clarification",
}
_LIST = {
    "actions": [{"args": {}, "tool": "list_metrics"}],
    "interpretation": "descriptive_observed_prefix",
    "status": "answered",
}


def _router():
    path = Path(__file__).with_name("test_live_eval_100.py")
    spec = importlib.util.spec_from_file_location("live_eval_100_router", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load the keyword router")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _wire(plan: dict, *, model: str = "gpt-6-luna") -> dict:
    payload = {
        "actions": [
            {"args_json": json.dumps(step["args"], sort_keys=True), "tool": step["tool"]}
            for step in plan["actions"]
        ],
        "interpretation": plan["interpretation"],
        "status": plan["status"],
    }
    return {
        "id": "resp_test",
        "model": model,
        "output": [{"content": [{"type": "output_text", "text": json.dumps(payload)}]}],
        "usage": dict(_USAGE),
    }


def _cases():
    _manifest, cases = load_live_cases(ROOT)
    return cases


def _by_question(cases):
    return {case["question"]: case for case in cases}


def _run(staged, transport, monkeypatch, **kwargs):
    monkeypatch.setenv(KEY_ENV, "test-personal-key")
    return run(
        ROOT,
        staged,
        acknowledged=True,
        max_run_usd=kwargs.pop("max_run_usd", 10),
        model=kwargs.pop("model", "gpt-6-luna"),
        repeats=kwargs.pop("repeats", 1),
        resamples=kwargs.pop("resamples", 20),
        run_id=kwargs.pop("run_id", "run-test"),
        seed=kwargs.pop("seed", 20261018),
        transport=transport,
        **kwargs,
    )


def test_oracle_plans_score_48(live_eval_stage):
    cases = _cases()
    passed = [score_live_plan(live_eval_stage, case, oracle_plan(case))["passed"] for case in cases]
    assert passed == [True] * 48


def test_keyword_router_and_constant_plans_match_the_record(live_eval_stage):
    router = _router()
    cases = _cases()

    def passed(case, plan) -> bool:
        return score_live_plan(live_eval_stage, case, plan)["passed"]

    router_hits = [
        case["id"] for case in cases if passed(case, router._keyword_plan(case["question"]))
    ]
    assert len(router_hits) == 40
    counts = {
        "needs_clarification": sum(passed(case, _CLARIFY) for case in cases),
        "unsupported": sum(passed(case, _UNSUPPORTED) for case in cases),
        "answered_list_metrics": sum(passed(case, _LIST) for case in cases),
        "answered_draw_rate": sum(passed(case, _DRAW) for case in cases),
    }
    assert counts == {
        "answered_draw_rate": 7,
        "answered_list_metrics": 0,
        "needs_clarification": 2,
        "unsupported": 7,
    }


def test_single_clock_call_passes_and_a_trailing_coverage_call_fails(live_eval_stage):
    case = next(item for item in _cases() if item["id"] == "clock_under_10_1")
    specialized = {
        "actions": [{"args": {"bucket": "under_10"}, "tool": "analyze_clock_pressure"}],
        "interpretation": "descriptive_observed_prefix",
        "status": "answered",
    }
    assert score_live_plan(live_eval_stage, case, specialized)["passed"] is True
    followed = {
        "actions": [
            {"args": {"bucket": "under_10"}, "tool": "analyze_clock_pressure"},
            {"args": {}, "tool": "get_dataset_coverage"},
        ],
        "interpretation": "descriptive_observed_prefix",
        "status": "answered",
    }
    trailed = score_live_plan(live_eval_stage, case, followed)
    assert trailed["passed"] is False
    assert "tool_or_filters" in trailed["failures"]


def test_invalid_plan_is_a_miss_not_a_crash(live_eval_stage):
    case = next(item for item in _cases() if item["id"] == "draw_rate_1")
    too_many = {
        "actions": [{"args": {}, "tool": "list_metrics"}] * 5,
        "interpretation": "descriptive_observed_prefix",
        "status": "answered",
    }
    scored = score_live_plan(live_eval_stage, case, too_many)
    assert scored["passed"] is False
    assert scored["plan_hallucination"] is True
    invented = {
        "actions": [
            {
                "args": {"filters": {"not_a_filter": 1}, "metric_id": "game_draw_rate"},
                "tool": "query_metric",
            }
        ],
        "interpretation": "descriptive_observed_prefix",
        "status": "answered",
    }
    refused = score_live_plan(live_eval_stage, case, invented)
    assert refused["plan_hallucination"] is True
    assert refused["passed"] is False


def test_argument_wrap_is_the_plan_that_gets_scored(live_eval_stage):
    case = next(item for item in _cases() if item["id"] == "compare_sicilian_french_1")
    flat = {
        "actions": [
            {
                "args": case["expected_tool_args"]["filters"],
                "tool": "compare_openings",
            }
        ],
        "interpretation": "descriptive_observed_prefix",
        "status": "answered",
    }
    normalized, repairs = _normalize_plan(flat)
    assert repairs == ["action_0:wrapped_compare_openings_filters"]
    assert score_live_plan(live_eval_stage, case, normalized)["passed"] is True
    assert score_live_plan(live_eval_stage, case, flat)["passed"] is False


def test_semantic_repair_does_not_flip_the_headline(live_eval_stage):
    from chess_analytics.analyst.plan_recovery import _repair_opening_usage

    case = next(item for item in _cases() if item["id"] == "usage_sicilian_1")
    repaired, repairs = _repair_opening_usage(
        case["question"], _UNSUPPORTED, CheckedTools(live_eval_stage)
    )
    assert repairs == ["one_exact_source_family_fraction:checked_opening_usage"]
    raw = score_live_plan(live_eval_stage, case, _UNSUPPORTED)
    fixed = score_live_plan(live_eval_stage, case, repaired)
    assert raw["passed"] is False
    assert fixed["passed"] is True


def test_recommended_caps_are_the_adr_figures():
    assert RECOMMENDED_CAP_USD == {"gpt-6-luna": 0.50, "gpt-6-sol": 10.0, "grok-4.7": 5.0}
    assert recorded_rates("gpt-6-luna")["input_usd_per_million"] == 0.10
    assert recorded_rates("gpt-6-sol")["output_usd_per_million"] == 10.0
    with pytest.raises(ValueError, match="explicit prices required"):
        recorded_rates("gpt-6-astra")


def test_dry_run_prints_the_plan_and_does_not_send(live_eval_stage, monkeypatch, capsys):
    monkeypatch.delenv(KEY_ENV, raising=False)

    def transport(_body, _key):
        raise AssertionError("dry run sent a request")

    plan = run(
        ROOT,
        live_eval_stage,
        acknowledged=True,
        dry_run=True,
        env_file=Path("/no/such/live-eval.env"),
        max_run_usd=10,
        model="gpt-6-luna",
        repeats=5,
        transport=transport,
    )
    assert plan["cases"] == 48
    assert plan["planned_requests"] == 240
    assert plan["scheduled"] is False
    assert plan["prices_rechecked"] is False
    assert plan["reasoning_effort"] == "none"
    assert plan["recommended_cap_usd"] == 0.50
    assert f"{plan['reserved_usd']:.6f}" == "0.443594"
    sol = run(
        ROOT,
        live_eval_stage,
        acknowledged=True,
        dry_run=True,
        max_run_usd=10,
        model="gpt-6-sol",
        repeats=5,
        transport=transport,
    )
    assert sol["recommended_cap_usd"] == 10.0
    assert f"{sol['reserved_usd']:.6f}" == "8.871288"
    text = format_dry_run(plan)
    assert "reserved_usd: 0.443594" in text
    assert "cases: 48" in text
    assert "planned_requests: 240" in text
    assert "prices_rechecked: false" in text
    assert "scheduled: false" in text
    assert capsys.readouterr().out == ""


def test_reservation_over_the_cap_refuses_before_any_send(live_eval_stage, monkeypatch):
    monkeypatch.delenv(KEY_ENV, raising=False)
    calls = []

    def transport(body, _key):
        calls.append(body)
        return _wire(_UNSUPPORTED)

    with pytest.raises(ReservationError) as caught:
        run(
            ROOT,
            live_eval_stage,
            acknowledged=True,
            max_run_usd=1e-9,
            model="gpt-6-luna",
            repeats=5,
            transport=transport,
        )
    assert calls == []
    assert caught.value.reserved > caught.value.cap


def test_missing_acknowledgement_refuses(live_eval_stage):
    def transport(_body, _key):
        raise AssertionError("unacknowledged run sent a request")

    with pytest.raises(ValueError, match="live provider explicitly disabled"):
        run(
            ROOT,
            Path("/no/such/stage"),
            acknowledged=False,
            max_run_usd=10,
            model="gpt-6-luna",
            transport=transport,
        )


def test_missing_key_refuses_and_ignores_other_names(live_eval_stage, monkeypatch):
    monkeypatch.delenv(KEY_ENV, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "not-the-lab-key")
    calls = []

    def transport(body, _key):
        calls.append(body)
        return _wire(_UNSUPPORTED)

    with pytest.raises(ValueError, match="explicit personal API key is absent"):
        run(
            ROOT,
            live_eval_stage,
            acknowledged=True,
            max_run_usd=10,
            model="gpt-6-luna",
            transport=transport,
        )
    assert calls == []


def test_transport_failure_stops_with_an_incomplete_receipt(live_eval_stage, monkeypatch):
    calls = []

    def transport(_body, key):
        calls.append(key)
        raise RuntimeError(f"provider HTTP 500: {key} down")

    receipt = _run(live_eval_stage, transport, monkeypatch, repeats=5)
    assert calls == ["test-personal-key"]
    assert receipt["complete"] is False
    assert receipt["incomplete_reason"] == "transport_failure"
    assert len(receipt["rows"]) == 1
    assert receipt["rows"][0]["status"] == "failed"
    assert receipt["planned_requests"] == 240
    assert "test-personal-key" not in receipt["rows"][0]["error"]
    assert "[redacted]" in receipt["rows"][0]["error"]
    assert receipt["stats"] is None


def test_second_transport_failure_keeps_the_first_row(live_eval_stage, monkeypatch):
    calls = {"n": 0}

    def transport(_body, _key):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("provider HTTP 500: down")
        return _wire(_UNSUPPORTED)

    receipt = _run(live_eval_stage, transport, monkeypatch)
    assert calls["n"] == 2
    assert [row["status"] for row in receipt["rows"]] == ["completed", "failed"]
    assert receipt["complete"] is False
    assert receipt["incomplete_reason"] == "transport_failure"


def test_oracle_transport_scores_48_and_matches_the_receipt_schema(
    live_eval_stage, monkeypatch, tmp_path
):
    cases = _cases()
    by_question = _by_question(cases)
    calls = []

    def transport(body, key):
        calls.append(key)
        question = json.loads(body)["input"]
        return _wire(oracle_plan(by_question[question]), model="gpt-6-luna-2026-10-04")

    receipt_path = tmp_path / "receipt.json"
    receipt = _run(live_eval_stage, transport, monkeypatch, output=receipt_path)
    assert json.loads(receipt_path.read_text())["run_id"] == receipt["run_id"]
    assert len(calls) == 48
    assert receipt["complete"] is True
    assert receipt["headline_passed"] == 48
    assert receipt["headline_pass_rate"] == 1
    assert receipt["hard_fail"] is False
    assert receipt["scheduled"] is False
    assert receipt["prices_rechecked"] is False
    assert receipt["reasoning_effort"] == "none"
    assert receipt["rubric_version"] == "live-eval-1.0"
    assert receipt["base_rubric_version"] == "portfolio-1.0"
    assert receipt["repeats"] == 1
    assert receipt["model"] == "gpt-6-luna"
    assert receipt["resolved_model"] == "gpt-6-luna-2026-10-04"
    assert set(receipt) == set(RECEIPT_FIELDS)
    assert set(receipt["rows"][0]) == set(ROW_FIELDS)
    assert all(row["model_plan_before_semantic_repair"] for row in receipt["rows"])
    assert all(row["passed"] is True for row in receipt["rows"])
    assert receipt["repair_counts"] == {"argument": 0, "extraction": 0, "semantic": 0}
    assert all(row["recovered_argument_suffixes"] == 0 for row in receipt["rows"])
    assert all(row["recovered_repeated_plan_objects"] == 0 for row in receipt["rows"])
    assert receipt["known_gross_cost_usd"] == pytest.approx(48 * 0.00002)
    assert receipt["token_usage"]["priced_requests"] == 48
    assert receipt["stats"]["wilson"]["successes"] == 48
    assert receipt["stats"]["bootstrap"]["seed"] == 20261018
    provider = hashlib_file("src/chess_analytics/analyst/provider.py")
    assert receipt["frozen_file_sha256"]["src/chess_analytics/analyst/provider.py"] == provider


def test_runner_keeps_a_semantic_repair_beside_the_headline(live_eval_stage, monkeypatch):
    def transport(_body, _key):
        return _wire(_UNSUPPORTED)

    receipt = _run(live_eval_stage, transport, monkeypatch, baseline_rate=1)
    assert receipt["headline_passed"] == 7
    row = next(item for item in receipt["rows"] if item["case_id"] == "usage_sicilian_1")
    assert row["passed"] is False
    assert row["semantic_repairs"] == ["one_exact_source_family_fraction:checked_opening_usage"]
    assert row["semantic_repair_would_pass"] is True
    assert row["repair_count"] == 1
    assert receipt["repair_counts"]["semantic"] == 1
    assert receipt["baseline_alert"]["alert"] is True
    assert receipt["baseline_alert"]["cutoff"] == 47


def test_high_severity_miss_is_a_hard_fail(live_eval_stage, monkeypatch):
    cases = _cases()
    by_question = _by_question(cases)

    def transport(body, _key):
        question = json.loads(body)["input"]
        case = by_question[question]
        if case["id"] == "boundary_budget":
            return _wire(_LIST)
        return _wire(oracle_plan(case))

    receipt = _run(live_eval_stage, transport, monkeypatch)
    row = next(item for item in receipt["rows"] if item["case_id"] == "boundary_budget")
    assert row["passed"] is False
    assert row["unsafe_answer"] is True
    assert row["high_severity_miss"] is True
    assert receipt["hard_fail"] is True
    assert receipt["headline_passed"] == 47
    assert receipt["complete"] is True


def test_same_seed_repeats_the_bootstrap(live_eval_stage, monkeypatch):
    def transport(_body, _key):
        return _wire(_UNSUPPORTED)

    first = _run(live_eval_stage, transport, monkeypatch, seed=7, resamples=30, run_id="one")
    second = _run(live_eval_stage, transport, monkeypatch, seed=7, resamples=30, run_id="two")
    third = _run(live_eval_stage, transport, monkeypatch, seed=8, resamples=30, run_id="three")
    assert first["stats"]["bootstrap"] == second["stats"]["bootstrap"]
    assert first["stats"]["bootstrap"] != third["stats"]["bootstrap"]


def test_a_flaky_repeat_is_flagged(live_eval_stage, monkeypatch):
    seen: dict[str, int] = {}

    def transport(body, _key):
        question = json.loads(body)["input"]
        seen[question] = seen.get(question, 0) + 1
        if "game draw rate in this fixture" in question and seen[question] == 1:
            return _wire(_DRAW)
        return _wire(_UNSUPPORTED)

    receipt = _run(live_eval_stage, transport, monkeypatch, repeats=2)
    assert receipt["flaky_cases"] == ["draw_rate_1"]
    assert receipt["complete"] is True


def test_bad_controls_send_nothing_and_do_not_read_the_key(live_eval_stage, monkeypatch):
    monkeypatch.delenv(KEY_ENV, raising=False)
    calls = []

    def transport(body, _key):
        calls.append(body)
        return _wire(_UNSUPPORTED)

    cases = (
        ({"seed": -1}, "seed must be a non-negative integer"),
        ({"resamples": 0}, "resamples must be a positive integer"),
        ({"baseline_rate": float("nan")}, "baseline rate must be finite"),
        ({"baseline_rate": 2}, "baseline rate must lie in 0..1"),
    )
    for kwargs, match in cases:
        calls.clear()
        with pytest.raises(ValueError, match=match):
            run(
                ROOT,
                live_eval_stage,
                acknowledged=True,
                max_run_usd=10,
                model="gpt-6-luna",
                repeats=1,
                transport=transport,
                **kwargs,
            )
        assert calls == []


def test_cap_just_under_the_reservation_sends_nothing(live_eval_stage, monkeypatch):
    monkeypatch.setenv(KEY_ENV, "test-personal-key")
    calls = []

    def transport(body, _key):
        calls.append(body)
        return _wire(_UNSUPPORTED)

    quoted = run(
        ROOT,
        live_eval_stage,
        acknowledged=True,
        dry_run=True,
        max_run_usd=10,
        model="gpt-6-luna",
        repeats=1,
        transport=transport,
    )
    cap = quoted["reserved_usd"] - 1e-15
    assert cap < quoted["reserved_usd"]
    with pytest.raises(ReservationError):
        run(
            ROOT,
            live_eval_stage,
            acknowledged=True,
            max_run_usd=cap,
            model="gpt-6-luna",
            repeats=1,
            transport=transport,
        )
    assert calls == []


def test_recovered_suffix_is_a_pass_with_a_repair_count(live_eval_stage, monkeypatch):
    cases = _cases()
    by_question = _by_question(cases)
    target = next(item for item in cases if item["id"] == "draw_rate_1")
    payload = {
        "actions": [
            {
                "args_json": json.dumps(step["args"], sort_keys=True) + " thanks",
                "tool": step["tool"],
            }
            for step in _DRAW["actions"]
        ],
        "interpretation": _DRAW["interpretation"],
        "status": _DRAW["status"],
    }
    recovered = {
        "id": "resp_test",
        "model": "gpt-6-luna",
        "output": [{"content": [{"type": "output_text", "text": json.dumps(payload)}]}],
        "usage": dict(_USAGE),
    }

    def transport(body, _key):
        question = json.loads(body)["input"]
        if question == target["question"]:
            return recovered
        return _wire(oracle_plan(by_question[question]))

    receipt = _run(live_eval_stage, transport, monkeypatch)
    row = next(item for item in receipt["rows"] if item["case_id"] == "draw_rate_1")
    assert row["passed"] is True
    assert row["recovered_argument_suffixes"] == 1
    assert row["repair_count"] == 1
    assert receipt["headline_passed"] == 48
    assert receipt["repair_counts"]["extraction"] == 1


def test_recovered_repeated_plan_is_counted_beside_the_pass(live_eval_stage, monkeypatch):
    cases = _cases()
    by_question = _by_question(cases)
    target = next(item for item in cases if item["id"] == "draw_rate_1")
    raw = {
        "actions": [
            {
                "args_json": json.dumps(step["args"], sort_keys=True),
                "tool": step["tool"],
            }
            for step in _DRAW["actions"]
        ],
        "interpretation": _DRAW["interpretation"],
        "status": _DRAW["status"],
    }
    text = json.dumps(raw) + "\n" + json.dumps(raw)
    repeated = {
        "id": "resp_test",
        "model": "gpt-6-luna",
        "output": [{"content": [{"type": "output_text", "text": text}]}],
        "usage": dict(_USAGE),
    }

    def transport(body, _key):
        question = json.loads(body)["input"]
        if question == target["question"]:
            return repeated
        return _wire(oracle_plan(by_question[question]))

    receipt = _run(live_eval_stage, transport, monkeypatch)
    row = next(item for item in receipt["rows"] if item["case_id"] == "draw_rate_1")
    assert row["passed"] is True
    assert row["recovered_repeated_plan_objects"] == 2
    assert row["repair_count"] == 1
    assert receipt["repair_counts"]["extraction"] == 1


def test_transport_error_redacts_key_fragments_and_paths(live_eval_stage, monkeypatch):
    key = "sk-personal-TESTKEY99"
    monkeypatch.setenv(KEY_ENV, key)
    calls = []

    def transport(_body, _key):
        calls.append(_key)
        raise RuntimeError(f"bad {key[:15]} and path /home/ubuntu/secret")

    receipt = run(
        ROOT,
        live_eval_stage,
        acknowledged=True,
        max_run_usd=10,
        model="gpt-6-luna",
        repeats=1,
        resamples=20,
        run_id="run-redact",
        seed=20261018,
        transport=transport,
    )
    error = receipt["rows"][0]["error"]
    assert calls == [key]
    assert error.startswith("transport_failure: RuntimeError:")
    assert "sk-personal" not in error
    assert "/home/ubuntu" not in error
    assert "[redacted]" in error
    assert "[path]" in error


def test_spend_under_the_cap_still_stops_before_the_next_reservation(live_eval_stage, monkeypatch):
    calls = {"n": 0}

    def transport(_body, _key):
        calls["n"] += 1
        response = _wire(_UNSUPPORTED)
        response["usage"] = {
            "input_tokens": 0,
            "input_tokens_details": {"cache_write_tokens": 0, "cached_tokens": 0},
            "output_tokens": 175591,
        }
        return response

    quoted = run(
        ROOT,
        live_eval_stage,
        acknowledged=True,
        dry_run=True,
        max_run_usd=1,
        model="gpt-6-luna",
        repeats=1,
        transport=transport,
    )
    assert f"{quoted['reserved_usd']:.9f}" == "0.088718875"
    receipt = _run(
        live_eval_stage,
        transport,
        monkeypatch,
        max_run_usd=quoted["reserved_usd"],
    )
    assert calls["n"] == 1
    assert receipt["incomplete_reason"] == "budget_exceeded"
    assert receipt["known_gross_cost_usd"] == pytest.approx(0.0877955)
    assert receipt["known_gross_cost_usd"] < quoted["reserved_usd"]


def test_high_severity_swap_and_invented_filter_are_not_refusal_labels(
    live_eval_stage, monkeypatch
):
    cases = _cases()
    by_question = _by_question(cases)
    invented = {
        "actions": [
            {
                "args": {"filters": {"not_a_filter": 1}, "metric_id": "game_draw_rate"},
                "tool": "query_metric",
            }
        ],
        "interpretation": "descriptive_observed_prefix",
        "status": "answered",
    }

    def transport(body, _key):
        question = json.loads(body)["input"]
        case = by_question[question]
        if case["id"] == "needs_clarification":
            return _wire(_UNSUPPORTED)
        if case["id"] == "boundary_budget":
            return _wire(invented)
        return _wire(oracle_plan(case))

    receipt = _run(live_eval_stage, transport, monkeypatch)
    swapped = next(item for item in receipt["rows"] if item["case_id"] == "needs_clarification")
    filtered = next(item for item in receipt["rows"] if item["case_id"] == "boundary_budget")
    assert swapped["passed"] is False
    assert swapped["high_severity_miss"] is True
    assert swapped["unsafe_answer"] is False
    assert swapped["over_abstention"] is False
    assert filtered["passed"] is False
    assert filtered["high_severity_miss"] is True
    assert filtered["unsafe_answer"] is False
    assert filtered["over_abstention"] is False
    assert "plan_hallucination" in filtered["failures"]
    assert receipt["hard_fail"] is True


def test_manifest_high_severity_families_match_the_nine_cases():
    manifest, cases = load_live_cases(ROOT)
    families = sorted({item["template_family"] for item in cases if item["severity"] == "high"})
    assert families == sorted(manifest["high_severity_families"])
    assert len(families) == 9
    assert "clarify_own_line" in families


def test_cost_over_the_cap_stops_before_the_next_send(live_eval_stage, monkeypatch):
    calls = {"n": 0}

    def transport(_body, _key):
        calls["n"] += 1
        response = _wire(_UNSUPPORTED)
        response["usage"] = {
            "input_tokens": 1_000_000_000,
            "input_tokens_details": {"cache_write_tokens": 0, "cached_tokens": 0},
            "output_tokens": 1_000_000_000,
        }
        return response

    receipt = _run(live_eval_stage, transport, monkeypatch)
    assert calls["n"] == 1
    assert receipt["complete"] is False
    assert receipt["incomplete_reason"] == "budget_exceeded"
    assert receipt["known_gross_cost_usd"] > 10


def test_unknown_usage_is_not_zero_and_stops(live_eval_stage, monkeypatch):
    calls = {"n": 0}

    def transport(_body, _key):
        calls["n"] += 1
        response = _wire(_UNSUPPORTED)
        response["usage"] = None
        return response

    receipt = _run(live_eval_stage, transport, monkeypatch)
    assert calls["n"] == 1
    assert receipt["complete"] is False
    assert receipt["incomplete_reason"] == "unknown_usage"
    assert receipt["known_gross_cost_usd"] == 0
    assert receipt["unknown_cost_reservation_usd"] > 0
    assert receipt["rows"][0]["gross_cost_usd"] is None


def test_cli_dry_run_and_missing_output(live_eval_stage, monkeypatch, capsys):
    from chess_analytics.analyst.__main__ import main

    monkeypatch.delenv(KEY_ENV, raising=False)
    with pytest.raises(SystemExit) as exited:
        main(
            [
                "--project",
                str(ROOT),
                "live-eval",
                "--model",
                "gpt-6-luna",
                "--max-run-usd",
                "10",
                "--staged",
                str(live_eval_stage),
                "--acknowledge-personal-account",
                "--dry-run",
                "--repeats",
                "1",
            ]
        )
    assert exited.value.code == 0
    captured = capsys.readouterr()
    assert "cases: 48" in captured.out
    assert "reserved_usd:" in captured.out
    with pytest.raises(SystemExit) as refused:
        main(
            [
                "--project",
                str(ROOT),
                "live-eval",
                "--model",
                "gpt-6-luna",
                "--max-run-usd",
                "10",
                "--staged",
                str(live_eval_stage),
                "--acknowledge-personal-account",
            ]
        )
    assert refused.value.code == 2
    assert "needs --output" in capsys.readouterr().err


def test_live_runner_source_has_no_schedule():
    names = sorted(path.name for path in (ROOT / ".github/workflows").glob("*.yml"))
    assert "live-eval.yml" in names
    text = (ROOT / "src/chess_analytics/analyst/live_runner.py").read_text()
    assert "workflow_dispatch" not in text
    assert "cron" not in text


def hashlib_file(relative: str) -> str:
    import hashlib

    return hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
