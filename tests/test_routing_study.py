"""Meaningful offline acceptance for the M8 frozen routing and spending boundary."""

import json
import shutil

import pytest

from chess_analytics.analyst.tools import CheckedTools
from chess_analytics.portfolio_demo import run as build_demo
from chess_analytics.routing_analyst import preflight as analyst_preflight
from chess_analytics.routing_analyst import route_from_answer
from chess_analytics.routing_analyst import run as run_analyst
from chess_analytics.routing_duckdb import offline_replay
from chess_analytics.routing_report import render
from chess_analytics.routing_study import (
    LABELS,
    cases,
    parse_jev_response,
    preflight,
    rules_report,
    run_jev,
    score,
)


def _project(tmp_path, repo):
    folder = tmp_path / "study"
    destination = folder / "evals/cases"
    destination.mkdir(parents=True)
    for name in ("jev_routing_v1.tsv", "jev_routing_v1_manifest.json"):
        shutil.copy2(repo / "evals/cases" / name, destination / name)
    key = folder / "work/.env.typesafe"
    key.parent.mkdir()
    key.write_text("TYPESAFE_API_KEY=offline-test-placeholder\n")
    return folder, key


def test_frozen_cases_and_rules_baseline(tmp_path, project):
    study, _ = _project(tmp_path, project)
    dev, manifest = cases(study, "dev")
    test, _ = cases(study, "test")
    assert len(dev) == len(test) == 40
    assert {row["id"] for row in dev}.isdisjoint({row["id"] for row in test})
    assert set(manifest["labels"]) == set(LABELS)
    report = rules_report(study, "test")
    assert report["correct"] == 35
    assert report["unsupported_recall"] == 1.0
    path = study / "evals/cases/jev_routing_v1.tsv"
    path.write_text(path.read_text().replace("Ruy Lopez", "Ruy Lopez altered", 1))
    with pytest.raises(ValueError, match="changed"):
        cases(study, "test")


def test_mocked_jev_scoring_and_failed_attempt_retention(tmp_path, project):
    study, key = _project(tmp_path, project)
    frozen = preflight(study, "test")
    lookup = {row["question"]: row["label"] for row in cases(study, "test")[0]}

    def perfect_mock(body, token):
        assert token == "offline-test-placeholder"
        label = lookup[json.loads(body)["state"]["question"]]
        return {
            "model": "jev-1.13.0",
            "answers": {
                "route": {
                    "type": "choice",
                    "choice": label,
                    "confidence": 1.0,
                    "probabilities": {option: float(option == label) for option in LABELS},
                }
            },
            "usage": {"input_tokens": 100},
        }

    cap = frozen["total_reserved_cost_usd"] + 0.01
    with pytest.raises(ValueError, match="cap"):
        run_jev(study, frozen, key, 0.000001, study / "work/too-small", transport=perfect_mock)
    result = run_jev(study, frozen, key, cap, study / "work/mock", transport=perfect_mock)
    assert result["complete"] is True
    assert result["transport_kind"] == "injected_mock"
    assert result["scoring"]["correct"] == 40
    assert result["scoring"]["selective_curve"][0]["coverage"] == 1.0
    assert len(list((study / "work/mock").glob("*.json"))) == 41
    selected, _ = cases(study, "test")
    mutated = [dict(row) for row in result["predictions"]]
    mutated[0]["route"] = next(label for label in LABELS if label != mutated[0]["route"])
    assert score(selected, mutated, "jev")["correct"] == 39

    def broken_mock(body, token):
        response = perfect_mock(body, token)
        response["answers"]["route"]["probabilities"]["invalid"] = 0.1
        return response

    failed = run_jev(study, frozen, key, cap, study / "work/failed", transport=broken_mock)
    assert failed["complete"] is False
    assert failed["completed_cases"] == 0
    assert failed["known_gross_cost_usd"] > 0
    assert (study / "work/failed/report.json").exists()
    with pytest.raises(ValueError, match="fresh attempt"):
        run_jev(study, frozen, key, cap, study / "work/failed", transport=perfect_mock)


