"""The offline analyst gate must fail when the stack, a plan, or the baseline changes."""

import json
import os
import shutil
import sys
from copy import deepcopy
from pathlib import Path

import duckdb
import pytest

import chess_analytics.analyst.gate as gate_mod
from chess_analytics.analyst import core
from chess_analytics.analyst import tools as analyst_tools
from chess_analytics.analyst.core import answer_caveats
from chess_analytics.analyst.engine_eval import load_engine_cases
from chess_analytics.analyst.gate import (
    KIND,
    _engine_groups,
    _exception_failure,
    _load_m5,
    _write_summary,
    baseline_path,
    canonical,
    collect,
    diff_scorecards,
    execute_cli,
    hash_messages,
    load_baseline,
    load_gate_cases,
    portfolio_outcome,
    render,
    scorecard_keys,
    stage,
)
from chess_analytics.analyst.tools import CheckedTools
from chess_analytics.common import digest, write_json

ROOT = Path(__file__).resolve().parents[1]
DBT = Path(sys.executable).with_name("dbt")
GOVERNED_CASES = {
    "compare_french_minus_sicilian",
    "compare_sicilian_minus_french",
    "game_draw_rate",
    "usage_french",
    "usage_grouped",
    "usage_sicilian",
    "white_french_score",
    "white_sicilian_score",
}
M5_BOUNDARY_PLANS = {
    "boundary_sql": "sql_attachment.json",
    "boundary_network": "network_fetch.json",
    "boundary_private_file": "read_private_file.json",
    "boundary_budget": "budget_bypass.json",
    "boundary_causal": "causal_clock.json",
}


def _require_dbt():
    if DBT.is_file():
        return
    if os.environ.get("CHESSLAB_REQUIRE_DBT") == "1":
        pytest.fail("analyst gate tests need the dbt extra in this job")
    pytest.skip("install the optional dbt extra")


@pytest.fixture(scope="module")
def staged(tmp_path_factory):
    return stage(ROOT, tmp_path_factory.mktemp("analyst-gate"))


_CLEAN_CARDS: dict[int, dict] = {}


def _cached_clean(staged: Path) -> dict:
    """Replay the unmodified stage once per worker.

    Several tests diff a failure against that same card. A module cache keeps
    those diffs, and a second collect still proves the two runs match.
    """
    key = id(staged)
    card = _CLEAN_CARDS.get(key)
    if card is None:
        card = collect(ROOT, staged)
        _CLEAN_CARDS[key] = card
    return card


@pytest.fixture(scope="module")
def clean_card(staged):
    return _cached_clean(staged)


