"""M7 frozen scoring and budget checks without a provider request."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from analyst_m5.evaluation import score_case_m7
from analyst_m5.experiment import prepare, run

PROJECT = Path(__file__).resolve().parents[1]


def test_clock_coverage_abstention_remains_a_scored_failure():
    cases = json.loads((PROJECT / "evals/cases/m7_holdout.json").read_text())
    case = next(c for c in cases if c["id"] == "m7_clock_10_to_29_coverage")
    answer = {
        "status": "unsupported",
        "dataset_id": case["dataset_id"],
        "result": None,
        "evidence_ids": [],
        "evidence": [],
        "caveats": ["observed_prefix_only"],
        "interpretation": "descriptive_observed_prefix",
    }
    scored = score_case_m7(case, answer)
    assert not scored["passed"]
    assert scored["rubric_version"] == "m7-1.0"
    assert {"status", "result_values", "evidence"} <= set(scored["failures"])


def test_full_m7_preflight_fits_approved_cumulative_cap():
    frozen = json.loads((PROJECT / "reports/M7-April-v8-preflight.json").read_text())
    assert frozen["conditions"] == ["semantic_context"]
    assert frozen["attempts_planned"] == len(frozen["cells"]) == 50
    assert frozen["max_transport_retries_per_run"] == 1
    assert 0.094620415 + 3 * frozen["conservative_total_usd"] <= 0.5
    april = PROJECT / "work/m7-april-project"
    if not (april / "data/analytical-current.json").exists():
        pytest.skip("optional April data snapshot not in clean checkout")
    for name, digest in frozen["frozen_file_sha256"].items():
        assert hashlib.sha256((april / name).read_bytes()).hexdigest() == digest


def test_single_transport_retry_is_logged_and_charged(tmp_path, monkeypatch):
    from analyst_m5 import experiment

    cases = [
        {"id": "a", "question": "A", "category": "basic_calculation"},
        {"id": "b", "question": "B", "category": "basic_calculation"},
    ]
    (tmp_path / "cases.json").write_text(json.dumps(cases))
    cells = [
        {"case_id": case["id"], "condition": "semantic_context", "reserved_cost_usd": 0.01}
        for case in cases
    ]
    frozen = {
        "case_file": "cases.json",
        "cells": cells,
        "max_run_usd": 0.5,
        "fits_cap": True,
        "max_transport_retries_per_run": 1,
    }
    frozen.update(
        {
            key: None
            for key in (
                "dataset_id",
                "case_set_sha256",
                "selection",
                "conditions",
                "model",
                "max_output_tokens",
                "input_usd_per_million",
                "output_usd_per_million",
                "cache_write_usd_per_million",
                "cached_input_usd_per_million",
                "price_source",
                "price_checked_utc_date",
                "attempts_planned",
                "transport_retry_reservation_usd",
                "conservative_total_usd",
                "frozen_file_sha256",
            )
        }
    )
    path = tmp_path / "preflight.json"
    path.write_text(json.dumps(frozen))
    monkeypatch.setattr(experiment, "prepare", lambda *a, **k: frozen)
    monkeypatch.setattr(
        experiment,
        "live_answer",
        lambda project, question, config_path, **kw: {
            "status": "answered",
            "provider": {"raw_response": kw["transport"](b"{}", "test-key")},
        },
    )
    monkeypatch.setattr(experiment, "score_case_m7", lambda case, answer: {"passed": True})
    monkeypatch.setenv(experiment.KEY_ENV, "test-key")
    calls = 0

    def transport(body, key):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("provider HTTP 400: invalid_request_error: Invalid prompt")
        return {"usage": {"input_tokens": 100, "output_tokens": 10}, "output": []}

    result = run(
        tmp_path,
        None,
        path,
        max_run_usd=0.5,
        transport=transport,
        holdout=True,
        holdout_version=10,
        conditions=("semantic_context",),
    )
    assert result["attempts"] == result["completed"] == 2
    assert result["transport_retries"] == 1
    assert result["unknown_cost_reservations_usd"] == 0.01
    assert result["gross_cost_accounted_usd"] == pytest.approx(
        result["known_gross_cost_usd"] + 0.01
    )
    first = json.loads(next(Path(result["records_dir"]).glob("00-*.json")).read_text())
    assert len(first["transport_retries"]) == 1
    assert first["transport_retries"][0]["reserved_cost_usd"] == 0.01


def test_march_frozen_preflight_and_remaining_cumulative_cap():
    frozen = json.loads((PROJECT / "reports/M7-March-v9-preflight.json").read_text())
    assert frozen["attempts_planned"] == 50
    assert frozen["max_transport_retries_per_run"] == 1
    assert 0.102386695 + 3 * frozen["conservative_total_usd"] <= 0.5
    march = PROJECT / "work/m7-march-project"
    if not (march / "data/analytical-current.json").exists():
        pytest.skip("optional March data snapshot not in clean checkout")
    for name, digest in frozen["frozen_file_sha256"].items():
        assert hashlib.sha256((march / name).read_bytes()).hexdigest() == digest


def test_february_preflight_reserves_three_retries_within_cumulative_cap():
    frozen = json.loads((PROJECT / "reports/M7-February-v10-preflight.json").read_text())
    assert frozen["attempts_planned"] == 50
    assert frozen["max_transport_retries_per_run"] == 3
    assert frozen["transport_retry_reservation_usd"] == pytest.approx(
        3 * max(cell["reserved_cost_usd"] for cell in frozen["cells"])
    )
    assert 0.10763917 + 3 * frozen["conservative_total_usd"] <= 0.5
    february = PROJECT / "work/m7-february-project"
    if not (february / "data/analytical-current.json").exists():
        pytest.skip("optional February data snapshot not in clean checkout")
    for name, digest in frozen["frozen_file_sha256"].items():
        assert hashlib.sha256((february / name).read_bytes()).hexdigest() == digest


def test_january_frozen_preflight_fits_remaining_cap():
    frozen = json.loads((PROJECT / "reports/M7-January-v11-preflight.json").read_text())
    assert frozen["attempts_planned"] == 50
    assert frozen["max_transport_retries_per_run"] == 3
    assert frozen["transport_retry_reservation_usd"] == pytest.approx(
        3 * max(cell["reserved_cost_usd"] for cell in frozen["cells"])
    )
    assert 0.11524751 + 3 * frozen["conservative_total_usd"] <= 0.5
    january = PROJECT / "work/m7-january-project"
    if not (january / "data/analytical-current.json").exists():
        pytest.skip("optional January data snapshot not in clean checkout")
    for name, digest in frozen["frozen_file_sha256"].items():
        assert hashlib.sha256((january / name).read_bytes()).hexdigest() == digest


def test_december_sol_preflight_is_independent_and_bounded():
    frozen = json.loads((PROJECT / "reports/M7-December-Sol-v12-preflight.json").read_text())
    assert frozen["model"] == "gpt-6-sol"
    assert frozen["attempts_planned"] == 50
    assert frozen["max_transport_retries_per_run"] == 0
    assert 0.13879496 + 3 * frozen["conservative_total_usd"] <= 6.0
    december = PROJECT / "work/m7-december-project"
    config = PROJECT / "work/m7-sol-provider.json"
    if not (december / "data/analytical-current.json").exists() or not config.exists():
        pytest.skip("optional December snapshot and proposed config not in clean checkout")
    if not (december / "src/chess_analytics/m7_campaign.py").exists():
        pytest.skip("December workspace predates the consolidated campaign command")
    current = prepare(
        december,
        config,
        holdout=True,
        holdout_version=14,
        conditions=("semantic_context",),
    )
    for key in ("case_set_sha256", "dataset_id", "cells"):
        assert current[key] == frozen[key]


def test_december_live_gate_reconciles_failed_reservation_and_three_runs(tmp_path):
    preflight = PROJECT / "reports/M7-December-Sol-v12-preflight.json"
    reports = [PROJECT / f"reports/M7-December-Sol-v12-run-{i}.json" for i in (1, 2, 3)]
    audits = [PROJECT / f"reports/M7-December-Sol-v12-run-{i}-audit.json" for i in (1, 2, 3)]
    sandbox = PROJECT / "reports/M7-December-Sol-v12-sandbox-partial.json"

    def gate(paths, output):
        process = subprocess.run(
            [
                sys.executable,
                "-m",
                "chess_analytics.cli",
                "m7",
                "--campaign",
                "december",
                "check",
                "--preflight",
                str(preflight),
                "--reports",
                *(str(path) for path in paths),
                "--audits",
                *(str(path) for path in audits),
                "--sandbox-attempt",
                str(sandbox),
                "--out",
                str(output),
            ],
            cwd=PROJECT,
            capture_output=True,
            text=True,
        )
        return process.returncode, json.loads(output.read_text())

    code, result = gate(reports, tmp_path / "accepted.json")
    assert code == 0
    assert result["live_gates_passed"]
    assert result["scored_per_repeat"] == [50, 50, 50]
    assert result["cumulative_gross_accounted_usd"] == pytest.approx(0.35392836)
    assert result["sandbox_unknown_cost_reservation_usd"] == pytest.approx(0.0372375)

    damaged = json.loads(reports[0].read_text())
    damaged["attempts"][0]["request_sha256"] = "drifted"
    changed = tmp_path / "damaged.json"
    changed.write_text(json.dumps(damaged))
    code, rejected = gate([changed, *reports[1:]], tmp_path / "rejected.json")
    assert code == 1
    assert not rejected["live_gates_passed"]
    assert not rejected["gates"]["frozen_complete_runs"]
