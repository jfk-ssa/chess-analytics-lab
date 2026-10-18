"""Offline regression gate for the deterministic analyst stack.

The gate replays frozen plans and rescores saved answers. It does not call a
model and it does not measure LLM quality. Live model evals stay a separate
run with their own cap.
"""

import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path

from chess_analytics.analyst import tools as analyst_tools
from chess_analytics.analyst.core import replay
from chess_analytics.analyst.engine_eval import (
    load_engine_cases,
    replay_digest,
    replay_engine_case,
    score_case_engine,
)
from chess_analytics.analyst.evaluation import score_case, score_case_portfolio
from chess_analytics.analyst.semantic import GOVERNED_METRICS
from chess_analytics.cli import fixture_plan
from chess_analytics.common import digest, write_json, writer_lock
from chess_analytics.corpus.publish import build_analytical
from chess_analytics.corpus.source import extracted_path
from chess_analytics.ingest.pipeline import ingest
from chess_analytics.warehouse.snapshots import build

KIND = "offline analyst stack regression gate; deterministic replay, not llm quality"
BASELINE_RELATIVE = Path("evals/baselines/analyst_gate_v1.json")
SLOW_SECONDS = 60.0
_PATH_RE = re.compile(r"(?:/[^\s'\"]+)+")
_CASE_KEYS = ("failures", "passed", "path")
_SUITE_KEYS = ("case_set_sha256", "cases", "category", "passed", "rubric_version", "total")


def baseline_path(project: Path) -> Path:
    return project / BASELINE_RELATIVE


def canonical(value: object) -> str:
    """Sorted, two-space JSON with a trailing newline and no timestamps."""
    return json.dumps(value, indent=2, sort_keys=True) + "\n"


def case_set_digest(cases: list, plans: dict[str, dict]) -> str:
    """Hash cases and replay plans together so deleting either changes the digest."""
    payload = {
        "cases": sorted(cases, key=lambda case: case["id"]),
        "plans": [{"body": plans[name], "file": name} for name in sorted(plans)],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def load_gate_cases(project: Path) -> tuple[dict, list]:
    """Load gate_v1. A changed case or plan raises ``case set hash changed``."""
    manifest = json.loads((project / "evals/cases/gate_v1_manifest.json").read_text())
    cases = json.loads((project / "evals/cases/gate_v1.json").read_text())
    directory = project / "evals/replay_plans/gate_v1"
    plans = {path.name: json.loads(path.read_text()) for path in sorted(directory.glob("*.json"))}
    missing = [case["id"] for case in cases if f"{case['id']}.json" not in plans]
    if missing:
        raise ValueError("replay plan missing: " + ", ".join(missing))
    for case in cases:
        plan = plans[f"{case['id']}.json"]
        if plan.get("question") != case["question"] or plan.get("kind") != (
            "fixture_plan_no_model_response"
        ):
            raise ValueError("replay fixture question/schema mismatch")
    if case_set_digest(cases, plans) != manifest["case_set_sha256"]:
        raise ValueError("case set hash changed")
    return manifest, cases


def load_baseline(project: Path) -> dict:
    path = baseline_path(project)
    if not path.is_file():
        raise ValueError("analyst gate baseline is missing")
    return json.loads(path.read_text())


def portfolio_outcome(case: dict, answer: dict, dataset_id: str, path: str) -> dict:
    """Score one portfolio replay with ``portfolio-1.0`` and record the metric path."""
    scoring = {**case, "dataset_id": dataset_id}
    scored = score_case_portfolio(scoring, answer)
    return _outcome(scored, path)


def stage(source: Path, workspace: Path) -> Path:
    """Publish the four-game portfolio fixture in a temp project.

    This does not call ``portfolio_demo._stage_project``. The demo helper also
    writes its own replay plans and scores one opening. The fixture plan fields
    match that demo so the same four games are published.
    """
    source = source.resolve()
    project = workspace.resolve() / "project"
    project.mkdir(parents=True, exist_ok=True)
    for directory in ("src", "contracts"):
        shutil.copytree(source / directory, project / directory, dirs_exist_ok=True)
    shutil.copy2(source / "uv.lock", project / "uv.lock")
    dbt = source / "dbt"
    if dbt.is_dir():
        shutil.copytree(
            dbt,
            project / "dbt",
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("target", "logs", "dbt_packages"),
        )
    plan = {
        **fixture_plan(project),
        "url": "local:tests/fixtures/portfolio_annotated.pgn",
        "period": "portfolio-fixture",
        "source_kind": "synthetic_test_fixture",
        "max_games": 20,
    }
    write_json(project / "config/datasets.json", {"analytical": plan})
    extracted = extracted_path(project / "data", plan)
    extracted.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source / "tests/fixtures/portfolio_annotated.pgn", extracted)
    write_json(
        extracted.with_suffix(".receipt.json"),
        {
            "source_sha256": digest(extracted),
            "partial_archive": True,
            "compressed_prefix_sha256": None,
            "source_kind": "synthetic_test_fixture",
        },
    )
    root = project / "data"
    with writer_lock(root):
        ingest(project, root, "analytical", extracted, plan)
        build(project, root, "analytical")
        build_analytical(project, root)
        _maybe_mart(project, root)
    return project


