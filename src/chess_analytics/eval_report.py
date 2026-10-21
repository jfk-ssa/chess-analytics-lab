"""Build the live-eval report from committed analyst_live_v1 receipts.

The documentation site renders this model with Jinja. Charts are inline SVG.
Nothing here contacts a network, and the same receipts always produce the same
fragments. Run labels use the receipt model and, when present, reasoning effort.
"""

from __future__ import annotations

import argparse
import html
import json
import math
import re
import statistics
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

from chess_analytics.analyst.live_runner import _tokens as receipt_token_totals
from chess_analytics.analyst.live_stats import cluster_bootstrap, exact_sign_test

INK = "#16181d"
INK_2 = "#454a54"
INK_3 = "#6b7280"
RULE = "#e3e5e9"
RULE_2 = "#c9ccd2"
PAPER = "#fbfaf7"
ALERT = "#b42318"
OK = "#1f6f4a"
MODEL_COLOURS = ("#0072B2", "#009E73", "#CC79A7", "#56B4E9", "#E69F00", "#4d4d4d")
FAIL_RAMP = ("#7a2a0c", "#a9431a", "#d0692f", "#ea9a5e", "#f6c99c", "#eef0f2")
FAILURE_MODES: tuple[tuple[str, str, str], ...] = (
    ("unsafe", "Answered a question it should refuse", "#000000"),
    ("over_abstention", "Refused an answerable question", "#E69F00"),
    ("plan_hallucination", "No valid plan (plan hallucination)", "#CC79A7"),
    ("boundary_swap", "Clarify / refuse swap on a high-severity case", "#D55E00"),
    ("wrong_answer", "Answered with wrong tool, filters or values", "#56B4E9"),
    ("other", "Other miss", "#999999"),
)
MODE_LABEL = {key: label for key, label, _ in FAILURE_MODES}
STATUS_ORDER = ("answered", "needs_clarification", "unsupported")
STATUS_SHORT: dict[str | None, str] = {
    "answered": "answer",
    "needs_clarification": "clarify",
    "unsupported": "refuse",
    None: "no plan",
}
REFUSAL_STATUSES = frozenset({"needs_clarification", "unsupported"})
SANS = "Inter, -apple-system, 'Segoe UI', system-ui, Roboto, sans-serif"
MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
RECEIPT_GLOB = "live-eval-receipt-*.json"
# ADR 0091: live-eval-receipt-<run id>.json
# ADR 0095: live-eval-receipt-<model>-<effort>-r<repeats>-<run id>.json
# The run id is the trailing integer. Repeats stay behind the r marker.
_RUN_ID = re.compile(r"live-eval-receipt-(?:(\d+)|.+-r\d+-(\d+))\.json$")
_REQUIRED = (
    "model",
    "rows",
    "cases",
    "repeats",
    "headline_passed",
    "headline_pass_rate",
    "hard_fail",
    "high_severity_misses",
    "over_abstention",
    "unsafe_answer",
    "known_gross_cost_usd",
    "token_usage",
    "repair_counts",
    "flaky_cases",
    "stats",
    "planned_requests",
    "rubric_version",
    "run_id",
    "max_run_usd",
    "reserved_usd",
    "instructions_sha256",
    "case_set_sha256",
    "fixture_sha256",
    "frozen_file_sha256",
    "resolved_model",
    "base_rubric_version",
    "price_checked_utc_date",
    "prices_rechecked",
    "complete",
    "scheduled",
)
# White text fails 4.5:1 on vermilion (#D55E00, 3.87:1) and pink (#CC79A7, 3.06:1).
# Ink on those fills passes. Black keeps white text.
_DARK_TEXT = frozenset({"#000000"})
# Perfect heatmap cells are #eef0f2. These two clear 4.5:1 (text) and 3:1 (dots).
PERFECT_TEXT = "#4b5563"
PERFECT_DOT = "#5c6370"
# The two committed prompts. They differ only by the dataset snapshot id.
# Run ids are not stored here. Any other hash is unexplained until dataset_id is recorded.
_DATASET_ONLY_INSTRUCTION_HASHES = frozenset(
    {
        "085a216a1be3e73e68dce4849d35e56cc5c5c13aff7b91ece5d95c44e42ef89e",
        "e4cd943340ee52138fd9a400aeed408d6a843c4cda0514d364aa2bc8ffbdc423",
    }
)


@dataclass(frozen=True)
class Case:
    id: str
    category: str
    question: str
    expected_status: str
    severity: str
    split: str
    template_family: str


@dataclass(frozen=True)
class Row:
    case_id: str
    repeat: int
    passed: bool
    failures: tuple[str, ...]
    severity: str
    high_severity_miss: bool
    over_abstention: bool
    unsafe_answer: bool
    repair_count: int
    emitted_status: str | None
    gross_cost_usd: float
    input_tokens: int
    cached_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class Receipt:
    path: Path
    raw: dict[str, Any]
    rows: tuple[Row, ...]
    label: str
    colour: str

    @property
    def model(self) -> str:
        return str(self.raw["model"])

    @property
    def effort(self) -> str:
        return str(self.raw.get("reasoning_effort") or "none")

    @property
    def n(self) -> int:
        return len(self.rows)

    @property
    def passed(self) -> int:
        return int(self.raw["headline_passed"])

    @property
    def rate(self) -> float:
        return float(self.raw["headline_pass_rate"])

    @property
    def wilson(self) -> tuple[float, float]:
        interval = self.raw["stats"]["wilson"]
        return float(interval["lower"]), float(interval["upper"])

    @property
    def bootstrap(self) -> tuple[float, float]:
        interval = self.raw["stats"]["bootstrap"]
        return float(interval["lower"]), float(interval["upper"])

    @property
    def cost(self) -> float:
        return float(self.raw["known_gross_cost_usd"])

    @property
    def hard_fail(self) -> bool:
        return bool(self.raw["hard_fail"])

    @property
    def repeats(self) -> int:
        return int(self.raw["repeats"])

    def passes_by_case(self) -> dict[str, int]:
        counts: dict[str, int] = defaultdict(int)
        for row in self.rows:
            counts[row.case_id] += int(row.passed)
        return dict(counts)

    def rows_by_case(self) -> dict[str, list[Row]]:
        grouped: dict[str, list[Row]] = defaultdict(list)
        for row in self.rows:
            grouped[row.case_id].append(row)
        for rows in grouped.values():
            rows.sort(key=lambda item: item.repeat)
        return dict(grouped)

    def flaky_count(self) -> int:
        return sum(1 for count in self.passes_by_case().values() if 0 < count < self.repeats)

    def pass_bits(self) -> dict[str, list[bool]]:
        """Pass bits in repeat order. Pair these with ``exact_sign_test``."""
        return {
            case_id: [row.passed for row in rows] for case_id, rows in self.rows_by_case().items()
        }


@dataclass(frozen=True)
class Integrity:
    checks: tuple[tuple[str, bool, str], ...]

    @property
    def all_ok(self) -> bool:
        return all(ok for _, ok, _ in self.checks)


class ReportIntegrityError(ValueError):
    """Raised when receipt totals do not match the rows, in strict builds."""

    def __init__(self, checks: tuple[tuple[str, bool, str], ...]) -> None:
        failed = [label for label, ok, _ in checks if not ok]
        detail = failed[0] if failed else "integrity"
        super().__init__(f"{len(failed)} live-eval integrity checks failed: {detail}")
        self.checks = checks


@dataclass(frozen=True)
class ReportView:
    """Escaped fragments and plain strings for the Jinja page."""

    title: str
    description: str
    meta: tuple[tuple[str, str], ...]
    caveat_html: str
    scorecards_html: str
    intervals_svg: str
    pairwise_html: str
    hard_intro: str
    callouts_html: str
    heat_take_html: str
    heat_legend_html: str
    heatmap_svg: str
    heat_table_html: str
    fail_take_html: str
    status_svg: str
    failure_legend_html: str
    failure_svg: str
    failure_note_html: str
    flaky_take_html: str
    consistency_svg: str
    cost_take_html: str
    cost_svg: str
    request_svg: str
    request_note_html: str
    provenance_html: str
    notes_html: str
    sensitivity_intro: str
    sensitivity_html: str
    repeat_word: str
    checks: tuple[tuple[str, bool], ...]
    n_cases: int
    repeats: int
    rubric: str
    receipt_files: tuple[str, ...]
    case_file: str
    requests_per_run: int


def _receipt_sort_key(path: Path) -> tuple[int, str]:
    """Sort by the trailing GitHub run id, not by ``r<repeats>``."""
    match = _RUN_ID.fullmatch(path.name)
    digits = (match.group(1) or match.group(2)) if match else None
    run_id = int(digits) if digits is not None else 10**18
    return run_id, path.name


def discover_receipts(directory: Path) -> list[Path]:
    """Return receipt paths sorted by the GitHub run id in the filename.

    ADR 0091 names the artifact ``live-eval-receipt-<github run id>.json``.
    ADR 0095 names it
    ``live-eval-receipt-<model>-<effort>-r<repeats>-<github run id>.json``.
    The runner's own ``run_id`` is a different uuid and stays inside the JSON.
    """
    paths = [path for path in directory.glob(RECEIPT_GLOB) if path.is_file()]
    return sorted(paths, key=_receipt_sort_key)


def load_cases(path: Path) -> dict[str, Case]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{path} is not a case list")
    cases: dict[str, Case] = {}
    for item in data:
        if not isinstance(item, dict) or "id" not in item:
            raise ValueError(f"{path} has a case without an id")
        cases[str(item["id"])] = Case(
            id=str(item["id"]),
            category=str(item["category"]),
            question=str(item["question"]),
            expected_status=str(item["expected_status"]),
            severity=str(item["severity"]),
            split=str(item.get("split", "")),
            template_family=str(item.get("template_family", "")),
        )
    return cases


def _row(raw: dict[str, Any]) -> Row:
    plan = raw.get("model_plan_before_semantic_repair") or None
    usage = raw.get("usage") or {}
    details = usage.get("input_tokens_details") or {}
    status = plan.get("status") if isinstance(plan, dict) else None
    failures = raw.get("failures") or ()
    return Row(
        case_id=str(raw["case_id"]),
        repeat=int(raw["repeat"]),
        passed=bool(raw["passed"]),
        failures=tuple(str(item) for item in failures),
        severity=str(raw.get("severity", "normal")),
        high_severity_miss=bool(raw.get("high_severity_miss")),
        over_abstention=bool(raw.get("over_abstention")),
        unsafe_answer=bool(raw.get("unsafe_answer")),
        repair_count=int(raw.get("repair_count") or 0),
        emitted_status=str(status) if status is not None else None,
        gross_cost_usd=float(raw.get("gross_cost_usd") or 0.0),
        input_tokens=int(usage.get("input_tokens") or 0),
        cached_tokens=int(details.get("cached_tokens") or 0),
        output_tokens=int(usage.get("output_tokens") or 0),
    )


def _run_label(raw: dict[str, Any]) -> str:
    model = str(raw["model"])
    effort = str(raw.get("reasoning_effort") or "none")
    if effort in {"none", ""}:
        return model
    return f"{model} · {effort}"


def load_receipts(paths: list[Path] | tuple[Path, ...]) -> list[Receipt]:
    loaded: list[tuple[Path, dict[str, Any], tuple[Row, ...]]] = []
    for path in paths:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"{path.name} is not a receipt object")
        missing = [key for key in _REQUIRED if key not in raw]
        if missing:
            raise ValueError(f"{path.name} is missing {', '.join(missing)}")
        rows_raw = raw["rows"]
        if not isinstance(rows_raw, list):
            raise ValueError(f"{path.name} has no rows")
        loaded.append((path, raw, tuple(_row(item) for item in rows_raw)))
    labels = [_run_label(raw) for _, raw, _ in loaded]
    counts = Counter(labels)
    receipts: list[Receipt] = []
    for index, (path, raw, rows) in enumerate(loaded):
        label = labels[index]
        if counts[label] > 1:
            label = f"{label} ({str(raw.get('run_id', ''))[:6]})"
        colour = MODEL_COLOURS[index % len(MODEL_COLOURS)]
        receipts.append(Receipt(path, raw, rows, label, colour))
    return receipts


def failure_mode(row: Row, case: Case) -> str | None:
    """One primary mode per failed row, in the ADR 0090 check order."""
    if row.passed:
        return None
    if row.unsafe_answer:
        return "unsafe"
    if row.over_abstention:
        return "over_abstention"
    if "plan_hallucination" in row.failures or row.emitted_status is None:
        return "plan_hallucination"
    expected = case.expected_status
    emitted = row.emitted_status
    if expected in REFUSAL_STATUSES and emitted in REFUSAL_STATUSES and emitted != expected:
        return "boundary_swap"
    if emitted == expected == "answered":
        return "wrong_answer"
    return "other"


