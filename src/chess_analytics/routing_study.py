"""Frozen, credential-free routing study with an explicitly capped Jev path."""

import argparse
import csv
import hashlib
import json
import math
import re
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

LABELS = (
    "opening_usage",
    "opening_score",
    "opening_compare",
    "clock_bucket",
    "clock_compare",
    "coverage",
    "clarify",
    "unsupported",
)
MODEL = "jev-1.13.0"
PRICE_USD_PER_MILLION_INPUT = 0.042
CASE_PATH = Path("evals/cases/jev_routing_v1.tsv")
MANIFEST_PATH = Path("evals/cases/jev_routing_v1_manifest.json")
KEY_NAME = "TYPESAFE_API_KEY"
RULES_VERSION = "routing-rules-1.0"
CHOICE_CRITERIA = {
    "opening_usage": "Count or fraction of games with one named source-tag opening family.",
    "opening_score": "Score, wins, draws, or losses for one opening and a specified player cohort.",
    "opening_compare": (
        "Compare score outcomes for two named opening families with matched filters."
    ),
    "clock_bucket": "One specified pre-turn clock bucket's proxy rate or evaluation coverage.",
    "clock_compare": "Compare proxy or evaluation coverage across two specified clock buckets.",
    "coverage": "Dataset provenance, observed dates, selection, missingness, or quality counts.",
    "clarify": (
        "A supported analysis request lacks the opening, bucket, cohort, or "
        "referent needed to execute it."
    ),
    "unsupported": (
        "Causal, personalized, cheating, live-game, forecast, or full-population "
        "claim outside this product's evidence."
    ),
}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json(data: object) -> bytes:
    return json.dumps(data, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode()


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def cases(project: Path, split: str = "test") -> tuple[list[dict], dict]:
    if split not in {"dev", "test", "all"}:
        raise ValueError("split must be dev, test, or all")
    source = project / CASE_PATH
    manifest = json.loads((project / MANIFEST_PATH).read_text())
    if _sha(source.read_bytes()) != manifest["case_sha256"]:
        raise ValueError("frozen routing case file changed")
    with source.open(newline="") as handle:
        all_rows = list(csv.DictReader(handle, delimiter="\t"))
    if len(all_rows) != manifest["cases"] or len({row["id"] for row in all_rows}) != len(all_rows):
        raise ValueError("frozen routing case count or identities changed")
    if set(row["label"] for row in all_rows) != set(LABELS) or any(
        row["split"] not in {"dev", "test"} or not row["question"].strip() for row in all_rows
    ):
        raise ValueError("invalid routing case schema")
    if dict(Counter(row["label"] for row in all_rows)) != manifest["labels"]:
        raise ValueError("frozen routing label counts changed")
    if dict(Counter(row["split"] for row in all_rows)) != manifest["splits"]:
        raise ValueError("frozen routing split counts changed")
    return [row for row in all_rows if split == "all" or row["split"] == split], manifest


def rule_route(question: str) -> str:
    """Deliberately small rule baseline; do not tune against frozen test labels."""
    q = question.lower()
    if re.search(
        r"\b(caus\w*|prove|cheat\w*|engine assistance|next match|ongoing game|live tournament|"
        r"forecast|predict|personaliz|private games|entire .*archive|every game|everywhere)\b",
        q,
    ):
        return "unsupported"
    if re.search(r"\b(missing ratings|missing opening tags)\b", q):
        return "coverage"
    if re.search(
        r"\b(which opening|those two|two openings i have|that opening|that cohort|"
        r"player color i mean|my chosen|my games|how did they|how common was it)\b",
        q,
    ):
        return "clarify"
    if re.search(
        r"\b(first|last) observed|missing|quarantin|excluded|duplicat|"
        r"snapshot|source|selection|selected|quality|utc date|monthly archive|"
        r"byte prefix|ingestion\b",
        q,
    ) and not re.search(r"\bopening|clock\b", q):
        return "coverage"
    if re.search(
        r"\b(compare|contrast|versus|against|side.by.side|which .*higher)\b", q
    ) and re.search(r"\b(opening|defense|game|gambit|lopez)\b", q):
        return "opening_compare"
    if re.search(
        r"\b(clock|seconds|pre.turn|time.left|bucket|proxy|centipawn|"
        r"evaluable|evaluation coverage|deterioration)\b",
        q,
    ):
        if re.search(
            r"\b(compare|contrast|versus|against|differ|between|side by side|which of)\b", q
        ):
            return "clock_compare"
        return "clock_bucket"
    if re.search(r"\b(compare|contrast|versus|against|side.by.side|which .*higher)\b", q):
        return "opening_compare"
    if re.search(r"\b(score|wins|draws|losses|points per|points earned|outcome)\b", q):
        return "opening_score"
    if re.search(
        r"\b(how many|count|share|fraction|percentage|proportion|frequency|"
        r"how common)\b",
        q,
    ):
        return "opening_usage"
    return "clarify"


def jev_request(question: str) -> bytes:
    if not 1 <= len(question) <= 2000:
        raise ValueError("question length outside bounded routing input")
    return _json(
        {
            "model": MODEL,
            "state": {
                "question": question,
                "catalog": (
                    "Observed archive prefix; exact source-tag openings; selected moves "
                    "with sparse evaluations. Numeric filters and actual coverage are "
                    "checked by code after routing."
                ),
            },
            "questions": {
                "route": {
                    "type": "choice",
                    "instructions": (
                        "Choose the single primary route for `question`. Do not "
                        "calculate a metric. A missing required referent needs "
                        "clarification; a claim outside the observed dataset is unsupported."
                    ),
                    "criteria": CHOICE_CRITERIA,
                }
            },
        }
    )


def quote(body: bytes) -> dict:
    # An intentionally generous planning allowance, not a tokenizer guarantee.
    reserved_tokens = 4 * len(body) + 1024
    return {
        "request_sha256": _sha(body),
        "request_bytes": len(body),
        "reserved_input_tokens": reserved_tokens,
        "reserved_cost_usd": reserved_tokens * PRICE_USD_PER_MILLION_INPUT / 1_000_000,
    }


def preflight(project: Path, split: str = "test") -> dict:
    selected, manifest = cases(project, split)
    cells = [{"id": row["id"], **quote(jev_request(row["question"]))} for row in selected]
    return {
        "kind": "m8_jev_routing_preflight_no_model_calls",
        "split": split,
        "model": MODEL,
        "price_usd_per_million_input": PRICE_USD_PER_MILLION_INPUT,
        "case_sha256": manifest["case_sha256"],
        "code_sha256": _sha(Path(__file__).read_bytes()),
        "cells": cells,
        "total_reserved_cost_usd": sum(cell["reserved_cost_usd"] for cell in cells),
        "pricing_source": "https://docs.typesafe.ai/models",
        "reservation_limit": (
            "Four times request UTF-8 bytes plus 1024 tokens per call is a "
            "conservative estimate, not a contractual tokenizer bound; actual usage "
            "and unknown-cost reservations are logged."
        ),
    }


def parse_jev_response(raw: dict) -> dict:
    if not isinstance(raw, dict) or raw.get("model") != MODEL:
        raise ValueError("unexpected resolved Jev model")
    answers = raw.get("answers")
    answer = answers.get("route") if isinstance(answers, dict) else None
    if not isinstance(answer, dict) or answer.get("type") != "choice":
        raise ValueError("missing Choice route")
    choice = answer.get("choice")
    probabilities = answer.get("probabilities")
    if (
        choice not in LABELS
        or not isinstance(probabilities, dict)
        or set(probabilities) != set(LABELS)
    ):
        raise ValueError("invalid route options")
    if (
        any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or not 0 <= value <= 1
            for value in probabilities.values()
        )
        or abs(sum(probabilities.values()) - 1) > 0.02
    ):
        raise ValueError("invalid route probabilities")
    usage_object = raw.get("usage")
    usage = usage_object.get("input_tokens") if isinstance(usage_object, dict) else None
    if isinstance(usage, bool) or not isinstance(usage, int) or usage < 0:
        raise ValueError("missing billable input token count")
    confidence = answer.get("confidence")
    if (
        isinstance(confidence, bool)
        or not isinstance(confidence, (int, float))
        or not math.isfinite(confidence)
        or not 0 <= confidence <= 1
    ):
        raise ValueError("invalid Choice confidence")
    return {
        "choice": choice,
        "probabilities": probabilities,
        "confidence": confidence,
        "input_tokens": usage,
        "gross_cost_usd": usage * PRICE_USD_PER_MILLION_INPUT / 1_000_000,
    }