def run_scorecard(project: Path, *, case_id: str | None = None) -> dict:
    """Stage a temp warehouse, replay the requested cases, and return a scorecard."""
    with tempfile.TemporaryDirectory(prefix="chesslab-gate-") as temporary:
        staged = stage(project, Path(temporary))
        return collect(project, staged, case_id=case_id)


def collect(project: Path, staged: Path, *, case_id: str | None = None) -> dict:
    """Replay against an already staged project. Two calls must match byte for byte."""
    gate_manifest, gate_cases = load_gate_cases(project)
    engine_manifest, engine_cases = _load_engine(project)
    m5_manifest, m5_cases = _load_m5(project)
    gate_ids = {case["id"] for case in gate_cases}
    boundary, structural = _engine_groups(engine_cases)
    engine_ids = {case["id"] for case in boundary + structural}
    m5_ids = {case["id"] for case in m5_cases}
    if case_id is not None and case_id not in gate_ids | engine_ids | m5_ids:
        raise ValueError(f"unknown gate case: {case_id}")
    suites: dict[str, dict] = {}
    if case_id is None or case_id in gate_ids:
        selected = [case for case in gate_cases if case_id in (None, case["id"])]
        rows = _gate_rows(project, staged, selected)
        suites["gate_v1"] = _suite(gate_manifest["case_set_sha256"], "portfolio-1.0", rows)
    if case_id is None or case_id in engine_ids:
        rows = _engine_rows(project, staged, boundary, structural, case_id)
        suites["engine_v1"] = _suite(engine_manifest["case_set_sha256"], "engine-1.0", rows)
    if case_id is None or case_id in m5_ids:
        selected = [case for case in m5_cases if case_id in (None, case["id"])]
        rows = _m5_rows(project, selected)
        suites["m5_saved"] = _suite(m5_manifest["case_set_sha256"], "m5-1.0", rows)
    return {"kind": KIND, "suites": suites}


def diff_scorecards(baseline: dict, current: dict) -> list[dict]:
    """Label every scorecard difference. Replay equality is exact."""
    diffs: list[dict] = []
    names = sorted(set(baseline.get("suites", {})) | set(current.get("suites", {})))
    for name in names:
        before = baseline.get("suites", {}).get(name)
        after = current.get("suites", {}).get(name)
        if before is None or after is None:
            present = after if before is None else before
            if present is None:
                continue
            for case_id, row in sorted(present["cases"].items()):
                if before is None:
                    diffs.append(_presence(name, case_id, None, row, row))
                else:
                    diffs.append(_presence(name, case_id, row, None, row))
            continue
        if before.get("rubric_version") != after.get("rubric_version"):
            diffs.append(
                {
                    "case_id": "rubric_version",
                    "detail": f"{before.get('rubric_version')}->{after.get('rubric_version')}",
                    "expected": {"rubric_version": before.get("rubric_version")},
                    "got": {"rubric_version": after.get("rubric_version")},
                    "label": "REGRESSION",
                    "suite": name,
                }
            )
        case_ids = sorted(set(before["cases"]) | set(after["cases"]))
        for case_id in case_ids:
            expected = before["cases"].get(case_id)
            got = after["cases"].get(case_id)
            row = expected if isinstance(expected, dict) else got
            if expected is None or got is None:
                if isinstance(row, dict):
                    diffs.append(_presence(name, case_id, expected, got, row))
                continue
            diffs.extend(_case_diffs(name, case_id, expected, got))
    return diffs


def hash_messages(baseline: dict, current: dict) -> list[str]:
    """Baseline hash drift uses the same words as a changed case file."""
    messages = []
    for name in sorted(set(baseline.get("suites", {})) & set(current.get("suites", {}))):
        before = baseline["suites"][name]["case_set_sha256"]
        after = current["suites"][name]["case_set_sha256"]
        if before != after:
            messages.append(f"case set hash changed: {name}")
    return messages


