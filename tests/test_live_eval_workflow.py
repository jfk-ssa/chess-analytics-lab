"""Static checks for the manual live-eval workflow.

Parsing and the assertions stay offline. Each contract assertion is also
run against a mutated workflow so a weakened file fails that assertion.
"""

import importlib.util
import re
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/live-eval.yml"
_SPEC = importlib.util.spec_from_file_location(
    "live_eval_dispatch", ROOT / "scripts/live_eval_dispatch.py"
)
assert _SPEC is not None and _SPEC.loader is not None
dispatch = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(dispatch)

_SHA = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+@[0-9a-f]{40}$")
_SECRET = re.compile(r"secrets\.([A-Za-z0-9_]+)")
_GIT_WRITE = re.compile(r"\bgit\s+(?:commit|add|push)\b")
_STEP_ORDER = (
    "Show the pre-run checklist",
    "Refuse a stale recorded price check",
    "Refuse inputs outside the live-eval caps",
    "Stage the fixture and print the dry-run reservation",
    "Run the live eval",
    "Write the job summary",
    "Upload the receipt",
)


class WorkflowParseError(ValueError):
    """The workflow YAML subset this test parses."""


def parse_workflow(text: str) -> dict:
    lines = text.splitlines()
    value, index = _parse_map(lines, 0, 0)
    if index < len(lines) and _structural(lines, index) is not None:
        raise WorkflowParseError(f"trailing content at line {index + 1}")
    if not isinstance(value, dict):
        raise WorkflowParseError("workflow root is not a mapping")
    return value


def workflow_problems(text: str) -> list[str]:
    try:
        document = parse_workflow(text)
    except WorkflowParseError as exc:
        return [f"parse:{exc}"]
    problems: list[str] = []
    _check_trigger(document, problems)
    _check_schedule(document, problems)
    _check_permissions(document, problems)
    _check_concurrency(document, problems)
    job = _job(document, problems)
    if job is None:
        return _unique(problems)
    _check_environment(job, problems)
    _check_inputs(document, problems)
    _check_secret(text, job, problems)
    _check_pins(document, problems)
    _check_receipt(job, problems)
    _check_runner(text, job, problems)
    _check_order(job, problems)
    return _unique(problems)


def test_live_eval_workflow_matches_the_dispatch_contract():
    problems = workflow_problems(WORKFLOW.read_text(encoding="utf-8"))
    assert problems == []


def test_each_workflow_assertion_fails_when_mutated():
    text = WORKFLOW.read_text(encoding="utf-8")
    cases = {
        "trigger": text.replace(
            "on:\n",
            "on:\n  push:\n    branches:\n      - main\n",
            1,
        ),
        "schedule": text.replace(
            "on:\n",
            'on:\n  schedule:\n    - cron: "0 0 1 * *"\n',
            1,
        ),
        "environment": text.replace("environment: live-eval\n", "environment: production\n", 1),
        "permissions": text.replace("contents: read\n", "contents: write\n", 1),
        "permissions-extra": text.replace(
            "permissions:\n  contents: read\n",
            "permissions:\n  contents: read\n  actions: write\n",
            1,
        ),
        "concurrency": text.replace("cancel-in-progress: false\n", "cancel-in-progress: true\n", 1),
        "concurrency-missing": text.replace("  cancel-in-progress: false\n", "", 1),
        "secret": text.replace(
            "secrets.CHESSLAB_OPENAI_API_KEY",
            "secrets.OPENAI_API_KEY",
            1,
        ),
        "secret-second": text.replace(
            'LIVE_EVAL_MODEL: "${{ inputs.model }}"\n',
            'LIVE_EVAL_MODEL: "${{ inputs.model }}"\n'
            '      OPENAI_API_KEY: "${{ secrets.OPENAI_API_KEY }}"\n',
            1,
        ),
        "pin": text.replace(
            "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
            "actions/checkout@v7",
            1,
        ),
        "receipt-upload": text.replace(
            "actions/upload-artifact@",
            "actions/download-artifact@",
            1,
        ),
        "receipt-commit": text.replace(
            "--output work/live-eval-receipt.json\n",
            "--output work/live-eval-receipt.json\n"
            "          git add work/live-eval-receipt.json\n"
            "          git commit -m receipt\n",
            1,
        ),
        "retention": text.replace("retention-days: 90\n", "retention-days: 30\n", 1),
        "model-choice": text.replace(
            "          - gpt-6-sol\n",
            "          - gpt-6-sol\n          - gpt-6-astra\n",
            1,
        ),
        "cap-input": text.replace(
            "        type: string\n        required: true\n      acknowledge_personal_account:\n",
            '        type: string\n        required: true\n        default: "10"\n'
            "      acknowledge_personal_account:\n",
            1,
        ),
        "price-step": text.replace(
            "python scripts/live_eval_dispatch.py check-price\n",
            "python scripts/live_eval_dispatch.py check-price --today 2026-10-04\n",
            1,
        ),
    }
    expected = {
        "trigger": "trigger",
        "schedule": "schedule",
        "environment": "environment",
        "permissions": "permissions",
        "permissions-extra": "permissions",
        "concurrency": "concurrency",
        "concurrency-missing": "concurrency",
        "secret": "secret",
        "secret-second": "secret",
        "pin": "pin",
        "receipt-upload": "receipt-upload",
        "receipt-commit": "receipt-commit",
        "retention": "receipt-upload",
        "model-choice": "model-choice",
        "cap-input": "cap-input",
        "price-step": "price-step",
    }
    seen = []
    for name, mutated in cases.items():
        problems = workflow_problems(mutated)
        code = expected[name]
        assert code in problems, (name, problems)
        assert problems != [], name
        seen.append(code)
    assert {
        "trigger",
        "schedule",
        "environment",
        "permissions",
        "concurrency",
        "secret",
        "pin",
        "receipt-upload",
        "receipt-commit",
    } <= set(seen)


