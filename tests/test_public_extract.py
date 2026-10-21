"""Equality checks for the committed public aggregate extract. Offline only."""

import importlib.util
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from chess_analytics.public_extract import (
    NEVER_METRICFLOW,
    QUERY_ORIGINS,
    SIZE_BUDGET_BYTES,
    connect,
    derived_mart_id,
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
    "opening-positions-checkpoint.json",
    "opening-positions-dashboard.json",
)
_POSITIONS_SHA = "31a395044203532224cbb387475ef0bb790c8e88faac98bc9b2a12f5d500c46e"


def _reports_project(tmp_path: Path, project: Path) -> Path:
    """Project with the committed reports and no analytical warehouse."""
    root = tmp_path / "reports-only"
    destination = root / "reports"
    destination.mkdir(parents=True)
    for name in _REPORTS:
        shutil.copy(project / "reports" / name, destination / name)
    for path in sorted((project / "reports").glob("live-eval-receipt-*.json")):
        shutil.copy(path, destination / path.name)
    cases = root / "evals" / "cases"
    cases.mkdir(parents=True)
    shutil.copy(
        project / "evals" / "cases" / "analyst_live_v1.json",
        cases / "analyst_live_v1.json",
    )
    return root


def _without_receipt_labels(payload: dict) -> dict:
    cloned = json.loads(json.dumps(payload))
    cloned.pop("build", None)
    for row in cloned["tables"]["metric_receipt"]:
        for key in _LABEL_FIELDS:
            del row[key]
    return cloned


def _committed_origins(extract: dict) -> None:
    receipts = table_rows(extract, "metric_receipt")
    by_origin = {
        origin: {row["receipt_id"] for row in receipts if row["query_origin"] == origin}
        for origin in QUERY_ORIGINS
    }
    assert by_origin["metricflow"] == set(METRICFLOW_RECEIPTS)
    assert by_origin["reviewed_sql"] == set(REVIEWED_SQL_RECEIPTS)
    assert by_origin["committed_report"] == {row["receipt_id"] for row in receipts} - set(
        METRICFLOW_RECEIPTS
    ) - set(REVIEWED_SQL_RECEIPTS)


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
    # No warehouse can raise query_origin, mart identity, or the build record.
    # Those are the only differences from the committed MetricFlow rebuild.
    rebuilt = json.loads(first.read_text())
    committed = load_extract(extract_path(project))
    _committed_origins(committed)
    assert "build" not in rebuilt
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


def test_committed_origins_reject_metricflow_on_a_clock_receipt(project):
    committed = json.loads(extract_path(project).read_text())
    for row in committed["tables"]["metric_receipt"]:
        if row["receipt_id"] == "clock_pressure_error_proxy:under_10":
            row["query_origin"] = "metricflow"
            break
    with pytest.raises(AssertionError):
        _committed_origins(committed)


def _published_build_pins(extract: dict) -> None:
    build = extract["build"]
    derived = derived_mart_id(
        build["source_snapshot_id"],
        build["model_sha256"],
        build["lock_sha256"],
    )
    assert build["source_snapshot_id"] == "7764247e6bdb0b6e73420253"
    assert build["lock_sha256"] == (
        "895bcfb181a6abc76ff2c466f222b8ebccf6b451a1c32e56f8080bde1194670f"
    )
    assert derived == "9d3ca923a6f1cd06d82a8645"
    for receipt_id in METRICFLOW_RECEIPTS:
        row = _receipt(extract, receipt_id)
        assert row["mart_id"] == derived
        assert row["model_sha256"] == build["model_sha256"]
        assert row["semantic_manifest_sha256"] == build["semantic_manifest_sha256"]


def test_mart_id_matches_the_recorded_snapshot_model_and_lock(project):
    _published_build_pins(load_extract(extract_path(project)))