def failure_mode_counts(receipt: Receipt, cases: dict[str, Case]) -> Counter[str]:
    return Counter(mode for row in receipt.rows if (mode := failure_mode(row, cases[row.case_id])))


def wilson(successes: int, trials: int, z: float = 1.959963984540054) -> tuple[float, float]:
    proportion = successes / trials
    denominator = 1 + z * z / trials
    centre = (proportion + z * z / (2 * trials)) / denominator
    margin = z * math.sqrt(proportion * (1 - proportion) / trials + z * z / (4 * trials * trials))
    half = margin / denominator
    return centre - half, centre + half


def sign_test(left: dict[str, list[bool]], right: dict[str, list[bool]]) -> tuple[int, int, float]:
    """Exact two-sided sign test. Unequal repeat counts raise.

    ``live_stats.exact_sign_test`` refuses a pair whose case ids differ or
    whose repeat lists have different lengths. Pass counts alone are not
    enough: one pass out of one repeat is not one pass out of five.
    """
    result = exact_sign_test(left, right)
    return result["favor_left"], result["favor_right"], float(result["p_value"])


def _times(count: int) -> str:
    return "1 time" if count == 1 else f"{count} times"


def _misses(count: int) -> str:
    noun = "miss" if count == 1 else "misses"
    return f"{count} high-severity {noun}"


def split_cohorts(receipts: list[Receipt]) -> tuple[list[Receipt], list[Receipt]]:
    """Split off runs whose repeat count or case ids differ from the headline.

    The headline cohort is the highest repeat count, then the largest
    case-id set, then the most receipts in that set. A 1-repeat receipt
    stays in the sensitivity section.
    """
    groups: dict[tuple[int, frozenset[str]], list[Receipt]] = defaultdict(list)
    for receipt in receipts:
        key = (receipt.repeats, frozenset(receipt.passes_by_case()))
        groups[key].append(receipt)
    headline_key = max(groups, key=lambda item: (item[0], len(item[1]), len(groups[item])))
    headline_ids = {id(item) for item in groups[headline_key]}
    headline = [receipt for receipt in receipts if id(receipt) in headline_ids]
    extra = [receipt for receipt in receipts if id(receipt) not in headline_ids]
    return headline, extra


def _bootstrap_repeats(receipt: Receipt) -> list[list[bool]]:
    """Case order matches the runner: first time each case id appears."""
    grouped: dict[str, list[bool]] = {}
    for item in receipt.raw["rows"]:
        if item.get("passed") is None:
            continue
        grouped.setdefault(str(item["case_id"]), []).append(bool(item["passed"]))
    return [grouped[case_id] for case_id in grouped]


def _add(checks: list[tuple[str, bool, str]], label: str, ok: bool, detail: str = "") -> None:
    checks.append((label, ok, detail))


def _check_extended_tokens(receipt: Receipt, checks: list[tuple[str, bool, str]]) -> None:
    """Re-derive reasoning and billed output when the receipt records them.

    Older OpenAI receipts omit both keys. A grok receipt from ADR 0095
    stores ``reasoning_tokens`` and ``billed_output_tokens`` beside input
    and output. The sums use the runner's billing rule.
    """
    usage = receipt.raw["token_usage"]
    if "reasoning_tokens" not in usage and "billed_output_tokens" not in usage:
        return
    summed = receipt_token_totals(list(receipt.raw["rows"]), str(receipt.raw["model"]))
    label = receipt.label
    if "reasoning_tokens" in usage:
        _add(
            checks,
            f"{label}: reasoning_tokens = sum of row reasoning",
            int(usage["reasoning_tokens"]) == int(summed["reasoning_tokens"]),
            f"{usage['reasoning_tokens']} vs {summed['reasoning_tokens']}",
        )
    if "billed_output_tokens" in usage:
        _add(
            checks,
            f"{label}: billed_output_tokens = sum of row billed output",
            int(usage["billed_output_tokens"]) == int(summed["billed_output_tokens"]),
            f"{usage['billed_output_tokens']} vs {summed['billed_output_tokens']}",
        )


def _token_detail(usage: dict[str, Any]) -> str:
    if "reasoning_tokens" not in usage and "billed_output_tokens" not in usage:
        return ""
    reasoning = int(usage.get("reasoning_tokens") or 0)
    billed = int(usage.get("billed_output_tokens") or 0)
    return f"<span>Reasoning / billed output tokens</span><span>{reasoning:,} / {billed:,}</span>"


def _verify_one(
    receipt: Receipt, cases: dict[str, Case], checks: list[tuple[str, bool, str]]
) -> None:
    label = receipt.label
    passed = sum(row.passed for row in receipt.rows)
    expected_rows = int(receipt.raw["cases"]) * receipt.repeats
    high_severity = sum(row.high_severity_miss for row in receipt.rows)
    cost = sum(row.gross_cost_usd for row in receipt.rows)
    usage = receipt.raw["token_usage"]
    flaky = sorted(
        key for key, count in receipt.passes_by_case().items() if 0 < count < receipt.repeats
    )
    lower, upper = wilson(passed, receipt.n)
    wilson_low, wilson_high = receipt.wilson
    _add(
        checks,
        f"{label}: row case ids equal the case file ({len(cases)})",
        {row.case_id for row in receipt.rows} == set(cases),
    )
    _add(
        checks,
        f"{label}: rows = cases × repeats ({expected_rows})",
        receipt.n == expected_rows,
        f"found {receipt.n}",
    )
    _add(
        checks,
        f"{label}: headline_passed re-derived from rows",
        passed == receipt.passed,
        f"{passed} vs {receipt.passed}",
    )
    _add(
        checks,
        f"{label}: headline_pass_rate = passed / rows",
        abs(passed / receipt.n - receipt.rate) < 1e-12,
    )
    _add(
        checks,
        f"{label}: high_severity_misses re-derived",
        high_severity == int(receipt.raw["high_severity_misses"]),
    )
    _add(
        checks,
        f"{label}: hard_fail matches any high-severity miss",
        receipt.hard_fail == (high_severity > 0),
    )
    _add(
        checks,
        f"{label}: over_abstention re-derived",
        sum(row.over_abstention for row in receipt.rows) == int(receipt.raw["over_abstention"]),
    )
    _add(
        checks,
        f"{label}: unsafe_answer re-derived",
        sum(row.unsafe_answer for row in receipt.rows) == int(receipt.raw["unsafe_answer"]),
    )
    _add(
        checks,
        f"{label}: known_gross_cost_usd = sum of row cost",
        abs(cost - receipt.cost) < 1e-9,
        f"{cost:.7f}",
    )
    _add(
        checks,
        f"{label}: token_usage = sum of row usage",
        sum(row.input_tokens for row in receipt.rows) == usage["input_tokens"]
        and sum(row.output_tokens for row in receipt.rows) == usage["output_tokens"],
    )
    _check_extended_tokens(receipt, checks)
    repair_total = sum((receipt.raw.get("repair_counts") or {}).values())
    _add(
        checks,
        f"{label}: repair_counts total = sum of row repair_count",
        repair_total == sum(row.repair_count for row in receipt.rows),
    )
    _add(checks, f"{label}: flaky_cases re-derived", flaky == sorted(receipt.raw["flaky_cases"]))
    _add(
        checks,
        f"{label}: Wilson interval recomputed",
        abs(lower - wilson_low) < 1e-9 and abs(upper - wilson_high) < 1e-9,
    )
    recorded_bootstrap = (receipt.raw.get("stats") or {}).get("bootstrap") or {}
    recomputed = cluster_bootstrap(
        _bootstrap_repeats(receipt),
        seed=int(recorded_bootstrap["seed"]),
        resamples=int(recorded_bootstrap["resamples"]),
        alpha=float(recorded_bootstrap.get("alpha", 0.05)),
    )
    _add(
        checks,
        f"{label}: bootstrap interval recomputed",
        abs(recomputed["lower"] - float(recorded_bootstrap["lower"])) < 1e-9
        and abs(recomputed["upper"] - float(recorded_bootstrap["upper"])) < 1e-9,
    )
    _add(
        checks,
        f"{label}: row severity matches case file",
        all(row.severity == cases[row.case_id].severity for row in receipt.rows),
    )


def verify(receipts: list[Receipt], cases: dict[str, Case]) -> Integrity:
    checks: list[tuple[str, bool, str]] = []
    for receipt in receipts:
        _verify_one(receipt, cases, checks)
    return Integrity(tuple(checks))


def category_groups(cases: dict[str, Case]) -> list[tuple[str, list[Case]]]:
    """High-severity categories first, then the rest, each alphabetical."""
    grouped: dict[str, list[Case]] = defaultdict(list)
    for case in cases.values():
        grouped[case.category].append(case)

    def key(category: str) -> tuple[int, str]:
        high = any(case.severity == "high" for case in grouped[category])
        return (0 if high else 1, category)

    return [
        (name, sorted(grouped[name], key=lambda case: case.id)) for name in sorted(grouped, key=key)
    ]


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def pct_num(value: float, digits: int = 1) -> str:
    """Half-up rounding, so 0.8625 renders as 86.3 rather than banker's 86.2."""
    quantum = Decimal(1).scaleb(-digits)
    return f"{(Decimal(repr(value)) * 100).quantize(quantum, rounding=ROUND_HALF_UP)}"


def pct(value: float, digits: int = 1) -> str:
    return pct_num(value, digits) + "%"


def usd(value: float, digits: int = 4) -> str:
    return f"${value:,.{digits}f}"


def _ratio(left: float, right: float) -> str:
    return f"{left / right:.1f}×" if right else "n/a"


def _text_width(text: str, size: float, factor: float = 0.56) -> float:
    return len(text) * size * factor


def _svg_open(
    width: float, height: float, title: str, desc: str, chart_id: str, extra: str = ""
) -> str:
    return (
        f'<svg class="chart {extra}" viewBox="0 0 {width:.0f} {height:.0f}" '
        f'width="{width:.0f}" height="{height:.0f}" role="img" '
        f'aria-labelledby="{chart_id}-title {chart_id}-desc" '
        f'xmlns="http://www.w3.org/2000/svg" font-family="{esc(SANS)}"> '
        f'<title id="{chart_id}-title">{esc(title)}</title> '
        f'<desc id="{chart_id}-desc">{esc(desc)}</desc>'
    )


def _text(
    x: float,
    y: float,
    text: str,
    size: float = 12,
    fill: str = INK_2,
    anchor: str = "start",
    weight: int = 400,
    family: str | None = None,
    extra: str = "",
) -> str:
    face = f' font-family="{esc(family)}"' if family else ""
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{fill}" text-anchor="{anchor}" '
        f'font-weight="{weight}"{face} {extra}>{esc(text)}</text>'
    )


def _marker(x: float, y: float, receipt: Receipt, radius: float = 7.0) -> str:
    """Filled dot means the gate is clear. A hollow ring means hard_fail."""
    if receipt.hard_fail:
        return (
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius}" fill="{PAPER}" '
            f'stroke="{receipt.colour}" '
            f'stroke-width="3"><title>{esc(receipt.label)} (hard fail)</title></circle>'
        )
    return (
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius}" fill="{receipt.colour}" stroke="#fff" '
        f'stroke-width="1.5"><title>{esc(receipt.label)}</title></circle>'
    )


def _repair_phrase(receipt: Receipt) -> str:
    repairs = receipt.raw.get("repair_counts") or {}
    shown = [(str(key), int(value)) for key, value in repairs.items() if int(value)]
    if not shown:
        return "0 repairs"
    body = ", ".join(f"{count} {name}" for name, count in shown)
    total = sum(count for _, count in shown)
    suffix = "repair" if total == 1 else "repairs"
    return f"{body} {suffix}"


def _shared_field(receipts: list[Receipt], key: str) -> bool:
    return len({json.dumps(receipt.raw.get(key), sort_keys=True) for receipt in receipts}) == 1


def _frozen_inputs_match(receipts: list[Receipt]) -> bool:
    return all(
        _shared_field(receipts, key)
        for key in ("case_set_sha256", "fixture_sha256", "rubric_version", "frozen_file_sha256")
    )


def _recorded_dataset_id(receipt: Receipt) -> str | None:
    value = receipt.raw.get("dataset_id")
    if isinstance(value, str) and value:
        return value
    return None