def test_existing_workflows_do_not_call_the_live_eval():
    for name in ("offline.yml", "pages.yml", "pr-title.yml"):
        text = (ROOT / ".github/workflows" / name).read_text(encoding="utf-8")
        assert "live-eval.yml" not in text
        assert "live_eval_dispatch" not in text


def test_price_window_is_fourteen_days_and_the_recorded_date_is_unchanged():
    assert dispatch.PRICE_CHECK_MAX_AGE_DAYS == 14
    assert "14 days" in WORKFLOW.read_text(encoding="utf-8")
    text = (ROOT / "src/chess_analytics/analyst/preflight.py").read_text(encoding="utf-8")
    assert dispatch.price_check_date(text) == date(2026, 10, 4)
    assert "2026-10-04" not in (ROOT / "src/chess_analytics/analyst/pricing.py").read_text(
        encoding="utf-8"
    )


def test_stale_price_check_refuses_unless_the_operator_overrides():
    checked = date(2026, 10, 4)
    dispatch.enforce_price_check(checked, date(2026, 10, 18), allow_stale=False)
    with pytest.raises(dispatch.DispatchError, match="15 days old"):
        dispatch.enforce_price_check(checked, date(2026, 10, 19), allow_stale=False)
    assert dispatch.enforce_price_check(checked, date(2026, 10, 19), allow_stale=True) == 15
    with pytest.raises(dispatch.DispatchError, match="future"):
        dispatch.enforce_price_check(checked, date(2026, 10, 3), allow_stale=True)


def test_caps_acknowledgement_and_repeats_match_the_five_repeat_ceilings():
    luna = dispatch.validate_dispatch("gpt-6-luna", "5", "0.50", "true")
    assert luna["cap_usd"] == dispatch.CAPS_USD["gpt-6-luna"]
    assert dispatch.validate_dispatch("gpt-6-sol", "1", "10", "true")["repeats"] == 1
    assert dispatch.validate_dispatch("gpt-6-sol", "20", "0.50", "true")["model"] == "gpt-6-sol"
    with pytest.raises(dispatch.DispatchError, match=r"0\.51"):
        dispatch.validate_dispatch("gpt-6-luna", "5", "0.51", "true")
    with pytest.raises(dispatch.DispatchError, match=r"10\.01"):
        dispatch.validate_dispatch("gpt-6-sol", "5", "10.01", "true")
    with pytest.raises(dispatch.DispatchError, match="positive decimal"):
        dispatch.validate_dispatch("gpt-6-luna", "5", "0", "true")
    with pytest.raises(dispatch.DispatchError, match="gpt-6-luna or gpt-6-sol"):
        dispatch.validate_dispatch("gpt-6-astra", "1", "1", "true")
    with pytest.raises(dispatch.DispatchError, match="must be true"):
        dispatch.validate_dispatch("gpt-6-luna", "5", "0.50", "false")
    with pytest.raises(dispatch.DispatchError, match="1 to 20"):
        dispatch.validate_dispatch("gpt-6-luna", "21", "0.50", "true")
    with pytest.raises(dispatch.DispatchError, match="1 to 20"):
        dispatch.validate_dispatch("gpt-6-luna", "5.0", "0.50", "true")


