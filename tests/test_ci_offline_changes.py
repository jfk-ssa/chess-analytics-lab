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
    "sync_ml": 0.0,
    "pytest_ml": 4.0,
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
        "sync_ml",
        "pytest_ml",
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
    sys.path.insert(0, str(ROOT / "scripts"))
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
        if step in chosen
        and flags.get(
            {"sync_mcp": "pytest_mcp", "sync_ml": "pytest_ml", "sync_dbt": "pytest_dbt"}.get(
                step, step
            )
        )
        != "true"
    )


def test_repository_map_matches_the_workflow(changes):
    assert changes.audit_repository(ROOT) == []


@pytest.mark.parametrize("quote", ["", "'", '"'])
def test_setup_uv_accepts_a_new_shared_full_sha(changes, quote):
    text = WORKFLOW.read_text(encoding="utf-8")
    mutated, count = re.subn(
        r"astral-sh/setup-uv@\S+", quote + "astral-sh/setup-uv@" + "a1" * 20 + quote, text
    )
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
@pytest.mark.parametrize(
    "pin", ["v10", "v10.3.3", "a" * 39, "a" * 41, "g" * 40, "", "a" * 40 + "#invalid-ref"]
)
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
        assert flags["pytest_ml"] == "true"
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
        assert flags["pytest_ml"] == "false"
        assert _skipped(flags, OFFLINE_STEPS) == 520.0


@pytest.mark.parametrize(
    "path",
    [
        "docs/review/reproduce_findings.py",
        "docs/review/reproduce_dashboard_empty_bucket.py",
        "docs/example.py",
    ],
)
def test_docs_python_runs_lint_without_pytest(changes, path):
    flags = changes.outputs_for("pull_request", [path])
    assert flags["run_all"] == "false"
    assert flags["ruff"] == flags["ruff_format"] == "true"
    assert flags["sync"] == flags["setup_uv"] == "true"
    assert all(
        flags[step.step_id] == "false" for step in changes.CHECKS if "pytest" in step.step_id
    )


def test_markdown_only_skips_lint_and_pytest(changes):
    flags = changes.outputs_for("pull_request", ["README.md", "docs/review/findings.md"])
    assert flags["run_all"] == "false"
    assert flags["ruff"] == flags["ruff_format"] == flags["sync"] == "false"
    assert all(
        flags[step.step_id] == "false" for step in changes.CHECKS if "pytest" in step.step_id
    )


def test_site_runs_biome_node_and_the_import_test(changes):
    flags = changes.outputs_for("pull_request", ["site/assets/site.css"])
    assert flags["biome"] == "true"
    assert flags["node_check_import"] == "true"
    assert flags["pytest_game_import"] == "true"
    assert flags["pytest"] == "false"
    assert flags["pytest_dbt"] == "false"
    assert flags["pytest_ml"] == "false"
    assert _skipped(flags, OFFLINE_STEPS) == 502.0
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
    assert replaced == 351.5
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
    assert flags["pytest_mcp"] == "true"
    assert flags["pytest_ml"] == "true"
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
    assert flags["pytest_ml"] == "false"
    assert flags["setup_node"] == "true"
    assert flags["core_setup_node"] == "true"
    assert _skipped(flags, OFFLINE_STEPS) == 24.0
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
    assert pure["pytest_ml"] == "false"
    assert _skipped(pure, OFFLINE_STEPS) == 38.0


def test_force_all_and_unknown_paths_run_every_historical_step(changes):
    for path in (
        ".github/workflows/offline.yml",
        ".github/workflows/pages.yml",
        "pyproject.toml",
        "uv.lock",
        "scripts/ci_offline_changes.py",
        "scripts/ci_offline_catalog.py",
        "scripts/ci_offline_install.py",
        "scripts/ci_offline_generate.py",
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


@pytest.mark.parametrize(
    "paths, extras",
    [
        (["docs/STATUS.md"], []),
        (["site/assets/site.css"], []),
        (["hosted/dashboard.py"], []),
        (["dbt/models/marts/games.sql"], ["dbt"]),
        (["evals/cases/analyst_live_v1.json"], ["dbt"]),
        (["site/assets/site.css", "dbt/models/marts/games.sql"], ["dbt"]),
        (["src/chess_analytics/cli.py"], ["mcp", "ml", "dbt"]),
    ],
)
def test_installed_union_matches_selected_steps(changes, monkeypatch, paths, extras):
    import ci_offline_install as install

    outputs = changes.outputs_for("pull_request", paths)
    calls, _ = _run_install(install, monkeypatch, outputs)
    assert calls == [
        [
            "uv",
            "sync",
            "--locked",
            "--no-editable",
            *(arg for extra in extras for arg in ("--extra", extra)),
        ]
    ]
    assert outputs["sync"] == str(bool(extras) or outputs["setup_uv"] == "true").lower()


def _run_install(install, monkeypatch, outputs, result="success", raw=None):
    import json
    from types import SimpleNamespace

    calls = []
    monkeypatch.setenv("CHANGES_RESULT", result)
    monkeypatch.setenv("SELECTION", json.dumps(outputs) if raw is None else raw)
    monkeypatch.setattr(
        install.subprocess,
        "run",
        lambda argv, **kwargs: calls.append(argv) or SimpleNamespace(returncode=0),
    )
    assert install.main([]) == 0
    return calls, install


@pytest.mark.parametrize(
    "failure",
    ["detection", "failed", "missing", "invalid", "json", "type", "inconsistent", "category"],
)
def test_failures_install_all_extras_before_the_full_suite(changes, monkeypatch, tmp_path, failure):
    import ci_offline_install as install

    outputs = changes.outputs_for("pull_request", ["docs/STATUS.md"])
    result, raw = "success", None
    if failure == "detection":
        outputs = changes.emit_outputs("pull_request", None)
    elif failure == "failed":
        result = "failure"
    elif failure == "missing":
        del outputs["pytest_mcp"]
    elif failure == "invalid":
        outputs["pytest_ml"] = "maybe"
    elif failure == "inconsistent":
        outputs["pytest_mcp"] = "true"
    elif failure == "category":
        outputs["categories"] = "all,docs"
    elif failure == "type":
        outputs["pytest_ml"] = []
    else:
        raw = "{broken"
    calls, _ = _run_install(install, monkeypatch, outputs, result, raw)
    assert calls == [
        [
            "uv",
            "sync",
            "--locked",
            "--no-editable",
            "--extra",
            "mcp",
            "--extra",
            "ml",
            "--extra",
            "dbt",
        ]
    ]
    output_file = tmp_path / "outputs"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))
    assert install.main(["--validate-only"]) == 0
    assert output_file.read_text() == f"fallback={str(failure != 'detection').lower()}\n"
    # Every selected step in every job consults the validated fallback.
    for step in (*changes.CHECKS, *changes.SUPPORT):
        from ci_offline_catalog import SELECTION_IDS

        condition = step.if_expr or changes.default_if(step.step_id, step.job)
        assert f"steps.{SELECTION_IDS[step.job]}.outputs.fallback != 'false'" in condition


