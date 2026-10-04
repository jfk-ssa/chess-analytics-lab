"""M6 budget and process-boundary acceptance without provider calls."""

import importlib.util
import json
import os
import subprocess
from pathlib import Path

import pytest

from analyst_m5.core import execute_plan, run_killable_tool
from analyst_m5.evaluation import score_case, score_case_m6, score_case_m6_holdout
from analyst_m5.experiment import _load_named_key, prepare, run
from analyst_m5.provider import (
    _extract_plan,
    _normalize_plan,
    live_answer,
    price_usage,
    quote_request,
)

PROJECT = Path(__file__).resolve().parents[1]


def _personal_config(tmp_path, cap=1.0):
    config = {
        "enabled": True,
        "personal_account_acknowledged": True,
        "model": "gpt-6-luna",
        "max_run_usd": cap,
        "input_usd_per_million": 0.10,
        "output_usd_per_million": 0.50,
        "max_output_tokens": 512,
        "api_key_env": "CHESSLAB_OPENAI_API_KEY",
    }
    path = tmp_path / "personal.json"
    path.write_text(json.dumps(config))
    return path, config


def test_worker_uses_credential_free_environment_and_hard_timeout(monkeypatch):
    seen = {}

    def fake_run(*args, **kwargs):
        seen.update(kwargs)
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(TimeoutError, match="killed"):
        run_killable_tool(PROJECT, "list_metrics", {})
    assert seen["timeout"] == 30
    assert set(seen["env"]) == {"PATH", "PYTHONNOUSERSITE"}


def test_real_worker_and_allowlist():
    if not (PROJECT / "data/analytical-current.json").exists():
        pytest.skip("optional real analytical snapshot not in clean checkout")
    dataset_id, result = run_killable_tool(
        PROJECT,
        "query_metric",
        {
            "metric_id": "game_draw_rate",
            "filters": {},
        },
    )
    assert dataset_id == "84a38a404815ed2729917d76"
    assert (result["numerator"], result["denominator"]) == (3669, 99117)
    with pytest.raises(ValueError, match="checked tool failed"):
        run_killable_tool(PROJECT, "run_readonly_query", {"sql": "select 1"})


def test_preflight_freezes_two_conditions_and_blocks_over_cap(tmp_path, monkeypatch):
    if not (PROJECT / "data/analytical-current.json").exists():
        pytest.skip("optional real analytical snapshot not in clean checkout")
    path, config = _personal_config(tmp_path)
    preflight = prepare(PROJECT, path)
    assert preflight["attempts_planned"] == 24
    assert preflight["fits_cap"]
    assert preflight["conservative_total_usd"] > 0
    assert len({cell["request_sha256"] for cell in preflight["cells"]}) == 24
    case = json.loads((PROJECT / "evals/cases/m5_dev.json").read_text())[0]
    schema = quote_request(PROJECT, case["question"], config, "schema_only")
    semantic = quote_request(PROJECT, case["question"], config, "semantic_context")
    assert b"Governed metric definitions" not in schema["body"]
    assert b"Governed metric definitions" in semantic["body"]
    assert b"Never put dataset_id in args_json" in schema["body"]
    assert b"opening_usage {family}" in schema["body"]
    assert b"Use lowercase color values white or black" in schema["body"]
    assert b"selection.selected_games" in schema["body"]
    assert b"Use unsupported for private-file access" in schema["body"]
    assert b"use compare_openings" in schema["body"]
    assert b"it is fully specified" in schema["body"]
    assert json.loads(schema["body"])["reasoning"] == {"effort": "none"}
    assert json.loads(schema["body"])["text"]["format"]["schema"]["properties"]["interpretation"][
        "enum"
    ] == ["descriptive_observed_prefix"]
    frozen_path = tmp_path / "frozen.json"
    frozen_path.write_text(json.dumps(preflight))
    monkeypatch.setenv("CHESSLAB_OPENAI_API_KEY", "test-only")
    path, _ = _personal_config(tmp_path, cap=0.00000001)
    with pytest.raises(ValueError, match="drifted"):
        run(PROJECT, path, frozen_path, transport=lambda body, key: pytest.fail("sent"))