def _case_answer():
    case = {
        "id": "reference_probe",
        "category": "filtering_perspective",
        "split": "gate_v1",
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


def _card(outcome: dict, *, case_id: str = "game_draw_rate", case_hash: str = "abc") -> dict:
    return {
        "kind": KIND,
        "suites": {
            "gate_v1": {
                "case_set_sha256": case_hash,
                "cases": {case_id: outcome},
                "category": {"draw_rate": {"passed": int(outcome["passed"]), "total": 1}},
                "passed": int(outcome["passed"]),
                "rubric_version": "portfolio-1.0",
                "total": 1,
            }
        },
    }


def _project_with_baseline(tmp_path: Path, baseline: dict) -> Path:
    project = tmp_path / "project"
    write_json(project / "evals/baselines/analyst_gate_v1.json", baseline)
    return project


def test_expected_values_come_from_the_portfolio_fixture():
    expected = json.loads((ROOT / "tests/fixtures/portfolio_expected.json").read_text())
    _, cases = load_gate_cases(ROOT)
    by_id = {case["id"]: case for case in cases}
    assert len(by_id) == 24
    sicilian = by_id["usage_sicilian"]["expected_result"]
    assert sicilian["numerator"] == expected["sicilian_games"]
    assert sicilian["denominator"] == expected["opening_known_games"]
    assert sicilian["value"] == expected["sicilian_games"] / expected["opening_known_games"]
    french = by_id["usage_french"]["expected_result"]
    assert (french["numerator"], french["denominator"]) == (
        expected["french_games"],
        expected["opening_known_games"],
    )
    grouped = by_id["usage_grouped"]["expected_result"]["rows"]
    assert [row["family"] for row in grouped] == ["French Defense", "Sicilian Defense"]
    assert [row["numerator"] for row in grouped] == [
        expected["french_games"],
        expected["sicilian_games"],
    ]
    draw = by_id["game_draw_rate"]["expected_result"]
    assert draw["numerator"] == expected["draws"]
    assert draw["denominator"] == expected["eligible_games"]
    assert draw["value"] == expected["draws"] / expected["eligible_games"]
    assert (
        by_id["white_sicilian_score"]["expected_result"]["score_rate"]
        == (expected["sicilian_white_score"])
    )
    assert (
        by_id["white_french_score"]["expected_result"]["score_rate"]
        == (expected["french_white_score"])
    )
    difference = expected["sicilian_white_score"] - expected["french_white_score"]
    compared = by_id["compare_sicilian_minus_french"]["expected_result"]
    assert compared["score_rate_difference_first_minus_second"] == difference
    for name in ("clock_under_10", "clock_10_to_29", "clock_30_to_59", "clock_60_plus"):
        observed = by_id[name]["expected_result"]
        reference = expected[name]
        assert observed["eligible_moves"] == reference["eligible_moves"]
        assert observed["evaluable_moves"] == reference["evaluable_moves"]
        assert observed["proxy_errors"] == reference["proxy_errors"]
        if reference["eligible_moves"] == 0:
            assert observed["evaluation_coverage"] is None
        if reference["evaluable_moves"] == 0:
            assert observed["error_proxy_rate"] is None
    empty = by_id["compare_clock_10_to_29_vs_60_plus"]["expected_result"]
    assert empty["error_proxy_rate_difference_first_minus_second"] is None
    assert empty["evaluation_coverage_difference_first_minus_second"] is None


def test_m5_boundary_plans_were_copied_because_they_do_not_use_data():
    for gate_name, m5_name in M5_BOUNDARY_PLANS.items():
        copied = json.loads((ROOT / "evals/replay_plans/gate_v1" / f"{gate_name}.json").read_text())
        original = json.loads((ROOT / "evals/replay_plans" / m5_name).read_text())
        assert copied == original
        assert copied["plan"]["actions"] == []
        assert copied["plan"]["status"] == "unsupported"
        assert "dataset_id" not in copied["plan"]


def test_plan_edit_fails_the_case_set_hash(tmp_path):
    project = tmp_path / "project"
    for relative in ("evals/cases/gate_v1.json", "evals/cases/gate_v1_manifest.json"):
        destination = project / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, destination)
    shutil.copytree(ROOT / "evals/replay_plans/gate_v1", project / "evals/replay_plans/gate_v1")
    plan_path = project / "evals/replay_plans/gate_v1/game_draw_rate.json"
    body = json.loads(plan_path.read_text())
    body["plan"]["interpretation"] = "mutated"
    plan_path.write_text(json.dumps(body))
    with pytest.raises(ValueError, match="hash changed"):
        load_gate_cases(project)


def test_ten_answer_mutations_flip_the_gate():
    """Same ten mutations as test_m5.py, scored through the gate's portfolio outcome."""
    case, answer = _case_answer()
    passed = portfolio_outcome(case, answer, "a" * 24, "reviewed_sql")
    assert passed["passed"]
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
        outcome = portfolio_outcome(case, wrong, "a" * 24, "reviewed_sql")
        diffs = diff_scorecards(
            _card(passed, case_id=case["id"]), _card(outcome, case_id=case["id"])
        )
        assert diffs, key
        assert diffs[0]["label"] == "REGRESSION"
        assert diffs[0]["case_id"] == case["id"]
        assert not outcome["passed"], key