def test_response_rejects_invalid_distribution_and_missing_usage():
    valid = {
        "model": "jev-1.13.0",
        "answers": {
            "route": {
                "type": "choice",
                "choice": "coverage",
                "confidence": 0.8,
                "probabilities": {label: float(label == "coverage") for label in LABELS},
            }
        },
        "usage": {"input_tokens": 12},
    }
    assert parse_jev_response(valid)["choice"] == "coverage"
    bad = {**valid, "usage": {"input_tokens": True}}
    with pytest.raises(ValueError, match="billable"):
        parse_jev_response(bad)
    bad = json.loads(json.dumps(valid))
    bad["answers"]["route"]["probabilities"]["coverage"] = float("nan")
    with pytest.raises(ValueError, match="probabilities"):
        parse_jev_response(bad)


def test_existing_analyst_quote_and_route_mapping_stay_offline(tmp_path, project):
    demo = tmp_path / "demo"
    build_demo(project, demo)
    data_project = demo / "project"
    clock = CheckedTools(data_project).compare_clock_buckets("30_to_59", "60_plus")
    assert clock["evaluation_coverage_difference_first_minus_second"] is None
    assert clock["error_proxy_rate_difference_first_minus_second"] is None
    frozen = analyst_preflight(project, data_project, "dev")
    assert len(frozen["cells"]) == 40
    assert 0 < frozen["total_reserved_cost_usd"] < 1
    assert route_from_answer({"status": "needs_clarification"}) == "clarify"
    assert route_from_answer({"status": "unsupported"}) == "unsupported"
    assert (
        route_from_answer(
            {
                "status": "answered",
                "evidence": [
                    {"tool": "query_metric", "args": {"metric_id": "opening_usage", "filters": {}}}
                ],
            }
        )
        == "opening_usage"
    )
    with pytest.raises(ValueError, match="cap"):
        run_analyst(
            project,
            data_project,
            frozen,
            project / "work/.env",
            0.000001,
            project / "work/m8-unaffordable",
        )


def test_duckdb_replay_and_display_do_not_claim_live_models(tmp_path, project):
    study, _ = _project(tmp_path, project)
    replay = offline_replay(study, "test", study / "work/questions.duckdb")
    assert replay["rows"] == 40
    assert replay["scoring"]["correct"] == 35
    assert "jev_eval" in replay["sql_preview"]
    assert replay["kind"].endswith("no_jev_calls")
    with pytest.raises(ValueError, match="fresh"):
        offline_replay(study, "test", study / "work/questions.duckdb")
    document = render(rules_report(study, "test"))
    assert "35/40 correct" in document
    assert document.count("Awaiting actual evaluation") == 2
    assert "40/40 correct" not in document


def test_comparison_hybrid_counts_paid_fallback_without_relabeling_harness(tmp_path, project):
    study, _ = _project(tmp_path, project)
    rules = rules_report(study, "test")
    selected, manifest = cases(study, "test")
    jev_predictions = [
        {
            "id": row["id"],
            "route": row["label"],
            "probabilities": {
                label: (0.8 if label == row["label"] else 0.2 / 7) for label in LABELS
            },
            "gross_cost_usd": 0.001,
        }
        for row in selected
    ]
    analyst_predictions = [
        {"id": row["id"], "route": row["label"], "gross_cost_usd": 0.002} for row in selected
    ]
    jev = {
        "kind": "m8_jev_live_attempt",
        "transport_kind": "typesafe_api",
        "split": "test",
        "case_sha256": manifest["case_sha256"],
        "complete": True,
        "accounted_gross_usd": 0.04,
        "predictions": jev_predictions,
        "scoring": score(selected, jev_predictions, "jev"),
    }
    analyst = {
        "kind": "m8_existing_structured_analyst_attempt",
        "transport_kind": "openai_api",
        "split": "test",
        "case_sha256": manifest["case_sha256"],
        "complete": True,
        "accounted_gross_usd": 0.08,
        "predictions": analyst_predictions,
        "scoring": score(selected, analyst_predictions, "analyst"),
    }
    document = render(rules, jev, analyst)
    assert "Pass 1 with analyst fallback" in document
    assert "$0.120000" in document  # All 40 analyst calls at threshold 0.95.
    jev["transport_kind"] = "injected_mock"
    assert "Pass 1 with analyst fallback" not in render(rules, jev, analyst)
