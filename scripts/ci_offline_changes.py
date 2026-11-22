#!/usr/bin/env python3
"""Choose Offline integrity steps from a pull request diff.

The workflow jobs ``offline``, ``offline-core``, and ``portfolio`` always run.
This script only decides which of their steps run. A pull request is the only
selective event. Every other event, including push, merge_group,
workflow_dispatch, and schedule, selects every step.

Fail safe: an empty diff, a path that matches no category, a change to the
workflow, the lockfile, this script, or its test, and any detection error all
select every step. ``pytest`` is the ``offline-core`` job. It covers the
narrower pytest steps, so those stay off when the full file set already runs.
That step shells out to Node, so ``offline-core`` sets up Node with it.
The dbt pytest step selects only tests marked ``dbt``. The existing Node 24
setup selection in ``offline`` stays unchanged.

The categories are docs, site, hosted, python, dbt, and analyst. ``docs``
selects no extra step. Run ``python3 scripts/ci_offline_changes.py --audit``
after adding a path or a workflow step.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

from ci_offline_catalog import (
    _CHECKOUT,
    ALWAYS_STEPS,
    CATEGORIES_WITHOUT_CHECKS,
    CHECKS,
    FAIL_OPEN_PATHS,
    FORCE_ALL_PATTERNS,
    MAPPED_JOBS,
    ORDER,
    RULES,
    SUPPORT,
    Step,
    default_if,
    github_output_names,
    selection_flags,
)
from ci_offline_generate import check_generated

SELECTIVE_EVENTS = frozenset({"pull_request"})
FULL_EVENTS = frozenset({"push", "merge_group", "workflow_dispatch", "schedule"})

_PATTERN_CACHE: dict[str, re.Pattern[str]] = {}


def _compile(pattern: str) -> re.Pattern[str]:
    cached = _PATTERN_CACHE.get(pattern)
    if cached is not None:
        return cached
    pieces: list[str] = []
    index = 0
    while index < len(pattern):
        if pattern.startswith("**", index):
            pieces.append(".*")
            index += 2
        elif pattern[index] == "*":
            pieces.append("[^/]*")
            index += 1
        else:
            pieces.append(re.escape(pattern[index]))
            index += 1
    compiled = re.compile("^" + "".join(pieces) + "$")
    _PATTERN_CACHE[pattern] = compiled
    return compiled


def _matches(path: str, patterns: tuple[str, ...]) -> bool:
    return any(_compile(pattern).match(path) for pattern in patterns)


def categories_for(path: str) -> set[str]:
    found: set[str] = set()
    for rule in RULES:
        if rule.excludes and _matches(path, rule.excludes):
            continue
        if _matches(path, rule.patterns):
            found.add(rule.category)
    return found


def is_force_all(path: str) -> bool:
    return _matches(path, FORCE_ALL_PATTERNS)


def is_fail_open(path: str) -> bool:
    for entry in FAIL_OPEN_PATHS:
        if entry.endswith("/"):
            if path.startswith(entry):
                return True
        elif path == entry:
            return True
    return False


def _normalize(path: str) -> str:
    text = path.strip().replace("\\", "/")
    if text.startswith("./"):
        text = text[2:]
    if text.startswith("/") or not text or ".." in text.split("/"):
        raise ValueError(f"unusable path: {path}")
    return text


def _unquote(token: str) -> str:
    if len(token) >= 2 and token[0] == '"' and token[-1] == '"':
        raise ValueError(f"quoted diff path: {token}")
    return token


def paths_from_name_status(text: str) -> list[str]:
    """Return every path in a ``git diff --name-status`` listing."""
    paths: list[str] = []
    for raw in text.splitlines():
        if not raw.strip():
            continue
        parts = [_unquote(part) for part in raw.split("\t")]
        status = parts[0]
        if status.startswith(("R", "C")):
            if len(parts) != 3:
                raise ValueError(f"bad rename line: {raw}")
            paths.extend((_normalize(parts[1]), _normalize(parts[2])))
        elif len(parts) == 2:
            paths.append(_normalize(parts[1]))
        elif len(parts) == 1:
            paths.append(_normalize(parts[0]))
        else:
            raise ValueError(f"bad diff line: {raw}")
    return paths


def _as_outputs(run_all: bool, categories: set[str], flags: dict[str, bool]) -> dict[str, str]:
    values = {
        "run_all": "true" if run_all else "false",
        "categories": "all" if run_all else ",".join(sorted(categories)),
    }
    values.update({key: "true" if enabled else "false" for key, enabled in flags.items()})
    return values


def outputs_for(event: str, paths: list[str] | None = None) -> dict[str, str]:
    """Return GitHub output values for one event and an optional path list.

    ``paths is None`` or an empty list on a pull request means the diff is
    missing. Both raise so callers fail open onto the full suite.
    """
    if event not in SELECTIVE_EVENTS:
        flags = selection_flags(True, set())
        return _as_outputs(True, set(), flags)
    if not paths:
        raise ValueError("pull request diff is missing")
    categories: set[str] = set()
    run_all = False
    for path in paths:
        normalized = _normalize(path)
        matched = categories_for(normalized)
        if is_force_all(normalized) or not matched:
            run_all = True
        categories |= matched
    return _as_outputs(run_all, categories, selection_flags(run_all, categories))


def emit_outputs(event: str, paths: list[str] | None) -> dict[str, str]:
    """Never raise. A detection error selects every step."""
    try:
        return outputs_for(event, paths)
    except Exception as exc:
        print(f"change detection failed ({exc}); running the full suite", file=sys.stderr)
        return outputs_for("full", None)


def _blank_step(line: str) -> dict[str, str]:
    return {"id": "", "if": "", "run": "", "uses": "", "blob": line + "\n"}


def _assign_run(step: dict[str, str], value: str) -> bool:
    if value in {"|", ">", "|-", ">-"}:
        return True
    step["run"] = value
    return False


def _assign_field(step: dict[str, str], stripped: str) -> bool | None:
    """Store one step field. None means the line is not a field."""
    if stripped.startswith("id:"):
        step["id"] = stripped.split(":", 1)[1].strip()
    elif stripped.startswith("if:"):
        step["if"] = stripped.split(":", 1)[1].strip()
    elif stripped.startswith("uses:"):
        step["uses"] = stripped.split(":", 1)[1].strip()
    elif stripped.startswith("run:"):
        return _assign_run(step, stripped.split(":", 1)[1].strip())
    else:
        return None
    return False


def _parse_workflow(text: str) -> dict[str, dict[str, object]]:
    jobs: dict[str, dict[str, object]] = {}
    current: dict[str, object] | None = None
    in_jobs = False
    in_steps = False
    in_outputs = False
    step: dict[str, str] | None = None
    collecting_run = False
    for line in text.splitlines():
        if line == "jobs:":
            in_jobs = True
            continue
        if not in_jobs:
            continue
        job_match = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", line)
        if job_match and not line.startswith("   "):
            current = {"steps": [], "outputs": [], "job_name": ""}
            jobs[job_match.group(1)] = current
            in_steps = False
            in_outputs = False
            step = None
            collecting_run = False
            continue
        if current is None:
            continue
        if line.startswith("    name:") and not in_steps:
            current["job_name"] = line.split(":", 1)[1].strip()
        if line.startswith("    outputs:"):
            in_outputs = True
            in_steps = False
            continue
        if in_outputs:
            output_match = re.match(r"^      ([A-Za-z0-9_]+):\s*(.*)$", line)
            if output_match:
                outputs = current["outputs"]
                assert isinstance(outputs, list)
                outputs.append((output_match.group(1), output_match.group(2).strip()))
                continue
            if line.startswith("    ") and not line.startswith("      "):
                in_outputs = False
        if line.startswith("    steps:"):
            in_steps = True
            in_outputs = False
            collecting_run = False
            continue
        if not in_steps:
            continue
        if line.startswith("      - "):
            step = _blank_step(line)
            steps = current["steps"]
            assert isinstance(steps, list)
            steps.append(step)
            assigned = _assign_field(step, line.strip()[2:].strip())
            collecting_run = bool(assigned)
            continue
        if step is None:
            continue
        step["blob"] += line + "\n"
        if collecting_run and line.startswith("          "):
            step["run"] += line.strip() + "\n"
            continue
        assigned = _assign_field(step, line.strip())
        collecting_run = False if assigned is None else assigned
    return jobs


def _step_problems(spec: Step, parsed: dict[str, str]) -> list[str]:
    problems: list[str] = []
    label = f"{spec.job}.{spec.step_id}"
    if spec.kind == "always":
        if parsed["if"]:
            problems.append(f"{label} must always run")
    else:
        expected_if = spec.if_expr or default_if(spec.step_id, spec.job)
        if parsed["if"] != expected_if:
            problems.append(f"{label} if-expression drifted")
    if spec.exact and parsed["run"].strip() != "\n".join(
        line.strip() for line in spec.exact.splitlines()
    ):
        problems.append(f"{label} command drifted")
    if (
        spec.uses
        and not spec.uses.startswith("astral-sh/setup-uv@")
        and spec.uses not in parsed["uses"]
    ):
        problems.append(f"{label} is not pinned to {spec.uses}")
    return problems


def _setup_uv_pin_problems(jobs: dict[str, dict[str, object]]) -> list[str]:
    problems: list[str] = []
    pins: dict[str, str] = {}
    for job, step_id in (
        ("offline", "setup_uv"),
        ("portfolio", "portfolio_setup_uv"),
        ("offline-core", "core_setup_uv"),
    ):
        steps = jobs[job]["steps"]
        assert isinstance(steps, list)
        for parsed in steps:
            if parsed["id"] != step_id:
                continue
            label = f"{job}.{step_id}"
            uses = re.split(r"\s+#", parsed["uses"], maxsplit=1)[0].strip()
            if len(uses) >= 2 and uses[0] == uses[-1] and uses[0] in "\"'":
                uses = uses[1:-1]
            match = re.fullmatch(r"astral-sh/setup-uv@([0-9a-f]{40})", uses)
            if match is None:
                problems.append(f"{label} must pin astral-sh/setup-uv to a full 40-hex SHA")
            else:
                pins[label] = match.group(1)
    if len(set(pins.values())) > 1:
        problems.append(f"setup-uv SHAs differ across steps: {', '.join(pins)}")
    return problems


def _order_problems(jobs: dict[str, dict[str, object]]) -> list[str]:
    problems: list[str] = []
    for job, earlier, later in ORDER:
        steps = jobs[job]["steps"]
        assert isinstance(steps, list)
        positions = {item["id"]: index for index, item in enumerate(steps)}
        if earlier not in positions or later not in positions:
            continue
        if positions[earlier] > positions[later]:
            problems.append(f"{job}: {earlier} must run before {later}")
    return problems


def _output_problems(jobs: dict[str, dict[str, object]]) -> list[str]:
    changes = jobs.get("changes")
    if changes is None:
        return ["changes job is missing"]
    outputs = changes["outputs"]
    assert isinstance(outputs, list)
    found = [name for name, _expr in outputs]
    expected = github_output_names()
    problems: list[str] = []
    if found != expected:
        problems.append("changes job outputs drifted from the step catalog")
    for name, expr in outputs:
        wanted = "${{ steps.filter.outputs." + name + " }}"
        if expr != wanted:
            problems.append(f"output {name} must read steps.filter.outputs.{name}")
    return problems


def _tracked_problems(tracked: list[str]) -> list[str]:
    problems: list[str] = []
    rule_categories = {rule.category for rule in RULES}
    step_categories: set[str] = set()
    for step in CHECKS:
        step_categories.update(step.categories)
    if rule_categories - step_categories != CATEGORIES_WITHOUT_CHECKS:
        problems.append("a path category is missing its steps, or docs gained a step")
    unknown_step_categories = step_categories - rule_categories
    if unknown_step_categories:
        problems.append(f"steps name unknown categories: {sorted(unknown_step_categories)}")
    for path in tracked:
        if categories_for(path) or is_force_all(path) or is_fail_open(path):
            continue
        problems.append(f"unmapped tracked path: {path}")
    return problems


def _trigger_problems(workflow_text: str) -> list[str]:
    problems: list[str] = []
    on_block = workflow_text.split("\njobs:", 1)[0]
    if re.search(r"(?m)^[ ]+paths(-ignore)?:", on_block):
        problems.append("workflow-level path filters leave required checks pending")
    for event in ("pull_request:", "workflow_dispatch:", "merge_group:"):
        if event not in on_block:
            problems.append(f"trigger {event[:-1]} is missing")
    if "branches: [main]" not in on_block:
        problems.append("push to main is missing")
    return problems


def _job_header(workflow_text: str, job: str) -> str:
    body = re.search(rf"\n  {job}:\n(?P<body>(?:    .*\n)*)", workflow_text)
    return body.group("body") if body else ""


def _job_level_if(workflow_text: str, job: str) -> str:
    """Return the job's own ``if``, ignoring step conditions."""
    for line in _job_header(workflow_text, job).splitlines():
        if line.startswith("      "):
            continue
        stripped = line.strip()
        if stripped.startswith("steps:"):
            break
        if stripped.startswith("if:"):
            return stripped.split(":", 1)[1].strip()
    return ""