def render(diffs: list[dict], baseline: dict, current: dict, hash_lines: list[str]) -> str:
    """Plain-text failure report: one block per diff, then totals and hints."""
    lines = list(hash_lines)
    for item in diffs:
        expected = json.dumps(item["expected"], sort_keys=True)
        got = json.dumps(item["got"], sort_keys=True)
        head = f"{item['label']} {item['suite']}/{item['case_id']}"
        if item.get("detail"):
            head = f"{head} {item['detail']}"
        lines.append(f"{head} expected {expected} got {got}")
    lines.append(_totals(baseline, current, len(diffs) + len(hash_lines)))
    case_id = diffs[0]["case_id"] if diffs else "<id>"
    lines.append(f"rerun: python -m chess_analytics.analyst gate --case {case_id}")
    lines.append("update: python -m chess_analytics.analyst gate --update")
    return "\n".join(lines) + "\n"


def execute_cli(project: Path, *, update: bool = False, case: str | None = None) -> int:
    """Check the baseline, rewrite it, or rerun one case. Returns a process code."""
    project = project.resolve()
    if update and case:
        print("gate: pass only one of --update and --case", file=sys.stderr)
        return 2
    if update and os.environ.get("CI"):
        print("gate: --update refused because CI is set", file=sys.stderr)
        return 1
    started = time.perf_counter()
    try:
        current = run_scorecard(project, case_id=case)
        baseline = current if update else load_baseline(project)
        if case:
            baseline = _narrow(baseline, project, case)
            current = _narrow(current, project, case)
    except (OSError, ValueError, TimeoutError) as exc:
        print(f"analyst: {exc}", file=sys.stderr)
        return 1
    elapsed = time.perf_counter() - started
    _note_timing(elapsed)
    if update:
        write_json(baseline_path(project), current)
        print(f"updated {baseline_path(project)}")
        return 0
    messages = hash_messages(baseline, current)
    diffs = diff_scorecards(baseline, current)
    _write_summary(baseline, current, elapsed)
    if messages or diffs or canonical(baseline) != canonical(current):
        if not messages and not diffs:
            diffs = [
                {
                    "case_id": "scorecard",
                    "detail": "bytes",
                    "expected": baseline,
                    "got": current,
                    "label": "REGRESSION",
                    "suite": "gate",
                }
            ]
        print(render(diffs, baseline, current, messages), end="")
        return 1
    passed, total = _counts(current)
    print(f"ok {passed}/{total}")
    return 0


def _maybe_mart(project: Path, root: Path) -> None:
    executable = Path(sys.executable).with_name("dbt")
    if not executable.is_file():
        return
    from chess_analytics.marts.pipeline import build_mart

    build_mart(project, root, "analytical", executable)


def _dataset_id(staged: Path) -> str:
    pointer = json.loads((staged / "data/analytical-moves-current.json").read_text())
    return pointer["analytical_id"]


def _gate_rows(project: Path, staged: Path, cases: list) -> list[tuple[str, str, dict]]:
    dataset_id = _dataset_id(staged)
    bucket: list[str] = []
    original = analyst_tools.resolve_governed

    def wrapped(tools, metric_id, filters, group_by):
        result = original(tools, metric_id, filters, group_by)
        if metric_id in GOVERNED_METRICS:
            bucket.append("governed" if result is not None else "reviewed_sql")
        return result

    analyst_tools.resolve_governed = wrapped
    rows = []
    try:
        for case in cases:
            bucket.clear()
            path = project / "evals/replay_plans/gate_v1" / f"{case['id']}.json"
            try:
                answer = replay(staged, case["question"], path)
                outcome = portfolio_outcome(case, answer, dataset_id, _path_name(bucket))
            except (OSError, ValueError, TimeoutError, RuntimeError) as exc:
                outcome = {
                    "failures": [_exception_failure(exc)],
                    "passed": False,
                    "path": _path_name(bucket),
                }
            rows.append((case["id"], case["category"], outcome))
    finally:
        analyst_tools.resolve_governed = original
    return rows


def _engine_rows(project, staged, boundary, structural, case_id) -> list[tuple[str, str, dict]]:
    rows = []
    selected_boundary = [case for case in boundary if case_id in (None, case["id"])]
    selected_structural = [case for case in structural if case_id in (None, case["id"])]
    if selected_boundary:
        _clear_engine(staged)
        rows.extend(_one_engine(project, staged, case) for case in selected_boundary)
    if selected_structural:
        _write_fake_engine(project, staged)
        rows.extend(_one_engine(project, staged, case) for case in selected_structural)
    return rows


