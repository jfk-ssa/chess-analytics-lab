"""Equality checks for the committed public aggregate extract. Offline only."""

import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from chess_analytics.public_extract import (
    NEVER_METRICFLOW,
    QUERY_ORIGINS,
    SIZE_BUDGET_BYTES,
    connect,
    extract_path,
    identifier_issues,
    load_extract,
    table_rows,
)

ROOT = Path(__file__).resolve().parents[1]
IDENTITY = {
    "mart_id": "a" * 24,
    "model_sha256": "b" * 64,
    "semantic_manifest_sha256": "c" * 64,
}
PUBLISHED_MART = {
    "mart_id": "9d3ca923a6f1cd06d82a8645",
    "model_sha256": "707aa83395a023e4b49756ef355271232871f9c413a82bd98168cd13d830f4b3",
    "semantic_manifest_sha256": "07df0b2f38fb275764541f292b810185e16e3f23fb507ee1fef426dec27bfd86",
}
METRICFLOW_RECEIPTS = frozenset(
    {
        "game_draw_rate",
        "opening_usage",
        "opening_player_score:French Defense",
        "opening_player_score:Sicilian Defense",
    }
)
REVIEWED_SQL_RECEIPTS = frozenset(
    f"clock_pressure_error_proxy:{bucket}"
    for bucket in ("under_10", "10_to_29", "30_to_59", "60_plus")
)
_LABEL_FIELDS = ("mart_id", "model_sha256", "query_origin", "semantic_manifest_sha256")
_REPORTS = (
    "M3-analytical-manifest.json",
    "M3-independent-reference.json",
    "M3-source-manifest.json",
    "M4-figures.json",
    "opening-corpus.json",
)


def _reports_project(tmp_path: Path, project: Path) -> Path:
    """Project with the committed reports and no analytical warehouse."""
    root = tmp_path / "reports-only"
    destination = root / "reports"
    destination.mkdir(parents=True)
    for name in _REPORTS:
        shutil.copy(project / "reports" / name, destination / name)
    return root


def _without_receipt_labels(payload: dict) -> dict:
    cloned = json.loads(json.dumps(payload))
    for row in cloned["tables"]["metric_receipt"]:
        for key in _LABEL_FIELDS:
            del row[key]
    return cloned