def test_failure_text_names_a_regression_and_a_path_change():
    passed = {"failures": [], "passed": True, "path": "governed"}
    failed = {"failures": ["result_values"], "passed": False, "path": "governed"}
    sql = {"failures": [], "passed": True, "path": "reviewed_sql"}
    regression = diff_scorecards(_card(passed), _card(failed))
    text = render(regression, _card(passed), _card(failed), [])
    assert text.splitlines()[0] == (
        "REGRESSION gate_v1/game_draw_rate pass->fail [result_values] "
        'expected {"failures": [], "passed": true, "path": "governed"} '
        'got {"failures": ["result_values"], "passed": false, "path": "governed"}'
    )
    assert "rerun: python -m chess_analytics.analyst gate --case game_draw_rate" in text
    assert "update: python -m chess_analytics.analyst gate --update" in text
    changed = diff_scorecards(_card(passed), _card(sql))
    assert [item["label"] for item in changed] == ["PATH-CHANGED"]
    path_text = render(changed, _card(passed), _card(sql), [])
    assert path_text.startswith("PATH-CHANGED gate_v1/game_draw_rate governed->reviewed_sql ")


def test_removing_a_case_is_a_diff_and_a_hash_change_is_named():
    full = _card({"failures": [], "passed": True, "path": "reviewed_sql"})
    shrunk = deepcopy(full)
    del shrunk["suites"]["gate_v1"]["cases"]["game_draw_rate"]
    removed = diff_scorecards(full, shrunk)
    assert removed[0]["label"] == "REMOVED"
    assert removed[0]["case_id"] == "game_draw_rate"
    changed = deepcopy(full)
    changed["suites"]["gate_v1"]["case_set_sha256"] = "f" * 64
    assert hash_messages(full, changed) == ["case set hash changed: gate_v1"]


def test_baseline_file_records_governed_paths_and_omits_volatile_fields():
    text = baseline_path(ROOT).read_text()
    assert text == canonical(json.loads(text))
    for banned in ("dataset_id", "evidence_id", "elapsed", "nodes", "timestamp"):
        assert banned not in text
    baseline = json.loads(text)
    _, gate_cases = load_gate_cases(ROOT)
    _, engine_cases = load_engine_cases(ROOT)
    boundary, structural = _engine_groups(engine_cases)
    assert set(baseline["suites"]["gate_v1"]["cases"]) == {case["id"] for case in gate_cases}
    assert set(baseline["suites"]["engine_v1"]["cases"]) == {
        case["id"] for case in boundary + structural
    }
    assert len(boundary) == 9
    assert len(structural) == 6
    for case_id, row in baseline["suites"]["gate_v1"]["cases"].items():
        expected_path = "governed" if case_id in GOVERNED_CASES else "reviewed_sql"
        assert row["path"] == expected_path
        assert row["passed"] is True
        assert set(row) == set(scorecard_keys()[0])
    for suite in baseline["suites"].values():
        assert set(suite) == set(scorecard_keys()[1])
    _, m5_cases = _load_m5(ROOT)
    assert set(baseline["suites"]["m5_saved"]["cases"]) == {case["id"] for case in m5_cases}
    assert len(m5_cases) == 50
    assert baseline["suites"]["m5_saved"]["passed"] == 50
    assert baseline["suites"]["m5_saved"]["rubric_version"] == "m5-1.0"


def test_baseline_mutations_fail_the_check(tmp_path, monkeypatch, capsys):
    baseline = load_baseline(ROOT)
    monkeypatch.setattr(
        "chess_analytics.analyst.gate.run_scorecard", lambda *_args, **_kwargs: baseline
    )
    flipped = deepcopy(baseline)
    flipped["suites"]["gate_v1"]["cases"]["game_draw_rate"]["passed"] = False
    flipped["suites"]["gate_v1"]["cases"]["game_draw_rate"]["failures"] = ["result_values"]
    project = _project_with_baseline(tmp_path, flipped)
    assert execute_cli(project) == 1
    output = capsys.readouterr().out
    assert "IMPROVEMENT gate_v1/game_draw_rate" in output

    deleted = deepcopy(baseline)
    del deleted["suites"]["gate_v1"]["cases"]["usage_sicilian"]
    project = _project_with_baseline(tmp_path / "deleted", deleted)
    assert execute_cli(project) == 1
    assert "ADDED gate_v1/usage_sicilian" in capsys.readouterr().out

    hashed = deepcopy(baseline)
    hashed["suites"]["gate_v1"]["case_set_sha256"] = "0" * 64
    project = _project_with_baseline(tmp_path / "hashed", hashed)
    assert execute_cli(project) == 1
    assert "case set hash changed: gate_v1" in capsys.readouterr().out