def pair_explained_by_dataset_id(left: Receipt, right: Receipt) -> bool:
    """True only for this pair, never for a larger set that contains it.

    Frozen inputs must match. The pair is then explained when its hashes are
    exactly the two committed hashes and neither receipt records ``dataset_id``,
    or when both record ``dataset_id`` and those ids stand in one-to-one
    correspondence with the hashes. The same id on two hashes is not explained.
    """
    left_hash = str(left.raw.get("instructions_sha256"))
    right_hash = str(right.raw.get("instructions_sha256"))
    if left_hash == right_hash or not _frozen_inputs_match([left, right]):
        return False
    hashes = {left_hash, right_hash}
    left_id = _recorded_dataset_id(left)
    right_id = _recorded_dataset_id(right)
    known = hashes == _DATASET_ONLY_INSTRUCTION_HASHES
    if known and left_id is None and right_id is None:
        return True
    return left_id is not None and right_id is not None and left_id != right_id


def _hash_pairs(receipts: list[Receipt]) -> list[tuple[Receipt, Receipt]]:
    pairs = []
    for left_index in range(len(receipts)):
        for right_index in range(left_index + 1, len(receipts)):
            left, right = receipts[left_index], receipts[right_index]
            if left.raw.get("instructions_sha256") != right.raw.get("instructions_sha256"):
                pairs.append((left, right))
    return pairs


def _known_hash_explanation() -> str:
    return (
        "prompts differ only by dataset id. The prompt embeds "
        "<code>Dataset: {dataset_id}</code>, the 24-character snapshot id. That id comes "
        "from <code>implementation_hash</code> over <code>src/**/*.py</code>, "
        "<code>src/**/*.sql</code> and <code>contracts/*.json</code>. Adding "
        "<code>public_extract.py</code> in #42 changed the hash. This pair is comparable. "
        "Future receipts should record <code>dataset_id</code> and "
        "<code>implementation_sha256</code>."
    )


def _pair_explanation(left: Receipt, right: Receipt) -> str:
    names = f"<b>{esc(left.label)}</b> vs <b>{esc(right.label)}</b>"
    if not pair_explained_by_dataset_id(left, right):
        return (
            f"{names}: <code>instructions_sha256</code> differs and the cause is not recorded. "
            "This report does not treat this pair as comparable."
        )
    hashes = {
        str(left.raw.get("instructions_sha256")),
        str(right.raw.get("instructions_sha256")),
    }
    known = hashes == _DATASET_ONLY_INSTRUCTION_HASHES
    if known and _recorded_dataset_id(left) is None and _recorded_dataset_id(right) is None:
        return f"{names}: {_known_hash_explanation()}"
    left_id = _recorded_dataset_id(left)
    right_id = _recorded_dataset_id(right)
    assert left_id is not None and right_id is not None
    listed = " and ".join(f"<code>{esc(item)}</code>" for item in sorted((left_id, right_id)))
    return (
        f"{names}: recorded dataset ids {listed} correspond one to one with the instruction "
        "hashes, and the other frozen inputs match, so the prompts differ only by that id. "
        "This pair is comparable."
    )


def caveat_html(receipts: list[Receipt]) -> str:
    """Explain each differing instruction-hash pair. One extra receipt does not cover the rest."""
    pairs = _hash_pairs(receipts)
    if not pairs:
        return ""
    items = "".join(f"<li>{_pair_explanation(left, right)}</li>" for left, right in pairs)
    return (
        '<div class="ev-caveat"><b>Comparability caveat.</b> '
        f"Each pair is judged on its own.<ul>{items}</ul></div>"
    )


def chart_intervals(receipts: list[Receipt]) -> str:
    width, row_height, top, left, right = 1040, 62, 50, 200, 62
    height = top + row_height * len(receipts) + 36
    lowest = min(min(receipt.wilson[0], receipt.bootstrap[0]) for receipt in receipts)
    x0 = max(0.0, math.floor(lowest * 20 - 1e-9) / 20)
    x1 = 1.0

    def sx(value: float) -> float:
        return left + (value - x0) / (x1 - x0) * (width - left - right)

    summary = "; ".join(
        f"{receipt.label} {pct(receipt.rate, 2)} "
        f"(Wilson {pct(receipt.wilson[0])} to {pct(receipt.wilson[1])}, "
        f"bootstrap {pct(receipt.bootstrap[0])} to {pct(receipt.bootstrap[1])})"
        for receipt in receipts
    )
    parts = [
        _svg_open(
            width,
            height,
            "Headline pass rate with 95% Wilson and case-bootstrap intervals",
            "Filled dot means the gate is clear. A hollow ring means hard_fail. " + summary,
            "ev-intervals",
            "wide",
        )
    ]
    tick = x0
    while tick <= x1 + 1e-9:
        parts.append(
            f'<line x1="{sx(tick):.1f}" x2="{sx(tick):.1f}" y1="{top - 14}" y2="{height - 30}" '
            f'stroke="{RULE}"/>'
        )
        parts.append(_text(sx(tick), height - 12, pct(tick, 0), 11, INK_3, "middle"))
        tick = round(tick + 0.05, 6)
    legend_x = left
    parts.append(
        f'<line x1="{legend_x}" x2="{legend_x + 26}" y1="14" y2="14" stroke="{INK_2}" '
        'stroke-width="12" stroke-opacity=".18" stroke-linecap="round"/>'
    )
    legend = "Case-cluster bootstrap 95% (2,000 resamples)"
    parts.append(_text(legend_x + 36, 18, legend, 11.5, INK_2))
    legend_x2 = legend_x + 36 + _text_width(legend, 11.5) + 30
    parts.append(
        f'<line x1="{legend_x2}" x2="{legend_x2 + 26}" y1="14" y2="14" stroke="{INK_2}" '
        f'stroke-width="2.5"/>'
    )
    parts.append(
        f'<line x1="{legend_x2}" x2="{legend_x2}" y1="9" y2="19" stroke="{INK_2}" '
        f'stroke-width="2"/>'
    )
    parts.append(
        f'<line x1="{legend_x2 + 26}" x2="{legend_x2 + 26}" y1="9" y2="19" stroke="{INK_2}" '
        f'stroke-width="2"/>'
    )
    parts.append(_text(legend_x2 + 36, 18, "Wilson 95% (each request independent)", 11.5, INK_2))
    for index, receipt in enumerate(receipts):
        parts.extend(_interval_row(receipt, index, row_height, top, left, width, sx))
    parts.append("</svg>")
    return "".join(parts)


def _interval_row(
    receipt: Receipt,
    index: int,
    row_height: int,
    top: int,
    left: int,
    width: int,
    sx: Any,
) -> list[str]:
    cy = top + row_height * index + row_height / 2
    boot_low, boot_high = receipt.bootstrap
    wilson_low, wilson_high = receipt.wilson
    parts = [
        (
            f'<line x1="{sx(boot_low):.1f}" x2="{sx(boot_high):.1f}" y1="{cy}" y2="{cy}" '
            f'stroke="{receipt.colour}" stroke-width="16" stroke-opacity=".18" '
            f'stroke-linecap="round"> '
            f"<title>{esc(receipt.label)} bootstrap {pct(boot_low)}–{pct(boot_high)}</title></line>"
        ),
        (
            f'<line x1="{sx(wilson_low):.1f}" x2="{sx(wilson_high):.1f}" y1="{cy}" y2="{cy}" '
            f'stroke="{receipt.colour}" stroke-width="2.5"> '
            f"<title>{esc(receipt.label)} Wilson "
            f"{pct(wilson_low)}–{pct(wilson_high)}</title></line>"
        ),
    ]
    for bound in (wilson_low, wilson_high):
        parts.append(
            f'<line x1="{sx(bound):.1f}" x2="{sx(bound):.1f}" y1="{cy - 6}" y2="{cy + 6}" '
            f'stroke="{receipt.colour}" stroke-width="2"/>'
        )
    parts.append(_marker(sx(receipt.rate), cy, receipt))
    parts.append(_text(left - 18, cy - 2, receipt.label, 14, INK, "end", 650))
    gate = "hard fail" if receipt.hard_fail else "gate clear"
    parts.append(
        _text(
            left - 18,
            cy + 15,
            f"{receipt.passed}/{receipt.n} · {gate}",
            11.5,
            ALERT if receipt.hard_fail else INK_3,
            "end",
            600 if receipt.hard_fail else 400,
        )
    )
    parts.append(_text(sx(receipt.rate), cy - 15, pct(receipt.rate, 2), 12, INK, "middle", 650))
    parts.append(_text(sx(boot_low) - 12, cy + 4, pct(boot_low), 10.5, INK_3, "end"))
    if sx(boot_high) + 40 < width:
        parts.append(_text(sx(boot_high) + 12, cy + 4, pct(boot_high), 10.5, INK_3, "start"))
    return parts


def _heat_case(
    case: Case,
    receipts: list[Receipt],
    rows_by_receipt: list[dict[str, list[Row]]],
    y: float,
    cell_height: int,
    id_width: int,
    question_width: int,
    column_width: int,
    cell_width: float,
    x_models: float,
) -> tuple[list[str], float]:
    cy = y + cell_height / 2 + 5.5
    parts = [_text(0, cy, case.id, 11.5, INK_2, family=MONO)]
    max_chars = int(question_width / (12 * 0.49)) - 3
    question = case.question
    if len(question) > max_chars:
        question = question[: max_chars - 1].rstrip() + "…"
    parts.append(
        f"<g><title>{esc(case.question)}</title>{_text(id_width, cy, question, 12, INK_2)}</g>"
    )
    refuse = case.expected_status != "answered"
    parts.append(
        _text(
            id_width + question_width,
            cy,
            STATUS_SHORT[case.expected_status],
            11.5,
            INK if refuse else INK_3,
            weight=650 if refuse else 400,
        )
    )
    for index, receipt in enumerate(receipts):
        parts.append(
            _heat_cell(
                case,
                receipt,
                rows_by_receipt[index].get(case.id, []),
                x_models + index * column_width,
                y,
                cell_height,
                cell_width,
                cy,
            )
        )
    return parts, y + cell_height + 3


def _heat_tip(receipt: Receipt, case: Case, rows: list[Row], passed: int) -> str:
    lines = [f"{receipt.label} · {case.id}: {passed}/{receipt.repeats} repeats passed"]
    for row in rows:
        if row.passed:
            repair = f" (extraction repair ×{row.repair_count})" if row.repair_count else ""
            lines.append(f"repeat {row.repeat}: pass{repair}")
        else:
            failed = ", ".join(row.failures)
            emitted = STATUS_SHORT.get(row.emitted_status, str(row.emitted_status))
            lines.append(f"repeat {row.repeat}: FAIL [{failed}], emitted {emitted}")
    return "\n".join(lines)


def _heat_cell(
    case: Case,
    receipt: Receipt,
    rows: list[Row],
    x: float,
    y: float,
    cell_height: int,
    cell_width: float,
    cy: float,
) -> str:
    passed = sum(row.passed for row in rows)
    repeats = receipt.repeats
    index = round(passed / repeats * (len(FAIL_RAMP) - 1)) if repeats else 0
    perfect = passed == repeats
    # Index 2 (#d0692f) is only 3.66:1 under white text, so counts use ink there.
    dark = index <= 2
    light_text = index <= 1
    parts = [
        f"<g><title>{esc(_heat_tip(receipt, case, rows, passed))}</title>",
        (
            f'<rect x="{x:.1f}" y="{y + 2:.1f}" width="{cell_width}" height="{cell_height}" rx="3" '
            f'fill="{FAIL_RAMP[index]}"/>'
        ),
    ]
    for row in rows:
        px = x + 10 + row.repeat * 8
        py = y + 2 + cell_height / 2
        if row.passed:
            colour = PERFECT_DOT if perfect else ("#ffffff" if dark else INK_2)
            parts.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="2.4" fill="{colour}"/>')
        else:
            colour = "#ffffff" if dark else INK
            parts.append(
                f'<circle cx="{px:.1f}" cy="{py:.1f}" r="2.3" fill="none" stroke="{colour}" '
                f'stroke-width="1.2"/>'
            )
    if perfect:
        text_colour = PERFECT_TEXT
    elif light_text:
        text_colour = "#ffffff"
    else:
        text_colour = INK
    parts.append(
        _text(
            x + cell_width - 9,
            cy,
            f"{passed}/{repeats}",
            11,
            text_colour,
            "end",
            700 if not perfect else 400,
            extra='font-variant-numeric="tabular-nums"',
        )
    )
    parts.append("</g>")
    return "".join(parts)


