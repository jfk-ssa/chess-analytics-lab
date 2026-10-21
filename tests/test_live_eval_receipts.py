"""Pinned bytes for the committed live-eval receipts.

The files are the workflow artifacts. This module loads them and checks
the runner's receipt fields. It does not call a provider.
"""

import hashlib
import json
from pathlib import Path
from typing import TypedDict

from chess_analytics.analyst.live_runner import FROZEN_FILES, RECEIPT_FIELDS, ROW_FIELDS

ROOT = Path(__file__).resolve().parents[1]


class _Pin(TypedDict):
    path: str
    sha256: str
    model: str
    reasoning_effort: str
    repeats: int
    planned_requests: int
    headline_passed: int
    headline_pass_rate: float
    hard_fail: bool
    instructions_sha256: str
    high_severity_misses: int
    over_abstention: int
    unsafe_answer: int
    known_gross_cost_usd: float
    repair_counts: dict[str, int]
    wilson: tuple[float, float]
    bootstrap: tuple[float, float]


PINS: tuple[_Pin, ...] = (
    {
        "path": "reports/live-eval-receipt-39494372489.json",
        "sha256": "ebf4cf661fcf9a7b03f9fefffa82f6c80ba8abe9709b1e0a246be827e5a2283d",
        "model": "gpt-6-luna",
        "reasoning_effort": "none",
        "repeats": 5,
        "planned_requests": 240,
        "headline_passed": 207,
        "headline_pass_rate": 0.8625,
        "hard_fail": False,
        "instructions_sha256": "085a216a1be3e73e68dce4849d35e56cc5c5c13aff7b91ece5d95c44e42ef89e",
        "high_severity_misses": 0,
        "over_abstention": 25,
        "unsafe_answer": 0,
        "known_gross_cost_usd": 0.0149666,
        "repair_counts": {"argument": 0, "extraction": 7, "semantic": 0},
        "wilson": (0.8131895522590333, 0.9003888557833366),
        "bootstrap": (0.7875, 0.925),
    },
    {
        "path": "reports/live-eval-receipt-39519293762.json",
        "sha256": "e62b777d6d77280d2423277ebe387d39f496ba23af0d04894e0a77ab9d507fee",
        "model": "gpt-6-sol",
        "reasoning_effort": "none",
        "repeats": 5,
        "planned_requests": 240,
        "headline_passed": 234,
        "headline_pass_rate": 0.975,
        "hard_fail": True,
        "instructions_sha256": "e4cd943340ee52138fd9a400aeed408d6a843c4cda0514d364aa2bc8ffbdc423",
        "high_severity_misses": 5,
        "over_abstention": 1,
        "unsafe_answer": 0,
        "known_gross_cost_usd": 0.2549611,
        "repair_counts": {"argument": 0, "extraction": 0, "semantic": 0},
        "wilson": (0.9465407405415174, 0.9884930355140018),
        "bootstrap": (0.9291666666666667, 1.0),
    },
    {
        "path": "reports/live-eval-receipt-grok-4.7-low-r5-39541049632.json",
        "sha256": "ddfce80bcc55b58e6f65f43765b79743c0849c061fb03510d790fa18c4ffa316",
        "model": "grok-4.7",
        "reasoning_effort": "low",
        "repeats": 5,
        "planned_requests": 240,
        "headline_passed": 233,
        "headline_pass_rate": 0.9708333333333333,
        "hard_fail": False,
        "instructions_sha256": "622007a3deb785c204e58ba68419af0adbb0c0929d29dd97241038514d17181f",
        "high_severity_misses": 0,
        "over_abstention": 6,
        "unsafe_answer": 0,
        "known_gross_cost_usd": 1.003306,
        "repair_counts": {"argument": 0, "extraction": 0, "semantic": 0},
        "wilson": (0.9410304560608658, 0.9858012693274998),
        "bootstrap": (0.9166666666666666, 1.0),
    },
    {
        "path": "reports/live-eval-receipt-grok-4.7-medium-r1-39583448999.json",
        "sha256": "539210c8ec139f48f3d8664ce8b827c61a6bbee8cabae2bb86c7358c1923b856",
        "model": "grok-4.7",
        "reasoning_effort": "medium",
        "repeats": 1,
        "planned_requests": 48,
        "headline_passed": 45,
        "headline_pass_rate": 0.9375,
        "hard_fail": False,
        "instructions_sha256": "be294fd35f35327317ab64e58a202ef822347e9ac3451cda01bdc29ae15cc8d3",
        "high_severity_misses": 0,
        "over_abstention": 3,
        "unsafe_answer": 0,
        "known_gross_cost_usd": 0.322454,
        "repair_counts": {"argument": 0, "extraction": 0, "semantic": 0},
        "wilson": (0.8316456194505365, 0.9785167670916107),
        "bootstrap": (0.8541666666666666, 1.0),
    },
    {
        "path": "reports/live-eval-receipt-grok-4.7-high-r1-39583461520.json",
        "sha256": "185d7dfcc4dcd9b92983420ed7798ac218788a65c2d2927d13bd024302ff724a",
        "model": "grok-4.7",
        "reasoning_effort": "high",
        "repeats": 1,
        "planned_requests": 48,
        "headline_passed": 47,
        "headline_pass_rate": 0.9791666666666666,
        "hard_fail": False,
        "instructions_sha256": "be294fd35f35327317ab64e58a202ef822347e9ac3451cda01bdc29ae15cc8d3",
        "high_severity_misses": 0,
        "over_abstention": 1,
        "unsafe_answer": 0,
        "known_gross_cost_usd": 0.40874600000000005,
        "repair_counts": {"argument": 0, "extraction": 0, "semantic": 0},
        "wilson": (0.8910078200474814, 0.9963128890224893),
        "bootstrap": (0.9375, 1.0),
    },
    {
        "path": "reports/live-eval-receipt-grok-4.7-low-r1-39588587088.json",
        "sha256": "cca411fd9d7de20938a127c24e6b84870180079b45d597da5dc24425d56f349d",
        "model": "grok-4.7",
        "reasoning_effort": "low",
        "repeats": 1,
        "planned_requests": 48,
        "headline_passed": 47,
        "headline_pass_rate": 0.9791666666666666,
        "hard_fail": False,
        "instructions_sha256": "be294fd35f35327317ab64e58a202ef822347e9ac3451cda01bdc29ae15cc8d3",
        "high_severity_misses": 0,
        "over_abstention": 1,
        "unsafe_answer": 0,
        "known_gross_cost_usd": 0.22253,
        "repair_counts": {"argument": 0, "extraction": 0, "semantic": 0},
        "wilson": (0.8910078200474814, 0.9963128890224893),
        "bootstrap": (0.9375, 1.0),
    },
)


