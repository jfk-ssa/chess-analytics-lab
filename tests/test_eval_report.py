"""Structural checks for the live-eval report. No provider and no network."""

import json
from pathlib import Path

import pytest

from chess_analytics.analyst.live_runner import _tokens as receipt_token_totals
from chess_analytics.analyst.live_stats import cluster_bootstrap, wilson_interval
from chess_analytics.eval_report import (
    PERFECT_DOT,
    PERFECT_TEXT,
    ReportIntegrityError,
    _misses,
    _pair_explanation,
    _times,
    build_page,
    discover_receipts,
    load_cases,
    load_receipts,
    pair_explained_by_dataset_id,
    pct,
    scorecard,
    sign_test,
    usd,
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
        "live-eval-receipt-grok-4.7-low-r5-39541049632.json",
        "live-eval-receipt-grok-4.7-medium-r1-39583448999.json",
        "live-eval-receipt-grok-4.7-high-r1-39583461520.json",
    ]
    source = SOURCE.read_text(encoding="utf-8")
    assert "39494372489" not in source
    assert "39519293762" not in source
    assert "urllib" not in source
    assert "fonts.googleapis.com" not in source
    assert "base64" not in source


def test_committed_page_matches_receipt_numbers_and_every_case():
    page = _page(_committed())
    by_name = {path.name: json.loads(path.read_text(encoding="utf-8")) for path in _committed()}
    luna = by_name["live-eval-receipt-39494372489.json"]
    sol = by_name["live-eval-receipt-39519293762.json"]
    grok = by_name["live-eval-receipt-grok-4.7-low-r5-39541049632.json"]
    medium = by_name["live-eval-receipt-grok-4.7-medium-r1-39583448999.json"]
    high = by_name["live-eval-receipt-grok-4.7-high-r1-39583461520.json"]
    cases = _cases()
    assert page.title == "The most accurate model failed the gate"
    assert f"{pct(luna['headline_pass_rate'], 2)}" in page.scorecards_html
    assert f"{pct(sol['headline_pass_rate'], 2)}" in page.scorecards_html
    assert f"{pct(grok['headline_pass_rate'], 2)}" in page.scorecards_html
    assert (
        f"{luna['headline_passed']} of {len(luna['rows'])} requests passed · 7 extraction repairs"
        in page.scorecards_html
    )
    assert (
        f"{sol['headline_passed']} of {len(sol['rows'])} requests passed · 0 repairs"
        in page.scorecards_html
    )
    assert (
        f"{grok['headline_passed']} of {len(grok['rows'])} requests passed · 0 repairs"
        in page.scorecards_html
    )
    assert "Hard fail" in page.scorecards_html
    assert "Gate clear" in page.scorecards_html
    assert page.scorecards_html.count('class="ev-stat"') == 3
    assert page.scorecards_html.count('class="ev-rate"') == 3
    assert "<small" not in page.scorecards_html
    assert all(ok for _, ok in page.checks)
    for case_id in cases:
        assert case_id in page.heat_table_html
        assert case_id in page.heatmap_svg
    assert "boundary_budget" in page.callouts_html
    assert "needs_clarification" in page.callouts_html
    assert "unsupported" in page.callouts_html
    assert "5 of 5" in page.callouts_html
    assert "240 requests" in page.callouts_html
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
    wins_luna, wins_sol, probability = sign_test(_bits(luna), _bits(sol))
    assert f"p = {probability:.4f}" in page.pairwise_html
    assert f"better on {wins_sol}" in page.pairwise_html
    assert f"on {wins_luna}" in page.pairwise_html
    assert "prompts differ only by dataset id" in page.pairwise_html
    assert "frozen inputs differ" not in page.pairwise_html
    assert "grok-4.7" not in page.pairwise_html
    assert "frozen inputs differ" in page.caveat_html
    assert "model_catalog.py" in page.caveat_html
    assert "97.50%" in page.description
    assert "86.25%" in page.description
    assert "86.25%" in page.scorecards_html
    assert "97.08%" in page.scorecards_html
    assert "97.08%" not in page.description
    assert "3.9×" not in page.description
    assert "same pass-rate" not in page.description
    assert "1/17" in page.description
    assert "boundary_budget" not in page.description
    assert "one sample" in page.description
    assert "not a second run" in page.description
    assert "5 times" in page.description
    assert "5 high-severity misses" in page.description
    assert "cautious direction" not in page.fail_take_html
    assert "25 over-abstentions" in page.fail_take_html
    assert "6 over-abstentions" in page.fail_take_html
    assert "7 no valid plans" in page.fail_take_html
    assert "1 wrong answer" in page.fail_take_html
    assert "usage_sicilian_3" in page.flaky_take_html
    assert "indirect_opening_1" in page.flaky_take_html
    assert "67.0×" in page.cost_take_html
    assert "3.9×" in page.cost_take_html
    assert "3,810.5" in page.cost_take_html
    assert "not a quality result" in page.cost_take_html
    assert "bought" not in page.cost_take_html
    assert "does not separate" not in page.cost_take_html
    assert "overlapping" not in page.cost_take_html
    assert "not prompt length alone" in page.cost_take_html
    assert "one 5-repeat sample" in page.cost_take_html
    assert "recovered_argument_suffixes" in page.notes_html
    assert "duplicated or trailing" not in page.notes_html
    assert "#9aa0a8" not in page.heatmap_svg
    assert "#b8bec6" not in page.heatmap_svg
    assert PERFECT_TEXT in page.heatmap_svg
    assert PERFECT_DOT in page.heatmap_svg
    assert "live-eval-receipt-39494372489.json" in page.provenance_html
    assert "live-eval-receipt-grok-4.7-low-r5-39541049632.json" in page.provenance_html
    assert "differs" in page.provenance_html
    assert "240 requests" in page.provenance_html
    sweep = page.sweep_lead_html + page.sweep_cards_html + page.sweep_detail_html
    assert page.sensitivity_html == ""
    assert "1-repeat effort comparison" in sweep
    assert 'data-sweep-slot="low-1"' in page.sweep_cards_html
    assert "1-repeat receipt not in this report yet" in sweep
    assert "not strictly comparable" in sweep
    assert "06bc03a3eabab5bbf3b958ec" in sweep
    assert "bea194558220eb669940d8f3" in sweep
    assert "cause is not recorded" not in page.caveat_html
    assert "cause is not recorded" not in sweep
    assert "This pair is comparable." in page.caveat_html
    for case_id in ("coverage_1", "coverage_2", "indirect_opening_1", "usage_sicilian_3"):
        assert case_id in sweep
    assert "The other 45 cases" in sweep
    assert f"{pct(medium['headline_pass_rate'], 2)}" in sweep
    assert f"{pct(high['headline_pass_rate'], 2)}" in sweep
    assert "93.75%" not in page.scorecards_html
    assert "97.92%" not in page.scorecards_html
    assert usd(grok["known_gross_cost_usd"] / grok["repeats"], 6) in sweep
    assert usd(medium["known_gross_cost_usd"], 6) in sweep
    assert usd(high["known_gross_cost_usd"], 6) in sweep
    assert "about $0.20" in sweep
    assert "13,955.2" in sweep
    assert f"{medium['token_usage']['reasoning_tokens']:,}" in sweep
    assert f"{high['token_usage']['reasoning_tokens']:,}" in sweep
    wins_medium, wins_high, sweep_p = sign_test(_bits(medium), _bits(high))
    assert f"p = {sweep_p:.4f}" in sweep
    assert f"better on {wins_high}" in sweep
    assert f"on {wins_medium}" in sweep
    assert "grok-4.7 · low</b> vs" not in sweep
    assert "vs <b>grok-4.7 · low</b>" not in sweep
    assert "Low's interval is not compared" in sweep
    assert "Medium and high clear the gate" in sweep
    assert "All three clear the gate" not in sweep
    assert "The 1-repeat low run is not in this test." in sweep
    assert "The 5-repeat headline low run is not in this test." in sweep
    assert page.sweep_cards_html.count('class="ev-card"') == 3
    assert 'id="ev-sweep-intervals-title"' in sweep
    assert "The system prompt is the same except" in sweep
    assert "the system prompt is the same except" not in sweep


