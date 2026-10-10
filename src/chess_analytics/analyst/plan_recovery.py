"""Recover one structured plan from provider text without calling the network."""

import hashlib
import json
import re
import unicodedata

from chess_analytics.analyst.tools import CheckedTools

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["answered", "needs_clarification", "unsupported"]},
        "interpretation": {"type": "string", "enum": ["descriptive_observed_prefix"]},
        "actions": {
            "type": "array",
            "maxItems": 4,
            "items": {
                "type": "object",
                "properties": {
                    "tool": {
                        "type": "string",
                        "enum": [
                            "list_metrics",
                            "get_metric_definition",
                            "get_dataset_coverage",
                            "query_metric",
                            "compare_openings",
                            "analyze_clock_pressure",
                            "compare_clock_buckets",
                        ],
                    },
                    "args_json": {"type": "string"},
                },
                "required": ["tool", "args_json"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["status", "interpretation", "actions"],
    "additionalProperties": False,
}


def _recover_repeated_plan_chunk(chunk: str, response: dict) -> tuple[dict, dict]:
    """Accept only identical repeated objects, with an optional duplicate truncation."""
    if len(chunk) > 8192:
        raise ValueError("repeated plan chunk too long")
    decoder = json.JSONDecoder()
    objects = []
    snippets = []
    remaining = chunk.strip()
    truncated = 0
    while remaining:
        if len(objects) >= 16:
            raise ValueError("too many repeated plan objects")
        try:
            value, end = decoder.raw_decode(remaining)
        except json.JSONDecodeError:
            if (
                response.get("status") == "incomplete"
                and len(objects) >= 2
                and len(remaining) >= 64
                and any(snippet.startswith(remaining) for snippet in snippets)
            ):
                truncated = len(remaining)
                break
            raise ValueError("unrecognized repeated-plan suffix") from None
        if not isinstance(value, dict) or (objects and value != objects[0]):
            raise ValueError("conflicting repeated-plan object")
        objects.append(value)
        snippets.append(remaining[:end])
        remaining = remaining[end:].strip()
        if remaining.startswith("1 final"):
            remaining = remaining[len("1 final") :].strip()
    if len(objects) < 2:
        raise ValueError("not a repeated plan")
    return objects[0], {
        "identical_complete_objects": len(objects),
        "truncated_duplicate_suffix_characters": truncated,
    }


def _recover_inert_suffix(chunk: str, response: dict) -> tuple[dict, int]:
    """Keep one complete plan before bounded non-ASCII repeated punctuation."""
    if response.get("status") != "incomplete" or len(chunk) > 8192:
        raise ValueError("not an incomplete bounded response")
    text = chunk.lstrip()
    raw, end = json.JSONDecoder().raw_decode(text)
    trailing = text[end:].strip()
    if (
        not isinstance(raw, dict)
        or not 64 <= len(trailing) <= 4096
        or len(set(trailing)) != 1
        or trailing[0].isascii()
        or unicodedata.category(trailing[0])[0] not in {"P", "S"}
    ):
        raise ValueError("not an inert repeated suffix")
    return raw, len(trailing)


def _extract_plan(response: dict) -> tuple[dict, dict]:
    """Accept one unambiguous structured plan; log invalid and duplicate chunks."""
    chunks = [
        part.get("text")
        for item in response.get("output", [])
        for part in item.get("content", [])
        if part.get("type") == "output_text"
    ]
    valid = []
    decoder = json.JSONDecoder()
    tools = set(PLAN_SCHEMA["properties"]["actions"]["items"]["properties"]["tool"]["enum"])
    for index, chunk in enumerate(chunks):
        if not isinstance(chunk, str):
            continue
        try:
            repeated = None
            inert_suffix = 0
            try:
                raw = json.loads(chunk)
            except json.JSONDecodeError:
                try:
                    raw, repeated = _recover_repeated_plan_chunk(chunk, response)
                except ValueError:
                    raw, inert_suffix = _recover_inert_suffix(chunk, response)
            if (
                not isinstance(raw, dict)
                or set(raw) != {"status", "interpretation", "actions"}
                or raw["status"] not in {"answered", "needs_clarification", "unsupported"}
                or raw["interpretation"] != "descriptive_observed_prefix"
                or not isinstance(raw["actions"], list)
                or len(raw["actions"]) > 4
            ):
                continue
            actions = []
            recovered_arguments = []
            for item in raw["actions"]:
                if not isinstance(item, dict) or set(item) != {"tool", "args_json"}:
                    raise ValueError("invalid action schema")
                if item["tool"] not in tools or not isinstance(item["args_json"], str):
                    raise ValueError("invalid action tool")
                argument_text = item["args_json"]
                try:
                    args = json.loads(argument_text)
                except json.JSONDecodeError:
                    # Some provider responses put a complete argument object first,
                    # then stray prose inside args_json. Keep the raw response,
                    # accept only that unique leading object, and log the repair.
                    args, end = decoder.raw_decode(argument_text.lstrip())
                    trailing = argument_text.lstrip()[end:]
                    if not trailing or len(trailing) > 4096:
                        raise ValueError("unbounded or absent argument suffix") from None
                    for match in re.finditer(r"[\[{]", trailing):
                        try:
                            extra, _ = decoder.raw_decode(trailing[match.start() :])
                        except json.JSONDecodeError:
                            continue
                        if isinstance(extra, (dict, list)):
                            raise ValueError("conflicting structured argument suffix") from None
                    recovered_arguments.append(
                        {"action_index": len(actions), "ignored_trailing_characters": len(trailing)}
                    )
                if not isinstance(args, dict):
                    raise ValueError("tool args must be an object")
                actions.append({"tool": item["tool"], "args": args})
            valid.append(
                (
                    index,
                    {
                        "status": raw["status"],
                        "interpretation": raw["interpretation"],
                        "actions": actions,
                    },
                    chunk,
                    recovered_arguments,
                    repeated,
                    inert_suffix,
                )
            )
        except (ValueError, TypeError, KeyError):
            continue
    if not valid or any(candidate[1] != valid[0][1] for candidate in valid[1:]):
        raise ValueError("provider returned no unique structured plan")
    index, plan, selected, recovered_arguments, repeated, inert_suffix = valid[0]
    return plan, {
        "output_text_chunks": len(chunks),
        "selected_chunk_index": index,
        "selected_chunk_sha256": hashlib.sha256(selected.encode()).hexdigest(),
        "discarded_invalid_chunks": len(chunks) - len(valid),
        "duplicate_valid_chunks": len(valid) - 1,
        "recovered_argument_suffixes": recovered_arguments,
        "recovered_repeated_plan_objects": repeated,
        "recovered_inert_suffix_characters": inert_suffix,
    }


def _normalize_plan(plan: dict) -> tuple[dict, list[str]]:
    """Wrap one known flat tool signature; preserve the raw plan in the response."""
    repairs = []
    normalized = {**plan, "actions": []}
    opening_keys = {
        "families",
        "color",
        "rating_min",
        "rating_max_exclusive",
        "base_seconds",
        "increment_seconds",
    }
    for index, action in enumerate(plan["actions"]):
        args = action["args"]
        if action["tool"] == "compare_openings" and set(args) == opening_keys:
            args = {"filters": args}
            repairs.append(f"action_{index}:wrapped_compare_openings_filters")
        normalized["actions"].append({"tool": action["tool"], "args": args})
    return normalized, repairs


def _repair_opening_usage(question: str, plan: dict, tools: CheckedTools) -> tuple[dict, list[str]]:
    """Route one clearly specified source-family fraction through the checked metric."""
    lower = question.lower()
    if not (
        ("fraction" in lower or "share" in lower)
        and ("known-opening" in lower or "source-tag" in lower or "opening usage" in lower)
    ) or any(
        word in lower
        for word in (
            "full-month",
            "full april",
            "full march",
            "full february",
            "full january",
            "full december",
            "full may",
            "full june",
            "full july",
            "caus",
            "guarantee",
            "personal",
            "my rating",
        )
    ):
        return plan, []
    rows = tools.query_metric("opening_usage", {}, ["opening_family"])["rows"]
    matches = [
        row["family"]
        for row in rows
        if re.search(r"(?<!\w)" + re.escape(row["family"]) + r"(?!\w)", question, re.I)
    ]
    matches.sort(key=len, reverse=True)
    if not matches or any(name.lower() not in matches[0].lower() for name in matches[1:]):
        return plan, []
    intended = {
        "status": "answered",
        "interpretation": "descriptive_observed_prefix",
        "actions": [
            {
                "tool": "query_metric",
                "args": {"metric_id": "opening_usage", "filters": {"family": matches[0]}},
            }
        ],
    }
    if plan == intended:
        return plan, []
    return intended, ["one_exact_source_family_fraction:checked_opening_usage"]