def _required_job_problems(workflow_text: str, jobs: dict[str, dict[str, object]]) -> list[str]:
    problems: list[str] = []
    for job in ("offline", "portfolio"):
        if jobs[job]["job_name"]:
            problems.append(f"do not rename required job {job}")
        header = _job_header(workflow_text, job)
        if "needs: changes" not in header or "!cancelled()" not in header:
            problems.append(f"{job} must need changes and still run when detection fails")
    return problems


def _offline_core_problems(workflow_text: str, jobs: dict[str, dict[str, object]]) -> list[str]:
    """Keep the new check name stable and successful when its pytest step is skipped."""
    job = jobs.get("offline-core")
    if job is None:
        return ["job offline-core is missing"]
    problems: list[str] = []
    if job["job_name"]:
        problems.append("offline-core must not set a display name")
    header = _job_header(workflow_text, "offline-core")
    if "needs: changes" not in header:
        problems.append("offline-core must need changes and still run when detection fails")
    if _job_level_if(workflow_text, "offline-core") != "${{ !cancelled() }}":
        problems.append("offline-core if must be ${{ !cancelled() }}")
    return problems


def _catalog_problems(jobs: dict[str, dict[str, object]]) -> list[str]:
    problems: list[str] = []
    catalog = {step.step_id: step for step in (*ALWAYS_STEPS, *CHECKS, *SUPPORT)}
    seen: set[str] = set()
    for job_name in MAPPED_JOBS:
        steps = jobs[job_name]["steps"]
        assert isinstance(steps, list)
        for parsed in steps:
            step_id = parsed["id"]
            if not step_id:
                problems.append(f"{job_name} has a step without an id")
                continue
            seen.add(step_id)
            spec = catalog.get(step_id)
            if spec is None or spec.job != job_name:
                problems.append(f"unmapped step {job_name}.{step_id}")
                continue
            problems.extend(_step_problems(spec, parsed))
    for step_id, spec in catalog.items():
        if step_id not in seen:
            problems.append(f"catalog step {spec.job}.{step_id} is missing from the workflow")
    return problems


