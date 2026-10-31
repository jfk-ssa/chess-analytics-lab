"""The offline workflow selects steps from the diff and still reports every job."""

import importlib.util
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "offline.yml"

# Medians in seconds from the 10 successful Offline integrity runs on 2026-10-21.
# 39573039885, 39569744454, 39565639588, 39564289206, 39564222989,
# 39553723369, 39550522492, 39545491973, 39543070270, 39541953315.
MEDIAN_SECONDS = {
    "setup_uv": 4.0,
    "setup_node": 1.0,
    "biome": 2.0,
    "node_test": 0.0,
    "node_check_import": 9.0,
    "node_parity_authored": 0.0,
    "node_parity_zero": 0.0,
    "sync": 2.0,
    "ruff": 0.0,
    "ruff_format": 0.0,
    "basedpyright": 5.0,
    "pytest": 156.5,
    "sync_mcp": 0.0,
    "pytest_mcp": 4.0,
    "demo": 0.0,
    "sync_dbt": 1.0,
    "pytest_dbt": 294.5,
    "transform": 5.5,
    "semantic": 4.5,
    "analyst_gate": 13.0,
    "dbt_base_checkout": 1.0,
    "dbt_slim": 13.0,
    "portfolio_setup_uv": 5.0,
    "portfolio_sync": 2.0,
    "pytest_portfolio": 8.5,
    "demo_all": 2.0,
}
OFFLINE_STEPS = frozenset(
    {
        "setup_uv",
        "setup_node",
        "biome",
        "node_test",
        "node_check_import",
        "node_parity_authored",
        "node_parity_zero",
        "sync",
        "ruff",
        "ruff_format",
        "basedpyright",
        "pytest",
        "sync_mcp",
        "pytest_mcp",
        "demo",
        "sync_dbt",
        "pytest_dbt",
        "transform",
        "semantic",
        "analyst_gate",
        "dbt_base_checkout",
        "dbt_slim",
    }
)


def _load():
    name = "ci_offline_changes"
    cached = sys.modules.get(name)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / "ci_offline_changes.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def changes():
    return _load()


def _skipped(flags: dict[str, str], steps: frozenset[str] | None = None) -> float:
    chosen = steps if steps is not None else frozenset(MEDIAN_SECONDS)
    return sum(
        seconds
        for step, seconds in MEDIAN_SECONDS.items()
        if step in chosen and flags.get(step) != "true"
    )


def test_repository_map_matches_the_workflow(changes):
    assert changes.audit_repository(ROOT) == []


def test_setup_uv_accepts_a_new_shared_full_sha(changes):
    text = WORKFLOW.read_text(encoding="utf-8")
    mutated, count = re.subn(r"astral-sh/setup-uv@\S+", "astral-sh/setup-uv@" + "a1" * 20, text)
    assert count == 3
    assert changes.audit_text(mutated, changes.tracked_files(ROOT)) == []


@pytest.mark.parametrize(
    "step_id, label",
    [
        ("setup_uv", "offline.setup_uv"),
        ("portfolio_setup_uv", "portfolio.portfolio_setup_uv"),
        ("core_setup_uv", "offline-core.core_setup_uv"),
    ],
)
@pytest.mark.parametrize("pin", ["v10", "v10.3.3", "a" * 39, "a" * 41, "g" * 40, ""])
def test_setup_uv_rejects_non_full_sha_pins(changes, step_id, label, pin):
    text = WORKFLOW.read_text(encoding="utf-8")
    mutated, count = re.subn(
        rf"(      - id: {step_id}\n.*?uses: astral-sh/setup-uv@)\S+",
        rf"\g<1>{pin}",
        text,
        count=1,
        flags=re.DOTALL,
    )
    assert count == 1
    problems = changes.audit_text(mutated, changes.tracked_files(ROOT))
    assert any(label in problem and "40-hex SHA" in problem for problem in problems)


def test_setup_uv_rejects_inconsistent_shas(changes):
    text = WORKFLOW.read_text(encoding="utf-8")
    shared, count = re.subn(r"astral-sh/setup-uv@\S+", "astral-sh/setup-uv@" + "a" * 40, text)
    assert count == 3
    mutated = shared.replace("astral-sh/setup-uv@" + "a" * 40, "astral-sh/setup-uv@" + "b" * 40, 1)
    problems = changes.audit_text(mutated, changes.tracked_files(ROOT))
    assert any("setup-uv SHAs differ across steps" in problem for problem in problems)