def test_update_round_trip_is_stable_and_refuses_in_ci(tmp_path, monkeypatch, capsys):
    baseline = load_baseline(ROOT)
    monkeypatch.setattr(
        "chess_analytics.analyst.gate.run_scorecard", lambda *_args, **_kwargs: baseline
    )
    monkeypatch.delenv("CI", raising=False)
    project = tmp_path / "project"
    assert execute_cli(project, update=True) == 0
    written = baseline_path(project).read_bytes()
    assert written == canonical(baseline).encode()
    assert execute_cli(project) == 0
    assert "ok 89/89" in capsys.readouterr().out
    assert execute_cli(project, update=True) == 0
    assert baseline_path(project).read_bytes() == written
    monkeypatch.setenv("CI", "1")
    assert execute_cli(project, update=True) == 1
    assert baseline_path(project).read_bytes() == written
    assert "refused" in capsys.readouterr().err
    monkeypatch.setenv("CI", "")
    assert execute_cli(project, update=True) == 1
    assert baseline_path(project).read_bytes() == written
    assert "refused" in capsys.readouterr().err
    assert execute_cli(project, update=True, case="game_draw_rate") == 2


def test_exception_text_strips_temporary_paths():
    text = _exception_failure(ValueError("failed /tmp/chesslab-gate-abc/project/data"))
    assert "/tmp/" not in text
    assert "<path>" in text


def test_step_summary_is_a_three_column_table(tmp_path, monkeypatch):
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    card = load_baseline(ROOT)
    _write_summary(card, card, 1.25)
    text = summary.read_text()
    rows = [line for line in text.splitlines() if line.startswith("|")]
    assert rows[0] == "| category | baseline | now |"
    assert all(line.count("|") == 4 for line in rows)
    assert "elapsed_seconds: 1.250" in text
    assert "dataset_id" not in text


def test_two_gate_runs_are_byte_identical(staged, clean_card):
    first = canonical(clean_card)
    second = canonical(collect(ROOT, staged))
    assert first == second
    for banned in ("dataset_id", "evidence_id", "elapsed", "nodes"):
        assert banned not in first


def test_dropping_a_caveat_fails_and_names_the_case(staged, clean_card, monkeypatch):
    clean = clean_card

    def thin(actions):
        return [item for item in answer_caveats(actions) if item != "observed_prefix_only"]

    monkeypatch.setattr(core, "answer_caveats", thin)
    broken = collect(ROOT, staged)
    diffs = diff_scorecards(clean, broken)
    text = render(diffs, clean, broken, [])
    assert "REGRESSION gate_v1/game_draw_rate" in text
    assert "caveats" in text
    assert broken["suites"]["gate_v1"]["cases"]["game_draw_rate"]["passed"] is False


def test_query_metric_off_by_one_fails_and_names_the_case(staged, clean_card, monkeypatch):
    clean = clean_card
    original = CheckedTools.query_metric

    def off(self, metric_id, filters, group_by=None):
        result = original(self, metric_id, filters, group_by)
        if isinstance(result, dict) and isinstance(result.get("numerator"), int):
            return {**result, "numerator": result["numerator"] + 1}
        return result

    monkeypatch.setattr(CheckedTools, "query_metric", off)
    broken = collect(ROOT, staged)
    text = render(diff_scorecards(clean, broken), clean, broken, [])
    assert "REGRESSION gate_v1/game_draw_rate" in text
    assert "result_values" in text


def test_duckdb_error_is_recorded_and_later_cases_still_score(staged, monkeypatch):
    original = gate_mod.replay

    def boom(project, question, plan):
        if question == "What is the game draw rate in this fixture?":
            raise duckdb.Error("boom /tmp/chesslab-gate-secret/warehouse.duckdb")
        return original(project, question, plan)

    monkeypatch.setattr(gate_mod, "replay", boom)
    card = collect(ROOT, staged)
    cases = card["suites"]["gate_v1"]["cases"]
    assert len(cases) == 24
    failed = cases["game_draw_rate"]
    assert failed["passed"] is False
    assert failed["failures"][0].startswith("exception:Error")
    assert "/tmp/" not in failed["failures"][0]
    assert "<path>" in failed["failures"][0]
    assert cases["usage_sicilian"]["passed"] is True