def test_grok_snapshot_pair_is_not_treated_as_comparable():
    """ADR 0096's dataset-id exception does not cover the grok effort hashes."""
    receipts = load_receipts(_committed())
    by_key = {(receipt.model, receipt.effort): receipt for receipt in receipts}
    low = by_key[("grok-4.7", "low")]
    medium = by_key[("grok-4.7", "medium")]
    high = by_key[("grok-4.7", "high")]
    luna = by_key[("gpt-6-luna", "none")]
    sol = by_key[("gpt-6-sol", "none")]
    assert not pair_explained_by_dataset_id(low, medium)
    assert not pair_explained_by_dataset_id(low, high)
    assert pair_explained_by_dataset_id(luna, sol)
    assert "not strictly comparable" in _pair_explanation(low, medium)
    assert "This pair is comparable." not in _pair_explanation(low, medium)


def test_one_repeat_low_fills_the_sweep_slot(tmp_path):
    """A later low x1 on the medium/high hash joins the sweep and leaves the headline."""
    committed = _committed()
    cases = _cases()
    medium_path = next(path for path in committed if "medium-r1" in path.name)
    payload = json.loads(medium_path.read_text(encoding="utf-8"))
    payload["reasoning_effort"] = "low"
    payload["run_id"] = "low1slot0000000000000000000000"
    slot = tmp_path / "live-eval-receipt-grok-4.7-low-r1-999.json"
    slot.write_text(json.dumps(payload), encoding="utf-8")
    page = build_page([*committed, slot], cases, strict=True)
    sweep = page.sweep_lead_html + page.sweep_cards_html + page.sweep_detail_html
    assert page.title == "The most accurate model failed the gate"
    assert "233 of 240 requests passed" in page.scorecards_html
    assert 'data-sweep-slot="low-1"' not in sweep
    assert "1-repeat receipt not in this report yet" not in sweep
    assert "Waiting" not in page.sweep_cards_html
    assert page.sweep_cards_html.count('class="ev-card"') == 3
    assert "45 of 48 requests passed" in page.sweep_cards_html
    assert "47 of 48 requests passed" in page.sweep_cards_html
    assert "grok-4.7 · low (low1sl)</b> vs" in sweep
    assert "p = 1.0000" in sweep
    assert "The 5-repeat headline low run is not in this test." in sweep
    assert "not strictly comparable" in sweep
    assert "All three 1-repeat runs clear the gate" in sweep
    assert page.sensitivity_html == ""