def test_check_inputs_cli_refuses_a_luna_cap_above_the_ceiling(monkeypatch, capsys):
    monkeypatch.setenv("LIVE_EVAL_MODEL", "gpt-6-luna")
    monkeypatch.setenv("LIVE_EVAL_REPEATS", "5")
    monkeypatch.setenv("LIVE_EVAL_MAX_RUN_USD", "0.51")
    monkeypatch.setenv("LIVE_EVAL_ACKNOWLEDGE", "true")
    assert dispatch.main(["check-inputs"]) == 1
    assert "0.50" in capsys.readouterr().err


def test_summary_shows_the_rate_wilson_repairs_and_an_incomplete_receipt(tmp_path, monkeypatch):
    receipt = {
        "complete": True,
        "hard_fail": False,
        "headline_pass_rate": 0.875,
        "headline_passed": 210,
        "known_gross_cost_usd": 0.012345,
        "model": "gpt-6-luna",
        "planned_requests": 240,
        "repair_counts": {"argument": 1, "extraction": 2, "semantic": 0},
        "repeats": 5,
        "stats": {"wilson": {"lower": 0.82, "successes": 210, "trials": 240, "upper": 0.91}},
        "unknown_cost_reservation_usd": 0,
    }
    text = dispatch.format_summary(receipt)
    assert "model: gpt-6-luna" in text
    assert "repeats: 5" in text
    assert "headline raw pass rate: 0.875000 (210/240)" in text
    assert "repair counts: argument 1, extraction 2, semantic 0" in text
    assert "Wilson interval: [0.820000, 0.910000] (210/240)" in text
    assert "hard_fail: false" in text
    assert "gross cost USD: 0.012345" in text
    assert "complete: true" in text
    assert "unknown cost reservation" not in text
    incomplete = dict(receipt)
    incomplete["complete"] = False
    incomplete["hard_fail"] = True
    incomplete["headline_pass_rate"] = None
    incomplete["stats"] = None
    incomplete["unknown_cost_reservation_usd"] = 0.25
    stopped = dispatch.format_summary(incomplete)
    assert "headline raw pass rate: unavailable; repair counts:" in stopped
    assert "Wilson interval: unavailable" in stopped
    assert "hard_fail: true" in stopped
    assert "complete: false" in stopped
    assert "unknown cost reservation USD: 0.250000" in stopped
    missing = tmp_path / "missing.json"
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    assert dispatch.main(["summarize", "--receipt", str(missing)]) == 0
    assert "No receipt was written." in summary.read_text(encoding="utf-8")


def test_checklist_names_the_model_id_the_effort_and_the_prices():
    text = dispatch.checklist_text()
    assert "gpt-6-sol" in text
    assert "gpt-6.1-sol" in text
    assert "reasoning.effort" in text
    assert "none" in text
    assert "prices" in text
    assert "does not probe" in text


def _check_trigger(document: dict, problems: list[str]) -> None:
    block = document.get("on")
    if not isinstance(block, dict) or set(block) != {"workflow_dispatch"}:
        problems.append("trigger")


def _check_schedule(document: dict, problems: list[str]) -> None:
    found: set[str] = set()
    _keys(document, found)
    if "schedule" in found or "cron" in found:
        problems.append("schedule")


def _check_permissions(document: dict, problems: list[str]) -> None:
    if document.get("permissions") != {"contents": "read"}:
        problems.append("permissions")
    found: set[str] = set()
    for key, value in document.items():
        if key == "permissions":
            continue
        _keys(value, found)
    if "permissions" in found:
        problems.append("permissions")


def _check_concurrency(document: dict, problems: list[str]) -> None:
    block = document.get("concurrency")
    group = None if not isinstance(block, dict) else block.get("group")
    cancel = None if not isinstance(block, dict) else block.get("cancel-in-progress")
    if group != "live-eval" or cancel is not False:
        problems.append("concurrency")


def _job(document: dict, problems: list[str]) -> dict | None:
    jobs = document.get("jobs")
    if not isinstance(jobs, dict) or set(jobs) != {"live-eval"}:
        problems.append("environment")
        return None
    job = jobs["live-eval"]
    if not isinstance(job, dict):
        problems.append("environment")
        return None
    return job


def _check_environment(job: dict, problems: list[str]) -> None:
    if job.get("environment") != "live-eval":
        problems.append("environment")


