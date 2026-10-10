"""Offline contract and failure checks for the paired Jev end-to-end path."""

import json
import shutil

import pytest

from chess_analytics import jev_e2e
from chess_analytics.analyst.core import execute_plan
from chess_analytics.portfolio_demo import run as build_demo
from chess_analytics.routing_study import LABELS


def _prepared(tmp_path, project, monkeypatch):
    demo = tmp_path / "demo"
    build_demo(project, demo)
    data_project = demo / "project"
    study = tmp_path / "study"
    for name in (
        "src/chess_analytics/analyst/provider.py",
        "src/chess_analytics/analyst/core.py",
        "src/chess_analytics/analyst/tools.py",
        "src/chess_analytics/analyst/evaluation.py",
        "src/chess_analytics/routing_study.py",
    ):
        destination = study / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(project / name, destination)
    work = study / "work"
    work.mkdir()
    (work / ".env.typesafe").write_text("TYPESAFE_API_KEY=offline-test\n")
    (work / ".env").write_text("CHESSLAB_OPENAI_API_KEY=offline-test\n")
    template = {
        "split": "test",
        "category": "opening_usage",
        "route": "opening_usage",
        "dataset_id": json.loads((data_project / "data/analytical-moves-current.json").read_text())[
            "analytical_id"
        ],
        "comparison": {"rates_absolute_tolerance": 1e-6},
        "allowed_interpretations": ["descriptive_observed_prefix"],
    }
    rows = [
        {
            **template,
            "id": "use",
            "question": "In this fixture, what fraction of tagged games used Sicilian Defense?",
            "expected_status": "answered",
            "expected_result": {"numerator": 2, "denominator": 4, "value": 0.5},
            "expected_tool": "query_metric",
            "expected_tool_args": {
                "metric_id": "opening_usage",
                "filters": {"family": "Sicilian Defense"},
            },
            "required_caveats": ["observed_prefix_only", "source_tags_only"],
        },
        {
            **template,
            "id": "clarify",
            "category": "clarify",
            "route": "clarify",
            "question": "What was the score in the opening I mean?",
            "expected_status": "needs_clarification",
            "expected_result": None,
            "expected_tool": None,
            "expected_tool_args": None,
            "required_caveats": ["observed_prefix_only"],
        },
        {
            **template,
            "id": "unsupported",
            "category": "unsupported",
            "route": "unsupported",
            "question": "Did time pressure cause every blunder in these games?",
            "expected_status": "unsupported",
            "expected_result": None,
            "expected_tool": None,
            "expected_tool_args": None,
            "required_caveats": ["observed_prefix_only"],
        },
    ]
    monkeypatch.setattr(
        jev_e2e,
        "cases",
        lambda repo, data: (rows, {"case_sha256": "mock-case", "reference_sha256": "mock-ref"}),
    )
    frozen = jev_e2e.preflight(study, data_project)
    return study, data_project, rows, frozen


def test_paired_mock_uses_analyst_only_when_gate_does_not_decide(tmp_path, project, monkeypatch):
    study, data_project, rows, frozen = _prepared(tmp_path, project, monkeypatch)
    lookup = {row["question"]: row for row in rows}
    calls = {"jev": 0, "openai": 0}

    def openai_mock(body, key):
        assert key == "offline-test"
        calls["openai"] += 1
        case = lookup[json.loads(body)["input"]]
        actions = []
        if case["expected_tool"]:
            actions = [
                {
                    "tool": case["expected_tool"],
                    "args_json": json.dumps(case["expected_tool_args"]),
                }
            ]
        plan = {
            "status": case["expected_status"],
            "interpretation": "descriptive_observed_prefix",
            "actions": actions,
        }
        return {
            "id": "mock-response",
            "model": "gpt-6-luna",
            "usage": {"input_tokens": 500, "output_tokens": 100},
            "output": [{"content": [{"type": "output_text", "text": json.dumps(plan)}]}],
        }

    def jev_mock(body, key):
        assert key == "offline-test"
        calls["jev"] += 1
        case = lookup[json.loads(body)["state"]["question"]]
        route = case["route"]
        return {
            "model": "jev-1.13.0",
            "answers": {
                "route": {
                    "type": "choice",
                    "choice": route,
                    "confidence": 0.9,
                    "probabilities": {
                        label: 0.95 if label == route else 0.05 / 7 for label in LABELS
                    },
                }
            },
            "usage": {"input_tokens": 100},
        }

    with pytest.raises(ValueError, match="caps"):
        jev_e2e.run(
            study,
            data_project,
            frozen,
            study / "work/.env.typesafe",
            study / "work/.env",
            0.00001,
            0.001,
            study / "work/too-small",
            jev_call=jev_mock,
            openai_call=openai_mock,
        )
    report = jev_e2e.run(
        study,
        data_project,
        frozen,
        study / "work/.env.typesafe",
        study / "work/.env",
        0.03,
        0.2,
        study / "work/mock",
        jev_call=jev_mock,
        openai_call=openai_mock,
    )
    assert report["kind"] == "m8_paired_e2e_mock_attempt"
    assert report["complete"] is True
    assert report["scores"]["baseline"]["passed"] == 3
    assert report["scores"]["gated"]["passed"] == 3
    assert calls == {"jev": 3, "openai": 4}
    assert sum(item["used_analyst"] for item in report["outcomes"]["gated"]) == 1
    assert report["scores"]["gated"]["gross_usd"] < report["scores"]["baseline"]["gross_usd"]