def _bits(receipt):
    grouped = {}
    for row in sorted(receipt["rows"], key=lambda item: (item["case_id"], item["repeat"])):
        grouped.setdefault(row["case_id"], []).append(bool(row["passed"]))
    return grouped


def test_page_builds_for_one_receipt_and_for_an_extra_effort(tmp_path):
    committed = _committed()
    cases = _cases()
    luna_only = build_page(committed[:1], cases, strict=True)
    assert "gpt-6-luna" in luna_only.scorecards_html
    assert "gpt-6-sol" not in luna_only.scorecards_html
    assert luna_only.pairwise_html == ""
    assert "86.25%" in luna_only.scorecards_html
    assert luna_only.scorecards_html.count('class="ev-stat"') == 1
    sol = json.loads(committed[1].read_text(encoding="utf-8"))
    sol["reasoning_effort"] = "high"
    sol["run_id"] = "effort-high-run"
    extra = tmp_path / "live-eval-receipt-9.json"
    extra.write_text(json.dumps(sol), encoding="utf-8")
    three = build_page([*committed, extra], cases, strict=True)
    assert "gpt-6-sol · high" in three.scorecards_html
    assert "gpt-6-luna" in three.scorecards_html
    assert three.scorecards_html.count('class="ev-stat"') == 4
    assert "<small" not in three.scorecards_html
    assert three.receipt_files == (extra.name, *(path.name for path in committed))
    sol["headline_passed"] = 0
    broken = tmp_path / "live-eval-receipt-8.json"
    broken.write_text(json.dumps(sol), encoding="utf-8")
    with pytest.raises(ReportIntegrityError):
        build_page([broken], cases, strict=True)


def test_scorecard_escapes_repair_names(tmp_path):
    raw = json.loads(_committed()[0].read_text(encoding="utf-8"))
    raw["repair_counts"] = {"<img alt=x>": 7}
    path = tmp_path / "live-eval-receipt-1.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    html = scorecard(load_receipts([path])[0])
    assert html.count("&lt;img alt=x&gt;") == 2
    assert "<img" not in html


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


