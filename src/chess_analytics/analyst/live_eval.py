"""Offline checks for the future live analyst eval. This module does not call a model.

The 100-game fixture and the 40-case set are scored here with oracle plans:
the plan a perfect model would emit, built from each case's expected tool and
arguments. ``score_case_portfolio`` is the existing rubric. Dataset ids are
read from the staged snapshot at score time and are not stored on the cases.
"""

import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

from chess_analytics.analyst import semantic as analyst_semantic
from chess_analytics.analyst import tools as analyst_tools
from chess_analytics.analyst.core import execute_plan
from chess_analytics.analyst.evaluation import score_case_portfolio
from chess_analytics.analyst.plan_recovery import PLAN_SCHEMA
from chess_analytics.analyst.tools import CheckedTools
from chess_analytics.cli import fixture_plan
from chess_analytics.common import digest, write_json, writer_lock
from chess_analytics.corpus.publish import build_analytical
from chess_analytics.corpus.source import extracted_path
from chess_analytics.ingest.pipeline import ingest
from chess_analytics.warehouse.snapshots import build

CASE_RELATIVE = Path("evals/cases/analyst_live_v1.json")
MANIFEST_RELATIVE = Path("evals/cases/analyst_live_v1_manifest.json")
FIXTURE_RELATIVE = Path("tests/fixtures/live_eval_100.pgn")
EXPECTED_RELATIVE = Path("tests/fixtures/live_eval_100_expected.json")
CASE_COUNT = 48
RUBRIC_VERSION = "portfolio-1.0"
PLAN_TOOLS = set(PLAN_SCHEMA["properties"]["actions"]["items"]["properties"]["tool"]["enum"])
PINNED = {"analytical_id", "dataset_id", "evidence_id", "evidence_ids"}
SCORE_KEYS = ("draws", "eligible_player_games", "losses", "score_rate", "win_rate", "wins")
CLOCK_KEYS = (
    "bucket",
    "eligible_moves",
    "error_proxy_rate",
    "evaluable_moves",
    "evaluation_coverage",
    "proxy_errors",
)
RATE_KEYS = ("denominator", "numerator", "value")
COHORT = {
    "base_seconds": 60,
    "color": "white",
    "families": ["Sicilian Defense", "French Defense"],
    "increment_seconds": 0,
    "rating_max_exclusive": 1600,
    "rating_min": 1400,
}


def case_set_digest(cases: list) -> str:
    """Hash the cases only. This set has no replay plans."""
    payload = sorted(cases, key=lambda case: case["id"])
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def oracle_plan(case: dict) -> dict:
    """The plan a perfect model would emit for one case. No dataset id."""
    status = case["expected_status"]
    if status == "answered":
        tool = case["expected_tool"]
        if tool not in PLAN_TOOLS or not isinstance(case["expected_tool_args"], dict):
            raise ValueError("oracle plan tool is not in PLAN_SCHEMA")
        actions = [{"args": case["expected_tool_args"], "tool": tool}]
    else:
        if case["expected_tool"] is not None or case["expected_tool_args"] is not None:
            raise ValueError("non-answer oracle plan cannot call a tool")
        actions = []
    return {
        "actions": actions,
        "interpretation": "descriptive_observed_prefix",
        "status": status,
    }