def _check_inputs(document: dict, problems: list[str]) -> None:
    inputs = document["on"]["workflow_dispatch"].get("inputs")
    if not isinstance(inputs, dict):
        problems.extend(["model-choice", "repeats", "cap-input", "acknowledge", "price-override"])
        return
    model = inputs.get("model")
    if not isinstance(model, dict) or model.get("options") != ["gpt-6-luna", "gpt-6-sol"]:
        problems.append("model-choice")
    repeats = inputs.get("repeats")
    if not isinstance(repeats, dict) or repeats.get("default") not in {5, "5"}:
        problems.append("repeats")
    cap = inputs.get("max_run_usd")
    if not isinstance(cap, dict) or cap.get("required") is not True or "default" in cap:
        problems.append("cap-input")
    acknowledge = inputs.get("acknowledge_personal_account")
    if (
        not isinstance(acknowledge, dict)
        or acknowledge.get("type") != "boolean"
        or acknowledge.get("required") is not True
    ):
        problems.append("acknowledge")
    stale = inputs.get("allow_stale_price_check")
    stale_ok = (
        isinstance(stale, dict) and stale.get("type") == "boolean" and stale.get("default") is False
    )
    if not stale_ok:
        problems.append("price-override")


def _check_secret(text: str, job: dict, problems: list[str]) -> None:
    if _SECRET.findall(text) != ["CHESSLAB_OPENAI_API_KEY"]:
        problems.append("secret")
    if "CHESSLAB_OPENAI_API_KEY" in (job.get("env") or {}):
        problems.append("secret")
    live = _step(job, "Run the live eval")
    expected = "${{ secrets.CHESSLAB_OPENAI_API_KEY }}"
    if live is None or (live.get("env") or {}).get("CHESSLAB_OPENAI_API_KEY") != expected:
        problems.append("secret")
    for step in job.get("steps") or []:
        if step is live:
            continue
        if "CHESSLAB_OPENAI_API_KEY" in (step.get("env") or {}):
            problems.append("secret")


def _check_pins(document: dict, problems: list[str]) -> None:
    found = _uses(document)
    if not found or any(_SHA.fullmatch(item) is None for item in found):
        problems.append("pin")


def _check_receipt(job: dict, problems: list[str]) -> None:
    steps = job.get("steps") or []
    uploads = [
        step for step in steps if str(step.get("uses", "")).startswith("actions/upload-artifact@")
    ]
    if len(uploads) != 1:
        problems.append("receipt-upload")
    else:
        payload = uploads[0].get("with") or {}
        if payload.get("path") != "work/live-eval-receipt.json":
            problems.append("receipt-upload")
        if payload.get("retention-days") != 90:
            problems.append("receipt-upload")
        if payload.get("if-no-files-found") != "error":
            problems.append("receipt-upload")
    runs = [step.get("run") for step in steps if isinstance(step.get("run"), str)]
    if any(_GIT_WRITE.search(run) for run in runs):
        problems.append("receipt-commit")


def _check_runner(text: str, job: dict, problems: list[str]) -> None:
    dry = _step(job, "Stage the fixture and print the dry-run reservation")
    live = _step(job, "Run the live eval")
    price = _step(job, "Refuse a stale recorded price check")
    dry_run = "" if dry is None else dry.get("run", "")
    live_run = "" if live is None else live.get("run", "")
    price_run = "" if price is None else price.get("run", "")
    if "--dry-run" not in dry_run or "--offline" not in dry_run or "--output" in dry_run:
        problems.append("runner")
    if "GITHUB_STEP_SUMMARY" not in dry_run:
        problems.append("runner")
    if "--dry-run" in live_run or "--offline" in live_run or "--env-file" in live_run:
        problems.append("runner")
    if "--output work/live-eval-receipt.json" not in live_run:
        problems.append("runner")
    if "check-price" not in price_run or "--today" in text:
        problems.append("price-step")
    summary = _step(job, "Write the job summary")
    summary_run = "" if summary is None else summary.get("run", "")
    summary_if = None if summary is None else summary.get("if")
    if "summarize" not in summary_run or summary_if != "always()":
        problems.append("dispatch-step")


def _check_order(job: dict, problems: list[str]) -> None:
    names = [step.get("name") for step in job.get("steps") or []]
    indexes = []
    for name in _STEP_ORDER:
        if name not in names:
            problems.append("order")
            return
        indexes.append(names.index(name))
    if indexes != sorted(indexes):
        problems.append("order")