def chart_heatmap(
    receipts: list[Receipt], cases: dict[str, Case], groups: list[tuple[str, list[Case]]]
) -> str:
    column_width, cell_height = 104, 20
    id_width, expected_width = 200, 66
    question_width = max(330, 1072 - id_width - expected_width - len(receipts) * column_width)
    width = id_width + question_width + expected_width + len(receipts) * column_width
    head_height, group_height = 64, 34
    height = (
        head_height + sum(group_height + len(items) * (cell_height + 3) for _, items in groups) + 8
    )
    x_models = id_width + question_width + expected_width
    cell_width = column_width - 8
    repeat_counts = {receipt.repeats for receipt in receipts}
    if len(repeat_counts) == 1:
        heat_title = (
            f"Passes out of {receipts[0].repeats} repeats for every case and model, "
            "grouped by category"
        )
    else:
        heat_title = "Passes out of each run's own repeats, grouped by category"
    parts = [
        _svg_open(
            width,
            height,
            heat_title,
            "Darker cells failed more often. Filled dots passed and hollow dots failed, one per "
            "repeat. "
            "The HTML table under the chart lists every case.",
            "ev-heatmap",
            "heat wide",
        )
    ]
    parts.extend(
        _heat_header(
            receipts,
            head_height,
            id_width,
            question_width,
            x_models,
            column_width,
            cell_width,
            width,
        )
    )
    y = float(head_height)
    rows_by_receipt = [receipt.rows_by_case() for receipt in receipts]
    passes = [receipt.passes_by_case() for receipt in receipts]
    for category, items in groups:
        y += group_height
        parts.extend(
            _heat_group_label(
                category,
                items,
                receipts,
                passes,
                y,
                x_models,
                column_width,
                cell_width,
                width,
            )
        )
        for case in items:
            row_parts, y = _heat_case(
                case,
                receipts,
                rows_by_receipt,
                y,
                cell_height,
                id_width,
                question_width,
                column_width,
                cell_width,
                x_models,
            )
            parts.extend(row_parts)
    parts.append("</svg>")
    return "".join(parts)


def _heat_header(
    receipts: list[Receipt],
    head_height: int,
    id_width: int,
    question_width: int,
    x_models: float,
    column_width: int,
    cell_width: float,
    width: int,
) -> list[str]:
    tracking = 'letter-spacing="1"'
    parts = [
        _text(0, head_height - 16, "CASE", 10.5, INK_3, weight=650, extra=tracking),
        _text(id_width, head_height - 16, "QUESTION", 10.5, INK_3, weight=650, extra=tracking),
        _text(
            id_width + question_width,
            head_height - 16,
            "EXPECTED",
            10.5,
            INK_3,
            weight=650,
            extra=tracking,
        ),
    ]
    for index, receipt in enumerate(receipts):
        cx = x_models + index * column_width + cell_width / 2
        lines = receipt.label.split(" · ")
        y0 = head_height - 16 - 14 * len(lines)
        for line_index, line in enumerate(lines):
            parts.append(_text(cx + 6, y0 + line_index * 14, line, 12.5, INK, "middle", 650))
        swatch_x = cx + 6 - _text_width(lines[0], 12.5, 0.58) / 2 - 13
        parts.append(
            f'<rect x="{swatch_x:.1f}" y="{y0 - 9}" width="8" height="8" rx="2" '
            f'fill="{receipt.colour}"/>'
        )
        parts.append(
            _text(
                cx,
                head_height - 16,
                f"{receipt.passed}/{receipt.n}",
                10.5,
                ALERT if receipt.hard_fail else INK_3,
                "middle",
                650,
                extra='font-variant-numeric="tabular-nums"',
            )
        )
    parts.append(
        f'<line x1="0" x2="{width}" y1="{head_height - 6}" y2="{head_height - 6}" stroke="{INK}" '
        f'stroke-width="1"/>'
    )
    return parts


def _heat_group_label(
    category: str,
    items: list[Case],
    receipts: list[Receipt],
    passes: list[dict[str, int]],
    y: float,
    x_models: float,
    column_width: int,
    cell_width: float,
    width: int,
) -> list[str]:
    high = any(case.severity == "high" for case in items)
    label = category.replace("_", " ").upper()
    noun = "case" if len(items) == 1 else "cases"
    meta = f"{len(items)} {noun}" + (" · high severity" if high else "")
    parts = [
        (
            f'<text x="0" y="{y - 11:.1f}" font-size="11" fill="{INK}" font-weight="750" '
            f'letter-spacing="1.1"> '
            f'{esc(label)}<tspan dx="10" letter-spacing="0" font-weight="{600 if high else 400}" '
            f'fill="{ALERT if high else INK_3}">{esc(meta)}</tspan></text>'
        )
    ]
    for index, receipt in enumerate(receipts):
        total = sum(passes[index].get(case.id, 0) for case in items)
        parts.append(
            _text(
                x_models + index * column_width + cell_width / 2,
                y - 11,
                f"{total}/{len(items) * receipt.repeats}",
                10.5,
                INK_2,
                "middle",
                600,
                extra='font-variant-numeric="tabular-nums"',
            )
        )
    parts.append(
        f'<line x1="0" x2="{width}" y1="{y - 4}" y2="{y - 4}" stroke="{RULE_2}" stroke-width=".8"/>'
    )
    return parts


def heat_legend(repeats: int) -> str:
    items = []
    for passed in range(repeats, -1, -1):
        index = round(passed / repeats * (len(FAIL_RAMP) - 1))
        items.append(
            f'<span class="ev-lg"><i '
            f'style="background:{FAIL_RAMP[index]}"></i>{passed}/{repeats}</span>'
        )
    pips = (
        '<span class="ev-lg"><svg width="26" height="10" aria-hidden="true"> '
        f'<circle cx="5" cy="5" r="2.6" fill="{INK_2}"/><circle cx="17" cy="5" r="2.5" fill="none" '
        f'stroke="{INK}" stroke-width="1.2"/></svg>one dot per repeat, in order: filled = pass, '
        f"hollow = fail</span>"
    )
    return (
        '<div class="ev-legend"><span class="ev-lg" '
        'style="font-weight:600;color:var(--ev-ink)">Repeats passed</span>'
        + "".join(items)
        + pips
        + "</div>"
    )


def heat_table(receipts: list[Receipt], groups: list[tuple[str, list[Case]]]) -> str:
    heads = "".join(f'<th scope="col">{esc(receipt.label)}</th>' for receipt in receipts)
    body = []
    passes = [receipt.passes_by_case() for receipt in receipts]
    for _category, items in groups:
        for case in items:
            cells = "".join(
                f"<td>{passes[index].get(case.id, 0)}/{receipt.repeats}</td>"
                for index, receipt in enumerate(receipts)
            )
            body.append(
                "<tr> "
                f'<th scope="row">{esc(case.id)}</th> '
                f"<td>{esc(case.question)}</td> "
                f"<td>{esc(case.expected_status)}</td> "
                f"{cells}</tr>"
            )
    return (
        '<details class="ev-details"><summary>Case results as a table</summary> '
        '<div class="scroll"><table class="ev-cases"><caption>Passes out of repeats for every case '
        "and run. "
        "The headline on each run is still the raw pass rate.</caption><thead><tr> "
        '<th scope="col">Case</th><th scope="col">Question</th><th scope="col">Expected</th> '
        f"{heads}</tr></thead><tbody>{''.join(body)}</tbody></table></div></details>"
    )


def _status_fill(expected: str, emitted: str | None, count: int, share: float) -> tuple[str, float]:
    if count == 0:
        return "#f3f4f6", 1.0
    if emitted == expected:
        return "#7f97b0", 0.18 + 0.5 * share
    if expected in REFUSAL_STATUSES and emitted in REFUSAL_STATUSES:
        return "#D55E00", 1.0
    if expected in REFUSAL_STATUSES and emitted == "answered":
        return "#000000", 1.0
    if emitted in REFUSAL_STATUSES:
        return "#E69F00", 1.0
    return "#CC79A7", 1.0


def _status_block(
    receipt: Receipt, cases: dict[str, Case], origin_x: int, origin_y: int
) -> list[str]:
    columns: tuple[str | None, ...] = ("answered", "needs_clarification", "unsupported", None)
    cell_w, cell_h, left, top = 70, 40, 78, 62
    counts = Counter(
        (cases[row.case_id].expected_status, row.emitted_status) for row in receipt.rows
    )
    parts = [
        f'<rect x="{origin_x}" y="{origin_y + 5}" width="9" height="9" rx="2" '
        f'fill="{receipt.colour}"/>',
        _text(origin_x + 15, origin_y + 14, f"{receipt.label} ({receipt.n})", 13, INK, weight=650),
        _text(origin_x + left, origin_y + 36, "emitted →", 10.5, INK_3),
    ]
    for index, status in enumerate(columns):
        parts.append(
            _text(
                origin_x + left + index * cell_w + cell_w / 2,
                origin_y + top - 9,
                STATUS_SHORT[status],
                11,
                INK_2,
                "middle",
                600,
            )
        )
    for row_index, expected in enumerate(STATUS_ORDER):
        ry = origin_y + top + row_index * cell_h
        parts.append(
            _text(
                origin_x + left - 10,
                ry + cell_h / 2 + 4,
                STATUS_SHORT[expected],
                11,
                INK_2,
                "end",
                600,
            )
        )
        row_total = sum(counts[(expected, status)] for status in columns) or 1
        for index, status in enumerate(columns):
            parts.append(
                _status_cell(
                    receipt,
                    counts,
                    expected,
                    status,
                    origin_x,
                    left,
                    index,
                    ry,
                    cell_w,
                    cell_h,
                    row_total,
                )
            )
    parts.append(
        _text(
            origin_x + 8,
            origin_y + top + cell_h * 1.5,
            "expected",
            10.5,
            INK_3,
            "middle",
            extra=f'transform="rotate(-90 {origin_x + 8} {origin_y + top + cell_h * 1.5})"',
        )
    )
    return parts


def _status_cell(
    receipt: Receipt,
    counts: Counter[tuple[str, str | None]],
    expected: str,
    emitted: str | None,
    origin_x: int,
    left: int,
    index: int,
    ry: int,
    cell_w: int,
    cell_h: int,
    row_total: int,
) -> str:
    count = counts[(expected, emitted)]
    x = origin_x + left + index * cell_w
    fill, opacity = _status_fill(expected, emitted, count, count / row_total)
    diagonal = emitted == expected
    off = (not diagonal) and count > 0
    if off and fill in _DARK_TEXT:
        text_fill = "#ffffff"
    elif off or count:
        text_fill = INK
    else:
        text_fill = INK_2
    label = str(count) if count else "·"
    emitted_name = emitted or "no valid plan"
    return (
        f'<rect x="{x + 1.5}" y="{ry + 1.5}" width="{cell_w - 3}" height="{cell_h - 3}" rx="4" '
        f'fill="{fill}" fill-opacity="{opacity:.2f}"><title>{esc(receipt.label)}: expected '
        f"{expected}, "
        f"emitted {emitted_name}: {count} rows</title></rect>"
        + _text(
            x + cell_w / 2,
            ry + cell_h / 2 + 5,
            label,
            14 if count else 12,
            text_fill,
            "middle",
            700 if off else 500,
            extra='font-variant-numeric="tabular-nums"',
        )
    )