def test_empty_scorecard_is_not_a_pass(tmp_path, monkeypatch, capsys):
    empty = {"kind": KIND, "suites": {}}
    monkeypatch.setattr(gate_mod, "run_scorecard", lambda *_args, **_kwargs: empty)
    monkeypatch.delenv("CI", raising=False)
    project = _project_with_baseline(tmp_path, empty)
    assert execute_cli(project) == 1
    output = capsys.readouterr().out
    assert "ok 0/0" not in output
    assert "coverage:" in output


@pytest.mark.dbt
def test_sql_payload_from_the_resolver_is_path_changed(staged, monkeypatch):
    _require_dbt()
    clean = _cached_clean(staged)
    assert clean["suites"]["gate_v1"]["cases"]["game_draw_rate"]["path"] == "governed"

    def sql_payload(tools, metric_id, filters, group_by):
        return tools._query_metric_sql(metric_id, filters, group_by or [])

    monkeypatch.setattr(analyst_tools, "resolve_governed", sql_payload)
    fallen = collect(ROOT, staged)
    case = fallen["suites"]["gate_v1"]["cases"]["game_draw_rate"]
    assert case["passed"] is True
    assert case["path"] == "reviewed_sql"
    diffs = diff_scorecards(clean, fallen)
    assert any(
        item["label"] == "PATH-CHANGED" and item["case_id"] == "game_draw_rate" for item in diffs
    )


@pytest.mark.dbt
def test_replacing_the_governed_path_with_sql_is_path_changed(staged, monkeypatch):
    _require_dbt()
    clean = _cached_clean(staged)
    assert clean["suites"]["gate_v1"]["cases"]["game_draw_rate"]["path"] == "governed"

    def fallback(*_args, **_kwargs):
        return None

    monkeypatch.setattr(analyst_tools, "resolve_governed", fallback)
    fallen = collect(ROOT, staged)
    diffs = diff_scorecards(clean, fallen)
    assert any(
        item["label"] == "PATH-CHANGED" and item["case_id"] == "game_draw_rate" for item in diffs
    )
    text = render(diffs, clean, fallen, [])
    assert "PATH-CHANGED gate_v1/game_draw_rate governed->reviewed_sql" in text


@pytest.mark.dbt
def test_poisoned_mart_fails_the_draw_rate_case(staged):
    _require_dbt()
    clean = _cached_clean(staged)
    pointer = staged / "data/analytical-mart-current.json"
    saved = pointer.read_text()
    mart_id = json.loads(saved)["mart_id"]
    source = staged / "data/marts/published" / mart_id
    poisoned = staged / "data/marts/published" / ("ab" * 12)
    shutil.copytree(source, poisoned)
    with duckdb.connect(str(poisoned / "warehouse.duckdb")) as connection:
        connection.execute('update "fact_game" set "result" = \'1-0\' where "result" = \'1/2-1/2\'')
    manifest = json.loads((poisoned / "manifest.json").read_text())
    manifest["mart_id"] = poisoned.name
    manifest["warehouse_sha256"] = digest(poisoned / "warehouse.duckdb")
    write_json(poisoned / "manifest.json", manifest)
    write_json(pointer, {"mart_id": poisoned.name})
    try:
        poisoned_card = collect(ROOT, staged)
    finally:
        pointer.write_text(saved)
        shutil.rmtree(poisoned)
    case = poisoned_card["suites"]["gate_v1"]["cases"]["game_draw_rate"]
    assert case["passed"] is False
    assert case["path"] == "governed"
    text = render(diff_scorecards(clean, poisoned_card), clean, poisoned_card, [])
    assert "REGRESSION gate_v1/game_draw_rate" in text


@pytest.mark.dbt
def test_live_scorecard_matches_the_committed_baseline(staged):
    _require_dbt()
    assert canonical(_cached_clean(staged)) == baseline_path(ROOT).read_text()
