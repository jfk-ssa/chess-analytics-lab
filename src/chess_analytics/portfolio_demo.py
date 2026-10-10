"""Credential-free, bounded portfolio demo in an ignored local workspace."""

import shutil
from pathlib import Path

from analyst_m5.core import replay
from analyst_m5.evaluation import score_case_portfolio
from chess_analytics.cli import fixture_plan
from chess_analytics.common import digest, read_json, write_json, writer_lock
from chess_analytics.corpus.metrics import clock_pressure, opening_player_score, opening_usage
from chess_analytics.corpus.publish import build_analytical
from chess_analytics.corpus.source import extracted_path
from chess_analytics.dashboard.analysis import clock_analysis, opening_catalog
from chess_analytics.ingest.pipeline import ingest
from chess_analytics.warehouse.snapshots import build, report

QUESTIONS = {
    "opening": "What share of tagged eligible fixture games used the Sicilian Defense?",
    "clarification": "Which opening should I choose for my own games?",
    "unsupported": "Did time pressure cause these players to make mistakes?",
}


def _stage_project(source_project: Path, project: Path) -> None:
    project.mkdir(parents=True, exist_ok=True)
    for directory in ("src", "contracts"):
        shutil.copytree(source_project / directory, project / directory, dirs_exist_ok=True)
    shutil.copy2(source_project / "uv.lock", project / "uv.lock")
    (project / "reports").mkdir(exist_ok=True)
    for name in ("M5-both-harness.json", "M7-December-Sol-v12-checkpoint.json"):
        shutil.copy2(source_project / "reports" / name, project / "reports" / name)
    plan = {
        **fixture_plan(project),
        "url": "local:tests/fixtures/portfolio_annotated.pgn",
        "period": "portfolio-fixture",
        "source_kind": "synthetic_test_fixture",
        "max_games": 20,
    }
    write_json(project / "config/datasets.json", {"analytical": plan})
    source = extracted_path(project / "data", plan)
    source.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_project / "tests/fixtures/portfolio_annotated.pgn", source)
    write_json(
        source.with_suffix(".receipt.json"),
        {
            "source_sha256": digest(source),
            "partial_archive": True,
            "compressed_prefix_sha256": None,
            "source_kind": "synthetic_test_fixture",
        },
    )


def _plans(project: Path) -> dict[str, Path]:
    folder = project / "evals/replay_plans"
    folder.mkdir(parents=True, exist_ok=True)
    actions = {
        "opening": [
            {
                "tool": "query_metric",
                "args": {"metric_id": "opening_usage", "filters": {"family": "Sicilian Defense"}},
            }
        ],
        "clarification": [],
        "unsupported": [],
    }
    status = {
        "opening": "answered",
        "clarification": "needs_clarification",
        "unsupported": "unsupported",
    }
    paths = {}
    for name, question in QUESTIONS.items():
        path = folder / f"portfolio-{name}.json"
        write_json(
            path,
            {
                "kind": "fixture_plan_no_model_response",
                "question": question,
                "plan": {
                    "status": status[name],
                    "interpretation": "descriptive_observed_prefix",
                    "actions": actions[name],
                },
            },
        )
        paths[name] = path
    return paths


