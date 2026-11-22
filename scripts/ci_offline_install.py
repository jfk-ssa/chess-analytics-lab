#!/usr/bin/env python3
"""Validate selection outputs or install the selected offline extras in one sync."""

import argparse
import json
import os
import subprocess
from pathlib import Path

from ci_offline_catalog import CHECKS, OFFLINE_EXTRAS, RULES, github_output_names, selection_flags


def selection_invalid(result: str, outputs: object) -> bool:
    if result != "success" or not isinstance(outputs, dict):
        return True
    if set(outputs) != set(github_output_names()):
        return True
    if any(
        not isinstance(value, str) or value not in {"true", "false"}
        for key, value in outputs.items()
        if key != "categories"
    ):
        return True
    categories = outputs["categories"]
    known = {rule.category for rule in RULES}
    if not isinstance(categories, str):
        return True
    run_all = outputs["run_all"] == "true"
    selected = set(categories.split(","))
    if (run_all and categories != "all") or (not run_all and not selected <= known):
        return True
    return any(
        outputs[key] != str(value).lower()
        for key, value in selection_flags(run_all, selected).items()
    )


def install_arguments(result: str, outputs: object) -> list[str]:
    full = selection_invalid(result, outputs) or outputs["run_all"] == "true"
    extras = (
        set(OFFLINE_EXTRAS)
        if full
        else {
            extra
            for step in CHECKS
            if step.job == "offline" and outputs[step.step_id] == "true"
            for extra in step.extras
        }
    )
    return [
        "uv",
        "sync",
        "--locked",
        "--no-editable",
        *(arg for extra in OFFLINE_EXTRAS if extra in extras for arg in ("--extra", extra)),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args(argv)
    try:
        outputs = json.loads(os.environ.get("SELECTION", ""))
        fallback = selection_invalid(os.environ.get("CHANGES_RESULT", ""), outputs)
    except (ValueError, TypeError):
        outputs, fallback = None, True
    if args.validate_only:
        with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as handle:
            handle.write(f"fallback={str(fallback).lower()}\n")
        print(f"selection fallback={fallback}: {outputs}")
        return 0
    return subprocess.run(
        install_arguments(os.environ.get("CHANGES_RESULT", ""), outputs), check=False
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
