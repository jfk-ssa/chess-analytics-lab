"""Regression checks for portfolio review findings, using only synthetic inputs."""

import json
import math
import shutil

import pytest

from analyst_m5.evaluation import score_case_portfolio
from analyst_m5.provider import price_usage, validate_personal_config
from analytics_m3.moves import write_sampled_moves
from analytics_m3.publish import build_analytical
from analytics_m3.source import extracted_path
from chess_analytics.cli import fixture_plan
from chess_analytics.common import digest, read_json, write_json
from chess_analytics.ingest.pipeline import ingest
from chess_analytics.warehouse.snapshots import build


def enabled_config(project):
    config = read_json(project / "config/personal_provider.example.json")
    config.update(
        enabled=True,
        personal_account_acknowledged=True,
        model="offline-test-model",
        max_run_usd=0.1,
        input_usd_per_million=1.0,
        output_usd_per_million=1.0,
        cache_write_usd_per_million=1.25,
        cached_input_usd_per_million=0.2,
    )
    return config


@pytest.mark.parametrize(
    "field",
    [
        "max_run_usd",
        "input_usd_per_million",
        "output_usd_per_million",
        "cache_write_usd_per_million",
        "cached_input_usd_per_million",
    ],
)
@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), -float("inf"), True, 0, -1])
def test_personal_budget_and_prices_are_finite(project, field, invalid):
    config = enabled_config(project)
    validate_personal_config(config)
    with pytest.raises(ValueError, match="positive"):
        validate_personal_config({**config, field: invalid})


def test_usage_pricing_rejects_nonfinite_overflow(project):
    config = enabled_config(project)
    with pytest.raises(ValueError, match="finite"):
        price_usage(
            {**config, "input_usd_per_million": 1e308},
            {"input_tokens": 1_000_000, "output_tokens": 1},
        )


def selected_record(eval_cp="0.10"):
    return f"""[Event "Rated Blitz synthetic review"]
[Site "https://lichess.org/00000013"]
[White "ReviewWhite"]
[Black "ReviewBlack"]
[Result "1-0"]
[TimeControl "60+0"]
[Opening "Sicilian Defense"]

1. e4 {{[%clk 0:00:59] [%eval {eval_cp}]}} c5 {{[%clk 0:00:59] [%eval {eval_cp}]}} \
2. Nf3 {{[%clk 0:00:05] [%eval {eval_cp}]}} d6 1-0

"""


def isolated_project(project, tmp_path):
    isolated = tmp_path / "project"
    isolated.mkdir()
    for directory in ("src", "contracts", "analytics_m3"):
        shutil.copytree(project / directory, isolated / directory)
    shutil.copy2(project / "uv.lock", isolated / "uv.lock")
    plan = fixture_plan(isolated)
    write_json(isolated / "config/datasets.json", {"analytical": plan})
    return isolated, plan


def test_duplicate_selected_record_emits_one_game(project, tmp_path):
    source = tmp_path / "source.pgn"
    source.write_text(selected_record() * 2)
    root = tmp_path / "data"
    stage = ingest(project, root, "analytical", source, fixture_plan(project))
    snapshot = build(project, root, "analytical")
    move_path = tmp_path / "moves.jsonl"
    observed = write_sampled_moves(source, snapshot, move_path, fixture_plan(project), root)
    assert read_json(stage / "manifest.json")["counts"]["duplicate"] == 1
    assert observed["selected_games"] == 1
    assert observed["move_rows"] == 4
    assert [json.loads(line)["ply"] for line in move_path.read_text().splitlines()] == [1, 2, 3, 4]


def test_selected_zero_ply_game_is_counted_without_move_rows(project, tmp_path):
    zero_ply = selected_record().replace("00000013", "00000042").split("\n\n", 1)[0]
    source = tmp_path / "source.pgn"
    source.write_text(selected_record() + zero_ply + "\n\n1-0\n\n")
    root = tmp_path / "data"
    ingest(project, root, "analytical", source, fixture_plan(project))
    snapshot = build(project, root, "analytical")
    counts = write_sampled_moves(
        source, snapshot, tmp_path / "moves.jsonl", fixture_plan(project), root
    )
    assert counts["selected_games"] == 2
    assert counts["selected_zero_ply_games"] == 1
    assert counts["move_rows"] == 4


def test_mismatched_annotated_source_preserves_published_pointer(project, tmp_path):
    isolated, plan = isolated_project(project, tmp_path)
    root = isolated / "data"
    extracted = extracted_path(root, plan)
    extracted.parent.mkdir(parents=True)
    extracted.write_text(selected_record())
    receipt = extracted.with_suffix(".receipt.json")
    write_json(
        receipt,
        {
            "source_sha256": digest(extracted),
            "partial_archive": True,
            "compressed_prefix_sha256": "synthetic-review",
        },
    )
    ingest(isolated, root, "analytical", extracted, plan)
    build(isolated, root, "analytical")
    published = build_analytical(isolated, root)
    pointer = (root / "analytical-moves-current.json").read_bytes()
    manifest = (published / "manifest.json").read_bytes()
    extracted.write_text(selected_record("9.90"))
    write_json(
        receipt,
        {
            "source_sha256": digest(extracted),
            "partial_archive": True,
            "compressed_prefix_sha256": "synthetic-review",
        },
    )
    with pytest.raises(ValueError, match="differs from checked source"):
        build_analytical(isolated, root)
    assert (root / "analytical-moves-current.json").read_bytes() == pointer
    assert (published / "manifest.json").read_bytes() == manifest
    extracted.write_text(selected_record())
    write_json(
        receipt,
        {
            "source_sha256": digest(extracted),
            "partial_archive": True,
            "compressed_prefix_sha256": "synthetic-review",
            "plan_sha256": "incorrect-plan",
        },
    )
    with pytest.raises(ValueError, match="receipt differs from configured plan"):
        build_analytical(isolated, root)
    assert (root / "analytical-moves-current.json").read_bytes() == pointer


def test_new_scorer_rejects_boolean_and_nonfinite_numeric_mutations():
    case = {
        "id": "synthetic-reference",
        "category": "numeric",
        "split": "fixture",
        "dataset_id": "synthetic",
        "expected_status": "answered",
        "expected_result": {"numerator": 1, "value": 1.0},
        "comparison": {"rates_absolute_tolerance": 1e-6},
        "required_caveats": [],
        "allowed_interpretations": ["descriptive_observed_prefix"],
    }
    answer = {
        "status": "answered",
        "dataset_id": "synthetic",
        "result": {"numerator": 1, "value": 1.0},
        "evidence_ids": ["ev_synthetic"],
        "caveats": [],
        "interpretation": "descriptive_observed_prefix",
    }
    assert score_case_portfolio(case, answer)["passed"]
    for key, value in (
        ("numerator", True),
        ("value", True),
        ("value", math.nan),
        ("value", math.inf),
    ):
        mutated = {**answer, "result": {**answer["result"], key: value}}
        assert score_case_portfolio(case, mutated)["failures"] == ["result_values"]