def _transport(body: bytes, key: str) -> dict:
    request = urllib.request.Request(
        "https://api.typesafe.ai/v1/systemone",
        data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        if response.status != 200:
            raise ValueError(f"TypeSafe HTTP {response.status}")
        payload = response.read(1_000_001)
    if len(payload) > 1_000_000:
        raise ValueError("TypeSafe response exceeded limit")
    return json.loads(payload)


def _personal_key(path: Path) -> str:
    if path.name != ".env.typesafe" or "work" not in path.parts:
        raise ValueError("use an explicit ignored work/.env.typesafe file")
    matches = []
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        name, separator, value = stripped.partition("=")
        if not separator or name.strip() != KEY_NAME or not value.strip():
            raise ValueError("env file may contain only the named TypeSafe key")
        token = value.strip().strip("\"'")
        if not token:
            raise ValueError("TypeSafe key value is blank")
        matches.append(token)
    if len(matches) != 1:
        raise ValueError("env file must contain exactly one TypeSafe key")
    return matches[0]


def score(selected: list[dict], predictions: list[dict], mode: str) -> dict:
    by_id = {row["id"]: row for row in selected}
    if len(by_id) != len(selected) or len({row["id"] for row in predictions}) != len(predictions):
        raise ValueError("duplicate case identity")
    if set(by_id) != {row["id"] for row in predictions}:
        raise ValueError("missing or unexpected prediction")
    confusion = {label: {pred: 0 for pred in (*LABELS, "fallback")} for label in LABELS}
    correct = 0
    for prediction in predictions:
        truth = by_id[prediction["id"]]["label"]
        predicted = prediction["route"]
        if predicted not in (*LABELS, "fallback"):
            raise ValueError("invalid predicted route")
        confusion[truth][predicted] += 1
        correct += truth == predicted
    result = {
        "kind": f"m8_{mode}_routing_results",
        "cases": len(selected),
        "correct": correct,
        "accuracy": correct / len(selected),
        "unsupported_recall": confusion["unsupported"]["unsupported"]
        / sum(confusion["unsupported"].values()),
        "confusion": confusion,
        "predictions": predictions,
    }
    if mode == "jev":
        costs = [row.get("gross_cost_usd", 0.0) for row in predictions]
        result["known_gross_cost_usd"] = sum(costs)
        result["gross_cost_per_correct_route_usd"] = sum(costs) / correct if correct else None
        result["selective_curve"] = []
        for threshold in (0.0, 0.5, 0.7, 0.85, 0.95):
            accepted = [
                p for p in predictions if p.get("probabilities", {}).get(p["route"], 0) >= threshold
            ]
            hits = sum(by_id[p["id"]]["label"] == p["route"] for p in accepted)
            result["selective_curve"].append(
                {
                    "threshold": threshold,
                    "coverage": len(accepted) / len(selected),
                    "accepted": len(accepted),
                    "errors": len(accepted) - hits,
                    "error_rate_among_accepted": (len(accepted) - hits) / len(accepted)
                    if accepted
                    else None,
                    "fallbacks": len(selected) - len(accepted),
                }
            )
    return result


def rules_report(project: Path, split: str) -> dict:
    selected, manifest = cases(project, split)
    start = time.monotonic()
    predictions = [{"id": row["id"], "route": rule_route(row["question"])} for row in selected]
    report = score(selected, predictions, "rules")
    report.update(
        split=split,
        case_sha256=manifest["case_sha256"],
        rules_version=RULES_VERSION,
        references={row["id"]: row["label"] for row in selected},
        elapsed_seconds=time.monotonic() - start,
    )
    return report


def run_jev(
    project: Path,
    frozen: dict,
    env_file: Path,
    max_run_usd: float,
    output: Path,
    *,
    transport=None,
) -> dict:
    if (
        isinstance(max_run_usd, bool)
        or not isinstance(max_run_usd, (int, float))
        or not math.isfinite(max_run_usd)
        or max_run_usd <= 0
    ):
        raise ValueError("explicit finite positive run cap required")
    selected, manifest = cases(project, frozen["split"])
    if frozen != preflight(project, frozen["split"]):
        raise ValueError("frozen Jev preflight drifted")
    if frozen["total_reserved_cost_usd"] > max_run_usd:
        raise ValueError("whole Jev run does not fit the explicit cap")
    work = (project / "work").resolve()
    if not output.resolve().is_relative_to(work):
        raise ValueError("raw Jev attempts must stay under ignored work/")
    if not env_file.resolve().is_relative_to(work):
        raise ValueError("TypeSafe key must come from this project's ignored work/")
    if output.exists() and any(output.iterdir()):
        raise ValueError("use a fresh attempt directory")
    key = _personal_key(env_file)
    output.mkdir(parents=True, exist_ok=True)
    predictions = []
    known = 0.0
    unknown_reserved = 0.0
    for row, cell in zip(selected, frozen["cells"], strict=True):
        body = jev_request(row["question"])
        if cell["id"] != row["id"] or cell["request_sha256"] != _sha(body):
            raise ValueError("frozen request drifted")
        if known + unknown_reserved + cell["reserved_cost_usd"] > max_run_usd:
            raise ValueError("next request does not fit remaining cap")
        started = time.monotonic()
        record = {"id": row["id"], "request_sha256": cell["request_sha256"]}
        try:
            raw = (transport or _transport)(body, key)
            record["raw_response"] = raw
            parsed = parse_jev_response(raw)
            if parsed["gross_cost_usd"] > cell["reserved_cost_usd"]:
                raise ValueError("actual usage exceeded conservative request reservation")
            known += parsed["gross_cost_usd"]
            record["parsed"] = parsed
            predictions.append(
                {
                    "id": row["id"],
                    "route": parsed["choice"],
                    "probabilities": parsed["probabilities"],
                    "gross_cost_usd": parsed["gross_cost_usd"],
                    "elapsed_seconds": time.monotonic() - started,
                }
            )
        except (OSError, ValueError, urllib.error.HTTPError) as exc:
            raw_response = record.get("raw_response")
            usage_object = raw_response.get("usage") if isinstance(raw_response, dict) else None
            observed_tokens = (
                usage_object.get("input_tokens") if isinstance(usage_object, dict) else None
            )
            if (
                isinstance(observed_tokens, int)
                and not isinstance(observed_tokens, bool)
                and observed_tokens >= 0
            ):
                observed_cost = observed_tokens * PRICE_USD_PER_MILLION_INPUT / 1_000_000
                known += observed_cost
                record["gross_cost_usd"] = observed_cost
            else:
                unknown_reserved += cell["reserved_cost_usd"]
                record["unknown_cost_reservation_usd"] = cell["reserved_cost_usd"]
            record["failure"] = {"type": type(exc).__name__, "message": str(exc)[:300]}
            record["elapsed_seconds"] = time.monotonic() - started
            _write(output / f"{row['id']}.json", record)
            break
        _write(output / f"{row['id']}.json", record)
    complete = len(predictions) == len(selected)
    report = {
        "kind": "m8_jev_live_attempt",
        "transport_kind": "injected_mock" if transport is not None else "typesafe_api",
        "split": frozen["split"],
        "case_sha256": manifest["case_sha256"],
        "model": MODEL,
        "max_run_usd": max_run_usd,
        "known_gross_cost_usd": known,
        "unknown_cost_reservation_usd": unknown_reserved,
        "accounted_gross_usd": known + unknown_reserved,
        "complete": complete,
        "completed_cases": len(predictions),
        "total_cases": len(selected),
        "predictions": predictions,
    }
    if complete:
        report["scoring"] = score(selected, predictions, "jev")
    _write(output / "report.json", report)
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Frozen M8 semantic routing study")
    parser.add_argument("mode", choices=("rules", "prepare", "run"))
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--split", choices=("dev", "test", "all"), default="test")
    parser.add_argument("--preflight", type=Path)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--max-run-usd", type=float)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.mode == "rules":
            result = rules_report(args.project, args.split)
        elif args.mode == "prepare":
            result = preflight(args.project, args.split)
            if args.preflight is None:
                raise ValueError("prepare requires --preflight")
            _write(args.preflight, result)
        else:
            if args.preflight is None or args.env_file is None or args.output is None:
                raise ValueError("run requires --preflight, --env-file and --output")
            result = run_jev(
                args.project,
                json.loads(args.preflight.read_text()),
                args.env_file,
                args.max_run_usd,
                args.output,
            )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (OSError, ValueError) as exc:
        parser.exit(1, f"routing study: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