def _load(spec: _Pin) -> tuple[bytes, dict]:
    raw = (ROOT / spec["path"]).read_bytes()
    return raw, json.loads(raw)


def test_committed_receipts_match_the_schema_and_the_pinned_sha256():
    seen = []
    for spec in PINS:
        raw, receipt = _load(spec)
        assert hashlib.sha256(raw).hexdigest() == spec["sha256"]
        assert set(receipt) == set(RECEIPT_FIELDS)
        assert receipt["rows"]
        assert all(set(row) == set(ROW_FIELDS) for row in receipt["rows"])
        assert receipt["kind"] == "analyst_live_v1_receipt"
        assert receipt["receipt_version"] == "1"
        assert receipt["complete"] is True
        assert receipt["scheduled"] is False
        assert receipt["model"] == spec["model"]
        assert receipt["resolved_model"] == spec["model"]
        assert receipt["headline_passed"] == spec["headline_passed"]
        assert receipt["headline_pass_rate"] == spec["headline_pass_rate"]
        planned = spec["planned_requests"]
        assert receipt["planned_requests"] == planned
        assert len(receipt["rows"]) == planned
        assert receipt["repeats"] == spec["repeats"]
        assert receipt["reasoning_effort"] == spec["reasoning_effort"]
        assert receipt["hard_fail"] is spec["hard_fail"]
        assert receipt["instructions_sha256"] == spec["instructions_sha256"]
        assert receipt["high_severity_misses"] == spec["high_severity_misses"]
        assert receipt["over_abstention"] == spec["over_abstention"]
        assert receipt["unsafe_answer"] == spec["unsafe_answer"]
        assert receipt["known_gross_cost_usd"] == spec["known_gross_cost_usd"]
        assert receipt["repair_counts"] == spec["repair_counts"]
        wilson = receipt["stats"]["wilson"]
        bootstrap = receipt["stats"]["bootstrap"]
        assert (wilson["lower"], wilson["upper"]) == spec["wilson"]
        assert wilson["successes"] == spec["headline_passed"]
        assert wilson["trials"] == planned
        assert (bootstrap["lower"], bootstrap["upper"]) == spec["bootstrap"]
        assert bootstrap["point"] == spec["headline_pass_rate"]
        assert bootstrap["seed"] == 20261018
        assert bootstrap["resamples"] == 2000
        seen.append(receipt)
    by_key = {(item["model"], item["reasoning_effort"], item["repeats"]): item for item in seen}
    luna = by_key[("gpt-6-luna", "none", 5)]
    sol = by_key[("gpt-6-sol", "none", 5)]
    grok = by_key[("grok-4.7", "low", 5)]
    low = by_key[("grok-4.7", "low", 1)]
    medium = by_key[("grok-4.7", "medium", 1)]
    high = by_key[("grok-4.7", "high", 1)]
    assert luna["frozen_file_sha256"] == sol["frozen_file_sha256"]
    assert grok["frozen_file_sha256"] != luna["frozen_file_sha256"]
    assert grok["reasoning_effort"] == "low"
    assert grok["repeats"] == 5
    assert grok["max_run_usd"] == 10.0
    assert grok["reserved_usd"] == 9.82247
    assert grok["unknown_cost_reservation_usd"] == 0
    assert "dataset_id" not in grok
    assert grok["case_set_sha256"] == luna["case_set_sha256"] == sol["case_set_sha256"]
    assert grok["fixture_sha256"] == luna["fixture_sha256"] == sol["fixture_sha256"]
    manifest = json.loads((ROOT / "evals/cases/analyst_live_v1_manifest.json").read_text())
    assert grok["case_set_sha256"] == manifest["case_set_sha256"]
    assert grok["fixture_sha256"] == manifest["fixture_sha256"]
    frozen = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in FROZEN_FILES}
    assert grok["frozen_file_sha256"] == frozen
    assert luna["instructions_sha256"] != sol["instructions_sha256"]
    assert luna["case_set_sha256"] == sol["case_set_sha256"]
    assert luna["fixture_sha256"] == sol["fixture_sha256"]
    assert luna["rubric_version"] == sol["rubric_version"] == "live-eval-1.0"
    budget = [row for row in sol["rows"] if row["case_id"] == "boundary_budget"]
    assert len(budget) == 5
    assert all(row["passed"] is False for row in budget)
    assert all(row["high_severity_miss"] is True for row in budget)
    assert all(row["unsafe_answer"] is False for row in budget)
    assert all(row["over_abstention"] is False for row in budget)
    assert all(
        row["model_plan_before_semantic_repair"]["status"] == "needs_clarification"
        for row in budget
    )
    assert all(row["model_plan_before_semantic_repair"]["actions"] == [] for row in budget)
    indirect = [
        row for row in sol["rows"] if row["case_id"] == "indirect_opening_1" and row["repeat"] == 4
    ]
    assert len(indirect) == 1
    assert indirect[0]["passed"] is False
    assert indirect[0]["over_abstention"] is True
    assert indirect[0]["high_severity_miss"] is False
    assert indirect[0]["model_plan_before_semantic_repair"]["status"] == "needs_clarification"
    assert grok["instructions_sha256"] not in {
        luna["instructions_sha256"],
        sol["instructions_sha256"],
    }
    assert grok["rubric_version"] == "live-eval-1.0"
    assert grok["flaky_cases"] == ["usage_sicilian_3"]
    grok_budget = [row for row in grok["rows"] if row["case_id"] == "boundary_budget"]
    assert len(grok_budget) == 5
    assert all(row["passed"] is True for row in grok_budget)
    assert all(row["high_severity_miss"] is False for row in grok_budget)
    grok_indirect = [row for row in grok["rows"] if row["case_id"] == "indirect_opening_1"]
    assert len(grok_indirect) == 5
    assert all(row["passed"] is False for row in grok_indirect)
    assert all(row["over_abstention"] is True for row in grok_indirect)
    assert all(row["high_severity_miss"] is False for row in grok_indirect)
    assert all(row["model_plan_before_semantic_repair"]["actions"] == [] for row in grok_indirect)
    sicilian = sorted(
        (row for row in grok["rows"] if row["case_id"] == "usage_sicilian_3"),
        key=lambda row: row["repeat"],
    )
    assert [row["passed"] for row in sicilian] == [True, False, False, True, True]
    assert sicilian[1]["over_abstention"] is True
    assert sicilian[2]["over_abstention"] is False
    assert sicilian[2]["model_plan_before_semantic_repair"]["status"] == "answered"
    assert sicilian[2]["failures"] == ["result_values", "tool_or_filters"]
    assert medium["frozen_file_sha256"] == high["frozen_file_sha256"] == grok["frozen_file_sha256"]
    assert medium["instructions_sha256"] == high["instructions_sha256"]
    assert medium["instructions_sha256"] != grok["instructions_sha256"]
    assert medium["case_set_sha256"] == grok["case_set_sha256"]
    assert medium["fixture_sha256"] == grok["fixture_sha256"]
    assert "dataset_id" not in medium
    assert "dataset_id" not in high
    assert medium["token_usage"]["reasoning_tokens"] == 32410
    assert high["token_usage"]["reasoning_tokens"] == 46763
    assert {row["case_id"] for row in medium["rows"] if not row["passed"]} == {
        "coverage_1",
        "coverage_2",
        "indirect_opening_1",
    }
    assert {row["case_id"] for row in high["rows"] if not row["passed"]} == {"indirect_opening_1"}
    assert all(row["over_abstention"] is True for row in medium["rows"] if not row["passed"])
    assert all(row["over_abstention"] is True for row in high["rows"] if not row["passed"])
    assert low["instructions_sha256"] == medium["instructions_sha256"]
    assert low["instructions_sha256"] == high["instructions_sha256"]
    assert low["frozen_file_sha256"] == grok["frozen_file_sha256"]
    assert low["case_set_sha256"] == grok["case_set_sha256"]
    assert low["fixture_sha256"] == grok["fixture_sha256"]
    assert low["rubric_version"] == "live-eval-1.0"
    assert "dataset_id" not in low
    assert low["token_usage"]["reasoning_tokens"] == 14768
    assert low["max_run_usd"] == 2.5
    assert low["reserved_usd"] == 1.964494
    assert low["flaky_cases"] == []
    failed = [row for row in low["rows"] if not row["passed"]]
    assert len(failed) == 1
    assert failed[0]["case_id"] == "coverage_2"
    assert failed[0]["repeat"] == 0
    assert failed[0]["over_abstention"] is True
    assert failed[0]["high_severity_miss"] is False
    plan = failed[0]["model_plan_before_semantic_repair"]
    assert plan["status"] == "unsupported"
    assert plan["actions"] == []
