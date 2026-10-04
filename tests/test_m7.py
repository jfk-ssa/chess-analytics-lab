"""M7 frozen scoring and budget checks without a provider request."""

import json
from pathlib import Path

import pytest

from analyst_m5.evaluation import score_case_m7
from analyst_m5.experiment import prepare

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
    if not (PROJECT / "data/analytical-current.json").exists():
        pytest.skip("optional real analytical snapshot not in clean checkout")
    frozen = json.loads((PROJECT / "reports/M7-holdout-v4-preflight.json").read_text())
    current = prepare(PROJECT, max_run_usd=0.5, holdout=True, holdout_version=6)
    for key in ("case_set_sha256", "dataset_id", "frozen_file_sha256", "cells"):
        assert current[key] == frozen[key]
    assert frozen["attempts_planned"] == 100
    assert len(frozen["cells"]) == 100
    assert 0.067626885 + 3 * frozen["conservative_total_usd"] <= 0.5