def test_plain_and_effort_names_sort_by_trailing_run_id(tmp_path):
    names = [
        "live-eval-receipt-20.json",
        "live-eval-receipt-grok-4.7-high-r5-10.json",
        "live-eval-receipt-grok-4.7-high-r5-900.json",
        "live-eval-receipt-grok-4.7-low-r1-100.json",
    ]
    for name in names:
        (tmp_path / name).write_text("{}", encoding="utf-8")
    assert [path.name for path in discover_receipts(tmp_path)] == [
        "live-eval-receipt-grok-4.7-high-r5-10.json",
        "live-eval-receipt-20.json",
        "live-eval-receipt-grok-4.7-low-r1-100.json",
        "live-eval-receipt-grok-4.7-high-r5-900.json",
    ]


def test_sign_test_refuses_unequal_repeats():
    with pytest.raises(ValueError, match="repeat"):
        sign_test({"case": [True, False]}, {"case": [True]})


def test_singular_repeat_and_miss_phrases():
    assert _times(1) == "1 time"
    assert _times(5) == "5 times"
    assert _misses(1) == "1 high-severity miss"
    assert _misses(5) == "5 high-severity misses"


def test_one_repeat_receipt_stays_out_of_the_headline_comparison(tmp_path):
    committed = _committed()
    cases = _cases()
    luna = json.loads(committed[0].read_text(encoding="utf-8"))
    single = _one_repeat(luna)
    path = tmp_path / "live-eval-receipt-11.json"
    path.write_text(json.dumps(single), encoding="utf-8")
    page = build_page([*committed, path], cases, strict=True)
    assert page.title == "The most accurate model failed the gate"
    assert "grok-4.7 · high" in page.sensitivity_html
    assert "1 time" in page.sensitivity_intro
    assert "sign test" in page.sensitivity_intro
    assert "grok-4.7 · high" not in page.pairwise_html
    assert "grok-4.7 · low" not in page.pairwise_html
    assert "p = 0.0000" not in page.pairwise_html
    assert "Each model answered the same 48 analytics questions 5 times" not in page.description
    assert "Repeat counts differ" in page.description
    assert "gpt-6-luna 5 times" in page.description
    assert "grok-4.7 · high" in page.description
    assert "1 time" in page.description
    assert "Not in this ratio" in page.cost_take_html
    assert "48 requests" in page.cost_take_html
    assert "headline sign test" in page.sensitivity_intro
    assert "equal repeats" not in page.sensitivity_intro
    items = page.caveat_html.split("</li>")
    luna_sol = next(item for item in items if "gpt-6-luna" in item and "gpt-6-sol" in item)
    assert "prompts differ only by dataset id" in luna_sol
    assert "prompts differ only by dataset id" in page.pairwise_html
    assert "This pair is comparable." in luna_sol
    grok_items = [item for item in items if "grok-4.7 · high" in item]
    assert grok_items
    assert all("differ only by" not in item for item in grok_items)
    assert all(
        "does not treat this pair as comparable" in item or "not strictly comparable" in item
        for item in grok_items
    )
    hashed = [item for item in grok_items if "cause is not recorded" in item]
    frozen = [item for item in grok_items if "frozen inputs differ" in item]
    assert hashed and frozen
    assert all("gpt-6-" in item for item in hashed)
    one_repeat_label = "grok-4.7 · high (grok-h) (48)"
    assert one_repeat_label in page.status_svg
    assert "gpt-6-luna (240)" in page.status_svg
    assert one_repeat_label in page.failure_svg
    assert one_repeat_label in page.request_svg
    assert "out of 48 requests" in page.fail_take_html
    assert "out of 240 requests" in page.fail_take_html


def test_unknown_instruction_hash_is_not_called_comparable(tmp_path):
    committed = _committed()
    cases = _cases()
    sol = json.loads(committed[1].read_text(encoding="utf-8"))
    sol["instructions_sha256"] = "ab" * 32
    sol.pop("dataset_id", None)
    path = tmp_path / "live-eval-receipt-12.json"
    path.write_text(json.dumps(sol), encoding="utf-8")
    page = build_page([committed[0], path], cases, strict=True)
    assert "prompts differ only by dataset id" not in page.caveat_html
    assert "differ only by that id" not in page.caveat_html
    assert "prompts differ only by dataset id" not in page.notes_html
    assert "does not treat this pair as comparable" in page.caveat_html
    assert "This pair is comparable." not in page.caveat_html
    assert "The runs are comparable." not in page.caveat_html
    assert "cause is not recorded" in page.caveat_html
    assert "cause is not recorded" in page.pairwise_html


