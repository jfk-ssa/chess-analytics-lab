#!/usr/bin/env python3
"""Render managed Offline integrity blocks; --check rejects drift."""

import argparse
import re
from pathlib import Path

from ci_offline_catalog import MAPPED_JOBS, STEPS, default_if, github_output_names


def render(text: str) -> str:
    # Accept coordinated full-SHA setup-uv bumps without a catalog edit (ADR 0100).
    pins = re.findall(r"uses: ([\'\"]?astral-sh/setup-uv@[0-9a-f]{40}[\'\"]?)(?=\s|$)", text)
    pin = pins[0] if pins else ""
    blocks = {
        "outputs": "".join(
            f"      {name}: ${{{{ steps.filter.outputs.{name} }}}}\n"
            for name in github_output_names()
        )
    }
    for job in MAPPED_JOBS:
        lines = []
        for step in STEPS:
            if step.job != job:
                continue
            lines.append(f"      - id: {step.step_id}\n")
            if step.kind != "always":
                lines.append(f"        if: {step.if_expr or default_if(step.step_id, job)}\n")
            if step.uses:
                uses = pin if step.uses.startswith("astral-sh/setup-uv@") else step.uses
                lines.append(f"        uses: {uses}\n")
            if step.details:
                lines.extend(f"        {line}\n" for line in step.details.splitlines())
            if step.exact:
                if "\n" in step.exact:
                    lines.append("        run: |\n")
                    lines.extend(f"          {line}\n" for line in step.exact.splitlines())
                else:
                    lines.append(f"        run: {step.exact}\n")
        blocks[job] = "".join(lines)
    for name, body in blocks.items():
        pattern = rf"(?m)(^      # BEGIN managed {name}\n).*?(^      # END managed {name}\n)"
        text, count = re.subn(pattern, lambda m, body=body: m[1] + body + m[2], text, flags=re.S)
        if count != 1:
            raise ValueError(f"missing or duplicated managed block: {name}")
    return text


def check_generated(text: str) -> list[str]:
    try:
        return (
            [] if render(text) == text else ["generated workflow blocks drifted; run the generator"]
        )
    except ValueError as exc:
        return [str(exc)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    path = Path(__file__).resolve().parents[1] / ".github/workflows/offline.yml"
    text = path.read_text(encoding="utf-8")
    if args.check:
        problems = check_generated(text)
        print("\n".join(problems) if problems else "generated offline blocks ok")
        return int(bool(problems))
    path.write_text(render(text), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