def _step(job: dict, name: str) -> dict | None:
    for step in job.get("steps") or []:
        if step.get("name") == name:
            return step
    return None


def _uses(value) -> list[str]:
    found = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "uses" and isinstance(child, str):
                found.append(child)
            else:
                found.extend(_uses(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(_uses(child))
    return found


def _keys(value, found: set[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            found.add(str(key))
            _keys(child, found)
    elif isinstance(value, list):
        for child in value:
            _keys(child, found)


def _unique(problems: list[str]) -> list[str]:
    result = []
    for item in problems:
        if item not in result:
            result.append(item)
    return result


def _structural(lines: list[str], index: int):
    if index >= len(lines):
        return None
    raw = lines[index]
    stripped = raw.strip()
    if not stripped or stripped.startswith("#"):
        return None
    indent = len(raw) - len(raw.lstrip(" "))
    content = _strip_comment(raw[indent:])
    if not content:
        return None
    return indent, content


def _next_structural(lines: list[str], index: int):
    while index < len(lines):
        found = _structural(lines, index)
        if found is not None:
            return index, found[0], found[1]
        index += 1
    return index, None, None


def _strip_comment(content: str) -> str:
    quote = False
    escaped = False
    for index, char in enumerate(content):
        if escaped:
            escaped = False
            continue
        if char == "\\" and quote:
            escaped = True
            continue
        if char == '"':
            quote = not quote
            continue
        if char == "#" and not quote and (index == 0 or content[index - 1] == " "):
            return content[:index].rstrip()
    return content.rstrip()


def _split_key(content: str) -> tuple[str, str]:
    quote = False
    for index, char in enumerate(content):
        if char == '"':
            quote = not quote
            continue
        if char == ":" and not quote:
            return content[:index], content[index + 1 :].lstrip()
    raise WorkflowParseError(f"expected a key: {content}")


def _scalar(content: str):
    if len(content) >= 2 and content[0] == '"' and content[-1] == '"':
        return content[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    if content == "true":
        return True
    if content == "false":
        return False
    if content == "null":
        return None
    if re.fullmatch(r"-?[0-9]+", content):
        return int(content)
    return content


def _parse_map(lines: list[str], index: int, indent: int):
    mapping: dict = {}
    while True:
        index, found_indent, content = _next_structural(lines, index)
        if found_indent is None or found_indent < indent:
            return mapping, index
        if found_indent > indent or content.startswith("- "):
            raise WorkflowParseError(f"expected a key at line {index + 1}")
        key, rest = _split_key(content)
        mapping[key], index = _parse_value(lines, index + 1, indent, rest)


def _parse_value(lines: list[str], index: int, key_indent: int, rest: str):
    if rest == "|":
        return _read_block(lines, index, key_indent)
    if rest != "":
        return _scalar(rest), index
    index, found_indent, content = _next_structural(lines, index)
    if found_indent is None or found_indent <= key_indent:
        return None, index
    if content.startswith("- "):
        return _parse_list(lines, index, found_indent)
    return _parse_map(lines, index, found_indent)


def _parse_list(lines: list[str], index: int, indent: int):
    items = []
    while True:
        index, found_indent, content = _next_structural(lines, index)
        if found_indent is None or found_indent < indent:
            return items, index
        if found_indent > indent or not content.startswith("- "):
            raise WorkflowParseError(f"expected a list item at line {index + 1}")
        item = content[2:]
        index += 1
        if item == "":
            child, index = _parse_value(lines, index, indent, "")
            items.append(child)
            continue
        if ": " in item or item.endswith(":"):
            key, rest = _split_key(item)
            node = {}
            node[key], index = _parse_value(lines, index, indent, rest)
            while True:
                peek, peek_indent, peek_content = _next_structural(lines, index)
                if peek_indent is None or peek_indent <= indent or peek_content.startswith("- "):
                    break
                key, rest = _split_key(peek_content)
                node[key], index = _parse_value(lines, peek + 1, peek_indent, rest)
            items.append(node)
            continue
        items.append(_scalar(item))


def _read_block(lines: list[str], index: int, key_indent: int):
    chunks = []
    content_indent = None
    while index < len(lines):
        raw = lines[index]
        if not raw.strip():
            if content_indent is None:
                index += 1
                continue
            chunks.append("")
            index += 1
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        if content_indent is None:
            if indent <= key_indent:
                break
            content_indent = indent
        if indent < content_indent:
            break
        chunks.append(raw[content_indent:])
        index += 1
    text = "\n".join(chunks)
    if chunks:
        text += "\n"
    return text, index
