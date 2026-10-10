"""Offline evidence, scorer and access-boundary checks."""

import json
from copy import deepcopy
from pathlib import Path

import pytest

from chess_analytics.analyst.core import execute_plan
from chess_analytics.analyst.evaluation import score_case
from chess_analytics.analyst.provider import live_answer, validate_personal_config
from chess_analytics.analyst.tools import CheckedTools


def _case_answer():
    case = {
        "id": "reference_probe",
        "category": "filtering_perspective",
        "split": "dev",
        "expected_status": "answered",
        "dataset_id": "a" * 24,
        "expected_result": {
            "wins": 15,
            "draws": 2,
            "losses": 13,
            "eligible_player_games": 30,
            "win_rate": 0.5,
            "score_rate": 16 / 30,
        },
        "comparison": {"rates_absolute_tolerance": 1e-6},
        "result_path": [],
        "required_caveats": ["observed_prefix_only", "association_not_causation"],
        "allowed_interpretations": ["descriptive_observed_prefix"],
    }
    answer = {
        "status": "answered",
        "dataset_id": "a" * 24,
        "result": deepcopy(case["expected_result"]),
        "evidence_ids": ["ev_1"],
        "caveats": case["required_caveats"],
        "interpretation": "descriptive_observed_prefix",
    }
    return case, answer


def test_scorer_rejects_ten_plausible_wrong_answers():
    case, answer = _case_answer()
    assert score_case(case, answer)["passed"]
    mutations = [
        ("result", "wins", 16),
        ("result", "draws", 0),
        ("result", "losses", 12),
        ("result", "eligible_player_games", 32),
        ("result", "win_rate", 16 / 30),
        ("result", "score_rate", 15 / 30),
        ("top", "dataset_id", "b" * 24),
        ("top", "evidence_ids", []),
        ("top", "status", "unsupported"),
        ("top", "caveats", ["observed_prefix_only"]),
    ]
    for location, key, value in mutations:
        wrong = deepcopy(answer)
        target = wrong["result"] if location == "result" else wrong
        target[key] = value
        assert not score_case(case, wrong)["passed"], key


def test_freeform_sql_and_unpublished_access_are_absent():
    tools = CheckedTools.__new__(CheckedTools)
    for sql in (
        "select * from read_text('/private/file')",
        "select * from read_csv_auto('https://example.com/x')",
        "load httpfs",
        "select 1; select 2",
        "select * from unpublished_table",
    ):
        with pytest.raises(ValueError, match="unsupported tool"):
            tools.execute("run_readonly_query", {"sql": sql})
    with pytest.raises(ValueError, match="unknown or malformed filter"):
        tools.query_metric("opening_usage", {"family": "Sicilian Defense", "sql": "drop table x"})


def test_state_machine_limits_steps_before_data_access():
    plan = {
        "status": "answered",
        "interpretation": "descriptive_observed_prefix",
        "actions": [{"tool": "list_metrics", "args": {}}] * 5,
    }

    class FakeTools:
        dataset_id = "a" * 24

        def __init__(self, project):
            pass

    from chess_analytics.analyst import core

    original = core.CheckedTools
    core.CheckedTools = FakeTools
    try:
        with pytest.raises(ValueError, match="tool-step limit"):
            execute_plan(Path(), "question", plan)
    finally:
        core.CheckedTools = original


def test_live_requires_explicit_personal_configuration():
    config = {
        "enabled": False,
        "personal_account_acknowledged": False,
        "model": "explicit-snapshot",
        "max_run_usd": 1.0,
        "input_usd_per_million": 1.0,
        "output_usd_per_million": 1.0,
        "max_output_tokens": 512,
        "api_key_env": "CHESSLAB_OPENAI_API_KEY",
    }
    with pytest.raises(ValueError, match="disabled"):
        validate_personal_config(config)
    config["enabled"] = config["personal_account_acknowledged"] = True
    config["max_run_usd"] = 0
    with pytest.raises(ValueError, match="positive"):
        validate_personal_config(config)
    config["max_run_usd"] = 1
    config["api_key_env"] = "OPENAI_API_KEY"
    with pytest.raises(ValueError, match="personal"):
        validate_personal_config(config)


def test_live_cap_prevents_transport_before_any_request(tmp_path, monkeypatch):
    from chess_analytics.analyst import provider

    class FakeTools:
        dataset_id = "a" * 24

        def __init__(self, project):
            pass

        def list_metrics(self):
            return {"metric_ids": ["opening_usage"]}

        def get_metric_definition(self, metric_id):
            return {"definition": {"id": metric_id}}

    monkeypatch.setattr(provider, "CheckedTools", FakeTools)
    monkeypatch.setenv("CHESSLAB_OPENAI_API_KEY", "test-only")
    config = {
        "enabled": True,
        "personal_account_acknowledged": True,
        "model": "explicit-snapshot",
        "max_run_usd": 0.00000001,
        "input_usd_per_million": 10.0,
        "output_usd_per_million": 10.0,
        "max_output_tokens": 512,
        "api_key_env": "CHESSLAB_OPENAI_API_KEY",
    }
    path = tmp_path / "personal.json"
    path.write_text(json.dumps(config))

    def forbidden_transport(body, key):
        raise AssertionError("no request is permitted")

    with pytest.raises(ValueError, match="spending cap"):
        live_answer(tmp_path, "Question?", path, transport=forbidden_transport)
