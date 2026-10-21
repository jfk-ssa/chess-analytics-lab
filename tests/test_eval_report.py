"""Structural checks for the live-eval report. No provider and no network."""

import json
from pathlib import Path

import pytest

from chess_analytics.eval_report import (
    ReportIntegrityError,
    build_page,
    discover_receipts,
    load_cases,
    pct,
    sign_test,
)

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "evals/cases/analyst_live_v1.json"
REPORTS = ROOT / "reports"
SOURCE = ROOT / "src/chess_analytics/eval_report.py"


def _cases():
    return load_cases(CASES)


def _committed():
    return discover_receipts(REPORTS)


def _page(paths):
    return build_page(paths, _cases(), strict=True)


def test_receipts_are_discovered_by_github_run_id_not_a_hard_coded_list(tmp_path):
    (tmp_path / "live-eval-receipt-20.json").write_text("{}", encoding="utf-8")
    (tmp_path / "live-eval-receipt-3.json").write_text("{}", encoding="utf-8")
    (tmp_path / "notes.json").write_text("{}", encoding="utf-8")
    found = discover_receipts(tmp_path)
    assert [path.name for path in found] == [
        "live-eval-receipt-3.json",
        "live-eval-receipt-20.json",
    ]
    committed = _committed()
    assert [path.name for path in committed] == [
        "live-eval-receipt-39494372489.json",
        "live-eval-receipt-39519293762.json",
    ]
    source = SOURCE.read_text(encoding="utf-8")
    assert "39494372489" not in source
    assert "39519293762" not in source
    assert "urllib" not in source
    assert "fonts.googleapis.com" not in source
    assert "base64" not in source


def test_committed_page_matches_receipt_numbers_and_every_case():
    page = _page(_committed())
    luna, sol = (json.loads(path.read_text(encoding="utf-8")) for path in _committed())
    cases = _cases()
    assert page.title == "The most accurate model failed the gate"
    assert f"{pct(luna['headline_pass_rate'], 2)}" in page.scorecards_html
    assert f"{pct(sol['headline_pass_rate'], 2)}" in page.scorecards_html
    assert (
        f"{luna['headline_passed']} of {len(luna['rows'])} requests passed · 7 extraction repairs"
        in page.scorecards_html
    )
    assert (
        f"{sol['headline_passed']} of {len(sol['rows'])} requests passed · 0 repairs"
        in page.scorecards_html
    )
    assert "Hard fail" in page.scorecards_html
    assert "Gate clear" in page.scorecards_html
    assert all(ok for _, ok in page.checks)
    for case_id in cases:
        assert case_id in page.heat_table_html
        assert case_id in page.heatmap_svg
    assert "boundary_budget" in page.callouts_html
    assert "needs_clarification" in page.callouts_html
    assert "unsupported" in page.callouts_html
    assert "5 of 5" in page.callouts_html
    combined = " ".join(
        (
            page.caveat_html,
            page.notes_html,
            page.callouts_html,
            page.scorecards_html,
            page.heatmap_svg,
            page.intervals_svg,
        )
    )
    assert "unexplained" not in combined.lower()
    assert "under investigation" not in combined.lower()
    assert "public_extract.py" in page.caveat_html
    assert "implementation_hash" in page.caveat_html
    assert "dataset_id" in page.caveat_html
    assert "implementation_sha256" in page.caveat_html
    assert "src/**/*.py" in page.caveat_html
    assert 'id="ev-intervals-title"' in page.intervals_svg
    assert 'id="ev-intervals-desc"' in page.intervals_svg
    assert 'role="img"' in page.heatmap_svg
    wins_luna, wins_sol, probability = sign_test(
        _passes(luna),
        _passes(sol),
    )
    assert f"p = {probability:.4f}" in page.pairwise_html
    assert f"better on {wins_sol}" in page.pairwise_html
    assert f"on {wins_luna}" in page.pairwise_html
    assert "prompts differ only by dataset id" in page.pairwise_html
    assert "live-eval-receipt-39494372489.json" in page.provenance_html
    assert "differs" in page.provenance_html
    assert "240 requests" in page.provenance_html


def _passes(receipt):
    counts = {}
    for row in receipt["rows"]:
        counts[row["case_id"]] = counts.get(row["case_id"], 0) + int(row["passed"])
    return counts


def test_page_builds_for_one_receipt_and_for_an_extra_effort(tmp_path):
    committed = _committed()
    cases = _cases()
    luna_only = build_page(committed[:1], cases, strict=True)
    assert "gpt-6-luna" in luna_only.scorecards_html
    assert "gpt-6-sol" not in luna_only.scorecards_html
    assert luna_only.pairwise_html == ""
    assert "86.25%" in luna_only.scorecards_html
    sol = json.loads(committed[1].read_text(encoding="utf-8"))
    sol["reasoning_effort"] = "high"
    sol["run_id"] = "effort-high-run"
    extra = tmp_path / "live-eval-receipt-9.json"
    extra.write_text(json.dumps(sol), encoding="utf-8")
    three = build_page([*committed, extra], cases, strict=True)
    assert "gpt-6-sol · high" in three.scorecards_html
    assert "gpt-6-luna" in three.scorecards_html
    assert three.receipt_files[-1] == extra.name
    sol["headline_passed"] = 0
    broken = tmp_path / "live-eval-receipt-8.json"
    broken.write_text(json.dumps(sol), encoding="utf-8")
    with pytest.raises(ReportIntegrityError):
        build_page([broken], cases, strict=True)


def test_model_effort_artifact_names_sort_by_the_trailing_run_id(tmp_path):
    """The grok artifact name keeps the GitHub run id last, after r<repeats>."""
    names = [
        "live-eval-receipt-grok-4.7-low-r5-20.json",
        "live-eval-receipt-gpt-6-luna-none-r5-3.json",
        "live-eval-receipt-gpt-6-sol-none-r1-100.json",
        "live-eval-receipt-grok-4.7-high-r1-9.json",
        "live-eval-receipt-grok-4.7-xhigh-r20-8.json",
        "live-eval-receipt-4.json",
        "live-eval-receipt-notes.json",
    ]
    for name in names:
        (tmp_path / name).write_text("{}", encoding="utf-8")
    assert [path.name for path in discover_receipts(tmp_path)] == [
        "live-eval-receipt-gpt-6-luna-none-r5-3.json",
        "live-eval-receipt-4.json",
        "live-eval-receipt-grok-4.7-xhigh-r20-8.json",
        "live-eval-receipt-grok-4.7-high-r1-9.json",
        "live-eval-receipt-grok-4.7-low-r5-20.json",
        "live-eval-receipt-gpt-6-sol-none-r1-100.json",
        "live-eval-receipt-notes.json",
    ]


def test_discover_on_the_committed_directory_ignores_other_reports():
    names = {path.name for path in _committed()}
    assert names == {path.name for path in REPORTS.glob("live-eval-receipt-*.json")}
    assert "opening-corpus.json" not in names