def load_script():
    spec = importlib.util.spec_from_file_location(
        "build_public_extract", ROOT / "scripts/build_public_extract.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _population(extract: dict, lineage: str, population: str, period: str | None = None) -> int:
    matches = [
        row
        for row in table_rows(extract, "lineage_stage")
        if row["lineage"] == lineage and row["population"] == population and row["period"] == period
    ]
    assert len(matches) == 1
    return matches[0]["count"]


def _receipt(extract: dict, receipt_id: str) -> dict:
    matches = [
        row for row in table_rows(extract, "metric_receipt") if row["receipt_id"] == receipt_id
    ]
    assert len(matches) == 1
    return matches[0]


def test_training_games_match_the_opening_corpus(project):
    extract = load_extract(extract_path(project))
    corpus = json.loads((project / "reports/opening-corpus.json").read_text())
    assert corpus["counts"]["training_games"] == 1_042_346
    assert _population(extract, "opening_corpus", "training_games") == 1_042_346
    children = [
        row
        for row in table_rows(extract, "lineage_stage")
        if row["rolls_up_to"] == "opening_corpus:training_games"
    ]
    assert sum(row["count"] for row in children) == 1_042_346


def test_august_prefix_stays_a_separate_lineage(project):
    extract = load_extract(extract_path(project))
    source = json.loads((project / "reports/M3-source-manifest.json").read_text())
    analytical = json.loads((project / "reports/M3-analytical-manifest.json").read_text())
    assert source["counts"]["accepted"] == 99_467
    assert _population(extract, "m3_august_prefix", "accepted", "2026-08") == 99_467
    known = analytical["summary"]["opening_coverage"]["known_opening_games"]
    assert known == 99_117
    assert _population(extract, "m3_august_prefix", "known_opening_games", "2026-08") == known
    assert _population(extract, "m3_august_prefix", "eligible_games", "2026-08") == known
    corpus = json.loads((project / "reports/opening-corpus.json").read_text())
    august = next(row for row in corpus["training_sources"] if row["period"] == "2026-08")
    corpus_august = _population(extract, "opening_corpus", "training_source_games", "2026-08")
    assert august["games"] == 88_840
    assert corpus_august == august["games"]
    assert corpus_august != 99_467
    prefix = [
        row for row in table_rows(extract, "lineage_stage") if row["lineage"] == "m3_august_prefix"
    ]
    assert prefix
    assert all(row["rolls_up_to"] is None for row in prefix)
    assert {row["lineage"] for row in table_rows(extract, "lineage_stage")} == {
        "opening_corpus",
        "m3_august_prefix",
    }


def test_opening_families_sum_to_known_openings(project):
    extract = load_extract(extract_path(project))
    reference = json.loads((project / "reports/M3-independent-reference.json").read_text())
    rows = table_rows(extract, "opening_family_share")
    assert sum(row["numerator"] for row in rows) == 99_117
    assert {row["family"]: row["numerator"] for row in rows} == reference["opening_families"]
    assert {row["denominator"] for row in rows} == {reference["known_opening_games"]}


def test_score_cells_and_clock_buckets_match_m4_figures(project):
    extract = load_extract(extract_path(project))
    figures = json.loads((project / "reports/M4-figures.json").read_text())
    opening = figures["opening"]
    cells = {row["family"]: row for row in table_rows(extract, "opening_score_cell")}
    assert set(cells) == set(opening["families"])
    for family, result in opening["families"].items():
        cell = cells[family]
        raw = result["raw"]
        assert (cell["wins"], cell["draws"], cell["losses"]) == (
            raw["wins"],
            raw["draws"],
            raw["losses"],
        )
        assert cell["eligible_player_games"] == raw["eligible_player_games"]
        assert cell["score_rate"] == raw["score_rate"]
        assert cell["win_rate"] == raw["win_rate"]
        assert cell["adjusted_score_rate"] == result["adjusted_score_rate"]
        assert [cell["adjusted_interval_low"], cell["adjusted_interval_high"]] == result[
            "adjusted_95pct_cluster_bootstrap_interval"
        ]
        assert cell["bootstrap_valid_repetitions"] == result["bootstrap_valid_repetitions"]
        assert cell["cluster_count"] == result["cluster_count"]
        assert cell["low_support"] == result["low_support"]
    weights = opening["common_rating_difference_weights"]
    assert cells["French Defense"]["weight_below_minus_100"] == weights["below_-100"]
    assert cells["French Defense"]["weight_minus_100_to_99"] == weights["-100_to_99"]
    assert cells["French Defense"]["weight_100_plus"] == weights["100_plus"]
    buckets = {row["bucket"]: row for row in table_rows(extract, "clock_bucket")}
    assert set(buckets) == {row["bucket"] for row in figures["clock"]["buckets"]}
    for source in figures["clock"]["buckets"]:
        row = buckets[source["bucket"]]
        for key in (
            "eligible_moves",
            "evaluable_moves",
            "proxy_errors",
            "mate_transition_moves",
            "evaluation_coverage",
            "error_proxy_rate",
        ):
            assert row[key] == source[key]
    strata = {
        (row["bucket"], row["time_control"], row["phase"], row["rating_band"]): row
        for row in table_rows(extract, "clock_stratum")
    }
    assert len(strata) == len(figures["clock"]["strata"])
    for source in figures["clock"]["strata"]:
        row = strata[
            (source["bucket"], source["time_control"], source["phase"], source["rating_band"])
        ]
        for key in (
            "eligible_moves",
            "evaluable_moves",
            "proxy_errors",
            "evaluation_coverage",
            "proxy_rate",
        ):
            assert row[key] == source[key]


def test_extract_has_no_identifier_columns_or_leaky_values(project):
    extract = load_extract(extract_path(project))
    assert identifier_issues(extract) == []
    leaked = json.loads(json.dumps(extract))
    leaked["tables"]["lineage_stage"][0]["player_key"] = "hidden"
    assert any(issue.startswith("column ") for issue in identifier_issues(leaked))
    path_row = json.loads(json.dumps(extract))
    path_row["tables"]["opening_family_share"][0]["family"] = "data/raw/secret.pgn"
    assert any(issue.startswith("value ") for issue in identifier_issues(path_row))


def test_query_origins_keep_clock_and_bootstrap_off_metricflow(project):
    extract = load_extract(extract_path(project))
    receipts = table_rows(extract, "metric_receipt")
    assert {row["receipt_id"] for row in receipts if row["query_origin"] == "metricflow"} == set(
        METRICFLOW_RECEIPTS
    )
    assert {row["receipt_id"] for row in receipts if row["query_origin"] == "reviewed_sql"} == set(
        REVIEWED_SQL_RECEIPTS
    )
    for row in receipts:
        assert row["query_origin"] in QUERY_ORIGINS
        if row["metric"] in NEVER_METRICFLOW:
            assert row["query_origin"] != "metricflow"
        if row["receipt_id"] in METRICFLOW_RECEIPTS:
            assert row["query_origin"] == "metricflow"
            assert row["mart_id"] == PUBLISHED_MART["mart_id"]
            assert row["model_sha256"] == PUBLISHED_MART["model_sha256"]
            assert row["semantic_manifest_sha256"] == PUBLISHED_MART["semantic_manifest_sha256"]
        else:
            assert row["mart_id"] is None
            assert row["model_sha256"] is None
            assert row["semantic_manifest_sha256"] is None
            if row["receipt_id"] in REVIEWED_SQL_RECEIPTS:
                assert row["query_origin"] == "reviewed_sql"
            else:
                assert row["query_origin"] == "committed_report"
    assert _receipt(extract, "game_draw_rate")["numerator"] == 3669
    assert _receipt(extract, "game_draw_rate")["denominator"] == 99_117
    french = _receipt(extract, "opening_player_score:French Defense")
    assert french["numerator"] == 118
    assert french["denominator"] == 239
    assert (
        _receipt(extract, "opening_adjusted_score:Sicilian Defense")["query_origin"]
        == "committed_report"
    )
    assert (
        _receipt(extract, "opening_adjusted_score_bootstrap:French Defense")["query_origin"]
        == "committed_report"
    )
    assert (
        _receipt(extract, "clock_pressure_error_proxy:under_10")["query_origin"] == "reviewed_sql"
    )


def test_extract_stays_under_the_size_budget(project):
    path = extract_path(project)
    assert path.stat().st_size <= SIZE_BUDGET_BYTES
    assert path.stat().st_size < 1024 * 1024


def test_reader_answers_lineage_counts_from_duckdb(project):
    extract = load_extract(extract_path(project))
    with connect(extract) as connection:
        training = connection.execute(
            """
            select "count" from "lineage_stage"
            where "lineage" = 'opening_corpus' and "population" = 'training_games'
            """
        ).fetchone()
        families = connection.execute(
            'select sum("numerator") from "opening_family_share"'
        ).fetchone()
    assert training[0] == 1_042_346
    assert families[0] == 99_117


def test_builder_is_deterministic_and_prints_skipped_warehouse_steps(project, tmp_path, capsys):
    builder = load_script()
    bare = _reports_project(tmp_path, project)
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    assert builder.main(["--project", str(bare), "--output", str(first)]) == 0
    first_logs = capsys.readouterr().out.splitlines()
    assert builder.main(["--project", str(bare), "--output", str(second)]) == 0
    assert first.read_bytes() == second.read_bytes()
    # No warehouse can raise query_origin or mart identity. Those fields are the
    # only difference from the committed MetricFlow rebuild.
    rebuilt = json.loads(first.read_text())
    committed = json.loads(extract_path(project).read_text())
    assert _without_receipt_labels(rebuilt) == _without_receipt_labels(committed)
    for row in rebuilt["tables"]["metric_receipt"]:
        assert row["query_origin"] == "committed_report"
        assert row["mart_id"] is None
        assert row["model_sha256"] is None
        assert row["semantic_manifest_sha256"] is None
    metricflow_skip = (
        "skipped: metricflow refresh for game_draw_rate, opening_usage, "
        "opening_player_score (analytical warehouse not found)"
    )
    reviewed_skip = (
        "skipped: reviewed_sql refresh for game_draw_rate, opening_usage, "
        "opening_player_score (analytical warehouse not found)"
    )
    assert metricflow_skip in first_logs
    assert reviewed_skip in first_logs
    assert any(
        line.startswith("skipped: metricflow label for clock_pressure_error_proxy")
        for line in first_logs
    )
    assert "mac rebuild needed: none; every table was filled from committed reports" in first_logs
    assert "relabeled: none" in first_logs
    assert (
        "not relabeled: opening_adjusted_score:French Defense stays committed_report "
        "(outside MetricFlow)"
    ) in first_logs
    assert (
        "not relabeled: game_draw_rate stays committed_report (analytical warehouse not found)"
    ) in first_logs
    assert not any(line.startswith("/") for line in first_logs)


def test_live_refresh_labels_matching_governed_metrics_and_refuses_clock(project, tmp_path):
    builder = load_script()
    extract, _logs = builder.build_extract(_reports_project(tmp_path, project))
    assert {row["query_origin"] for row in table_rows(extract, "metric_receipt")} == {
        "committed_report"
    }
    families = {
        row["family"]: row["numerator"] for row in table_rows(extract, "opening_family_share")
    }
    cells = {
        row["family"]: {
            "wins": row["wins"],
            "draws": row["draws"],
            "losses": row["losses"],
            "eligible_player_games": row["eligible_player_games"],
            "score_rate": row["score_rate"],
        }
        for row in table_rows(extract, "opening_score_cell")
    }
    buckets = {
        row["bucket"]: {
            "eligible_moves": row["eligible_moves"],
            "evaluable_moves": row["evaluable_moves"],
            "proxy_errors": row["proxy_errors"],
            "mate_transition_moves": row["mate_transition_moves"],
            "evaluation_coverage": row["evaluation_coverage"],
            "error_proxy_rate": row["error_proxy_rate"],
        }
        for row in table_rows(extract, "clock_bucket")
    }
    probe = {
        "unusable": False,
        "game_draw_rate": {
            "origin": "metricflow",
            "numerator": 3669,
            "denominator": 99_117,
            **IDENTITY,
        },
        "opening_usage": {
            "origin": "metricflow",
            "denominator": 99_117,
            "families": families,
            "truncated": False,
            **IDENTITY,
        },
        "opening_player_score": {"origin": "metricflow", "cells": cells, **IDENTITY},
        "clock_pressure_error_proxy": {"origin": "reviewed_sql", "buckets": buckets},
    }
    before = json.dumps(table_rows(extract, "opening_family_share"), sort_keys=True)
    logs = builder.upgrade_receipts(extract, probe)
    assert json.dumps(table_rows(extract, "opening_family_share"), sort_keys=True) == before
    assert _receipt(extract, "game_draw_rate")["query_origin"] == "metricflow"
    assert _receipt(extract, "game_draw_rate")["mart_id"] == IDENTITY["mart_id"]
    assert _receipt(extract, "opening_usage")["query_origin"] == "metricflow"
    assert _receipt(extract, "opening_player_score:French Defense")["query_origin"] == "metricflow"
    assert (
        _receipt(extract, "clock_pressure_error_proxy:under_10")["query_origin"] == "reviewed_sql"
    )
    assert (
        _receipt(extract, "opening_adjusted_score:French Defense")["query_origin"]
        == "committed_report"
    )
    bootstrap = _receipt(extract, "opening_adjusted_score_bootstrap:Sicilian Defense")
    assert bootstrap["query_origin"] == "committed_report"
    assert any("no governed source" in line for line in logs)
    assert (
        "relabeled: game_draw_rate committed_report -> metricflow "
        "(live counts matched the committed reference)"
    ) in logs
    assert (
        "relabeled: clock_pressure_error_proxy:under_10 committed_report -> reviewed_sql "
        "(live counts matched the committed reference)"
    ) in logs
    assert (
        "not relabeled: opening_adjusted_score:French Defense stays committed_report "
        "(outside MetricFlow)"
    ) in logs
    clock_probe = {
        **probe,
        "clock_pressure_error_proxy": {"origin": "metricflow", "buckets": buckets},
    }
    with pytest.raises(ValueError, match="cannot be metricflow"):
        builder.upgrade_receipts(json.loads(json.dumps(extract)), clock_probe)


def test_live_refresh_keeps_committed_report_when_counts_differ(project, tmp_path):
    builder = load_script()
    extract, _logs = builder.build_extract(_reports_project(tmp_path, project))
    assert _receipt(extract, "game_draw_rate")["query_origin"] == "committed_report"
    probe = {
        "unusable": False,
        "game_draw_rate": {
            "origin": "metricflow",
            "numerator": 1,
            "denominator": 99_117,
            **IDENTITY,
        },
        "opening_usage": None,
        "opening_player_score": None,
        "clock_pressure_error_proxy": None,
    }
    logs = builder.upgrade_receipts(extract, probe)
    assert _receipt(extract, "game_draw_rate")["query_origin"] == "committed_report"
    assert _receipt(extract, "game_draw_rate")["mart_id"] is None
    assert any("counts differ" in line for line in logs)
    assert (
        "not relabeled: game_draw_rate stays committed_report "
        "(live counts did not match the committed reference)"
    ) in logs


def test_public_data_ignore_rules_track_only_the_extract(project):
    git = shutil.which("git")
    if git is None:
        pytest.skip("git is not installed")
    ignored = (
        "data/public/.env",
        "data/public/secrets.json",
        "data/public/warehouse.duckdb",
        "data/public/nested/games.csv",
    )
    tracked = ("data/public/dashboard_extract.json", "data/README.md")
    for relative in ignored:
        result = subprocess.run(
            [git, "check-ignore", "-q", "--no-index", relative],
            cwd=project,
            check=False,
        )
        assert result.returncode == 0, relative
    for relative in tracked:
        result = subprocess.run(
            [git, "check-ignore", "-q", "--no-index", relative],
            cwd=project,
            check=False,
        )
        assert result.returncode == 1, relative


def test_extract_path_away_from_the_repo_names_the_environment_variable(monkeypatch):
    away = Path("/tmp/chesslab-extract-away")
    away.mkdir(exist_ok=True)
    monkeypatch.chdir(away)
    monkeypatch.delenv("CHESSLAB_PUBLIC_EXTRACT", raising=False)
    with pytest.raises(FileNotFoundError, match="CHESSLAB_PUBLIC_EXTRACT"):
        extract_path()


def test_extract_path_uses_cwd_repo_root_and_environment(project, monkeypatch, tmp_path):
    monkeypatch.delenv("CHESSLAB_PUBLIC_EXTRACT", raising=False)
    monkeypatch.chdir(project)
    assert extract_path() == project / "data" / "public" / "dashboard_extract.json"
    monkeypatch.chdir(project / "src")
    assert extract_path() == project / "data" / "public" / "dashboard_extract.json"
    explicit = tmp_path / "elsewhere"
    assert extract_path(explicit) == explicit / "data" / "public" / "dashboard_extract.json"
    target = tmp_path / "dashboard_extract.json"
    target.write_text("{}\n")
    monkeypatch.setenv("CHESSLAB_PUBLIC_EXTRACT", str(target))
    away = Path("/tmp/chesslab-extract-away")
    away.mkdir(exist_ok=True)
    monkeypatch.chdir(away)
    assert extract_path() == target


def test_load_extract_rejects_metricflow_on_clock_receipts(project, tmp_path):
    extract = json.loads(extract_path(project).read_text())
    for row in extract["tables"]["metric_receipt"]:
        if row["metric"] != "clock_pressure_error_proxy":
            continue
        row["query_origin"] = "metricflow"
        row["mart_id"] = "a" * 24
        row["model_sha256"] = "b" * 64
        row["semantic_manifest_sha256"] = "c" * 64
        break
    path = tmp_path / "extract.json"
    path.write_text(json.dumps(extract))
    with pytest.raises(ValueError, match="cannot be metricflow"):
        load_extract(path)


def test_time_control_rejects_a_bare_username(project, tmp_path):
    extract = json.loads(extract_path(project).read_text())
    extract["tables"]["clock_stratum"][0]["time_control"] = "DrNykterstein"
    assert any(
        issue.startswith("value ") and issue.endswith(".time_control")
        for issue in identifier_issues(extract)
    )
    path = tmp_path / "extract.json"
    path.write_text(json.dumps(extract))
    with pytest.raises(ValueError, match="identifier check"):
        load_extract(path)


def test_elite_lineage_names_the_curator(project):
    extract = load_extract(extract_path(project))
    elite = [
        row for row in table_rows(extract, "lineage_stage") if row["cohort"] == "elite_reference"
    ]
    assert len(elite) == 1
    assert elite[0]["note"] == (
        "Curated elite month published by nikonoel. "
        "Inside the opening corpus, not the August prefix."
    )
    assert "://" not in elite[0]["note"]


def test_builder_help_matches_the_readme_mac_command(project, capsys):
    builder = load_script()
    with pytest.raises(SystemExit) as caught:
        builder.main(["--help"])
    assert caught.value.code == 0
    command = (
        "UV_PROJECT_ENVIRONMENT=$HOME/.venvs/chess-analytics-lab "
        "uv run --directory $HOME/Developer/chess-analytics-lab "
        "--locked --no-editable --extra dbt "
        "python scripts/build_public_extract.py"
    )
    assert command in capsys.readouterr().out
    assert command in (project / "data/README.md").read_text()