def test_recorded_dataset_ids_can_establish_the_hash_claim(tmp_path):
    committed = _committed()
    cases = _cases()
    luna = json.loads(committed[0].read_text(encoding="utf-8"))
    sol = json.loads(committed[1].read_text(encoding="utf-8"))
    luna["instructions_sha256"] = "cd" * 32
    sol["instructions_sha256"] = "ef" * 32
    luna["dataset_id"] = "dataset-luna"
    sol["dataset_id"] = "dataset-sol"
    left = tmp_path / "live-eval-receipt-13.json"
    right = tmp_path / "live-eval-receipt-14.json"
    left.write_text(json.dumps(luna), encoding="utf-8")
    right.write_text(json.dumps(sol), encoding="utf-8")
    page = build_page([left, right], cases, strict=True)
    assert "prompts differ only by that id" in page.caveat_html
    assert "dataset-luna" in page.caveat_html
    assert "dataset-sol" in page.caveat_html
    assert "This pair is comparable." in page.caveat_html
    assert "The runs are comparable." not in page.caveat_html


def test_shared_dataset_id_does_not_explain_different_hashes(tmp_path):
    committed = _committed()
    cases = _cases()
    luna = json.loads(committed[0].read_text(encoding="utf-8"))
    specs = (
        ("aa", "id-a", "model-a", "live-eval-receipt-15.json"),
        ("bb", "id-a", "model-b", "live-eval-receipt-16.json"),
        ("cc", "id-c", "model-c", "live-eval-receipt-17.json"),
    )
    paths = []
    for digest, dataset_id, model, name in specs:
        data = json.loads(json.dumps(luna))
        data["instructions_sha256"] = digest * 32
        data["dataset_id"] = dataset_id
        data["model"] = model
        data["run_id"] = model
        path = tmp_path / name
        path.write_text(json.dumps(data), encoding="utf-8")
        paths.append(path)
    page = build_page(paths, cases, strict=True)
    items = page.caveat_html.split("</li>")
    same = next(item for item in items if "model-a" in item and "model-b" in item)
    crossed = next(item for item in items if "model-a" in item and "model-c" in item)
    assert "cause is not recorded" in same
    assert "differ only by" not in same
    assert "does not treat this pair as comparable" in same
    assert "differ only by that id" in crossed
    assert "This pair is comparable." in crossed
    assert "The runs are comparable." not in page.caveat_html


def test_known_pair_with_the_same_dataset_id_is_not_explained(tmp_path):
    committed = _committed()
    cases = _cases()
    luna = json.loads(committed[0].read_text(encoding="utf-8"))
    sol = json.loads(committed[1].read_text(encoding="utf-8"))
    luna["dataset_id"] = "same-snapshot"
    sol["dataset_id"] = "same-snapshot"
    left = tmp_path / "live-eval-receipt-18.json"
    right = tmp_path / "live-eval-receipt-19.json"
    left.write_text(json.dumps(luna), encoding="utf-8")
    right.write_text(json.dumps(sol), encoding="utf-8")
    page = build_page([left, right], cases, strict=True)
    assert "prompts differ only by dataset id" not in page.caveat_html
    assert "differ only by that id" not in page.caveat_html
    assert "prompts differ only by dataset id" not in page.pairwise_html
    assert "cause is not recorded" in page.caveat_html
    assert "cause is not recorded" in page.pairwise_html
    assert "This pair is comparable." not in page.caveat_html