def test_a_removed_step_id_fails_the_audit(changes):
    text = WORKFLOW.read_text(encoding="utf-8")
    mutated = text.replace("      - id: analyst_gate\n", "      - name: Offline analyst gate\n", 1)
    problems = changes.audit_text(mutated, changes.tracked_files(ROOT))
    assert any("analyst_gate" in problem for problem in problems)
    renamed = text.replace(
        "  offline-core:\n    needs: changes\n",
        "  offline-core:\n    name: Pytest without dbt\n    needs: changes\n",
        1,
    )
    name_problems = changes.audit_text(renamed, changes.tracked_files(ROOT))
    assert any("display name" in problem for problem in name_problems)
    gated = text.replace(
        "  offline-core:\n    needs: changes\n    if: ${{ !cancelled() }}\n",
        "  offline-core:\n    needs: changes\n"
        "    if: ${{ !cancelled() && needs.changes.outputs.pytest == 'true' }}\n",
        1,
    )
    gated_problems = changes.audit_text(gated, changes.tracked_files(ROOT))
    assert any(
        "offline-core if must be ${{ !cancelled() }}" in problem for problem in gated_problems
    )


def test_a_workflow_path_filter_fails_the_audit(changes):
    text = WORKFLOW.read_text(encoding="utf-8")
    mutated = text.replace("pull_request:\n", "pull_request:\n    paths:\n      - docs/**\n", 1)
    problems = changes.audit_text(mutated, changes.tracked_files(ROOT))
    assert any("path filter" in problem for problem in problems)


def test_only_pull_requests_select_steps(changes):
    assert frozenset({"pull_request"}) == changes.SELECTIVE_EVENTS
    for event in ("push", "merge_group", "workflow_dispatch", "schedule", "workflow_call", ""):
        flags = changes.outputs_for(event, ["docs/STATUS.md"])
        assert flags["run_all"] == "true"
        assert flags["pytest"] == "true"
        assert flags["pytest_dbt"] == "true"
        assert flags["analyst_gate"] == "true"


def test_docs_skip_the_long_steps(changes):
    for path in (
        "docs/STATUS.md",
        "docs/adr/0098-hosted-dashboard-analysis.md",
        "README.md",
        "CONTRIBUTING.md",
        "AGENTS.md",
        "LICENSE",
        "auxiliary-examples/README.md",
    ):
        flags = changes.outputs_for("pull_request", [path])
        assert flags["run_all"] == "false"
        assert flags["pytest"] == "false"
        assert flags["pytest_dbt"] == "false"
        assert flags["analyst_gate"] == "false"
        assert flags["biome"] == "false"
        assert flags["core_setup_uv"] == "false"
        assert flags["core_setup_node"] == "false"
        assert flags["core_sync"] == "false"
        assert _skipped(flags, OFFLINE_STEPS) == 516.0


def test_site_runs_biome_node_and_the_import_test(changes):
    flags = changes.outputs_for("pull_request", ["site/assets/site.css"])
    assert flags["biome"] == "true"
    assert flags["node_check_import"] == "true"
    assert flags["pytest_game_import"] == "true"
    assert flags["pytest"] == "false"
    assert flags["pytest_dbt"] == "false"
    assert _skipped(flags, OFFLINE_STEPS) == 498.0
    templates = changes.outputs_for("pull_request", ["scripts/templates/shell.html.j2"])
    assert templates["biome"] == "true"
    assert templates["pytest"] == "false"


def test_hosted_runs_the_extract_budget_test_and_skips_dbt_pytest(changes):
    flags = changes.outputs_for("pull_request", ["data/public/dashboard_extract.json"])
    assert flags["pytest_extract"] == "true"
    assert flags["pytest"] == "false"
    assert flags["pytest_dbt"] == "false"
    assert flags["pytest_portfolio"] == "true"
    assert flags["basedpyright"] == "true"
    replaced = _skipped(flags, OFFLINE_STEPS) - MEDIAN_SECONDS["pytest"]
    assert replaced == 348.5
    source = changes.outputs_for("pull_request", ["src/chess_analytics/public_extract.py"])
    assert source["pytest"] == "true"
    builder = changes.outputs_for("pull_request", ["scripts/build_public_extract.py"])
    assert builder["pytest"] == "true"
    notices = changes.outputs_for("pull_request", ["THIRD_PARTY_NOTICES.md"])
    assert notices["run_all"] == "false"
    assert notices["categories"] == "hosted"
    assert notices["pytest_extract"] == "true"
    assert notices["pytest_portfolio"] == "true"
    assert notices["pytest"] == "false"


def test_metrics_contract_keeps_the_analyst_guards(changes):
    flags = changes.outputs_for("pull_request", ["docs/METRICS.md"])
    assert flags["run_all"] == "false"
    assert flags["categories"] == "analyst,docs"
    assert flags["analyst_gate"] == "true"
    assert flags["pytest"] == "true"
    assert flags["pytest_dbt"] == "true"


def test_python_runs_the_full_pytest_and_not_the_narrow_files(changes):
    flags = changes.outputs_for("pull_request", ["src/chess_analytics/cli.py"])
    assert flags["pytest"] == "true"
    assert flags["pytest_dbt"] == "true"
    assert flags["pytest_extract"] == "false"
    assert flags["pytest_game_import"] == "false"
    assert flags["ruff"] == "true"
    assert flags["ruff_format"] == "true"
    assert flags["basedpyright"] == "true"
    assert flags["dbt_slim"] == "false"
    assert flags["biome"] == "false"
    assert flags["setup_node"] == "true"
    assert flags["core_setup_uv"] == "true"
    assert flags["core_setup_node"] == "true"
    assert flags["core_sync"] == "true"
    assert _skipped(flags, OFFLINE_STEPS) == 25.0