def verify_live_set(
    manifest: dict, cases: list, fixture: bytes, expected: bytes, case_file: bytes
) -> None:
    """Raise when the case set, fixture, or expected file disagrees with the manifest."""
    if (
        manifest.get("rubric_version") != RUBRIC_VERSION
        or manifest.get("replay_plans") is not False
    ):
        raise ValueError("live case manifest schema mismatch")
    if len(cases) != CASE_COUNT or manifest.get("cases") != CASE_COUNT:
        raise ValueError(f"expected {CASE_COUNT} cases")
    if case_set_digest(cases) != manifest["case_set_sha256"]:
        raise ValueError("case set hash changed")
    if hashlib.sha256(case_file).hexdigest() != manifest["case_file_sha256"]:
        raise ValueError("case file hash changed")
    if hashlib.sha256(fixture).hexdigest() != manifest["fixture_sha256"]:
        raise ValueError("fixture hash changed")
    if hashlib.sha256(expected).hexdigest() != manifest["expected_sha256"]:
        raise ValueError("expected hash changed")
    dev = set(manifest["split"]["dev"])
    test = set(manifest["split"]["test"])
    if dev & test:
        raise ValueError("template family is in both splits")
    high = set(manifest["high_severity_families"])
    if high - (dev | test):
        raise ValueError("high-severity family missing from the split")
    seen = set()
    for case in cases:
        if PINNED & set(case):
            raise ValueError("dataset_id is pinned")
        result = case.get("expected_result")
        if isinstance(result, dict) and PINNED & set(result):
            raise ValueError("dataset_id is pinned")
        family = case["template_family"]
        seen.add(family)
        if family in dev:
            split = "dev"
        elif family in test:
            split = "test"
        else:
            raise ValueError("template family missing from manifest split")
        if case["split"] != split:
            raise ValueError("case split does not match template family")
        severity = "high" if family in high else "normal"
        if case["severity"] != severity:
            raise ValueError("severity does not match template family")
    if seen != dev | test:
        raise ValueError("manifest split does not match cases")


def load_live_cases(project: Path) -> tuple[dict, list]:
    """Load the committed case set. A changed case, fixture, or reference raises."""
    manifest = json.loads((project / MANIFEST_RELATIVE).read_text())
    case_path = project / CASE_RELATIVE
    case_file = case_path.read_bytes()
    cases = json.loads(case_file)
    fixture = (project / FIXTURE_RELATIVE).read_bytes()
    expected = (project / EXPECTED_RELATIVE).read_bytes()
    verify_live_set(manifest, cases, fixture, expected, case_file)
    return manifest, cases


def stage_live_fixture(source: Path, workspace: Path) -> Path:
    """Publish the 100-game fixture through the same ingest path as the portfolio PGN."""
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
        "max_games": 100,
        "period": "live-eval-100",
        "source_kind": "synthetic_test_fixture",
        "url": "local:tests/fixtures/live_eval_100.pgn",
    }
    write_json(project / "config/datasets.json", {"analytical": plan})
    extracted = extracted_path(project / "data", plan)
    extracted.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source / FIXTURE_RELATIVE, extracted)
    write_json(
        extracted.with_suffix(".receipt.json"),
        {
            "compressed_prefix_sha256": None,
            "partial_archive": True,
            "source_kind": "synthetic_test_fixture",
            "source_sha256": digest(extracted),
        },
    )
    root = project / "data"
    with writer_lock(root):
        ingest(project, root, "analytical", extracted, plan)
        build(project, root, "analytical")
        build_analytical(project, root)
        _maybe_mart(project, root)
    return project


def score_case_live(case: dict, answer: dict) -> dict:
    """``portfolio-1.0`` plus single-bucket clock equivalence.

    The last action may be ``analyze_clock_pressure`` with ``{bucket}`` or one
    ``query_metric`` of ``clock_pressure_error_proxy`` for that bucket. A second
    action, including a coverage call after the clock call, is not equivalent.
    This composes the frozen scorer and does not change it.
    """
    scored = score_case_portfolio(case, answer)
    if _equivalent_single_clock(case, answer) and "tool_or_filters" in scored["failures"]:
        scored["failures"] = [item for item in scored["failures"] if item != "tool_or_filters"]
        scored["passed"] = not scored["failures"]
    scored["rubric_version"] = "live-eval-1.0"
    return scored


def score_oracle_plans(project: Path, staged: Path) -> list[dict]:
    """Execute one oracle plan per case and score it with the live-eval rule."""
    _manifest, cases = load_live_cases(project)
    pointer = json.loads((staged / "data/analytical-moves-current.json").read_text())
    dataset_id = pointer["analytical_id"]
    rows = []
    for case in cases:
        answer = execute_plan(staged, case["question"], oracle_plan(case), source="fixture_replay")
        scored = score_case_live({**case, "dataset_id": dataset_id}, answer)
        scored["answer"] = answer
        rows.append(scored)
    return rows