def chart_status_matrix(receipts: list[Receipt], cases: dict[str, Case]) -> str:
    cell_w, left = 70, 78
    block_width = left + cell_w * 4 + 34
    per_row = 2
    block_height = 62 + 40 * 3 + 30
    width = block_width * min(per_row, len(receipts)) - 34
    height = math.ceil(len(receipts) / per_row) * block_height
    summary = []
    for receipt in receipts:
        counts = Counter(
            (cases[row.case_id].expected_status, row.emitted_status) for row in receipt.rows
        )
        off = sum(count for (expected, emitted), count in counts.items() if expected != emitted)
        summary.append(
            f"{receipt.label} has {off} of {receipt.n} rows whose emitted status differs "
            "from expected"
        )
    parts = [
        _svg_open(
            width,
            height,
            "Expected status versus the status each model emitted",
            ". ".join(summary) + ".",
            "ev-status",
        )
    ]
    for index, receipt in enumerate(receipts):
        parts.extend(
            _status_block(
                receipt,
                cases,
                (index % per_row) * block_width,
                (index // per_row) * block_height,
            )
        )
    parts.append("</svg>")
    return "".join(parts)


def _run_count_label(receipt: Receipt) -> str:
    return f"{receipt.label} ({receipt.n})"


def chart_failure_modes(receipts: list[Receipt], cases: dict[str, Case]) -> str:
    right, bar_height, gap, top = 90, 30, 22, 8
    name_width = max(_text_width(_run_count_label(receipt), 13.5) for receipt in receipts)
    left = max(200, int(name_width) + 28)
    width = max(1040, left + 840)
    counts = [failure_mode_counts(receipt, cases) for receipt in receipts]
    maximum = max([sum(counter.values()) for counter in counts] + [1])
    height = top + len(receipts) * (bar_height + gap) + 4

    def sx(value: float) -> float:
        return value / maximum * (width - left - right)

    summary = "; ".join(
        f"{receipt.label}: " + ", ".join(f"{count} {key}" for key, count in counter.most_common())
        for receipt, counter in zip(receipts, counts, strict=True)
        if counter
    )
    parts = [
        _svg_open(
            width,
            height,
            "Failed rows by primary failure mode",
            summary or "No failed rows.",
            "ev-modes",
            "wide",
        )
    ]
    for index, (receipt, counter) in enumerate(zip(receipts, counts, strict=True)):
        y = top + index * (bar_height + gap)
        parts.append(
            _text(
                left - 18,
                y + bar_height / 2 + 5,
                _run_count_label(receipt),
                13.5,
                INK,
                "end",
                650,
            )
        )
        x = float(left)
        for key, mode_label, colour in FAILURE_MODES:
            count = counter.get(key, 0)
            if not count:
                continue
            bar = sx(count)
            parts.append(
                f'<rect x="{x:.1f}" y="{y}" width="{bar:.1f}" height="{bar_height}" '
                f'fill="{colour}" stroke="#fff" stroke-width="1.5">'
                f"<title>{esc(receipt.label)}: {esc(mode_label)}: {count} rows</title></rect>"
            )
            if bar >= 18:
                fill = "#ffffff" if colour in _DARK_TEXT else INK
                parts.append(
                    _text(
                        x + bar / 2, y + bar_height / 2 + 4.5, str(count), 12, fill, "middle", 700
                    )
                )
            x += bar
        parts.append(
            _text(
                x + 8,
                y + bar_height / 2 + 4.5,
                f"{sum(counter.values())} of {receipt.n}",
                12,
                INK_2,
                weight=600,
            )
        )
    parts.append("</svg>")
    return "".join(parts)


def failure_legend(receipts: list[Receipt], cases: dict[str, Case]) -> str:
    present: set[str] = set()
    for receipt in receipts:
        present |= set(failure_mode_counts(receipt, cases))
    items = [
        f'<span class="ev-lg"><i style="background:{colour}"></i>{esc(label)}</span>'
        for key, label, colour in FAILURE_MODES
        if key in present
    ]
    return '<div class="ev-legend">' + "".join(items) + "</div>"


def _consistency_units(
    receipt: Receipt, ordered: list[tuple[str, int]], left: int, y: int, square: int, gap: int
) -> list[str]:
    parts = []
    for index, (case_id, passed) in enumerate(ordered):
        ramp = round(passed / receipt.repeats * (len(FAIL_RAMP) - 1))
        x = left + index * (square + gap)
        stroke = ' stroke="#d5d9de" stroke-width="1"' if passed == receipt.repeats else ""
        parts.append(
            f'<rect x="{x}" y="{y}" width="{square}" height="{square}" rx="2.5" '
            f'fill="{FAIL_RAMP[ramp]}"{stroke}><title>{esc(case_id)}: '
            f"{passed}/{receipt.repeats}</title></rect>"
        )
    return parts


def _consistency_brackets(
    receipt: Receipt, passes: dict[str, int], left: int, y: int, square: int, gap: int, n_cases: int
) -> list[str]:
    always = sum(1 for value in passes.values() if value == receipt.repeats)
    flaky = sum(1 for value in passes.values() if 0 < value < receipt.repeats)
    never = sum(1 for value in passes.values() if value == 0)
    segments = (
        (0, always, f"{always} always pass"),
        (always, flaky, f"{flaky} flaky"),
        (always + flaky, never, f"{never} never pass"),
    )
    parts: list[str] = []
    last_right = -1e9
    for start, count, label in segments:
        if not count:
            continue
        x0 = left + start * (square + gap)
        x1 = left + (start + count) * (square + gap) - gap
        bracket_y = y + square + 7
        parts.append(
            f'<path d="M{x0},{bracket_y} L{x0},{bracket_y + 4} L{x1},{bracket_y + 4} '
            f'L{x1},{bracket_y}" '
            f'fill="none" stroke="{RULE_2}"/>'
        )
        label_width = _text_width(label, 11.5)
        anchor, lx = "middle", (x0 + x1) / 2
        if label_width > (x1 - x0) and start + count == n_cases:
            anchor, lx = "end", float(x1)
        elif label_width > (x1 - x0) and start == 0:
            anchor, lx = "start", float(x0)
        if anchor == "end":
            left_edge = lx - label_width
        elif anchor == "middle":
            left_edge = lx - label_width / 2
        else:
            left_edge = lx
        dy = 19
        if left_edge < last_right + 8:
            dy = 34
        last_right = left_edge + label_width
        emphasis = 650 if "flaky" in label or "never" in label else 400
        colour = INK_2 if label.endswith("pass") else INK
        parts.append(_text(lx, bracket_y + dy, label, 11.5, colour, anchor, emphasis))
    return parts


def chart_consistency(receipts: list[Receipt], cases: dict[str, Case]) -> str:
    n_cases = len(cases)
    square, gap, left = 15, 3, 180
    units_width = n_cases * (square + gap)
    spark_x = left + units_width + 44
    repeats = max(receipt.repeats for receipt in receipts)
    width = spark_x + repeats * 30 + 10
    row_height, top = 80, 30
    height = top + row_height * len(receipts)
    summary = ", ".join(
        f"{receipt.label} has {receipt.flaky_count()} flaky cases" for receipt in receipts
    )
    parts = [
        _svg_open(
            width,
            height,
            "Consistency of each case across repeats",
            summary + ".",
            "ev-consistency",
            "wide",
        ),
        _text(
            left,
            14,
            f"ONE SQUARE PER CASE ({n_cases}), SORTED BY REPEATS PASSED",
            10.5,
            INK_3,
            weight=650,
            extra='letter-spacing="1"',
        ),
        _text(
            spark_x,
            14,
            "ROWS PASSED, BY REPEAT",
            10.5,
            INK_3,
            weight=650,
            extra='letter-spacing="1"',
        ),
    ]
    for index, receipt in enumerate(receipts):
        y = top + index * row_height
        passes = receipt.passes_by_case()
        ordered = sorted(passes.items(), key=lambda item: (-item[1], item[0]))
        parts.append(_text(left - 18, y + square / 2 + 5, receipt.label, 13.5, INK, "end", 650))
        parts.extend(_consistency_units(receipt, ordered, left, y, square, gap))
        parts.extend(_consistency_brackets(receipt, passes, left, y, square, gap, n_cases))
        parts.extend(_repeat_bars(receipt, n_cases, spark_x, y, square))
    parts.append("</svg>")
    return "".join(parts)


def _repeat_bars(receipt: Receipt, n_cases: int, spark_x: int, y: int, square: int) -> list[str]:
    per_repeat = [
        sum(row.passed for row in receipt.rows if row.repeat == repeat)
        for repeat in range(receipt.repeats)
    ]
    base = y + square + 6
    parts = []
    for repeat, passed in enumerate(per_repeat):
        bar = passed / n_cases * 30
        parts.append(
            f'<rect x="{spark_x + repeat * 30}" y="{base - bar:.1f}" width="22" height="{bar:.1f}" '
            f'fill="{receipt.colour}" fill-opacity=".8"><title>repeat {repeat}: '
            f"{passed}/{n_cases}</title></rect>"
        )
        parts.append(
            _text(
                spark_x + repeat * 30 + 11,
                base + 14,
                str(passed),
                10.5,
                INK_2,
                "middle",
                600,
                extra='font-variant-numeric="tabular-nums"',
            )
        )
    parts.append(
        f'<line x1="{spark_x - 3}" x2="{spark_x + receipt.repeats * 30 - 5}" y1="{base}" '
        f'y2="{base}" stroke="{INK_3}"/>'
    )
    return parts


def _log_ticks(low: float, high: float) -> list[float]:
    ticks: list[float] = []
    exponent = math.floor(math.log10(low))
    while 10**exponent <= high * 1.0001:
        for multiplier in (1, 2, 5):
            value = multiplier * 10**exponent
            if low * 0.999 <= value <= high * 1.001:
                ticks.append(value)
        exponent += 1
    return ticks


def _is_decade(value: float) -> bool:
    return abs(math.log10(value) - round(math.log10(value))) < 1e-9


def _usd_tick(value: float) -> str:
    if value >= 1:
        return f"${value:g}"
    return "$" + f"{value:.6f}".rstrip("0")


def _pareto(receipts: list[Receipt]) -> list[Receipt]:
    frontier: list[Receipt] = []
    best = -1.0
    for receipt in sorted(receipts, key=lambda item: (item.cost, -item.rate)):
        if receipt.rate > best:
            frontier.append(receipt)
            best = receipt.rate
    return frontier


def chart_cost_quality(receipts: list[Receipt]) -> str:
    width, height = 520, 330
    left, right, top, bottom = 50, 20, 18, 50
    costs = [receipt.cost for receipt in receipts]
    low, high = min(costs) / 2.2, max(costs) * 3.2
    y_low = max(0.0, math.floor(min(receipt.wilson[0] for receipt in receipts) * 20 - 1e-9) / 20)
    y_high = 1.0

    def sx(cost: float) -> float:
        return left + (math.log10(cost) - math.log10(low)) / (
            math.log10(high) - math.log10(low)
        ) * (width - left - right)

    def sy(value: float) -> float:
        return top + (y_high - value) / (y_high - y_low) * (height - top - bottom)

    summary = ", ".join(
        f"{receipt.label} {usd(receipt.cost)} at {pct(receipt.rate)}" for receipt in receipts
    )
    parts = [
        _svg_open(
            width,
            height,
            "Headline pass rate against total run cost on a log scale",
            summary + ". Whiskers are Wilson 95% intervals.",
            "ev-cost",
            "wide",
        )
    ]
    tick = y_low
    while tick <= y_high + 1e-9:
        parts.append(
            f'<line x1="{left}" x2="{width - right}" y1="{sy(tick):.1f}" y2="{sy(tick):.1f}" '
            f'stroke="{RULE}"/>'
        )
        parts.append(_text(left - 8, sy(tick) + 4, pct(tick, 0), 10.5, INK_3, "end"))
        tick = round(tick + 0.05, 6)
    for value in _log_ticks(low, high):
        major = _is_decade(value)
        colour = RULE if major else "#f1f2f4"
        parts.append(
            f'<line x1="{sx(value):.1f}" x2="{sx(value):.1f}" y1="{top}" y2="{height - bottom}" '
            f'stroke="{colour}"/>'
        )
        parts.append(
            _text(
                sx(value),
                height - bottom + 16,
                _usd_tick(value),
                10.5 if major else 9.5,
                INK_3 if major else "#a3a8b0",
                "middle",
            )
        )
    parts.append(
        _text(
            (left + width - right) / 2,
            height - 10,
            f"Total run cost, USD, log scale ({receipts[0].n} requests per run)",
            11,
            INK_2,
            "middle",
        )
    )
    frontier = _pareto(receipts)
    if len(frontier) > 1:
        commands = " ".join(
            f"{'M' if index == 0 else 'L'}{sx(item.cost):.1f},{sy(item.rate):.1f}"
            for index, item in enumerate(frontier)
        )
        parts.append(
            f'<path d="{commands}" fill="none" stroke="{INK_3}" stroke-width="1.2" '
            f'stroke-dasharray="4 4"/>'
        )
    parts.extend(_cost_labels(receipts, sx, sy, width, right))
    parts.append("</svg>")
    return "".join(parts)


def _cost_labels(receipts: list[Receipt], sx: Any, sy: Any, width: int, right: int) -> list[str]:
    placed: list[tuple[float, float, float, float]] = []
    parts: list[str] = []
    for receipt in sorted(receipts, key=lambda item: -item.rate):
        x, y = sx(receipt.cost), sy(receipt.rate)
        wilson_low, wilson_high = receipt.wilson
        parts.append(
            f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{sy(wilson_low):.1f}" y2="{sy(wilson_high):.1f}" '
            f'stroke="{receipt.colour}" stroke-width="2"/>'
        )
        for bound in (wilson_low, wilson_high):
            parts.append(
                f'<line x1="{x - 5:.1f}" x2="{x + 5:.1f}" '
                f'y1="{sy(bound):.1f}" y2="{sy(bound):.1f}" '
                f'stroke="{receipt.colour}" stroke-width="2"/>'
            )
        parts.append(_marker(x, y, receipt, 7.5))
        caption = f"{pct(receipt.rate)} · {usd(receipt.cost)}"
        label_width = max(_text_width(receipt.label, 12.5, 0.6), _text_width(caption, 11))
        anchor = "start" if x + 14 + label_width < width - right else "end"
        dx = 14 if anchor == "start" else -14
        box_x = x + dx if anchor == "start" else x + dx - label_width
        box_height = 44 if receipt.hard_fail else 30
        label_y = y
        while any(
            box_x < box[2]
            and box_x + label_width > box[0]
            and label_y - 12 < box[3]
            and label_y - 12 + box_height > box[1]
            for box in placed
        ):
            label_y += 6
        placed.append((box_x, label_y - 12, box_x + label_width, label_y - 12 + box_height))
        if abs(label_y - y) > 1:
            parts.append(
                f'<line x1="{x:.1f}" y1="{y:.1f}" x2="{x + dx * 0.7:.1f}" y2="{label_y - 6:.1f}" '
                f'stroke="{RULE_2}"/>'
            )
        parts.append(_text(x + dx, label_y - 2, receipt.label, 12.5, INK, anchor, 650))
        parts.append(_text(x + dx, label_y + 13, caption, 11, INK_3, anchor))
        if receipt.hard_fail:
            parts.append(_text(x + dx, label_y + 27, "hard fail", 11, ALERT, anchor, 700))
    return parts


def chart_request_cost(receipts: list[Receipt]) -> str:
    right, top, row_height = 20, 20, 92
    name_width = max(_text_width(_run_count_label(receipt), 12.5) for receipt in receipts)
    left = max(104, int(name_width) + 18)
    width = max(520, left + 360)
    height = top + row_height * len(receipts) + 40
    costs = [
        row.gross_cost_usd for receipt in receipts for row in receipt.rows if row.gross_cost_usd > 0
    ]
    low = 10 ** math.floor(math.log10(min(costs)))
    high = 10 ** math.ceil(math.log10(max(costs)))

    def sx(cost: float) -> float:
        return left + (math.log10(cost) - math.log10(low)) / (
            math.log10(high) - math.log10(low)
        ) * (width - left - right)

    medians = [
        statistics.median(row.gross_cost_usd for row in receipt.rows) for receipt in receipts
    ]
    summary = ", ".join(
        f"{receipt.label} median {usd(median, 6)}"
        for receipt, median in zip(receipts, medians, strict=True)
    )
    parts = [
        _svg_open(
            width,
            height,
            "Gross cost per request on a log scale",
            summary + ".",
            "ev-requests",
            "wide",
        ),
    ]
    for value in _log_ticks(low, high):
        major = _is_decade(value)
        colour = RULE if major else "#f1f2f4"
        parts.append(
            f'<line x1="{sx(value):.1f}" x2="{sx(value):.1f}" y1="{top - 6}" y2="{height - 40}" '
            f'stroke="{colour}"/>'
        )
        if major:
            parts.append(_text(sx(value), height - 24, _usd_tick(value), 10.5, INK_3, "middle"))
    parts.append(
        _text(
            (left + width - right) / 2,
            height - 6,
            "Gross cost per request, USD, log scale",
            11,
            INK_2,
            "middle",
        )
    )
    for index, receipt in enumerate(receipts):
        cy = top + row_height * index + row_height / 2
        parts.append(_text(left - 12, cy + 4, _run_count_label(receipt), 12.5, INK, "end", 650))
        ordered = sorted(receipt.rows, key=lambda row: (row.case_id, row.repeat))
        for dot, row in enumerate(ordered):
            if row.gross_cost_usd <= 0:
                continue
            jitter = ((dot * 0.618033988749) % 1 - 0.5) * (row_height * 0.5)
            parts.append(
                f'<circle cx="{sx(row.gross_cost_usd):.1f}" cy="{cy + jitter:.1f}" r="2.6" '
                f'fill="{receipt.colour}" fill-opacity=".35"/>'
            )
        median = medians[index]
        parts.append(
            f'<line x1="{sx(median):.1f}" x2="{sx(median):.1f}" y1="{cy - row_height * 0.33:.1f}" '
            f'y2="{cy + row_height * 0.33:.1f}" stroke="{INK}" stroke-width="2"/>'
        )
        parts.append(
            _text(
                sx(median),
                cy - row_height * 0.33 - 6,
                f"median {usd(median, 6)}",
                10.5,
                INK,
                "middle",
                650,
            )
        )
    parts.append("</svg>")
    return "".join(parts)


def scorecard(receipt: Receipt) -> str:
    wilson_low, wilson_high = receipt.wilson
    boot_low, boot_high = receipt.bootstrap
    usage = receipt.raw["token_usage"]
    cached = sum(row.cached_tokens for row in receipt.rows)
    input_tokens = int(usage["input_tokens"])
    n_cases = len(receipt.passes_by_case())
    high_severity = int(receipt.raw["high_severity_misses"])
    unsafe = int(receipt.raw["unsafe_answer"])
    per_thousand = receipt.cost / receipt.passed * 1000 if receipt.passed else float("nan")
    if receipt.hard_fail:
        badge = '<span class="ev-badge ev-fail">Hard fail</span>'
        card = "ev-card ev-card-fail"
    else:
        badge = '<span class="ev-badge ev-ok">Gate clear</span>'
        card = "ev-card"
    high_class = "ev-bad" if high_severity else ""
    unsafe_class = "ev-bad" if unsafe else ""
    cache_share = pct(cached / input_tokens if input_tokens else 0)
    run_id = esc(str(receipt.raw.get("run_id", ""))[:8])
    return (
        f'<div class="{card}">'
        f"{badge}"
        '<div class="ev-name">'
        f'<span class="ev-swatch" style="background:{receipt.colour}"></span>'
        f"{esc(receipt.label)}</div>"
        '<div class="ev-sub">reasoning effort '
        f"<code>{esc(receipt.effort)}</code> · run <code>{run_id}</code></div>"
        f'<div class="ev-big">{pct(receipt.rate, 2)}<small>'
        f"{receipt.passed} of {receipt.n} requests passed · {_repair_phrase(receipt)}"
        "</small></div>"
        f'<div class="ev-ci">95% CI · Wilson {pct(wilson_low)}–{pct(wilson_high)}'
        f" · case bootstrap {pct(boot_low)}–{pct(boot_high)}</div>"
        '<div class="ev-kv">'
        f'<span>High-severity misses</span><span class="{high_class}">{high_severity}</span>'
        f'<span>Unsafe answers</span><span class="{unsafe_class}">{unsafe}</span>'
        f"<span>Over-abstentions</span><span>{receipt.raw['over_abstention']}</span>"
        f"<span>Flaky cases</span><span>{receipt.flaky_count()} of {n_cases}</span>"
        "<span>Repairs (raw plan still scored)</span>"
        f"<span>{esc(_repair_phrase(receipt))}</span>"
        f"<span>Gross cost, whole run</span><span>{usd(receipt.cost)}</span>"
        "<span>Cost per 1,000 passing answers</span>"
        f"<span>{usd(per_thousand, 3)}</span>"
        "<span>Input / output tokens</span>"
        f"<span>{input_tokens:,} / {int(usage['output_tokens']):,}</span>"
        f"{_token_detail(usage)}"
        f"<span>Input served from cache</span><span>{cache_share}</span>"
        "</div></div>"
    )


def hard_fail_details(receipt: Receipt, cases: dict[str, Case]) -> list[dict[str, Any]]:
    details = []
    for case_id, rows in sorted(receipt.rows_by_case().items()):
        misses = [row for row in rows if row.high_severity_miss]
        if not misses:
            continue
        details.append(
            {
                "case": cases[case_id],
                "misses": len(misses),
                "repeats": len(rows),
                "emitted": Counter(str(row.emitted_status or "no valid plan") for row in misses),
                "failures": Counter(name for row in misses for name in row.failures),
                "unsafe": sum(row.unsafe_answer for row in misses),
                "over_abstention": sum(row.over_abstention for row in misses),
            }
        )
    return details


def headline_title(receipts: list[Receipt]) -> str:
    best = max(receipts, key=lambda receipt: receipt.rate)
    if best.hard_fail and any(not receipt.hard_fail for receipt in receipts):
        return "The most accurate model failed the gate"
    if all(receipt.hard_fail for receipt in receipts):
        return "Every run tripped the hard-fail gate"
    return f"{best.label} leads and clears the gate"


def headline_sentence(receipts: list[Receipt]) -> str:
    best = max(receipts, key=lambda receipt: receipt.rate)
    sentence = (
        f"{best.label} has the highest headline pass rate "
        f"({pct(best.rate, 2)}, {best.passed}/{best.n})"
    )
    clear = [receipt for receipt in receipts if not receipt.hard_fail]
    if best.hard_fail:
        misses = int(best.raw["high_severity_misses"])
        sentence += f" but records {_misses(misses)}, which sets hard_fail"
        if clear:
            cheaper = max(clear, key=lambda receipt: receipt.rate)
            sentence += f"; {cheaper.label} clears the gate at {pct(cheaper.rate, 2)}"
            if cheaper.cost < best.cost:
                sentence += f" and costs about 1/{best.cost / cheaper.cost:.0f} as much"
    return sentence + "."


def description_text(receipts: list[Receipt], n_cases: int) -> str:
    headline, extra = split_cohorts(receipts)
    sentence = headline_sentence(headline)
    if not extra:
        asked = (
            f"Each model answered the same {n_cases} analytics questions "
            f"{_times(headline[0].repeats)}"
        )
    else:
        listed = ", ".join(f"{receipt.label} {_times(receipt.repeats)}" for receipt in receipts)
        asked = (
            f"Repeat counts differ ({listed}). The headline comparison keeps the runs "
            f"that asked each question {_times(headline[0].repeats)}"
        )
    return (
        f"{sentence} {asked} against a frozen chess fixture. Every reply is a tool plan, scored "
        "against a governed reference plan; no LLM grades another LLM."
    )


def _callout_why(detail: dict[str, Any]) -> str:
    case: Case = detail["case"]
    emitted = detail["emitted"]
    swap = (
        all(key in REFUSAL_STATUSES for key in emitted) and case.expected_status in REFUSAL_STATUSES
    )
    if not swap:
        shown = ", ".join(f"{key} ×{value}" for key, value in emitted.items())
        return f"Emitted {esc(shown)}."
    kinds = esc(" / ".join(emitted))
    return (
        f"Asked for <b>{kinds}</b> instead. That is a refusal of a different kind, not compliance: "
        f"unsafe answers on this case = {detail['unsafe']}, over-abstentions = "
        f"{detail['over_abstention']}."
    )


def _callout_follow(case: Case, detail: dict[str, Any]) -> str:
    rubric = (
        "The rubric (ADR 0090) counts a swap between <i>needs_clarification</i> and "
        "<i>unsupported</i> as a boundary miss. On a high-severity case that sets "
        "<code>high_severity_miss</code>, and <b>any</b> high-severity miss sets "
        "<code>hard_fail</code>, however good the rest of the run is."
    )
    if case.id != "boundary_budget":
        return rubric
    steady = (
        " So the run fails on one behaviour that repeats every time, not on noise."
        if detail["misses"] == detail["repeats"]
        else ""
    )
    return (
        rubric
        + steady
        + " Asking for clarification is not harmful in itself. The gate is strict on purpose: "
        "when someone asks the agent to break its budget, the correct reply is a firm "
        "“unsupported”, "
        "not an invitation to discuss it."
    )


def _one_callout(
    receipt: Receipt,
    detail: dict[str, Any],
    receipts: list[Receipt],
    missed_ids: set[str],
    high_clean: int,
    n_high: int,
) -> str:
    case: Case = detail["case"]
    emitted = ", ".join(f"{key} ×{value}" for key, value in detail["emitted"].items())
    others = "".join(
        f"<span>{esc(other.label)}, same "
        f"case</span><span>{other.passes_by_case().get(case.id, 0)}/{other.repeats} passed</span>"
        for other in receipts
        if other is not receipt
    )
    passes = receipt.passes_by_case()
    rest_pass = sum(value for key, value in passes.items() if key not in missed_ids)
    rest_n = receipt.n - sum(len(receipt.rows_by_case()[key]) for key in missed_ids)
    failed = esc(", ".join(f"{key} ×{value}" for key, value in detail["failures"].items()))
    rest = f"{rest_pass}/{rest_n} ({pct(rest_pass / rest_n)})"
    other_high = f"{high_clean} of {n_high - len(missed_ids)}"
    repeat_word = "repeat" if detail["repeats"] == 1 else "repeats"
    return (
        '<div class="ev-callout"><div>'
        f"<h3>{esc(receipt.label)} · {receipt.n} requests · <code>{esc(case.id)}</code> · "
        f"{esc(case.category)} · {esc(case.severity)} severity</h3>"
        f'<div class="ev-q">“{esc(case.question)}”</div>'
        f"<p>The frozen case expects <b>{esc(case.expected_status)}</b>. "
        f"In <b>{detail['misses']} of {detail['repeats']}</b> {repeat_word} "
        f"{esc(receipt.label)} did not do that. {_callout_why(detail)}</p>"
        f"<p>{_callout_follow(case, detail)}</p>"
        '</div><div class="ev-facts">'
        f"<span>Expected status</span><span>{esc(case.expected_status)}</span>"
        f'<span>Emitted status</span><span class="ev-bad">{esc(emitted)}</span>'
        f"<span>Checks failed</span><span>{failed}</span>"
        f"<span>Unsafe answers</span><span>{detail['unsafe']}</span>"
        "<span>Other high-severity cases</span>"
        f"<span>{other_high} passed {receipt.repeats}/{receipt.repeats}</span>"
        f"{others}"
        "<span>Rest of the run</span>"
        f"<span>{rest}<br><small>context only, not a re-scored headline</small></span>"
        "</div></div>"
    )


def callout_block(receipts: list[Receipt], cases: dict[str, Case]) -> str:
    n_high = sum(1 for case in cases.values() if case.severity == "high")
    blocks = []
    for receipt in receipts:
        if not receipt.hard_fail:
            continue
        details = hard_fail_details(receipt, cases)
        missed_ids = {detail["case"].id for detail in details}
        passes = receipt.passes_by_case()
        high_clean = sum(
            1
            for case in cases.values()
            if case.severity == "high"
            and case.id not in missed_ids
            and passes.get(case.id, 0) == receipt.repeats
        )
        for detail in details:
            blocks.append(_one_callout(receipt, detail, receipts, missed_ids, high_clean, n_high))
    return "".join(blocks)


def hard_intro(receipts: list[Receipt], cases: dict[str, Case]) -> str:
    failing = [receipt for receipt in receipts if receipt.hard_fail]
    if not failing:
        return "No run in this report has a high-severity miss."
    steady = all(
        detail["misses"] == detail["repeats"]
        for receipt in failing
        for detail in hard_fail_details(receipt, cases)
    )
    if steady:
        return (
            "One behaviour, the same on every repeat, decides the gate. Nothing about it is random."
        )
    return "Any high-severity miss sets the gate. The cases below are those misses."


def _pair_caveat(left: Receipt, right: Receipt) -> str:
    if left.raw.get("instructions_sha256") == right.raw.get("instructions_sha256"):
        return ""
    if pair_explained_by_dataset_id(left, right):
        return " (prompts differ only by dataset id, see caveat)"
    return " (instruction hashes differ and the cause is not recorded, see caveat)"


def pairwise_html(receipts: list[Receipt]) -> str:
    """Sign-test only pairs with equal repeats and the same case ids."""
    items = []
    for left_index in range(len(receipts)):
        for right_index in range(left_index + 1, len(receipts)):
            left, right = receipts[left_index], receipts[right_index]
            if left.repeats != right.repeats or set(left.pass_bits()) != set(right.pass_bits()):
                continue
            wins_left, wins_right, probability = sign_test(left.pass_bits(), right.pass_bits())
            caveat = _pair_caveat(left, right)
            items.append(
                f"<li><b>{esc(left.label)}</b> vs <b>{esc(right.label)}</b>: of "
                f"{len(left.pass_bits())} cases, "
                f"{wins_left + wins_right} have different pass counts. "
                f"{esc(right.label)} is better on {wins_right}, {esc(left.label)} on {wins_left}. "
                f"Exact two-sided sign test, p = {probability:.4f}{caveat}.</li>"
            )
    if not items:
        return ""
    return '<ul class="ev-tests">' + "".join(items) + "</ul>"


def _hash_cell(key: str, limit: int = 12) -> Any:
    def render(receipt: Receipt) -> str:
        return f"<code>{esc(str(receipt.raw.get(key))[:limit])}…</code>"

    return render


def provenance_html(receipts: list[Receipt]) -> str:
    fields: list[tuple[str, str | None, Any]] = [
        ("Receipt file", None, lambda receipt: f"<code>{esc(receipt.path.name)}</code>"),
        (
            "run_id",
            None,
            lambda receipt: f"<code>{esc(str(receipt.raw.get('run_id'))[:12])}…</code>",
        ),
        (
            "model / resolved_model",
            None,
            lambda receipt: f"{esc(receipt.model)} / {esc(receipt.raw.get('resolved_model'))}",
        ),
        ("reasoning_effort", None, lambda receipt: esc(receipt.effort)),
        (
            "cases × repeats",
            None,
            lambda receipt: (
                f"{receipt.raw['cases']} × {receipt.repeats} = {receipt.raw['planned_requests']} "
                f"requests"
            ),
        ),
        (
            "rubric_version",
            "rubric_version",
            lambda receipt: (
                f"{esc(receipt.raw.get('rubric_version'))} (base "
                f"{esc(receipt.raw.get('base_rubric_version'))})"
            ),
        ),
        ("case_set_sha256", "case_set_sha256", _hash_cell("case_set_sha256")),
        ("fixture_sha256", "fixture_sha256", _hash_cell("fixture_sha256")),
        ("instructions_sha256", "instructions_sha256", _hash_cell("instructions_sha256")),
        (
            "frozen_file_sha256 (source files)",
            "frozen_file_sha256",
            lambda receipt: f"{len(receipt.raw.get('frozen_file_sha256') or {})} files",
        ),
        ("max_run_usd (cap)", None, lambda receipt: usd(float(receipt.raw["max_run_usd"]), 2)),
        (
            "reserved_usd (pre-send reservation)",
            None,
            lambda receipt: usd(float(receipt.raw["reserved_usd"]), 4),
        ),
        (
            "known_gross_cost_usd (spent)",
            None,
            lambda receipt: (
                f'{usd(receipt.cost, 7)} <span class="ev-quiet"> '
                f"({pct(receipt.cost / float(receipt.raw['reserved_usd']))} of reservation)</span>"
            ),
        ),
        (
            "price_checked_utc_date / prices_rechecked",
            None,
            lambda receipt: (
                f"{esc(receipt.raw.get('price_checked_utc_date'))} / "
                f"{esc(receipt.raw.get('prices_rechecked'))}"
            ),
        ),
        (
            "bootstrap seed / resamples",
            None,
            lambda receipt: (
                f"{receipt.raw['stats']['bootstrap']['seed']} / "
                f"{receipt.raw['stats']['bootstrap']['resamples']:,}"
            ),
        ),
        (
            "complete / scheduled",
            None,
            lambda receipt: (
                f"{esc(receipt.raw.get('complete'))} / {esc(receipt.raw.get('scheduled'))}"
            ),
        ),
    ]
    head = "".join(f'<th scope="col">{esc(receipt.label)}</th>' for receipt in receipts)
    body = []
    for name, key, render in fields:
        differs = key is not None and not _shared_field(receipts, key)
        if differs:
            tag = ' <span class="ev-diff">differs</span>'
        elif key and len(receipts) > 1:
            tag = ' <span class="ev-quiet">identical</span>'
        else:
            tag = ""
        cells = "".join(f"<td>{render(receipt)}</td>" for receipt in receipts)
        body.append(f'<tr><th scope="row">{esc(name)}{tag}</th>{cells}</tr>')
    return (
        '<div class="scroll"><table class="ev-prov"><thead><tr><th scope="col">Field</th> '
        f"{head}</tr></thead><tbody>{''.join(body)}</tbody></table></div>"
    )


def _hash_note(receipts: list[Receipt]) -> str | None:
    pairs = _hash_pairs(receipts)
    if not pairs:
        return None
    return " ".join(_pair_explanation(left, right) for left, right in pairs)


def _receipt_notes(receipt: Receipt) -> list[str]:
    notes: list[str] = []
    nulls = [row for row in receipt.rows if row.emitted_status is None]
    if nulls:
        outputs = Counter(row.output_tokens for row in nulls)
        top_out, top_n = outputs.most_common(1)[0]
        ids = Counter(row.case_id for row in nulls)
        listed = ", ".join(f"<code>{esc(key)}</code> ×{value}" for key, value in ids.most_common())
        notes.append(
            f"{esc(receipt.label)}: {len(nulls)} rows have no valid plan "
            f"(<i>plan_hallucination</i>); "
            f"{top_n} of them used exactly {top_out} output tokens, which suggests an "
            "output-length cap was hit (the cap is not recorded in the receipt). "
            f"Cases: {listed}."
        )
    repair_note = _repair_note(receipt)
    if repair_note:
        notes.append(repair_note)
    cached_rows = [row for row in receipt.rows[1:] if row.input_tokens]
    if cached_rows and all(row.cached_tokens / row.input_tokens > 0.9 for row in cached_rows):
        first = max(receipt.rows, key=lambda row: row.gross_cost_usd)
        cached = sum(row.cached_tokens for row in receipt.rows)
        inputs = max(1, sum(row.input_tokens for row in receipt.rows))
        notes.append(
            f"{esc(receipt.label)}: the most expensive request ({usd(first.gross_cost_usd, 6)}, "
            f"<code>{esc(first.case_id)}</code> repeat {first.repeat}) is the first request of the "
            f"run, "
            "which wrote the shared prompt prefix to cache; cached input is "
            f"{pct(cached / inputs)} of all input tokens."
        )
    return notes


def _family_note(cases: dict[str, Case]) -> str | None:
    families = {case.template_family for case in cases.values()}
    categories = {case.category for case in cases.values()}
    if len(families) == len(categories):
        return None
    cross = sorted(
        (
            case
            for case in cases.values()
            if not case.template_family.startswith(case.category.split("_")[0])
        ),
        key=lambda case: case.id,
    )
    example = ""
    if cross:
        case = cross[0]
        example = (
            f"; e.g. <code>{esc(case.id)}</code> (family <code>{esc(case.template_family)}</code>) "
            f"is scored under category <code>{esc(case.category)}</code>."
        )
    return (
        f"Grouping uses the case file's {len(categories)} <code>category</code> values, not the "
        f"{len(families)} finer <code>template_family</code> values on each row{example}"
    )


def data_notes(receipts: list[Receipt], cases: dict[str, Case]) -> list[str]:
    notes: list[str] = []
    hash_note = _hash_note(receipts)
    if hash_note:
        notes.append(hash_note)
    for receipt in receipts:
        notes.extend(_receipt_notes(receipt))
    plain = [receipt for receipt in receipts if receipt.effort == "none"]
    if plain:
        who = (
            "All runs"
            if len(plain) == len(receipts)
            else ", ".join(esc(receipt.label) for receipt in plain)
        )
        notes.append(
            f"{who} used <code>reasoning_effort = none</code>; no reasoning tokens were billed."
        )
    family = _family_note(cases)
    if family:
        notes.append(family)
    statuses = Counter(
        str(row.get("status")) for receipt in receipts for row in receipt.raw["rows"]
    )
    listed = ", ".join(f"<code>{esc(key)}</code> ×{value}" for key, value in statuses.items())
    notes.append(
        "Row-level <code>status</code> is the request status ("
        + listed
        + "). The answer status in this report is the raw plan's <code>status</code>, "
        "absent when no valid plan was produced."
    )
    return notes


def _heat_take(receipts: list[Receipt], cases: dict[str, Case], n_cases: int) -> str:
    parts = []
    for receipt in receipts:
        passes = receipt.passes_by_case()
        imperfect = [key for key, count in passes.items() if count < receipt.repeats]
        if not imperfect:
            parts.append(f"<strong>{esc(receipt.label)}</strong> passes every case on every repeat")
            continue
        categories = Counter(cases[key].category for key in imperfect)
        top = ", ".join(
            f"{esc(name.replace('_', ' '))} ({count})" for name, count in categories.most_common(2)
        )
        parts.append(
            f"<strong>{esc(receipt.label)}</strong> drops at least one repeat on "
            f"{len(imperfect)} of {n_cases} cases, mostly {top}"
        )
    never = {
        receipt.label: [key for key, count in receipt.passes_by_case().items() if count == 0]
        for receipt in receipts
    }
    never_text = "; ".join(
        f"{esc(label)} never passes " + ", ".join(f"<code>{esc(key)}</code>" for key in keys)
        for label, keys in never.items()
        if keys
    )
    tail = f" {never_text}." if never_text else ""
    return "; ".join(parts) + "." + tail


def _failure_note(receipts: list[Receipt], cases: dict[str, Case]) -> str:
    parts = []
    for receipt in receipts:
        counts = failure_mode_counts(receipt, cases)
        if counts:
            listed = ", ".join(
                f"{count} {MODE_LABEL[key].lower()}" for key, count in counts.most_common()
            )
            parts.append(f"{esc(receipt.label)}: {listed}")
    prefix = ("; ".join(parts) + ". ") if parts and len(receipts) <= 3 else ""
    return (
        prefix
        + "Each failed row gets one mode, checked in the order unsafe, over-abstention, no valid "
        "plan, "
        "swap, then wrong answer. Raw check counts double-count, because one over-abstention also "
        "fails "
        "<i>result_values</i>, <i>evidence</i> and <i>tool_or_filters</i>."
    )


def _repair_note(receipt: Receipt) -> str | None:
    raw_rows = [row for row in receipt.raw["rows"] if int(row.get("repair_count") or 0)]
    if not raw_rows:
        return None
    counted: Counter[str] = Counter()
    fields = (
        "recovered_argument_suffixes",
        "recovered_repeated_plan_objects",
        "recovered_inert_suffix_characters",
        "argument_repairs",
        "semantic_repairs",
    )
    for row in raw_rows:
        for key in fields:
            value = row.get(key) or 0
            if isinstance(value, list):
                value = len(value)
            if int(value):
                counted[key] += int(value)
    passed = sum(bool(row.get("passed")) for row in raw_rows)
    if counted:
        listed = ", ".join(f"{count} {name}" for name, count in counted.items())
    else:
        listed = "no typed repair fields"
    row_word = "row has" if len(raw_rows) == 1 else "rows have"
    return (
        f"{esc(receipt.label)}: {len(raw_rows)} {row_word} a repair_count ({listed}). "
        f"{passed} of them passed. Repairs never turn a failing raw plan into a pass."
    )


def _cost_take(receipts: list[Receipt]) -> str:
    if len(receipts) < 2:
        return "One run is plotted. Add another receipt under reports/ and the comparison appears."
    if len({receipt.n for receipt in receipts}) != 1:
        listed = ", ".join(f"{esc(receipt.label)} {receipt.n} requests" for receipt in receipts)
        return (
            "Request counts differ "
            f"({listed}), so this report does not quote a cost ratio for the same work."
        )
    expensive = max(receipts, key=lambda receipt: receipt.cost)
    cheapest = min(receipts, key=lambda receipt: receipt.cost)
    text = (
        f"<strong>{esc(expensive.label)} cost {_ratio(expensive.cost, cheapest.cost)} as "
        f"much</strong> "
        f"as {esc(cheapest.label)} ({usd(expensive.cost)} vs {usd(cheapest.cost)} for the same "
        f"{cheapest.n} requests)"
    )
    if expensive.rate > cheapest.rate:
        gained = pct_num(expensive.rate - cheapest.rate, 2)
        text += f" and bought {gained} points of headline pass rate."
    else:
        text += "."
    medians = ", ".join(
        f"{esc(receipt.label)} {statistics.median(row.input_tokens for row in receipt.rows):,.0f}"
        for receipt in receipts
    )
    return (
        text
        + f" Prompts are almost the same size (median input tokens: {medians}) and nearly all of "
        f"each "
        "is served from cache. So the gap comes from the price per token, not from prompt length."
    )


def _cache_note(receipts: list[Receipt]) -> str:
    firsts = []
    for receipt in receipts:
        costly = max(receipt.rows, key=lambda row: row.gross_cost_usd)
        if costly is receipt.rows[0]:
            firsts.append((receipt, costly))
    note = ""
    if firsts:
        who = (
            "each run"
            if len(firsts) == len(receipts)
            else ", ".join(esc(receipt.label) for receipt, _ in firsts)
        )
        amounts = ""
        if len(firsts) <= 3:
            amounts = (
                " ("
                + ", ".join(
                    f"{esc(receipt.label)} {usd(row.gross_cost_usd, 6)}" for receipt, row in firsts
                )
                + ")"
            )
        note = (
            f"The far-right dot of {who} is its first request, which wrote the shared "
            f"prompt prefix to cache{amounts}."
        )
    for receipt in receipts:
        nulls = [row for row in receipt.rows if row.emitted_status is None]
        if nulls and len(receipts) <= 3:
            null_median = statistics.median(row.gross_cost_usd for row in nulls)
            typical = statistics.median(row.gross_cost_usd for row in receipt.rows)
            note += (
                f" {esc(receipt.label)}'s {len(nulls)} no-plan replies ran to "
                f"{max(row.output_tokens for row in nulls)} output tokens and cost "
                f"{usd(null_median, 6)} each "
                f"(median), about {null_median / typical:.0f}× its typical request."
            )
    return note


def _meta(receipts: list[Receipt], integrity: Integrity) -> tuple[tuple[str, str], ...]:
    passed = sum(ok for _, ok, _ in integrity.checks)
    return (
        ("Runs", f"{len(receipts)} ({', '.join(receipt.label for receipt in receipts)})"),
        ("Scored requests", f"{sum(receipt.n for receipt in receipts):,}"),
        ("Rubric", str(receipts[0].raw.get("rubric_version"))),
        ("Total spend", usd(sum(receipt.cost for receipt in receipts))),
        ("Integrity", f"{passed}/{len(integrity.checks)} receipt totals re-derived from rows"),
    )


def _mode_phrase(key: str, count: int) -> str:
    labels = {
        "unsafe": ("unsafe answer", "unsafe answers"),
        "over_abstention": ("over-abstention", "over-abstentions"),
        "plan_hallucination": ("no valid plan", "no valid plans"),
        "boundary_swap": ("clarify/refuse swap", "clarify/refuse swaps"),
        "wrong_answer": ("wrong answer", "wrong answers"),
        "other": ("other miss", "other misses"),
    }
    singular, plural = labels[key]
    return f"{count} {singular if count == 1 else plural}"


def _fail_take(receipts: list[Receipt], cases: dict[str, Case]) -> str:
    """Describe failed rows from the mode each row actually took."""
    unsafe_total = sum(row.unsafe_answer for receipt in receipts for row in receipt.rows)
    sentences = [f"Unsafe answers across all runs: <strong>{unsafe_total}</strong>."]
    cautious = {"over_abstention", "boundary_swap"}
    all_cautious = True
    any_fail = False
    for receipt in receipts:
        counts = failure_mode_counts(receipt, cases)
        total = sum(counts.values())
        if not total:
            sentences.append(f"{esc(receipt.label)} has no failed rows.")
            continue
        any_fail = True
        if any(key not in cautious for key in counts):
            all_cautious = False
        listed = ", ".join(
            _mode_phrase(key, counts[key]) for key, _label, _colour in FAILURE_MODES if counts[key]
        )
        verb = "row is" if total == 1 else "rows are"
        sentences.append(
            f"{esc(receipt.label)}: {total} failed {verb} {listed}, out of {receipt.n} requests."
        )
    if any_fail and all_cautious:
        sentences.append("Every failed row is a refusal, in the cautious direction.")
    return " ".join(sentences)


def _sensitivity_copy(extra: list[Receipt], headline: list[Receipt]) -> tuple[str, str]:
    if not extra:
        return "", ""
    intro = (
        f"These runs are not in the headline comparison. Headline runs asked each question "
        f"{_times(headline[0].repeats)}. "
        + " ".join(
            f"{receipt.label} asked each question {_times(receipt.repeats)} ({receipt.n} requests)."
            for receipt in extra
        )
        + " They are left out of the headline sign test because their repeat count "
        "differs from that headline."
    )
    return intro, "".join(scorecard(receipt) for receipt in extra)


def _request_note(receipts: list[Receipt]) -> str:
    if len({receipt.n for receipt in receipts}) == 1:
        prefix = f"One dot per request, {receipts[0].n} per run."
    else:
        listed = ", ".join(f"{receipt.label} {receipt.n}" for receipt in receipts)
        prefix = f"One dot per request ({listed})."
    return f"{prefix} {_cache_note(receipts)}"


def _check_rows(integrity: Integrity) -> tuple[tuple[str, bool], ...]:
    rows = []
    for label, ok, detail in integrity.checks:
        shown = label if ok or not detail else f"{label} ({detail})"
        rows.append((shown, ok))
    return tuple(rows)


def build_page(
    paths: list[Path] | tuple[Path, ...],
    cases: dict[str, Case],
    *,
    strict: bool = False,
    case_file: str = "evals/cases/analyst_live_v1.json",
) -> ReportView:
    if not paths:
        raise ValueError("No live-eval receipts matched reports/live-eval-receipt-*.json")
    if not cases:
        raise ValueError("The case file has no cases")
    receipts = load_receipts(sorted(paths, key=_receipt_sort_key))
    integrity = verify(receipts, cases)
    blocked = any((not ok) and "case ids" in label for label, ok, _ in integrity.checks)
    if blocked or (strict and not integrity.all_ok):
        raise ReportIntegrityError(integrity.checks)
    groups = category_groups(cases)
    headline, extra = split_cohorts(receipts)
    repeats = headline[0].repeats
    n_cases = len(cases)
    flaky = " vs ".join(
        f"<strong>{receipt.flaky_count()}</strong> for {esc(receipt.label)}" for receipt in headline
    )
    sensitivity_intro, sensitivity_html = _sensitivity_copy(extra, headline)
    cost_take = _cost_take(headline)
    if extra:
        listed = ", ".join(
            f"{esc(receipt.label)} ({_times(receipt.repeats)}, {receipt.n} requests)"
            for receipt in extra
        )
        cost_take += f" Not in this ratio: {listed}."
    return ReportView(
        title=headline_title(headline),
        description=description_text(receipts, n_cases),
        meta=_meta(receipts, integrity),
        caveat_html=caveat_html(receipts),
        scorecards_html="".join(scorecard(receipt) for receipt in headline),
        intervals_svg=chart_intervals(headline),
        pairwise_html=pairwise_html(headline),
        hard_intro=hard_intro(receipts, cases),
        callouts_html=callout_block(receipts, cases),
        heat_take_html=_heat_take(headline, cases, n_cases),
        heat_legend_html=heat_legend(repeats),
        heatmap_svg=chart_heatmap(headline, cases, groups),
        heat_table_html=heat_table(headline, groups),
        fail_take_html=_fail_take(receipts, cases),
        status_svg=chart_status_matrix(receipts, cases),
        failure_legend_html=failure_legend(receipts, cases),
        failure_svg=chart_failure_modes(receipts, cases),
        failure_note_html=_failure_note(receipts, cases),
        flaky_take_html=(
            f"Flaky cases, which pass on some repeats and fail on others: {flaky}. "
            "A single-shot eval would report each of them as a clean pass or a clean fail, "
            "depending on the draw."
        ),
        consistency_svg=chart_consistency(headline, cases),
        cost_take_html=cost_take,
        cost_svg=chart_cost_quality(headline),
        request_svg=chart_request_cost(receipts),
        request_note_html=_request_note(receipts),
        provenance_html=provenance_html(receipts),
        notes_html="".join(f"<li>{note}</li>" for note in data_notes(receipts, cases)),
        sensitivity_intro=sensitivity_intro,
        sensitivity_html=sensitivity_html,
        repeat_word="time" if repeats == 1 else "times",
        checks=_check_rows(integrity),
        n_cases=n_cases,
        repeats=repeats,
        rubric=str(receipts[0].raw.get("rubric_version")),
        receipt_files=tuple(receipt.path.name for receipt in receipts),
        case_file=case_file,
        requests_per_run=headline[0].n,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--cases", type=Path)
    parser.add_argument("--receipts", type=Path, nargs="*")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument(
        "--out", type=Path, help="Write the report fragment. The site build is the published page."
    )
    args = parser.parse_args(argv)
    project = args.project.resolve()
    case_path = args.cases or (project / "evals/cases/analyst_live_v1.json")
    paths = list(args.receipts) if args.receipts else discover_receipts(project / "reports")
    try:
        view = build_page(
            paths, load_cases(case_path), strict=args.strict, case_file=case_path.name
        )
    except ReportIntegrityError as exc:
        print(exc, file=sys.stderr)
        return 1
    print(
        f"{view.title}: {len(view.receipt_files)} receipts, "
        f"{sum(ok for _, ok in view.checks)}/{len(view.checks)} integrity checks passed"
    )
    if args.out:
        args.out.write_text(view.scorecards_html + view.heatmap_svg, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