def test_loader_rejects_metricflow_receipts_without_a_build_record(project, tmp_path):
    payload = json.loads(extract_path(project).read_text())
    del payload["build"]
    path = tmp_path / "extract.json"
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="require a build record"):
        load_extract(path)


def test_loader_rejects_a_null_build_when_receipts_are_metricflow(project, tmp_path):
    payload = json.loads(extract_path(project).read_text())
    payload["build"] = None
    path = tmp_path / "extract.json"
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="require a build record"):
        load_extract(path)


def test_loader_rejects_metricflow_on_an_unapproved_metric(project, tmp_path):
    payload = json.loads(extract_path(project).read_text())
    del payload["build"]
    for row in payload["tables"]["metric_receipt"]:
        if row["receipt_id"] == "opening_corpus_training_games":
            row["query_origin"] = "metricflow"
            break
    path = tmp_path / "extract.json"
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="governed metrics"):
        load_extract(path)


def test_loader_rejects_a_build_record_without_metricflow(project, tmp_path):
    payload = json.loads(extract_path(project).read_text())
    for row in payload["tables"]["metric_receipt"]:
        if row["query_origin"] != "metricflow":
            continue
        row["query_origin"] = "committed_report"
        row["mart_id"] = None
        row["model_sha256"] = None
        row["semantic_manifest_sha256"] = None
    path = tmp_path / "extract.json"
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="requires a metricflow receipt"):
        load_extract(path)
    payload["build"] = None
    path.write_text(json.dumps(payload))
    assert load_extract(path)["build"] is None


def test_committed_pins_reject_a_substituted_snapshot(project):
    # A self-consistent forged build cannot be caught by a loader with no warehouse.
    # The committed-file pins reject a substituted snapshot.
    payload = json.loads(extract_path(project).read_text())
    payload["build"]["source_snapshot_id"] = "ab" * 12
    derived = derived_mart_id(
        payload["build"]["source_snapshot_id"],
        payload["build"]["model_sha256"],
        payload["build"]["lock_sha256"],
    )
    for row in payload["tables"]["metric_receipt"]:
        if row["query_origin"] == "metricflow":
            row["mart_id"] = derived
    with pytest.raises(AssertionError):
        _published_build_pins(payload)


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


def test_loader_rejects_extract_version_one(project, tmp_path):
    payload = json.loads(extract_path(project).read_text())
    assert payload["extract_version"] == "2"
    payload["extract_version"] = "1"
    path = tmp_path / "extract.json"
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="unsupported public extract version"):
        load_extract(path)


def test_opening_color_scores_match_the_published_window(project):
    extract = load_extract(extract_path(project))
    cells = table_rows(extract, "opening_color_score")
    assert len(cells) == 4
    assert {(row["family"], row["color"]) for row in cells} == {
        ("French Defense", "white"),
        ("French Defense", "black"),
        ("Sicilian Defense", "white"),
        ("Sicilian Defense", "black"),
    }
    figures = json.loads((project / "reports/M4-figures.json").read_text())
    published = figures["opening"]["families"]
    for cell in cells:
        games = cell["games"]
        assert games >= 100
        assert cell["low_support"] is False
        assert cell["rating_min"] == 1400
        assert cell["rating_max_exclusive"] == 1600
        assert cell["base_seconds"] == 60
        assert cell["increment_seconds"] == 0
        assert cell["score_rate"] == pytest.approx((cell["wins"] + cell["draws"] / 2) / games)
        if cell["color"] == "white":
            assert cell["adjusted_score_rate"] is None
            assert cell["adjusted_interval_low"] is None
            assert cell["adjusted_interval_high"] is None
            continue
        family = published[cell["family"]]
        low, high = family["adjusted_95pct_cluster_bootstrap_interval"]
        assert cell["adjusted_score_rate"] == family["adjusted_score_rate"]
        assert cell["adjusted_interval_low"] == low
        assert cell["adjusted_interval_high"] == high
        assert cell["games"] == family["raw"]["eligible_player_games"]