def test_fresh_raw_reference_matches_checked_tools_when_local_source_exists(project):
    data_project = project / "work/m7-december-project"
    if not (data_project / "data/analytical-moves-current.json").exists():
        pytest.skip("optional retained December dataset absent from clean checkout")
    selected, manifest = jev_e2e.cases(project, data_project)
    assert len(selected) == manifest["cases"] == 32
    for case in selected:
        plan = {
            "status": case["expected_status"],
            "interpretation": "descriptive_observed_prefix",
            "actions": []
            if case["expected_tool"] is None
            else [{"tool": case["expected_tool"], "args": case["expected_tool_args"]}],
        }
        answer = execute_plan(data_project, case["question"], plan, source="offline_oracle")
        assert jev_e2e.score_answer(case, answer)["passed"], case["id"]


def test_transport_failure_is_retained_and_reserved(tmp_path, project, monkeypatch):
    study, data_project, _, frozen = _prepared(tmp_path, project, monkeypatch)

    def failed_transport(body, key):
        raise TimeoutError("mock timeout after transport start")

    output = study / "work/failed"
    report = jev_e2e.run(
        study,
        data_project,
        frozen,
        study / "work/.env.typesafe",
        study / "work/.env",
        0.03,
        0.20,
        output,
        jev_call=lambda body, key: None,
        openai_call=failed_transport,
    )
    assert report["complete"] is False
    assert report["failure"]["case_id"] == "use"
    reserved = frozen["cells"][0]["openai_reserved_cost_usd"]
    assert report["attempt_gross_usd"] == {"jev": 0.0, "openai": reserved}
    assert report["unknown_cost_reservation_usd"]["openai"] == reserved
    record = json.loads((output / "baseline-use.json").read_text())
    assert record["failure"]["type"] == "TimeoutError"
    assert record["unknown_cost_reservation"] is True


def test_expected_checked_tool_need_not_be_last_evidence(tmp_path, project, monkeypatch):
    _, data_project, rows, _ = _prepared(tmp_path, project, monkeypatch)
    case = rows[0]
    answer = execute_plan(
        data_project,
        case["question"],
        {
            "status": "answered",
            "interpretation": "descriptive_observed_prefix",
            "actions": [
                {"tool": "query_metric", "args": case["expected_tool_args"]},
                {"tool": "get_dataset_coverage", "args": {}},
            ],
        },
        source="offline_test",
    )
    answer["result"] = answer["evidence"][0]["result"]
    assert jev_e2e.score_answer(case, answer)["passed"]


def test_interrupted_openai_request_keeps_pending_reservation(tmp_path, project, monkeypatch):
    study, data_project, _, frozen = _prepared(tmp_path, project, monkeypatch)
    output = study / "work/interrupted-openai"

    def interrupted(body, key):
        raise KeyboardInterrupt

    report = jev_e2e.run(
        study,
        data_project,
        frozen,
        study / "work/.env.typesafe",
        study / "work/.env",
        0.03,
        0.20,
        output,
        jev_call=lambda body, key: None,
        openai_call=interrupted,
    )
    reservation = frozen["cells"][0]["openai_reserved_cost_usd"]
    assert report["failure"]["type"] == "KeyboardInterrupt"
    assert report["complete"] is False
    assert report["attempt_gross_usd"]["openai"] == reservation
    assert report["unknown_cost_reservation_usd"]["openai"] == reservation
    assert json.loads((output / "baseline-use.json").read_text())["state"] == "pending"
    assert jev_e2e.reconcile_attempt_costs(output)["gross_usd"]["openai"] == reservation
    with pytest.raises(ValueError, match="remaining provider caps"):
        jev_e2e.run(
            study,
            data_project,
            frozen,
            study / "work/.env.typesafe",
            study / "work/.env",
            0.03,
            frozen["openai_whole_run_reservation_usd"],
            study / "work/retry",
            prior_attempts=(output,),
            jev_call=lambda body, key: None,
            openai_call=interrupted,
        )