def collect_references(staged: Path) -> dict:
    """Run the checked tools and return metric values plus the governed/reviewed path."""
    tools = CheckedTools(staged)
    bucket: list[str] = []
    calls = {"n": 0}
    original_resolve = analyst_tools.resolve_governed
    original_rows = analyst_semantic.query_rows

    def counting_rows(*args, **kwargs):
        calls["n"] += 1
        return original_rows(*args, **kwargs)

    def wrapped(bound, metric_id, filters, group_by):
        before = calls["n"]
        result = original_resolve(bound, metric_id, filters, group_by)
        if metric_id in analyst_semantic.GOVERNED_METRICS:
            ran = result is not None and calls["n"] > before
            bucket.append("governed" if ran else "reviewed_sql")
        return result

    analyst_tools.resolve_governed = wrapped
    analyst_semantic.query_rows = counting_rows
    try:
        return _read_tools(tools, bucket)
    finally:
        analyst_tools.resolve_governed = original_resolve
        analyst_semantic.query_rows = original_rows


def reference_mismatches(values: dict, expected: dict) -> list[str]:
    """Names of oracle fields the checked tools did not reproduce."""
    found: list[str] = []
    found += _fields(
        "game_draw_rate", expected["game_draw_rate"], values["game_draw_rate"], RATE_KEYS
    )
    for family in ("Sicilian Defense", "French Defense"):
        found += _fields(
            f"opening_usage.{family}",
            expected["opening_usage"][family],
            values["opening_usage"][family],
            RATE_KEYS,
        )
        found += _fields(
            f"white_score.{family}",
            expected[
                "sicilian_white_score" if family.startswith("Sicilian") else "french_white_score"
            ],
            values["white_score"][family],
            SCORE_KEYS,
        )
    found += _fields(
        "compare_openings",
        expected["compare_openings"],
        values["compare_openings"],
        (
            "score_rate_difference_first_minus_second",
            "win_rate_difference_first_minus_second",
        ),
    )
    for bucket in ("10_to_29", "30_to_59", "60_plus", "under_10"):
        found += _fields(
            f"clock.{bucket}", expected["clock"][bucket], values["clock"][bucket], CLOCK_KEYS
        )
    for name in (
        "clock_compare_under_10_minus_30_to_59",
        "clock_compare_under_10_minus_10_to_29",
    ):
        found += _fields(
            name,
            expected[name],
            values[name],
            (
                "error_proxy_rate_difference_first_minus_second",
                "evaluation_coverage_difference_first_minus_second",
            ),
        )
    found += _fields(
        "coverage", expected["coverage"], values["coverage"], tuple(expected["coverage"])
    )
    expected_families = expected["population"]["families"]
    if set(values["family_counts"]) != set(expected_families):
        found.append("family_counts keys differ")
    for family, count in expected_families.items():
        if values["family_counts"].get(family) != count:
            found.append(
                f"family_counts.{family} expected {count} got {values['family_counts'].get(family)}"
            )
    return found