def test_low_support_threshold_matches_the_corpus_rule(project):
    builder = load_script()
    assert builder.LOW_SUPPORT_PLAYER_GAMES == 100
    source = (project / "src/chess_analytics/corpus/metrics.py").read_text()
    assert "total < 100" in source


def test_clock_pressure_bands_pool_the_buckets(project):
    extract = load_extract(extract_path(project))
    bands = table_rows(extract, "clock_pressure_band")
    buckets = table_rows(extract, "clock_bucket")
    assert len(bands) == 52
    assert len({(row["rating_band"], row["time_control"]) for row in bands}) == 52
    for field in ("proxy_errors", "evaluable_moves", "eligible_moves"):
        assert sum(row[field] for row in bands) == sum(row[field] for row in buckets)
    for row in bands:
        if row["evaluable_moves"] == 0:
            assert row["error_proxy_rate"] is None
        else:
            assert row["error_proxy_rate"] == pytest.approx(
                row["proxy_errors"] / row["evaluable_moves"]
            )


def test_transposition_reduction_matches_the_checkpoint(project):
    extract = load_extract(extract_path(project))
    scope = table_rows(extract, "transposition_scope")
    assert len(scope) == 1
    assert scope[0]["positions_sha256"] == _POSITIONS_SHA
    assert scope[0]["games"] == 1_042_346
    assert scope[0]["visits"] == 8_338_768
    views = table_rows(extract, "transposition_view")
    lenses = {
        ("elite_reference", "d4-g3"): 16_647,
        ("elite_reference", "d4-g3-catalan"): 6_850,
        ("elite_reference", "d4-g3-kings-indian"): 2_867,
        ("rated_public", "d4-g3"): 20_745,
        ("rated_public", "d4-g3-catalan"): 5_429,
        ("rated_public", "d4-g3-kings-indian"): 1_647,
    }
    for key, games in lenses.items():
        matches = [row for row in views if (row["cohort"], row["view"]) == key]
        assert len(matches) == 1
        assert matches[0]["denominator_games"] == games
    all_views = [row for row in views if row["view"] == "all"]
    assert sum(row["denominator_games"] for row in all_views) == 1_042_346
    summary = json.loads((project / "reports/opening-positions-dashboard.json").read_text())
    assert summary["source_sha256"] == _POSITIONS_SHA
    assert len(table_rows(extract, "transposition_limitation")) == len(summary["limitations"])
    hex24 = re.compile(r"^[0-9a-f]{24}$")
    for name in (
        "transposition_view",
        "transposition_compression",
        "transposition_coverage",
        "transposition_scope",
        "transposition_limitation",
    ):
        for row in table_rows(extract, name):
            for value in row.values():
                if isinstance(value, str):
                    assert hex24.fullmatch(value) is None


def test_dashboard_reduction_matches_the_pinned_blob(project):
    probe = subprocess.run(
        ["git", "cat-file", "-e", f"{_POSITIONS_SHA}^{{blob}}"],
        cwd=project,
        capture_output=True,
        check=False,
    )
    if probe.returncode != 0:
        pytest.skip("opening-positions blob is not in this checkout")
    raw = subprocess.check_output(["git", "cat-file", "-p", _POSITIONS_SHA], cwd=project)
    reduced = load_script().reduce_opening_positions(json.loads(raw))
    committed = json.loads((project / "reports/opening-positions-dashboard.json").read_text())
    for key in ("compression", "coverage", "views", "limitations", "plan_min_ply", "plan_max_ply"):
        assert reduced[key] == committed[key]