@pytest.mark.parametrize("drift", ["command", "output", "order"])
def test_generated_audit_rejects_drift(changes, drift):
    text = WORKFLOW.read_text()
    if drift == "command":
        text = text.replace("ruff check .", "ruff check src")
    elif drift == "output":
        text = text.replace("      sync: ${{ steps.filter.outputs.sync }}\n", "")
    else:
        start = text.index("      - id: sync\n")
        end = text.index("      - id: ruff\n", start)
        block = text[start:end]
        text = text[:start] + text[end:]
        start = text.index("      - id: transform\n")
        text = text[:start] + block + text[start:]
    problems = changes.audit_text(text, changes.tracked_files(ROOT))
    assert any("generated workflow blocks drifted" in problem for problem in problems)
    if drift == "order":
        assert any("sync must run before" in problem for problem in problems)


@pytest.mark.parametrize("job", ["offline", "portfolio"])
def test_required_job_names_stay_stable(changes, job):
    text = WORKFLOW.read_text().replace(f"  {job}:\n", f"  {job}:\n    name: Renamed\n", 1)
    assert any(f"do not rename required job {job}" in p for p in changes.audit_text(text, []))


@pytest.mark.parametrize(
    "event, path",
    [
        ("push", "README.md"),
        ("pull_request", "README.md"),
        ("pull_request", "src/chess_analytics/cli.py"),
    ],
)
def test_valid_selection_keeps_skips_and_narrow_suppression(
    changes, monkeypatch, tmp_path, event, path
):
    import ci_offline_install as install

    flags = changes.outputs_for(event, [path])
    _run_install(install, monkeypatch, flags)
    output = tmp_path / "outputs"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    assert install.main(["--validate-only"]) == 0
    assert output.read_text() == "fallback=false\n"
    assert flags["pytest_extract"] == flags["pytest_game_import"] == "false"
    if event == "pull_request" and path == "README.md":
        assert all(flags[step.step_id] == "false" for step in (*changes.CHECKS, *changes.SUPPORT))


@pytest.mark.parametrize(
    "path",
    [
        "site/assets/dashboard-core.mjs",
        "site/assets/dashboard-ui.mjs",
        "site/assets/dashboard.css",
        "scripts/templates/dashboard.html.j2",
        "scripts/templates/shell.html.j2",
        "scripts/templates/live_eval.html.j2",
        "tests/js/dashboard.test.mjs",
        "tests/js/dashboard_query.mjs",
        "tests/test_dashboard_export.py",
        "tests/test_dashboard_cube.py",
        "scripts/build_docs_site.py",
        "scripts/build_dashboard_cube.py",
        "scripts/build_warehouse_cube.py",
        "src/chess_analytics/dashboard_cube.py",
        "src/chess_analytics/dashboard_export.py",
        "src/chess_analytics/dashboard/analysis.py",
        "src/chess_analytics/public_extract.py",
        "scripts/build_public_extract.py",
        "data/public/dashboard_cube.parquet",
        "data/public/dashboard_extract.json",
    ],
)
def test_dashboard_changes_select_node_and_python_coverage(changes, path):
    flags = changes.outputs_for("pull_request", [path])
    assert flags["setup_node"] == flags["node_test"] == "true"
    assert flags["pytest_dashboard"] == "true" or flags["pytest"] == "true"
    assert flags["sync"] == "true"
    if path.startswith("data/public/"):
        assert flags["pytest_dashboard"] == "true"
        assert flags["pytest"] == "false"


def test_dashboard_command_and_order_are_catalogued(changes):
    steps = {step.step_id: step for step in changes.CHECKS}
    assert "tests/js/dashboard.test.mjs" in steps["node_test"].exact
    assert "tests/js/game_import.test.mjs" in steps["node_test"].exact
    assert "tests/test_dashboard_cube.py" in steps["pytest_dashboard"].exact
    assert "tests/test_dashboard_export.py" in steps["pytest_dashboard"].exact
    assert "setup_node" in steps["pytest_dashboard"].requires