def _changes_job_problems(jobs: dict[str, dict[str, object]]) -> list[str]:
    changes_steps = jobs["changes"]["steps"]
    assert isinstance(changes_steps, list)
    change_ids = [item["id"] for item in changes_steps]
    if change_ids != ["changes_checkout", "filter"]:
        return ["changes job must checkout and then classify"]
    problems: list[str] = []
    checkout_blob = changes_steps[0]["blob"]
    full_history = "fetch-depth: 0" in checkout_blob
    no_credentials = "persist-credentials: false" in checkout_blob
    if not full_history or not no_credentials:
        problems.append("changes checkout must fetch history without persisted credentials")
    if _CHECKOUT not in changes_steps[0]["uses"]:
        problems.append("changes checkout pin drifted")
    filter_blob = changes_steps[1]["blob"]
    if "scripts/ci_offline_changes.py" not in filter_blob:
        problems.append("changes job must run the classifier")
    if changes_steps[1]["if"]:
        problems.append("the classifier step must always run")
    return problems


def audit_text(workflow_text: str, tracked: list[str]) -> list[str]:
    """Return mapping problems. An empty list means the workflow matches the catalog."""
    problems = [*_trigger_problems(workflow_text), *check_generated(workflow_text)]
    try:
        jobs = _parse_workflow(workflow_text)
    except ValueError as exc:
        return [*problems, f"workflow parse failed: {exc}"]
    for job in ("changes", *MAPPED_JOBS):
        if job not in jobs:
            problems.append(f"job {job} is missing")
    if any(item.endswith("is missing") for item in problems):
        return problems
    problems.extend(_required_job_problems(workflow_text, jobs))
    problems.extend(_offline_core_problems(workflow_text, jobs))
    problems.extend(_output_problems(jobs))
    problems.extend(_catalog_problems(jobs))
    problems.extend(_setup_uv_pin_problems(jobs))
    problems.extend(_changes_job_problems(jobs))
    problems.extend(_order_problems(jobs))
    problems.extend(_tracked_problems(tracked))
    return problems