def test_live_eval_rows_match_the_committed_receipts(project):
    extract = load_extract(extract_path(project))
    runs = {row["model"]: row for row in table_rows(extract, "live_eval_run")}
    assert set(runs) == {"gpt-6-luna", "gpt-6-sol", "grok-4.7"}
    receipts = sorted((project / "reports").glob("live-eval-receipt-*.json"))
    assert len(receipts) == 3
    for path in receipts:
        receipt = json.loads(path.read_text())
        row = runs[receipt["model"]]
        assert row["effort"] == receipt["reasoning_effort"]
        assert row["passed"] == receipt["headline_passed"]
        assert row["trials"] == receipt["planned_requests"]
        assert row["pass_rate"] == receipt["headline_pass_rate"]
        assert row["hard_fail"] is receipt["hard_fail"]
        assert row["repeats"] == receipt["repeats"]
        assert row["headline"] is True
        assert row["wilson_low"] == receipt["stats"]["wilson"]["lower"]
        assert row["wilson_high"] == receipt["stats"]["wilson"]["upper"]
        assert row["known_gross_cost_usd"] == receipt["known_gross_cost_usd"]
        assert row["source_report"] == path.name
    assert runs["gpt-6-sol"]["wilson_low"] > runs["gpt-6-luna"]["wilson_high"]
    assert runs["gpt-6-sol"]["hard_fail"] is True
    assert runs["gpt-6-luna"]["hard_fail"] is False
    assert runs["gpt-6-sol"]["passed"] == 234
    assert runs["gpt-6-luna"]["passed"] == 207
    assert runs["grok-4.7"]["passed"] == 233
    assert runs["grok-4.7"]["hard_fail"] is False
    assert runs["grok-4.7"]["effort"] == "low"
    assert runs["grok-4.7"]["known_gross_cost_usd"] == 1.003306
    assert runs["grok-4.7"]["wilson_low"] == 0.9410304560608658
    assert runs["gpt-6-luna"]["frozen_group"] == runs["gpt-6-sol"]["frozen_group"]
    assert runs["grok-4.7"]["frozen_group"] != runs["gpt-6-luna"]["frozen_group"]
    assert len(runs["gpt-6-luna"]["frozen_group"]) == 64
    cases = table_rows(extract, "live_eval_case")
    assert len(cases) == 144
    assert "source_report" not in cases[0]
    categories = table_rows(extract, "live_eval_category")
    assert "source_report" not in categories[0]
    by_run = {(row["model"], row["effort"]): row["source_report"] for row in runs.values()}
    assert len(by_run) == len(runs)

    def passed(model: str, case_id: str) -> int:
        matches = [row for row in cases if row["model"] == model and row["case_id"] == case_id]
        assert len(matches) == 1
        return matches[0]["passed"]

    assert passed("gpt-6-sol", "boundary_budget") == 0
    assert passed("gpt-6-luna", "boundary_budget") == 5
    assert passed("grok-4.7", "boundary_budget") == 5
    assert passed("grok-4.7", "indirect_opening_1") == 0
    assert passed("grok-4.7", "usage_sicilian_3") == 3
    assert len(categories) == 30
    rate_ids = {
        row["receipt_id"]
        for row in table_rows(extract, "metric_receipt")
        if row["metric"] == "live_eval_pass_rate"
    }
    assert rate_ids == {
        "live_eval_pass_rate:gpt-6-luna none",
        "live_eval_pass_rate:gpt-6-sol none",
        "live_eval_pass_rate:grok-4.7 low",
    }
    grok_rate = _receipt(extract, "live_eval_pass_rate:grok-4.7 low")
    assert grok_rate["numerator"] == 233
    assert grok_rate["denominator"] == 240
    assert grok_rate["query_origin"] == "committed_report"


def test_live_eval_model_effort_must_be_unique(project, tmp_path):
    builder = load_script()
    bare = _reports_project(tmp_path, project)
    source = next((bare / "reports").glob("live-eval-receipt-grok-4.7-low-r5-*.json"))
    duplicate = bare / "reports" / "live-eval-receipt-grok-4.7-low-r5-99.json"
    duplicate.write_bytes(source.read_bytes())
    with pytest.raises(ValueError, match="not unique"):
        builder.live_eval_tables(bare)


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