def _read_tools(tools: CheckedTools, bucket: list[str]) -> dict:
    paths: dict[str, str] = {}
    draw, paths["game_draw_rate"] = _metric(tools, bucket, "game_draw_rate", {})
    usage = {}
    for family in ("Sicilian Defense", "French Defense"):
        result, paths[f"opening_usage.{family}"] = _metric(
            tools, bucket, "opening_usage", {"family": family}
        )
        usage[family] = result
    white = {}
    for family in ("Sicilian Defense", "French Defense"):
        filters = {key: value for key, value in COHORT.items() if key != "families"}
        filters["family"] = family
        result, paths[f"white_score.{family}"] = _metric(
            tools, bucket, "opening_player_score", filters
        )
        white[family] = result
    bucket.clear()
    compared = tools.compare_openings(dict(COHORT))
    paths["compare_openings"] = _path_name(bucket)
    clock = {}
    for name in ("10_to_29", "30_to_59", "60_plus", "under_10"):
        result, paths[f"clock.{name}"] = _metric(
            tools, bucket, "clock_pressure_error_proxy", {"bucket": name}
        )
        clock[name] = result
    bucket.clear()
    clock_compare = tools.compare_clock_buckets("under_10", "30_to_59")
    paths["clock_compare"] = "reviewed_sql"
    bucket.clear()
    empty_compare = tools.compare_clock_buckets("under_10", "10_to_29")
    paths["clock_compare_empty"] = "reviewed_sql"
    grouped, paths["opening_usage_grouped"] = _metric(
        tools, bucket, "opening_usage", {}, ["opening_family"]
    )
    cover = tools.get_dataset_coverage()
    return {
        "paths": paths,
        "values": {
            "clock": {name: _pick(clock[name], CLOCK_KEYS) for name in clock},
            "clock_compare_under_10_minus_10_to_29": _pick(
                empty_compare,
                (
                    "error_proxy_rate_difference_first_minus_second",
                    "evaluation_coverage_difference_first_minus_second",
                ),
            ),
            "clock_compare_under_10_minus_30_to_59": _pick(
                clock_compare,
                (
                    "error_proxy_rate_difference_first_minus_second",
                    "evaluation_coverage_difference_first_minus_second",
                ),
            ),
            "compare_openings": _pick(
                compared,
                (
                    "score_rate_difference_first_minus_second",
                    "win_rate_difference_first_minus_second",
                ),
            ),
            "coverage": _coverage(cover),
            "family_counts": {row["family"]: row["numerator"] for row in grouped["rows"]},
            "game_draw_rate": _pick(draw, RATE_KEYS),
            "opening_usage": {family: _pick(usage[family], RATE_KEYS) for family in usage},
            "white_score": {family: _pick(white[family], SCORE_KEYS) for family in white},
        },
    }


def _maybe_mart(project: Path, root: Path) -> None:
    executable = Path(sys.executable).with_name("dbt")
    if not executable.is_file():
        if os.environ.get("CHESSLAB_REQUIRE_DBT") == "1":
            raise RuntimeError("live eval stage needs the dbt extra")
        return
    from chess_analytics.marts.pipeline import build_mart

    build_mart(project, root, "analytical", executable)


def _metric(tools, bucket, metric_id, filters, group_by=None):
    bucket.clear()
    result = tools.query_metric(metric_id, filters, group_by)
    return result, _path_name(bucket)


def _path_name(bucket: list[str]) -> str:
    if not bucket:
        return "reviewed_sql"
    if any(name != "governed" for name in bucket):
        return "reviewed_sql"
    return "governed"


def _pick(row: dict, keys: tuple[str, ...]) -> dict:
    return {key: row[key] for key in keys}


def _coverage(cover: dict) -> dict:
    counts = cover["source_counts"]
    opening = cover["opening_coverage"]
    moves = cover["move_coverage"]
    selection = cover["selection"]
    return {
        "accepted": counts["accepted"],
        "conflict": counts["conflict"],
        "duplicate": counts["duplicate"],
        "eligible_games": opening["eligible_games"],
        "excluded": counts["excluded"],
        "known_opening_games": opening["known_opening_games"],
        "missing_source_opening": opening["missing_source_opening"],
        "move_rows": moves["moves"],
        "partial_archive": cover["partial_archive"],
        "quarantine": counts["quarantine"],
        "seen": counts["seen"],
        "selected_games": selection["selected_games"],
        "selected_zero_ply_games": selection["selected_zero_ply_games"],
        "source_kind": cover["source_kind"],
    }


def _fields(path: str, expected: dict, observed: dict, keys: tuple[str, ...]) -> list[str]:
    found = []
    for key in keys:
        if not _close(expected[key], observed[key]):
            found.append(f"{path}.{key} expected {expected[key]} got {observed[key]}")
    return found


def _equivalent_single_clock(case: dict, answer: dict) -> bool:
    expected = case.get("expected_tool_args") or {}
    filters = expected.get("filters")
    trace = answer.get("evidence") or []
    return (
        case.get("expected_tool") == "query_metric"
        and expected.get("metric_id") == "clock_pressure_error_proxy"
        and isinstance(filters, dict)
        and set(filters) == {"bucket"}
        and len(trace) == 1
        and trace[0].get("tool") == "analyze_clock_pressure"
        and trace[0].get("args") == filters
    )


def _close(left, right) -> bool:
    if left is None or right is None:
        return left is right
    if isinstance(left, bool) or isinstance(right, bool):
        return left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return abs(float(left) - float(right)) <= 1e-6
    return left == right
