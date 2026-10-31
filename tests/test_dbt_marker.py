"""Collect the whole suite and require dbt selection for visible unexplained skips.

No fixtures or test bodies run in the child collection. Inspect test helpers and
the resolved fixture closure too. Skip/importorskip and dbt-executable checks
cover only tests/, including helpers reached from unmarked items' fixture
closures. Silent dual-path staging in src/ (_maybe_mart, with_name("dbt")) is
invisible; governed-path preservation relies on the marked baseline byte-match,
path-changed / poisoned-mart cases, and independent-oracle path check.
"""

import ast
import inspect
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# These conditions are independent of dbt and remain optional in both jobs.
OPTIONAL_EXTRAS = {"mcp", "markdown", "streamlit", "altair"}
JUSTIFIED_REASONS = {
    # Ignored real datasets and historical workspaces are absent in CI.
    "optional real analytical snapshot not in clean checkout",
    "optional April data snapshot not in clean checkout",
    "optional March data snapshot not in clean checkout",
    "optional February data snapshot not in clean checkout",
    "optional January data snapshot not in clean checkout",
    "optional December snapshot and proposed config not in clean checkout",
    "December workspace predates the consolidated campaign command",
    "optional retained December dataset absent from clean checkout",
    "opening-positions blob is not in this checkout",
    # Optional local runtimes/configuration; Node has its own mandatory CI step.
    "git is not installed",
    "Browser parity requires Node; CI explicitly runs Node tests",
    "Node unit suite is a separate mandatory hosted CI step",
    "engine config is not present",
    "configured engine binary is not available",
    "torch and maia3 are installed",
    "config/maia.json is absent",
}


def _selection_problem(call, function=None):
    if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Attribute):
        return None
    kind = call.func.attr
    if (
        kind == "with_name"
        and call.args
        and isinstance(call.args[0], ast.Constant)
        and call.args[0].value == "dbt"
    ):
        return ast.unparse(call)
    if kind not in {"skip", "skipif", "importorskip"}:
        return None
    if (
        kind == "importorskip"
        and call.args
        and isinstance(call.args[0], ast.Constant)
        and call.args[0].value in OPTIONAL_EXTRAS
    ):
        return None
    reason = next((kw.value for kw in call.keywords if kw.arg == "reason"), None)
    if reason is None and kind == "skip" and call.args:
        reason = call.args[0]
    if isinstance(reason, ast.Constant) and reason.value in JUSTIFIED_REASONS:
        return None
    # This one reason comes from the optional real Maia checkpoint scorer.
    if function == ("test_maia_trust.py", "test_maia_v1_runs_on_the_real_project_when_configured"):
        return None
    return ast.unparse(call)


def _function_problems(function, seen):
    function = inspect.unwrap(function)
    if not inspect.isfunction(function) or function in seen:
        return []
    seen.add(function)
    path = Path(inspect.getfile(function))
    if not path.is_relative_to(ROOT / "tests"):
        return []
    tree = ast.parse(textwrap.dedent(inspect.getsource(function)))
    problems = []
    for node in ast.walk(tree):
        problem = _selection_problem(node, (path.name, function.__name__))
        if problem:
            problems.append(f"{path.name}:{function.__name__}: {problem}")
        if isinstance(node, ast.Name):
            helper = function.__globals__.get(node.id)
            if inspect.isfunction(helper):
                problems.extend(_function_problems(helper, seen))
    return problems


def _module_level_selection_problems(source: str) -> list[str]:
    """Flag module-level skip/importorskip Calls; skip function/class bodies."""
    problems = []
    pending = list(ast.parse(source).body)
    while pending:
        node = pending.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in {"skip", "importorskip"}
        ):
            problem = _selection_problem(node)
            if problem:
                problems.append(problem)
        pending.extend(ast.iter_child_nodes(node))
    return problems


class _CoverageGuard:
    def pytest_collection_finish(self, session):
        problems = []
        for item in session.items:
            if item.get_closest_marker("dbt") is not None:
                continue
            skips = _function_problems(item.obj, set())
            # pytest is pinned; name2fixturedefs includes transitive/autouse fixtures.
            for definitions in item._fixtureinfo.name2fixturedefs.values():
                if definitions:
                    skips.extend(_function_problems(definitions[-1].func, set()))
            for mark in item.iter_markers():
                if (
                    mark.name in {"skip", "skipif"}
                    and mark.kwargs.get("reason") not in JUSTIFIED_REASONS
                ):
                    skips.append(str(mark))
            if skips:
                problems.append(f"{item.nodeid} needs @pytest.mark.dbt: {skips}")
        # Module-level importorskip can prevent items from being collected at all.
        for path in (ROOT / "tests").rglob("test_*.py"):
            for problem in _module_level_selection_problems(path.read_text()):
                problems.append(f"{path.name}: unexplained collection skip: {problem}")
        if problems:
            raise pytest.UsageError("\n".join(problems))


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ('dbt = pytest.importorskip("dbt")', ["pytest.importorskip('dbt')"]),
        (
            'if True:\n    pytest.skip("no dbt", allow_module_level=True)',
            ["pytest.skip('no dbt', allow_module_level=True)"],
        ),
        ('pytest.importorskip("dbt")', ["pytest.importorskip('dbt')"]),
        ('pytest.importorskip("mcp")', []),
        ('def helper():\n    pytest.importorskip("dbt")', []),
        ('async def helper():\n    pytest.importorskip("dbt")', []),
        ('class Helper:\n    pytest.importorskip("dbt")', []),
    ],
)
def test_module_level_selection_problems(source, expected):
    assert _module_level_selection_problems(source) == expected


def test_no_dbt_skips_are_covered_by_the_dbt_selection():
    env = {**os.environ, "PYTEST_ADDOPTS": ""}
    collected = subprocess.run(
        [sys.executable, __file__], cwd=ROOT, env=env, capture_output=True, text=True, timeout=60
    )
    assert collected.returncode == 0, collected.stdout + collected.stderr


if __name__ == "__main__":
    raise SystemExit(pytest.main(["--collect-only", "-q", "tests"], plugins=[_CoverageGuard()]))