def tracked_files(root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def audit_repository(root: Path) -> list[str]:
    workflow = root / ".github" / "workflows" / "offline.yml"
    text = workflow.read_text(encoding="utf-8")
    return audit_text(text, tracked_files(root))


def _write_outputs(path: Path | None, values: dict[str, str]) -> None:
    payload = "".join(f"{key}={value}\n" for key, value in values.items())
    if path is None:
        sys.stdout.write(payload)
        return
    with path.open("a", encoding="utf-8") as handle:
        handle.write(payload)


def _print_decision(values: dict[str, str]) -> None:
    enabled = [key for key, value in values.items() if value == "true"]
    categories = values["categories"] or "(none)"
    print(f"change detection: run_all={values['run_all']} categories={categories}")
    for name in enabled:
        print(f"run {name}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event", default="pull_request")
    parser.add_argument("--name-status", type=Path)
    parser.add_argument("--github-output", type=Path)
    parser.add_argument("--audit", action="store_true")
    parser.add_argument("--root", type=Path)
    parser.add_argument("--explain", nargs="*", metavar="PATH")
    args = parser.parse_args(argv)
    root = args.root or Path(__file__).resolve().parents[1]
    if args.audit:
        problems = audit_repository(root)
        if problems:
            for problem in problems:
                print(problem, file=sys.stderr)
            return 1
        print("offline step map ok")
        return 0
    if args.explain is not None:
        values = emit_outputs(args.event, list(args.explain))
        _print_decision(values)
        return 0
    try:
        paths = _paths_for_event(args.event, args.name_status)
        values = emit_outputs(args.event, paths)
    except Exception as exc:
        print(f"change detection failed ({exc}); running the full suite", file=sys.stderr)
        values = outputs_for("full", None)
    try:
        _write_outputs(args.github_output, values)
    except OSError as exc:
        print(f"could not write GitHub outputs: {exc}", file=sys.stderr)
        return 1
    _print_decision(values)
    return 0


def _paths_for_event(event: str, name_status: Path | None) -> list[str] | None:
    if event not in SELECTIVE_EVENTS:
        return None
    if name_status is None:
        return None
    return paths_from_name_status(name_status.read_text(encoding="utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