def run(source_project: Path, workspace: Path) -> dict:
    """Exercise all three projects; every expected number comes from a separate fixture file."""
    source_project = source_project.resolve()
    project = workspace.resolve() / "project"
    _stage_project(source_project, project)
    root = project / "data"
    plan = read_json(project / "config/datasets.json")["analytical"]
    source = extracted_path(root, plan)
    with writer_lock(root):
        ingest(project, root, "analytical", source, plan)
        source_snapshot = build(project, root, "analytical")
        source_report = report(project, source_snapshot)
        snapshot = build_analytical(project, root)
    expected = read_json(source_project / "tests/fixtures/portfolio_expected.json")
    counts = source_report["counts"]
    for key in ("seen", "accepted", "duplicate", "excluded"):
        if counts[key] != expected[key]:
            raise ValueError(f"fixture source reference mismatch: {key}")
    if source_report["metric"]["numerator"] != expected["draws"]:
        raise ValueError("fixture draw reference mismatch")
    manifest = read_json(snapshot / "manifest.json")
    if manifest["selection"]["selected_games"] != expected["selected_games"] or (
        manifest["selection"]["move_rows"] != expected["move_rows"]
    ):
        raise ValueError("fixture move reference mismatch")
    opening = {}
    scores = {}
    for family, prefix in (("Sicilian Defense", "sicilian"), ("French Defense", "french")):
        usage = opening_usage(project, snapshot, family)
        score = opening_player_score(
            project,
            snapshot,
            family=family,
            color="white",
            rating_min=1400,
            rating_max_exclusive=1600,
            base_seconds=60,
            increment_seconds=0,
        )
        if (usage["numerator"], usage["denominator"]) != (
            expected[f"{prefix}_games"],
            expected["opening_known_games"],
        ) or score["score_rate"] != expected[f"{prefix}_white_score"]:
            raise ValueError(f"fixture opening reference mismatch: {family}")
        opening[prefix] = usage
        scores[prefix] = score
    clocks = {}
    for bucket, reference in (
        ("30_to_59", "clock_30_to_59"),
        ("under_10", "clock_under_10"),
        ("10_to_29", "clock_10_to_29"),
        ("60_plus", "clock_60_plus"),
    ):
        observed = clock_pressure(project, snapshot, bucket)
        if any(observed[key] != expected[reference][key] for key in reference_keys()):
            raise ValueError(f"fixture clock reference mismatch: {bucket}")
        clocks[bucket] = observed
    # Exercise the same analysis functions consumed by all six dashboard views.
    opening_catalog(project, snapshot)
    clock_analysis(project, snapshot)
    answers = {}
    for name, path in _plans(project).items():
        answers[name] = replay(project, QUESTIONS[name], path)
    case = {
        "id": "portfolio-opening",
        "category": "opening",
        "split": "fixture",
        "dataset_id": snapshot.name,
        "expected_status": "answered",
        "expected_result": {
            "numerator": expected["sicilian_games"],
            "denominator": expected["opening_known_games"],
            "value": 0.5,
        },
        "comparison": {"rates_absolute_tolerance": 1e-6},
        "required_caveats": ["source_tags_only"],
        "allowed_interpretations": ["descriptive_observed_prefix"],
        "expected_tool": "query_metric",
        "expected_tool_args": {
            "metric_id": "opening_usage",
            "filters": {"family": "Sicilian Defense"},
        },
    }
    scored = score_case_portfolio(case, answers["opening"])
    if not scored["passed"] or [
        answers[key]["status"] for key in ("clarification", "unsupported")
    ] != ["needs_clarification", "unsupported"]:
        raise ValueError("fixture analyst reference mismatch")
    if any(answers[key]["evidence_ids"] for key in ("clarification", "unsupported")):
        raise ValueError("boundary answer unexpectedly used evidence")
    result = {
        "kind": "synthetic offline three-project demo; fixture replay, no model response",
        "source_kind": expected["source"],
        "source_snapshot_id": source_snapshot.name,
        "analytical_id": snapshot.name,
        "source_counts": counts,
        "draw_rate": source_report["metric"],
        "opening_usage": opening,
        "white_player_score": scores,
        "clock_pressure": clocks,
        "analyst": {
            "statuses": {name: answer["status"] for name, answer in answers.items()},
            "opening_evidence_ids": answers["opening"]["evidence_ids"],
            "opening_reference_case": case,
            "scored_opening": scored,
        },
        "workspace": str(project),
        "live_requests": 0,
    }
    write_json(project / "reports/portfolio-demo.json", result)
    return result


def reference_keys() -> tuple[str, ...]:
    return ("eligible_moves", "evaluable_moves", "proxy_errors")
