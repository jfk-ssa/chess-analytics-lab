"""Stdlib-only source of truth for offline steps and their dependencies."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Rule:
    category: str
    patterns: tuple[str, ...]
    excludes: tuple[str, ...] = ()


@dataclass(frozen=True)
class Step:
    job: str
    step_id: str
    kind: str
    categories: tuple[str, ...] = ()
    exact: str = ""
    uses: str = ""
    if_expr: str = ""
    extras: tuple[str, ...] = ()
    requires: tuple[str, ...] = ()
    details: str = ""


SELECTION_IDS = {
    "offline": "record_selection",
    "offline-core": "core_selection",
    "portfolio": "portfolio_record",
}
OFFLINE_EXTRAS = ("mcp", "ml", "dbt")
MAPPED_JOBS = ("offline", "offline-core", "portfolio")
_CHECKOUT = "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1"


def default_if(step_id: str, job: str) -> str:
    return (
        "${{ needs.changes.result != 'success' || "
        f"steps.{SELECTION_IDS[job]}.outputs.fallback != 'false' || "
        f"needs.changes.outputs.{step_id} == 'true' }}}}"
    )


RULES = (
    Rule(
        "docs",
        ("docs/**", "*.md", "LICENSE", "auxiliary-examples/**"),
        ("THIRD_PARTY_NOTICES.md",),
    ),
    Rule(
        "dashboard",
        (
            "site/assets/dashboard*",
            "scripts/templates/**",
            "tests/js/dashboard*",
            "tests/test_dashboard*.py",
            "scripts/build_docs_site.py",
            "scripts/build_*cube.py",
            "src/chess_analytics/dashboard_cube.py",
            "src/chess_analytics/dashboard_export.py",
            "src/chess_analytics/dashboard/analysis.py",
            "src/chess_analytics/public_extract.py",
            "scripts/build_public_extract.py",
            "data/public/dashboard_cube.parquet",
            "data/public/dashboard_extract.json",
        ),
    ),
    Rule("lint", ("docs/*.py", "docs/**/*.py")),
    Rule(
        "site",
        (
            "site/**",
            "scripts/templates/**",
            "biome.json",
            "tests/js/**",
            "tests/fixtures/imports/**",
            "scripts/check_game_import.mjs",
        ),
    ),
    Rule(
        "hosted",
        (
            "hosted/**",
            "data/public/**",
            "data/README.md",
            ".streamlit/**",
            "THIRD_PARTY_NOTICES.md",
        ),
    ),
    Rule(
        "python",
        (
            "src/**",
            "scripts/*.py",
            "scripts/*.sh",
            "tests/*.py",
            "tests/**/*.py",
            "tests/fixtures/**",
            "config/**",
        ),
        (
            "tests/fixtures/imports/**",
            "tests/fixtures/live_eval_100.pgn",
            "tests/fixtures/live_eval_100_expected.json",
        ),
    ),
    Rule("dbt", ("dbt/**", "contracts/**", "docs/DBT_LINEAGE.md")),
    Rule(
        "analyst",
        (
            "src/chess_analytics/analyst/**",
            "evals/**",
            "reports/live-eval-receipt-*",
            "tests/fixtures/live_eval_100.pgn",
            "tests/fixtures/live_eval_100_expected.json",
            "docs/METRICS.md",
        ),
    ),
)

# These paths select every step. They are not a narrow category.
FORCE_ALL_PATTERNS = (
    ".github/**",
    "pyproject.toml",
    "uv.lock",
    "scripts/ci_offline_*.py",
    "tests/test_ci_offline_changes.py",
)

# Tracked paths that intentionally match no narrow category. At runtime they
# select every step. The audit requires new tracked paths to be listed here
# or matched by a rule, so a forgotten directory cannot hide.
FAIL_OPEN_PATHS = (
    "reports/",
    ".gitignore",
    ".python-version",
    ".pre-commit-config.yaml",
    ".env.example",
    "doppler.yaml",
)

STEPS = (
    Step(
        "offline",
        "checkout",
        "always",
        uses="actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
    ),
    Step("offline", "audit_map", "always", exact="python3 scripts/ci_offline_changes.py --audit"),
    Step(
        "offline",
        "record_selection",
        "always",
        exact="python3 scripts/ci_offline_install.py --validate-only",
        details=(
            "env:\n  CHANGES_RESULT: ${{ needs.changes.result }}\n  SELECTION: "
            "${{ toJSON(needs.changes.outputs) }}"
        ),
    ),
    Step(
        "offline",
        "setup_uv",
        "support",
        uses="astral-sh/setup-uv@68559e99cc807c1eb7e9238fd43a15bba460eec2",
        requires=("record_selection",),
        details='with:\n  version: "0.12.18"\n  enable-cache: true\n  cache-suffix: offline',
    ),
    Step(
        "offline",
        "setup_node",
        "support",
        uses="actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1",
        requires=("record_selection",),
        details='with:\n  node-version: "24"',
    ),
    Step(
        "offline",
        "biome",
        "check",
        categories=("site",),
        exact="npx --yes @biomejs/biome@2.5.15 check",
        requires=("setup_node", "record_selection"),
    ),
    Step(
        "offline",
        "node_test",
        "check",
        categories=("site", "dashboard"),
        exact=(
            "node --test --test-isolation=none tests/js/game_import.test.mjs "
            "tests/js/dashboard.test.mjs"
        ),
        requires=("record_selection", "setup_node"),
    ),
    Step(
        "offline",
        "node_check_import",
        "check",
        categories=("site",),
        exact="node scripts/check_game_import.mjs",
        requires=("record_selection", "setup_node"),
    ),
    Step(
        "offline",
        "node_parity_authored",
        "check",
        categories=("site",),
        exact="node tests/js/import_parity.mjs tests/fixtures/imports/authored-games.pgn",
        requires=("record_selection", "setup_node"),
    ),
    Step(
        "offline",
        "node_parity_zero",
        "check",
        categories=("site",),
        exact="node tests/js/import_parity.mjs tests/fixtures/imports/zero-castling.pgn",
        requires=("record_selection", "setup_node"),
    ),
    Step(
        "offline",
        "sync",
        "support",
        exact="python3 scripts/ci_offline_install.py",
        requires=("setup_uv", "record_selection"),
        details=(
            "env:\n  CHANGES_RESULT: ${{ needs.changes.result }}\n  SELECTION: "
            "${{ toJSON(needs.changes.outputs) }}"
        ),
    ),
    Step(
        "offline",
        "ruff",
        "check",
        categories=("python", "hosted", "lint"),
        exact="uv run --locked --offline --no-editable --no-sync ruff check .",
        requires=("sync", "record_selection", "setup_uv"),
    ),
    Step(
        "offline",
        "ruff_format",
        "check",
        categories=("python", "hosted", "lint"),
        exact="uv run --locked --offline --no-editable --no-sync ruff format --check .",
        requires=("sync", "record_selection", "setup_uv"),
    ),
    Step(
        "offline",
        "basedpyright",
        "check",
        categories=("python", "hosted"),
        exact="uv run --locked --offline --no-editable --no-sync basedpyright",
        requires=("sync", "record_selection", "setup_uv"),
    ),
    Step(
        "offline",
        "pytest_extract",
        "check",
        categories=("hosted",),
        exact=(
            "uv run --locked --offline --no-editable --no-sync pytest -q "
            "tests/test_public_extract.py"
        ),
        requires=("sync", "record_selection", "setup_uv"),
    ),
    Step(
        "offline",
        "pytest_dashboard",
        "check",
        categories=("dashboard",),
        exact=(
            "uv run --locked --offline --no-editable --no-sync pytest -q "
            "tests/test_dashboard_cube.py tests/test_dashboard_export.py"
        ),
        requires=("setup_node", "sync", "record_selection", "setup_uv"),
    ),
    Step(
        "offline",
        "pytest_game_import",
        "check",
        categories=("site",),
        exact=(
            "uv run --locked --offline --no-editable --no-sync pytest -q tests/test_game_import.py"
        ),
        requires=("setup_node", "sync", "record_selection", "setup_uv"),
    ),
    Step(
        "offline",
        "pytest_mcp",
        "check",
        categories=("python",),
        exact=(
            "uv run --locked --offline --no-editable --no-sync pytest -q tests/test_mcp_protocol.py"
        ),
        extras=("mcp",),
        requires=("sync", "record_selection", "setup_uv"),
    ),
    Step(
        "offline",
        "pytest_ml",
        "check",
        categories=("python",),
        exact=(
            "uv run --locked --offline --no-editable --no-sync pytest -q "
            "tests/test_mistake_classifier.py"
        ),
        extras=("ml",),
        requires=("sync", "record_selection", "setup_uv"),
    ),
    Step(
        "offline",
        "demo",
        "check",
        categories=("python", "analyst", "dbt"),
        exact="uv run --locked --offline --no-editable --no-sync chesslab demo",
        requires=("sync", "record_selection", "setup_uv"),
    ),
    Step(
        "offline",
        "pytest_dbt",
        "check",
        categories=("python", "analyst", "dbt"),
        exact=(
            "CHESSLAB_REQUIRE_DBT=1 uv run --locked --offline --no-editable "
            "--no-sync pytest -m dbt -q -n 4 --durations=15"
        ),
        extras=("dbt",),
        requires=("setup_node", "sync", "record_selection", "setup_uv"),
    ),
    Step(
        "offline",
        "transform",
        "check",
        categories=("python", "analyst", "dbt"),
        exact=(
            "uv run --locked --offline --no-editable --no-sync python -m "
            "chess_analytics.marts transform --dataset tiny"
        ),
        extras=("dbt",),
        requires=("sync", "record_selection", "setup_uv"),
    ),
    Step(
        "offline",
        "semantic",
        "check",
        categories=("python", "analyst", "dbt"),
        exact=(
            'set -euo pipefail\nmart="$(uv run --locked --offline '
            "--no-editable --no-sync python -c 'import json; "
            'print(json.load(open("data/tiny-mart-current.json"))["mart_id"])'
            '\')"\nwarehouse="$PWD/data/marts/published/${mart}/warehouse.duckd'
            'b"\nmanifest="$PWD/data/marts/published/${mart}/semantic_manifest'
            '.json"\ncp "$warehouse" "$RUNNER_TEMP/warehouse.duckdb"\nexport '
            'CHESSLAB_DBT_PATH="$RUNNER_TEMP/warehouse.duckdb"\nexport '
            'DBT_PROFILES_DIR="$PWD/dbt"\nexport '
            'DBT_PROJECT_DIR="$PWD/dbt"\nexport DBT_TARGET=local\nexport '
            "DBT_SEND_ANONYMOUS_USAGE_STATS=false\nexport "
            'DO_NOT_TRACK=1\nexport DBT_LOG_PATH="$RUNNER_TEMP/dbt-logs"\nuv '
            "run --locked --offline --no-editable --no-sync dbt parse "
            "--project-dir dbt --profiles-dir dbt --target-path "
            '"$RUNNER_TEMP/dbt-target" --no-use-colors\nuv run --locked '
            "--offline --no-editable --no-sync python -m "
            "chess_analytics.analyst.semantic validate-configs "
            '"$RUNNER_TEMP/dbt-target/semantic_manifest.json"\nuv run '
            "--locked --offline --no-editable --no-sync python -m "
            'chess_analytics.analyst.semantic smoke-draw-rate "$warehouse" '
            '"$manifest"\nuv run --locked --offline --no-editable --no-sync '
            "python scripts/render_dbt_dag.py --manifest "
            '"$RUNNER_TEMP/dbt-target/manifest.json" --output '
            "docs/DBT_LINEAGE.md --check"
        ),
        extras=("dbt",),
        requires=("transform", "sync", "record_selection", "setup_uv"),
    ),
    Step(
        "offline",
        "analyst_gate",
        "check",
        categories=("python", "analyst", "dbt"),
        exact=(
            "uv run --locked --offline --no-editable --no-sync python -m "
            "chess_analytics.analyst gate"
        ),
        extras=("dbt",),
        requires=("semantic", "sync", "record_selection", "setup_uv"),
    ),
    Step(
        "offline",
        "dbt_base_checkout",
        "support",
        uses="actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
        if_expr=(
            "${{ (needs.changes.result != 'success' || "
            "steps.record_selection.outputs.fallback != 'false' || "
            "needs.changes.outputs.dbt_base_checkout == 'true') && "
            "(github.event_name == 'pull_request' || (github.event.before != "
            "'0000000000000000000000000000000000000000' && "
            "github.event.before != '')) }}"
        ),
        requires=("record_selection",),
        details=(
            "with:\n  ref: ${{ github.event_name == 'pull_request' && "
            "github.event.pull_request.base.sha || github.event.before }}\n  "
            "path: base-checkout\n  fetch-depth: 1\n  sparse-checkout: dbt\n  "
            "persist-credentials: false"
        ),
    ),
    Step(
        "offline",
        "dbt_slim",
        "check",
        categories=("dbt",),
        exact=(
            "set -euo pipefail\nif [ ! -f base-checkout/dbt/dbt_project.yml "
            ']; then\n  echo "slim CI: no base dbt project; skipping state '
            'selection"\n  exit 0\nfi\nmart="$(uv run --locked --offline '
            "--no-editable --no-sync python -c 'import json; "
            'print(json.load(open("data/tiny-mart-current.json"))["mart_id"])'
            "')\"\n# The file stem is the DuckDB catalog. Published views "
            'qualify "warehouse".\nmkdir -p "$RUNNER_TEMP/slim"\ncp '
            '"$PWD/data/marts/published/${mart}/warehouse.duckdb" '
            '"$RUNNER_TEMP/slim/warehouse.duckdb"\nexport '
            'CHESSLAB_DBT_PATH="$RUNNER_TEMP/slim/warehouse.duckdb"\nexport '
            'DBT_PROFILES_DIR="$PWD/dbt"\nexport '
            "DBT_SEND_ANONYMOUS_USAGE_STATS=false\nexport "
            'DO_NOT_TRACK=1\nstate="${RUNNER_TEMP}/dbt-state"\nuv run --locked '
            "--offline --no-editable --no-sync dbt parse --project-dir "
            "base-checkout/dbt --profiles-dir base-checkout/dbt "
            '--target-path "${state}" --log-path '
            '"$RUNNER_TEMP/dbt-state-logs" --no-use-colors\necho "slim CI: '
            'state:modified+"\nuv run --locked --offline --no-editable '
            '--no-sync dbt ls --select "state:modified+" --state "${state}" '
            "--project-dir dbt --profiles-dir dbt --target-path "
            '"$RUNNER_TEMP/dbt-slim" --log-path "$RUNNER_TEMP/dbt-slim-logs" '
            "--no-use-colors\nuv run --locked --offline --no-editable "
            '--no-sync dbt build --select "state:modified+" --state '
            '"${state}" --project-dir dbt --profiles-dir dbt --target-path '
            '"$RUNNER_TEMP/dbt-slim" --log-path "$RUNNER_TEMP/dbt-slim-logs" '
            "--no-use-colors\n# dbt 1.12 build counts modified unit tests but "
            "does not run them when their model is unmodified.\nuv run "
            "--locked --offline --no-editable --no-sync dbt test --select "
            '"test_type:unit,state:modified" --state "${state}" '
            "--project-dir dbt --profiles-dir dbt --target-path "
            '"$RUNNER_TEMP/dbt-slim" --log-path "$RUNNER_TEMP/dbt-slim-logs" '
            "--no-use-colors"
        ),
        extras=("dbt",),
        requires=("dbt_base_checkout", "sync", "record_selection", "setup_uv"),
    ),
    Step(
        "offline-core",
        "core_checkout",
        "always",
        uses="actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
    ),
    Step(
        "offline-core",
        "core_selection",
        "always",
        exact="python3 scripts/ci_offline_install.py --validate-only",
        details=(
            "env:\n  CHANGES_RESULT: ${{ needs.changes.result }}\n  SELECTION: "
            "${{ toJSON(needs.changes.outputs) }}"
        ),
    ),
    Step(
        "offline-core",
        "core_setup_uv",
        "support",
        uses="astral-sh/setup-uv@68559e99cc807c1eb7e9238fd43a15bba460eec2",
        requires=("core_selection",),
        details='with:\n  version: "0.12.18"\n  enable-cache: true\n  cache-suffix: offline-core',
    ),
    Step(
        "offline-core",
        "core_setup_node",
        "support",
        uses="actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1",
        requires=("core_selection",),
        details='with:\n  node-version: "24"',
    ),
    Step(
        "offline-core",
        "core_sync",
        "support",
        exact="uv sync --locked --no-editable",
        requires=("core_setup_uv", "core_selection"),
    ),
    Step(
        "offline-core",
        "pytest",
        "check",
        categories=("python", "analyst", "dbt"),
        exact="uv run --locked --offline --no-editable --no-sync pytest -q -n 4 --durations=15",
        requires=("core_sync", "core_setup_node", "core_selection", "core_setup_uv"),
    ),
    Step(
        "portfolio",
        "portfolio_checkout",
        "always",
        uses="actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
    ),
    Step(
        "portfolio",
        "portfolio_record",
        "always",
        exact="python3 scripts/ci_offline_install.py --validate-only",
        details=(
            "env:\n  CHANGES_RESULT: ${{ needs.changes.result }}\n  SELECTION: "
            "${{ toJSON(needs.changes.outputs) }}"
        ),
    ),
    Step(
        "portfolio",
        "portfolio_setup_uv",
        "support",
        uses="astral-sh/setup-uv@68559e99cc807c1eb7e9238fd43a15bba460eec2",
        requires=("portfolio_record",),
        details='with:\n  version: "0.12.18"\n  enable-cache: true\n  cache-suffix: portfolio',
    ),
    Step(
        "portfolio",
        "portfolio_sync",
        "support",
        exact="uv sync --locked --no-editable --extra dashboard",
        requires=("portfolio_record", "portfolio_setup_uv"),
    ),
    Step(
        "portfolio",
        "pytest_portfolio",
        "check",
        categories=("python", "analyst", "dbt", "hosted"),
        exact=(
            "uv run --locked --offline --no-editable --no-sync --extra dashboard "
            "pytest -q tests/test_portfolio_integrity.py "
            "tests/test_portfolio_demo.py tests/test_hosted_dashboard.py"
        ),
        requires=("portfolio_sync", "portfolio_record", "portfolio_setup_uv"),
    ),
    Step(
        "portfolio",
        "demo_all",
        "check",
        categories=("python", "analyst", "dbt", "hosted"),
        exact=(
            "uv run --locked --offline --no-editable --no-sync --extra dashboard "
            "chesslab demo --scope all"
        ),
        requires=("pytest_portfolio", "portfolio_record", "portfolio_setup_uv", "portfolio_sync"),
    ),
)
CHECKS = tuple(step for step in STEPS if step.kind == "check")
SUPPORT = tuple(step for step in STEPS if step.kind == "support")
ALWAYS_STEPS = tuple(step for step in STEPS if step.kind == "always")
ORDER = tuple((step.job, earlier, step.step_id) for step in STEPS for earlier in step.requires)
SUPPRESS_WHEN = {
    "pytest_dashboard": "pytest",
    "pytest_extract": "pytest",
    "pytest_game_import": "pytest",
}
CATEGORIES_WITHOUT_CHECKS = frozenset({"docs"})


def github_output_names() -> list[str]:
    return ["run_all", "categories", *(step.step_id for step in (*CHECKS, *SUPPORT))]


def selection_flags(run_all: bool, categories: set[str]) -> dict[str, bool]:
    flags = {step.step_id: run_all or bool(set(step.categories) & categories) for step in CHECKS}
    for narrow, broad in SUPPRESS_WHEN.items():
        if flags[broad]:
            flags[narrow] = False
    flags.update({step.step_id: False for step in SUPPORT})
    catalog = {step.step_id: step for step in STEPS}
    pending = [step for step in CHECKS if flags[step.step_id]]
    while pending:
        for required in pending.pop().requires:
            if required in flags and not flags[required]:
                flags[required] = True
                pending.append(catalog[required])
    return flags