def _one_repeat(source):
    data = json.loads(json.dumps(source))
    rows = [row for row in data["rows"] if int(row["repeat"]) == 0]
    data["rows"] = rows
    data["repeats"] = 1
    data["cases"] = len({row["case_id"] for row in rows})
    data["planned_requests"] = len(rows)
    passed = sum(bool(row["passed"]) for row in rows)
    data["headline_passed"] = passed
    data["headline_pass_rate"] = passed / len(rows)
    data["high_severity_misses"] = sum(bool(row["high_severity_miss"]) for row in rows)
    data["hard_fail"] = data["high_severity_misses"] > 0
    data["over_abstention"] = sum(bool(row["over_abstention"]) for row in rows)
    data["unsafe_answer"] = sum(bool(row["unsafe_answer"]) for row in rows)
    data["known_gross_cost_usd"] = sum(float(row.get("gross_cost_usd") or 0) for row in rows)
    data["repair_counts"] = {
        "extraction": sum(int(row.get("repair_count") or 0) for row in rows),
    }
    data["flaky_cases"] = []
    grouped = {}
    for row in rows:
        grouped.setdefault(row["case_id"], []).append(bool(row["passed"]))
    repeats = [grouped[key] for key in grouped]
    seed = int(data["stats"]["bootstrap"]["seed"])
    resamples = int(data["stats"]["bootstrap"]["resamples"])
    data["stats"]["wilson"] = wilson_interval(passed, len(rows))
    data["stats"]["bootstrap"] = cluster_bootstrap(repeats, seed=seed, resamples=resamples)
    data["model"] = "grok-4.7"
    data["reasoning_effort"] = "high"
    data["run_id"] = "grok-high-one-repeat"
    data["instructions_sha256"] = "11" * 32
    data.pop("dataset_id", None)
    data["token_usage"] = receipt_token_totals(data["rows"], data["model"])
    return data


def test_grok_efforts_stay_separate_and_one_repeat_is_sensitivity(tmp_path):
    """low/medium/high of one model stay three labels. 1-repeat is not headline."""
    committed = _committed()
    cases = _cases()
    luna = json.loads(committed[0].read_text(encoding="utf-8"))
    low = json.loads(json.dumps(luna))
    low["model"] = "grok-4.7"
    low["reasoning_effort"] = "low"
    low["run_id"] = "grok-low-five"
    low["instructions_sha256"] = "22" * 32
    low.pop("dataset_id", None)
    low["token_usage"] = receipt_token_totals(low["rows"], low["model"])
    medium = _one_repeat(luna)
    medium["reasoning_effort"] = "medium"
    medium["run_id"] = "grok-medium-one"
    medium["instructions_sha256"] = "33" * 32
    medium["token_usage"] = receipt_token_totals(medium["rows"], medium["model"])
    high = _one_repeat(luna)
    high["run_id"] = "grok-high-one"
    high["instructions_sha256"] = "44" * 32
    high["token_usage"] = receipt_token_totals(high["rows"], high["model"])
    names = {
        "low": tmp_path / "live-eval-receipt-grok-4.7-low-r5-31.json",
        "medium": tmp_path / "live-eval-receipt-grok-4.7-medium-r1-32.json",
        "high": tmp_path / "live-eval-receipt-grok-4.7-high-r1-33.json",
    }
    names["low"].write_text(json.dumps(low), encoding="utf-8")
    names["medium"].write_text(json.dumps(medium), encoding="utf-8")
    names["high"].write_text(json.dumps(high), encoding="utf-8")
    page = build_page([*committed, *names.values()], cases, strict=True)
    assert "grok-4.7 · low" in page.scorecards_html
    assert "grok-4.7 · medium" not in page.scorecards_html
    assert "grok-4.7 · high" not in page.scorecards_html
    assert "grok-4.7</div>" not in page.scorecards_html
    assert "Reasoning / billed output tokens" in page.scorecards_html
    assert "grok-4.7 · low" in page.pairwise_html
    assert "grok-4.7 · medium" not in page.pairwise_html
    assert "grok-4.7 · high" not in page.pairwise_html
    assert "grok-4.7 · medium" in page.sensitivity_html
    assert "grok-4.7 · high" in page.sensitivity_html
    assert "grok-4.7 · low" not in page.sensitivity_html
    assert "grok-4.7 · medium" in page.description
    assert "grok-4.7 · high" in page.description
    assert "1 time" in page.description
    assert "grok-4.7 · low" in page.description
    assert "grok-4.7 · low 1 time" not in page.description
    assert "Not in this ratio" in page.cost_take_html


def test_discover_on_the_committed_directory_ignores_other_reports():
    names = {path.name for path in _committed()}
    assert names == {path.name for path in REPORTS.glob("live-eval-receipt-*.json")}
    assert "opening-corpus.json" not in names
