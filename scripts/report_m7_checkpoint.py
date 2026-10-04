"""Summarize retained M7 live and offline evidence without erasing stopped runs."""

import json
from decimal import Decimal
from pathlib import Path

from chess_analytics.common import write_json

PROJECT = Path(__file__).resolve().parents[1]


def _read(project: Path, name: str) -> dict:
    return json.loads((project / name).read_text())


def _usd(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.000000001"))


def build(project: Path = PROJECT) -> dict:
    v1_preflight = _read(project, "reports/M7-holdout-preflight.json")
    v1_reports = [
        _read(project, "reports/M7-holdout-partial-1.json"),
        _read(project, "reports/M7-holdout-v1-complete-1.json"),
        _read(project, "reports/M7-holdout-v1-partial-2.json"),
    ]
    diagnostic = _read(project, "reports/M7-http-diagnostic.json")
    v2 = _read(project, "reports/M7-holdout-v2-checkpoint.json")
    v3 = _read(project, "reports/M7-holdout-v3-checkpoint.json")
    v4_preflight = _read(project, "reports/M7-holdout-v4-preflight.json")
    v4 = _read(project, "reports/M7-holdout-v4-partial-1.json")
    v4_audit = _read(project, "reports/M7-holdout-v4-partial-audit-1.json")
    depth = _read(project, "reports/M7-depth-feasibility.json")
    if not (
        [report["attempted"] for report in v1_reports] == [49, 100, 20]
        and v1_reports[0]["attempts"][-1]["gross_cost_usd"] is None
        and v4["attempted"] == 59
        and v4["attempts"][-1]["gross_cost_usd"] is None
        and v4_audit["integrity_passed"] == 58
        and not v2["live_gates_passed"]
        and not v3["live_gates_passed"]
        and v2["attempted"] == v3["attempted"] == 300
    ):
        raise ValueError("retained M7 results differ from expected checkpoint")
    known = (
        sum((_usd(report["known_gross_cost_usd"]) for report in v1_reports), Decimal(0))
        + _usd(diagnostic["gross_cost_usd"])
        + _usd(v2["gross_cost_usd"])
        + _usd(v3["gross_cost_usd"])
        + _usd(v4["known_gross_cost_usd"])
    )
    unknown_reservations = _usd(v1_preflight["cells"][48]["reserved_cost_usd"]) + _usd(
        v4_preflight["cells"][58]["reserved_cost_usd"]
    )
    accounted = known + unknown_reservations
    cap = _usd(v4_preflight["max_run_usd"])
    if accounted > cap or accounted != Decimal("0.074362145"):
        raise ValueError("M7 cumulative gross accounting drift")
    return {
        "kind": "M7 depth checkpoint; inspected live failures retained",
        "phase_status": "in_progress_quality_gate_not_met",
        "live_quality_gate_passed": False,
        "evidence_class": "actual model responses except labeled offline oracle and diagnostic",
        "live_runs": {
            "v1": {
                "benchmark_attempts": sum(r["attempted"] for r in v1_reports),
                "completed_full_repeats": 1,
                "stopped_partial_repeats": 2,
                "full_repeat_scored": "95/100",
                "separate_http_diagnostic_requests": 1,
            },
            "v2": {
                "full_repeats": 3,
                "scored": [90, 96, 92],
                "gate_passed": v2["live_gates_passed"],
                "failed_gate": "run-1 answerable 72/82 below 90%",
            },
            "v3": {
                "full_repeats": 3,
                "scored": [96, 95, 98],
                "gate_passed": v3["live_gates_passed"],
                "failed_gate": "run-1 ambiguity/unsupported 16/18 below 90%",
            },
            "v4": {
                "benchmark_attempts": v4["attempted"],
                "completed": v4["completed"],
                "scored_passed": sum(
                    bool((attempt["score"] or {}).get("passed")) for attempt in v4["attempts"]
                ),
                "schema_only_completed_passed": "12/29",
                "semantic_context_completed_passed": "29/29",
                "not_attempted": v4["planned"] - v4["attempted"],
                "stop_reason": v4["attempts"][-1]["error"],
                "failed_cell_reserved_usd": float(
                    _usd(v4_preflight["cells"][58]["reserved_cost_usd"])
                ),
            },
        },
        "budget": {
            "approved_cumulative_gross_cap_usd": float(cap),
            "known_actual_gross_usd": float(known),
            "unknown_attempt_full_reservations_usd": float(unknown_reservations),
            "cumulative_accounted_gross_usd": float(accounted),
            "remaining_authorized_headroom_usd": float(cap - accounted),
            "credit_balance_not_used_as_cap": True,
        },
        "offline_reference_checks": {
            "splits": 4,
            "cases_per_split": 50,
            "oracle_matches_per_split": 50,
            "source": "independent raw-PGN opening/cohort tallies and M3 clock reference",
        },
        "depth_feasibility": depth["measured"],
        "next_gate": (
            "New independently referenced data and an uninspected holdout; "
            "retain the frozen failures, validate a bounded source-depth method, "
            "then quote any live run against remaining cumulative cap."
        ),
        "limitations": [
            "M7 splits reuse the bounded August 1 source and some clock-bucket concepts.",
            "The v4 run is censored; its 41 unattempted cells are not successes.",
            "Schema-only versus governed context compares prompt conditions, not a SQL baseline.",
            "No broad model-accuracy, monthwide, causal, engine or new-day claim follows.",
        ],
    }


if __name__ == "__main__":
    result = build()
    write_json(PROJECT / "reports/M7-checkpoint.json", result)
    print(json.dumps({"phase_status": result["phase_status"], "budget": result["budget"]}))