def _one_engine(project: Path, staged: Path, case: dict) -> tuple[str, str, dict]:
    try:
        answer = replay_engine_case(staged, case, plans=project)
        scored = score_case_engine(case, answer)
        outcome = _outcome(scored, "reviewed_sql")
    except (OSError, ValueError, TimeoutError, RuntimeError) as exc:
        outcome = {"failures": [_exception_failure(exc)], "passed": False, "path": "reviewed_sql"}
    return case["id"], case["category"], outcome


def _m5_rows(project: Path, cases: list) -> list[tuple[str, str, dict]]:
    """Rescore the committed M5 report. This does not replay and does not need a mart."""
    report = json.loads((project / "reports/M5-both-harness.json").read_text())
    saved = {item["case_id"]: item for item in report["outcomes"]}
    rows = []
    for case in cases:
        item = saved.get(case["id"])
        answer = item.get("answer") if isinstance(item, dict) else None
        if not isinstance(answer, dict):
            outcome = {
                "failures": ["missing_saved_answer"],
                "passed": False,
                "path": "reviewed_sql",
            }
        else:
            outcome = _outcome(score_case(case, answer), "reviewed_sql")
        rows.append((case["id"], case["category"], outcome))
    return rows


def _load_engine(project: Path) -> tuple[dict, list]:
    manifest, cases = load_engine_cases(project)
    digest_now = replay_digest(project / "evals/replay_plans/engine_v1")
    if digest_now != manifest["replay_plans_sha256"]:
        raise ValueError("engine replay plan hash changed")
    return manifest, cases


def _load_m5(project: Path) -> tuple[dict, list]:
    manifest = json.loads((project / "evals/cases/m5_manifest.json").read_text())
    cases = [
        case
        for name in ("dev", "test")
        for case in json.loads((project / f"evals/cases/m5_{name}.json").read_text())
    ]
    digest_now = hashlib.sha256(
        json.dumps(sorted(cases, key=lambda case: case["id"]), sort_keys=True).encode()
    ).hexdigest()
    if digest_now != manifest["case_set_sha256"]:
        raise ValueError("case set hash changed")
    report = json.loads((project / "reports/M5-both-harness.json").read_text())
    if report.get("case_set_sha256") != digest_now:
        raise ValueError("case set hash changed")
    return manifest, cases


def _engine_groups(cases: list) -> tuple[list, list]:
    boundary = [case for case in cases if case.get("group") == "boundary"]
    structural = [
        case
        for case in cases
        if case.get("requires_engine_binary") and not case.get("requires_opening_fixture")
    ]
    return boundary, structural


def _suite(case_hash: str, rubric: str, rows: list[tuple[str, str, dict]]) -> dict:
    cases = {}
    category: dict[str, dict[str, int]] = {}
    for case_id, name, outcome in rows:
        cases[case_id] = {key: outcome[key] for key in _CASE_KEYS}
        bucket = category.setdefault(name, {"passed": 0, "total": 0})
        bucket["total"] += 1
        bucket["passed"] += int(outcome["passed"])
    passed = sum(int(item["passed"]) for item in cases.values())
    return {
        "case_set_sha256": case_hash,
        "cases": cases,
        "category": category,
        "passed": passed,
        "rubric_version": rubric,
        "total": len(cases),
    }


def _outcome(scored: dict, path: str) -> dict:
    return {"failures": list(scored["failures"]), "passed": bool(scored["passed"]), "path": path}


def _path_name(bucket: list[str]) -> str:
    if bucket and all(item == "governed" for item in bucket):
        return "governed"
    return "reviewed_sql"


def _exception_failure(exc: BaseException) -> str:
    text = _PATH_RE.sub("<path>", f"{type(exc).__name__}: {exc}")
    return "exception:" + text


def _clear_engine(project: Path) -> None:
    for name in ("config/engine.json", "config/opening-visits.json"):
        (project / name).unlink(missing_ok=True)


def _write_fake_engine(source: Path, staged: Path) -> None:
    binary = (source / "tests/fixtures/engines/fake_uci.py").resolve()
    write_json(
        staged / "config/engine.json",
        {"binary_path": str(binary), "binary_sha256": digest(binary), "version": "1"},
    )


def _presence(suite: str, case_id: str, expected, got, row: dict) -> dict:
    if expected is None:
        return {
            "case_id": case_id,
            "detail": "",
            "expected": {},
            "got": got,
            "label": "ADDED",
            "suite": suite,
        }
    return {
        "case_id": case_id,
        "detail": "",
        "expected": expected if isinstance(expected, dict) else row,
        "got": {},
        "label": "REMOVED",
        "suite": suite,
    }