def test_interrupted_jev_request_keeps_pending_reservation(tmp_path, project, monkeypatch):
    study, data_project, rows, frozen = _prepared(tmp_path, project, monkeypatch)
    lookup = {row["question"]: row for row in rows}

    def openai_mock(body, key):
        case = lookup[json.loads(body)["input"]]
        actions = (
            []
            if case["expected_tool"] is None
            else [
                {"tool": case["expected_tool"], "args_json": json.dumps(case["expected_tool_args"])}
            ]
        )
        plan = {
            "status": case["expected_status"],
            "interpretation": "descriptive_observed_prefix",
            "actions": actions,
        }
        return {
            "model": "gpt-6-luna",
            "usage": {"input_tokens": 500, "output_tokens": 100},
            "output": [{"content": [{"type": "output_text", "text": json.dumps(plan)}]}],
        }

    def interrupted(body, key):
        raise KeyboardInterrupt

    output = study / "work/interrupted-jev"
    report = jev_e2e.run(
        study,
        data_project,
        frozen,
        study / "work/.env.typesafe",
        study / "work/.env",
        0.03,
        0.20,
        output,
        jev_call=interrupted,
        openai_call=openai_mock,
    )
    reservation = frozen["cells"][0]["jev_reserved_cost_usd"]
    assert report["failure"]["phase"] == "gated"
    assert report["unknown_cost_reservation_usd"]["jev"] == reservation
    assert json.loads((output / "jev-use.json").read_text())["state"] == "pending"
    recovered = jev_e2e.reconcile_attempt_costs(output)
    assert recovered["gross_usd"] == report["attempt_gross_usd"]
    assert recovered["unknown_usd"] == report["unknown_cost_reservation_usd"]


def test_pretransport_failure_has_zero_reservation(tmp_path, project, monkeypatch):
    study, data_project, _, frozen = _prepared(tmp_path, project, monkeypatch)

    def fail_before_transport(*args, **kwargs):
        raise ValueError("pre-transport refusal")

    monkeypatch.setattr(jev_e2e.provider, "live_answer", fail_before_transport)
    output = study / "work/pretransport"
    report = jev_e2e.run(
        study,
        data_project,
        frozen,
        study / "work/.env.typesafe",
        study / "work/.env",
        0.03,
        0.20,
        output,
        jev_call=lambda body, key: None,
        openai_call=lambda body, key: None,
    )
    assert report["complete"] is False
    assert report["attempt_gross_usd"] == {"jev": 0.0, "openai": 0.0}
    assert json.loads((output / "baseline-use.json").read_text())["state"] == "failed"


def test_cli_exit_distinguishes_complete_and_stopped_attempts(tmp_path, monkeypatch, capsys):
    preflight = tmp_path / "preflight.json"
    preflight.write_text("{}")
    args = [
        "run",
        "--repo",
        str(tmp_path),
        "--data-project",
        str(tmp_path),
        "--preflight",
        str(preflight),
        "--jev-env",
        str(tmp_path / "jev"),
        "--openai-env",
        str(tmp_path / "openai"),
        "--output",
        str(tmp_path / "output"),
    ]
    monkeypatch.setattr(jev_e2e, "run", lambda *a, **k: {"complete": False})
    assert jev_e2e.main(args) == 1
    assert json.loads(capsys.readouterr().out)["complete"] is False
    monkeypatch.setattr(jev_e2e, "run", lambda *a, **k: {"complete": True})
    assert jev_e2e.main(args) == 0
    assert json.loads(capsys.readouterr().out)["complete"] is True
    monkeypatch.setattr(jev_e2e, "preflight", lambda *a, **k: {"kind": "offline_quote"})
    assert (
        jev_e2e.main(
            [
                "prepare",
                "--repo",
                str(tmp_path),
                "--data-project",
                str(tmp_path),
                "--preflight",
                str(tmp_path / "quote.json"),
            ]
        )
        == 0
    )