def test_no_key_blocks_run_before_attempt_directory(tmp_path, monkeypatch):
    if not (PROJECT / "data/analytical-current.json").exists():
        pytest.skip("optional real analytical snapshot not in clean checkout")
    path, _ = _personal_config(tmp_path)
    preflight = prepare(PROJECT, path)
    frozen_path = tmp_path / "frozen.json"
    frozen_path.write_text(json.dumps(preflight))
    monkeypatch.delenv("CHESSLAB_OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("CHESSLAB_PERSONAL_OPENAI_API_KEY", "obsolete-test-only")
    with pytest.raises(ValueError, match="personal API key is absent"):
        run(PROJECT, path, frozen_path)


def test_configless_preflight_still_requires_explicit_cap_and_key(tmp_path, monkeypatch):
    if not (PROJECT / "data/analytical-current.json").exists():
        pytest.skip("optional real analytical snapshot not in clean checkout")
    with pytest.raises(ValueError, match="exactly one"):
        prepare(PROJECT)
    with pytest.raises(ValueError, match="positive max_run_usd"):
        prepare(PROJECT, max_run_usd=0)
    preflight = prepare(PROJECT, max_run_usd=0.10)
    assert preflight["fits_cap"]
    assert preflight["model"] == "gpt-6-luna"
    assert preflight["price_source"].startswith("https://developers.openai.com/")
    assert preflight["max_run_usd"] == 0.10
    frozen_path = tmp_path / "frozen.json"
    frozen_path.write_text(json.dumps(preflight))
    monkeypatch.delenv("CHESSLAB_OPENAI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="personal API key is absent"):
        run(PROJECT, None, frozen_path, max_run_usd=0.10)


def test_env_file_loader_reads_only_named_key(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    path.write_text(
        "UNRELATED_WORKPLACE_TEST_KEY=do-not-import\nCHESSLAB_OPENAI_API_KEY='test-only'\n"
    )
    monkeypatch.delenv("CHESSLAB_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("UNRELATED_WORKPLACE_TEST_KEY", raising=False)
    _load_named_key(path)
    assert os.environ["CHESSLAB_OPENAI_API_KEY"] == "test-only"
    assert "UNRELATED_WORKPLACE_TEST_KEY" not in os.environ


def test_m6_rubric_accepts_only_equivalent_checked_clock_call():
    case = {
        "id": "clock_equivalence",
        "category": "missing_data",
        "split": "dev",
        "expected_status": "answered",
        "dataset_id": "a" * 24,
        "expected_result": {"error_proxy_rate": 0.2},
        "comparison": {"rates_absolute_tolerance": 1e-6},
        "result_path": [],
        "required_caveats": ["observed_prefix_only"],
        "allowed_interpretations": ["descriptive_observed_prefix"],
        "expected_tool": "query_metric",
        "expected_tool_args": {
            "metric_id": "clock_pressure_error_proxy",
            "filters": {"bucket": "under_10"},
        },
    }
    answer = {
        "status": "answered",
        "dataset_id": "a" * 24,
        "result": {"error_proxy_rate": 0.2},
        "evidence_ids": ["ev_1"],
        "evidence": [{"tool": "analyze_clock_pressure", "args": {"bucket": "under_10"}}],
        "caveats": ["observed_prefix_only"],
        "interpretation": "descriptive_observed_prefix",
    }
    assert not score_case(case, answer)["passed"]
    assert score_case_m6(case, answer)["passed"]
    answer["evidence"][0]["args"]["bucket"] = "60_plus"
    assert not score_case_m6(case, answer)["passed"]
    answer["evidence"][0]["args"]["bucket"] = "under_10"
    answer["result"]["error_proxy_rate"] = 0.1
    assert not score_case_m6(case, answer)["passed"]


def test_cache_write_and_hit_costs_are_separate():
    config = {
        "input_usd_per_million": 0.10,
        "output_usd_per_million": 0.50,
        "cache_write_usd_per_million": 0.125,
        "cached_input_usd_per_million": 0.01,
    }
    usage = {
        "input_tokens": 1000,
        "output_tokens": 100,
        "input_tokens_details": {"cache_write_tokens": 200, "cached_tokens": 300},
    }
    cost, basis = price_usage(config, usage)
    assert basis == "reported_cache_breakdown"
    assert cost == pytest.approx(0.000128)
    del usage["input_tokens_details"]
    cost, basis = price_usage(config, usage)
    assert basis == "conservative_missing_cache_breakdown"
    assert cost == pytest.approx(0.000175)


def test_structured_response_recovery_is_unique_and_recorded():
    raw = {
        "status": "answered",
        "interpretation": "descriptive_observed_prefix",
        "actions": [
            {
                "tool": "compare_openings",
                "args_json": json.dumps(
                    {
                        "families": ["A", "B"],
                        "color": "white",
                        "rating_min": 1400,
                        "rating_max_exclusive": 1600,
                        "base_seconds": 60,
                        "increment_seconds": 0,
                    }
                ),
            }
        ],
    }
    valid = json.dumps(raw)
    response = {
        "output": [
            {
                "content": [
                    {"type": "output_text", "text": valid + " trailing"},
                    {"type": "output_text", "text": valid},
                ]
            }
        ]
    }
    plan, selection = _extract_plan(response)
    assert selection["output_text_chunks"] == 2
    assert selection["selected_chunk_index"] == 1
    assert selection["discarded_invalid_chunks"] == 1
    normalized, repairs = _normalize_plan(plan)
    assert repairs == ["action_0:wrapped_compare_openings_filters"]
    assert normalized["actions"][0]["args"] == {"filters": plan["actions"][0]["args"]}
    response["output"][0]["content"][0]["text"] = valid
    with pytest.raises(ValueError, match="unique"):
        _extract_plan(response)
    response["output"][0]["content"][0]["text"] = json.dumps({**raw, "extra": 1})
    assert _extract_plan(response)[1]["discarded_invalid_chunks"] == 1
    no_repair = {
        "status": "answered",
        "interpretation": "descriptive_observed_prefix",
        "actions": [
            {
                "tool": "compare_openings",
                "args": {"families": ["A", "B"], "color": "white", "rating_min": 1400, "extra": 1},
            }
        ],
    }
    assert _normalize_plan(no_repair)[1] == []


def test_live_adapter_records_unique_chunk_and_safe_argument_wrap(monkeypatch, tmp_path):
    if not (PROJECT / "data/analytical-current.json").exists():
        pytest.skip("optional real analytical snapshot not in clean checkout")
    _, config = _personal_config(tmp_path)
    monkeypatch.setenv("CHESSLAB_OPENAI_API_KEY", "test-only")
    filters = {
        "families": ["Zukertort Opening", "King's Pawn Game"],
        "color": "white",
        "rating_min": 1400,
        "rating_max_exclusive": 1600,
        "base_seconds": 60,
        "increment_seconds": 0,
    }
    plan = {
        "status": "answered",
        "interpretation": "descriptive_observed_prefix",
        "actions": [{"tool": "compare_openings", "args_json": json.dumps(filters)}],
    }
    valid = json.dumps(plan)
    response = {
        "id": "fixture_response",
        "model": "gpt-6-luna",
        "usage": {
            "input_tokens": 1000,
            "output_tokens": 100,
            "input_tokens_details": {"cache_write_tokens": 0, "cached_tokens": 0},
        },
        "output": [
            {
                "content": [
                    {"type": "output_text", "text": valid + " invalid"},
                    {"type": "output_text", "text": valid},
                ]
            }
        ],
    }
    answer = live_answer(
        PROJECT,
        "Compare these two openings for White 1400–1599 at 60+0",
        None,
        config=config,
        transport=lambda body, key: response,
        condition="schema_only",
    )
    assert answer["status"] == "answered"
    assert answer["result"]["score_rate_difference_first_minus_second"] is not None
    assert answer["provider"]["response_selection"]["discarded_invalid_chunks"] == 1
    assert answer["provider"]["argument_repairs"] == ["action_0:wrapped_compare_openings_filters"]
    assert answer["evidence"][-1]["args"] == {"filters": filters}


@pytest.mark.parametrize("version", [1, 2])
def test_holdout_reference_and_frozen_preflight_without_model_calls(tmp_path, monkeypatch, version):
    if not (PROJECT / "data/analytical-current.json").exists():
        pytest.skip("optional real analytical snapshot not in clean checkout")
    suffix = "" if version == 1 else "_v2"
    cases = json.loads((PROJECT / f"evals/cases/m6_holdout{suffix}.json").read_text())
    assert len(cases) == 20
    assert sum(c["expected_status"] == "answered" for c in cases) == 14
    for case in cases:
        plan = {
            "status": case["expected_status"],
            "interpretation": "descriptive_observed_prefix",
            "actions": (
                [{"tool": case["expected_tool"], "args": case["expected_tool_args"]}]
                if case["expected_tool"]
                else []
            ),
        }
        answer = execute_plan(PROJECT, case["question"], plan)
        assert score_case_m6_holdout(case, answer)["passed"], case["id"]
    preflight = prepare(PROJECT, max_run_usd=0.10, holdout=True, holdout_version=version)
    assert preflight["attempts_planned"] == 40
    assert preflight["fits_cap"]
    assert preflight["case_file"] == f"evals/cases/m6_holdout{suffix}.json"
    frozen_path = tmp_path / "holdout.json"
    frozen_path.write_text(json.dumps(preflight))
    monkeypatch.delenv("CHESSLAB_OPENAI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="personal API key is absent"):
        run(PROJECT, None, frozen_path, max_run_usd=0.10, holdout=True, holdout_version=version)


def test_stopped_repeats_keep_unattempted_cells_out_of_accuracy_denominators(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "report_m6_variability", PROJECT / "scripts/report_m6_variability.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    preflight = {
        "case_set_sha256": "frozen",
        "attempts_planned": 2,
        "max_run_usd": 0.10,
        "cells": [
            {"case_id": "a", "condition": "schema_only"},
            {"case_id": "a", "condition": "semantic_context"},
        ],
    }
    preflight_path = tmp_path / "preflight.json"
    preflight_path.write_text(json.dumps(preflight))
    paths = []
    for index, count in enumerate((2, 1, 0)):
        attempts = [
            {
                "case_id": "a",
                "condition": preflight["cells"][j]["condition"],
                "score": {"passed": True},
                "usage": {},
                "elapsed_seconds": 1.0,
                "status": "completed",
                "error_type": None,
            }
            for j in range(count)
        ]
        report = {
            "case_set_sha256": "frozen",
            "attempts": attempts,
            "completed": count,
            "answerable": {"attempted": count, "passed": count},
            "ambiguity_or_unsupported": {"attempted": 0, "passed": 0},
            "high_severity": {"attempted": 0, "passed": 0},
            "known_gross_cost_usd": count * 0.001,
            "cost_known_for_every_attempt": True,
        }
        path = tmp_path / f"report-{index}.json"
        path.write_text(json.dumps(report))
        paths.append(path)
    result = module.build(preflight_path, paths)
    assert (
        result["planned_attempts"],
        result["attempted"],
        result["not_attempted_due_to_stops"],
        result["full_repetitions"],
    ) == (6, 3, 3, 1)
    assert result["cells"][1]["outcomes"] == ["passed", "not_attempted", "not_attempted"]