def _case_diffs(suite: str, case_id: str, expected: dict, got: dict) -> list[dict]:
    diffs = []
    if expected.get("passed") != got.get("passed") or expected.get("failures") != got.get(
        "failures"
    ):
        before = "pass" if expected.get("passed") else "fail"
        after = "pass" if got.get("passed") else "fail"
        improved = expected.get("passed") is False and bool(got.get("passed"))
        label = "IMPROVEMENT" if improved else "REGRESSION"
        names = ",".join(got.get("failures") or [])
        diffs.append(
            {
                "case_id": case_id,
                "detail": f"{before}->{after} [{names}]",
                "expected": expected,
                "got": got,
                "label": label,
                "suite": suite,
            }
        )
    if expected.get("path") != got.get("path"):
        diffs.append(
            {
                "case_id": case_id,
                "detail": f"{expected.get('path')}->{got.get('path')}",
                "expected": expected,
                "got": got,
                "label": "PATH-CHANGED",
                "suite": suite,
            }
        )
    return diffs


def _counts(card: dict) -> tuple[int, int]:
    passed = total = 0
    for suite in card.get("suites", {}).values():
        passed += suite["passed"]
        total += suite["total"]
    return passed, total


def _totals(baseline: dict, current: dict, diffs: int) -> str:
    before_passed, before_total = _counts(baseline)
    after_passed, after_total = _counts(current)
    return (
        f"totals: baseline {before_passed}/{before_total}, "
        f"now {after_passed}/{after_total}, diffs {diffs}"
    )


def _narrow(card: dict, project: Path, case_id: str) -> dict:
    for name, suite in card["suites"].items():
        if case_id not in suite["cases"]:
            continue
        category = _category_of(project, case_id)
        row = suite["cases"][case_id]
        return {
            "kind": card["kind"],
            "suites": {
                name: {
                    "case_set_sha256": suite["case_set_sha256"],
                    "cases": {case_id: row},
                    "category": {category: {"passed": int(row["passed"]), "total": 1}},
                    "passed": int(row["passed"]),
                    "rubric_version": suite["rubric_version"],
                    "total": 1,
                }
            },
        }
    raise ValueError(f"unknown gate case: {case_id}")


def _category_of(project: Path, case_id: str) -> str:
    _, gate_cases = load_gate_cases(project)
    for case in gate_cases:
        if case["id"] == case_id:
            return case["category"]
    _, engine_cases = _load_engine(project)
    for case in engine_cases:
        if case["id"] == case_id:
            return case["category"]
    _, m5_cases = _load_m5(project)
    for case in m5_cases:
        if case["id"] == case_id:
            return case["category"]
    raise ValueError(f"unknown gate case: {case_id}")


def _note_timing(elapsed: float) -> None:
    print(f"gate elapsed_seconds: {elapsed:.3f}", file=sys.stderr)
    if elapsed >= SLOW_SECONDS:
        print("warning: gate elapsed exceeds 60 seconds", file=sys.stderr)


def _write_summary(baseline: dict, current: dict, elapsed: float) -> None:
    destination = os.environ.get("GITHUB_STEP_SUMMARY")
    if not destination:
        return
    lines = ["| category | baseline | now |", "|---|---|---|"]
    names = sorted(set(baseline.get("suites", {})) | set(current.get("suites", {})))
    for name in names:
        before = baseline.get("suites", {}).get(name, {})
        after = current.get("suites", {}).get(name, {})
        lines.append(f"| {name} | {_pair(before)} | {_pair(after)} |")
        categories = sorted(set(before.get("category", {})) | set(after.get("category", {})))
        for category in categories:
            lines.append(
                f"| {name}/{category} | {_pair(before, category)} | {_pair(after, category)} |"
            )
    lines.append("")
    lines.append(f"elapsed_seconds: {elapsed:.3f}")
    if elapsed >= SLOW_SECONDS:
        lines.append("warning: gate elapsed exceeds 60 seconds")
    lines.append("")
    with Path(destination).open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


def _pair(suite: dict, category: str | None = None) -> str:
    if not suite:
        return "0/0"
    if category is None:
        return f"{suite.get('passed', 0)}/{suite.get('total', 0)}"
    bucket = suite.get("category", {}).get(category)
    if not bucket:
        return "0/0"
    return f"{bucket['passed']}/{bucket['total']}"


def scorecard_keys() -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Allowed scorecard keys. Volatile ids, evidence, elapsed time, and nodes stay out."""
    return _CASE_KEYS, _SUITE_KEYS
