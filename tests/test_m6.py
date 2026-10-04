"""M6 budget and process-boundary acceptance without provider calls."""

import json
import os
import subprocess
from pathlib import Path

import pytest

from analyst_m5.core import run_killable_tool
from analyst_m5.evaluation import score_case, score_case_m6
from analyst_m5.experiment import _load_named_key, prepare, run
from analyst_m5.provider import quote_request

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