def test_dbt_runs_slim_selection_and_both_pytest_steps(changes):
    flags = changes.outputs_for("pull_request", ["dbt/models/marts/games.sql"])
    assert flags["dbt_slim"] == "true"
    assert flags["pytest"] == "true"
    assert flags["pytest_dbt"] == "true"
    assert flags["semantic"] == "true"
    assert flags["analyst_gate"] == "true"
    assert flags["biome"] == "false"
    assert flags["pytest_mcp"] == "false"
    assert flags["setup_node"] == "true"
    assert flags["core_setup_node"] == "true"
    assert _skipped(flags, OFFLINE_STEPS) == 20.0
    lineage = changes.outputs_for("pull_request", ["docs/DBT_LINEAGE.md"])
    assert lineage["semantic"] == "true"
    assert lineage["pytest_dbt"] == "true"
    assert lineage["setup_node"] == "true"


def test_analyst_evals_and_receipts_keep_their_guards(changes):
    paths = (
        "src/chess_analytics/analyst/gate.py",
        "evals/baselines/analyst_gate_v1.json",
        "evals/cases/analyst_live_v1.json",
        "reports/live-eval-receipt-39494372489.json",
        "tests/fixtures/live_eval_100.pgn",
        "tests/fixtures/live_eval_100_expected.json",
    )
    for path in paths:
        flags = changes.outputs_for("pull_request", [path])
        assert flags["analyst_gate"] == "true", path
        assert flags["pytest"] == "true", path
        assert flags["pytest_dbt"] == "true", path
        assert flags["pytest_portfolio"] == "true", path
    pure = changes.outputs_for("pull_request", ["evals/baselines/analyst_gate_v1.json"])
    assert pure["setup_node"] == "true"
    assert pure["core_setup_uv"] == "true"
    assert pure["core_sync"] == "true"
    assert _skipped(pure, OFFLINE_STEPS) == 34.0


def test_force_all_and_unknown_paths_run_every_historical_step(changes):
    for path in (
        ".github/workflows/offline.yml",
        ".github/workflows/pages.yml",
        "pyproject.toml",
        "uv.lock",
        "scripts/ci_offline_changes.py",
        "tests/test_ci_offline_changes.py",
        "mystery.bin",
        "reports/M3-independent-reference.json",
    ):
        flags = changes.outputs_for("pull_request", [path])
        assert flags["run_all"] == "true", path
        assert _skipped(flags) == 0.0
    mixed = changes.outputs_for("pull_request", ["docs/STATUS.md", "notes.txt"])
    assert mixed["run_all"] == "true"
    assert mixed["pytest_dbt"] == "true"


def test_an_empty_diff_fails_open(changes, tmp_path):
    with pytest.raises(ValueError, match="missing"):
        changes.outputs_for("pull_request", [])
    flags = changes.emit_outputs("pull_request", [])
    assert flags["run_all"] == "true"
    assert flags["categories"] == "all"
    assert _skipped(flags) == 0.0
    listing = tmp_path / "diff.txt"
    listing.write_text("", encoding="utf-8")
    output = tmp_path / "github.txt"
    code = changes.main(
        [
            "--event",
            "pull_request",
            "--name-status",
            str(listing),
            "--github-output",
            str(output),
        ]
    )
    assert code == 0
    assert "run_all=true\n" in output.read_text(encoding="utf-8")


def test_detection_errors_select_the_full_suite(changes, tmp_path):
    broken = changes.emit_outputs("pull_request", None)
    assert broken["run_all"] == "true"
    listing = tmp_path / "diff.txt"
    listing.write_text('"docs/quoted.md"\n', encoding="utf-8")
    output = tmp_path / "github.txt"
    code = changes.main(
        [
            "--event",
            "pull_request",
            "--name-status",
            str(listing),
            "--github-output",
            str(output),
        ]
    )
    assert code == 0
    assert "run_all=true\n" in output.read_text(encoding="utf-8")
    status = changes.paths_from_name_status("R100\tdocs/OLD.md\tsrc/chess_analytics/cli.py\n")
    flags = changes.outputs_for("pull_request", status)
    assert flags["pytest"] == "true"
    docs_rename = changes.paths_from_name_status("R100\tdocs/OLD.md\tdocs/NEW.md\n")
    assert changes.outputs_for("pull_request", docs_rename)["pytest"] == "false"


def test_every_check_category_has_a_pattern(changes):
    categories = {rule.category for rule in changes.RULES}
    used = {category for step in changes.CHECKS for category in step.categories}
    assert categories - used == changes.CATEGORIES_WITHOUT_CHECKS
    assert used <= categories
