"""Create an isolated February project view with its own data pointers."""

import json
import os
import shutil
import subprocess
from pathlib import Path

from chess_analytics.common import digest, read_json, write_json

PROJECT = Path(__file__).resolve().parents[1]
DIRECTORIES = (
    "src",
    "analytics_m3",
    "analytics_m4",
    "analyst_m5",
    "contracts",
    "docs",
    "scripts",
    "evals",
    "reports",
    "config",
)
FILES = ("pyproject.toml", "uv.lock", "README.md")


def create(project: Path = PROJECT) -> Path:
    destination = project / "work/m7-february-project"
    if destination.exists():
        raise ValueError("M7 February workspace already exists; preserve existing work")
    plan = read_json(project / "config/m7_february_source.json")
    source = project / "work/m7-february-prefix-40000000.zst"
    if (
        source.stat().st_size != plan["max_download_bytes"]
        or digest(source) != plan["compressed_prefix_sha256"]
    ):
        raise ValueError("pinned February prefix failed size/hash check")
    destination.mkdir(parents=True)
    for name in DIRECTORIES:
        shutil.copytree(project / name, destination / name)
    for name in FILES:
        shutil.copy2(project / name, destination / name)
    # The August-specific caveats are incompatible with this independently dated slice.
    for contract_name in ("opening_usage.json", "clock_pressure_error_proxy.json"):
        contract_path = destination / "contracts" / contract_name
        contract = read_json(contract_path)
        contract["caveats"] = [
            caveat.replace(
                "an August 2026 population sample", "a full-month population sample"
            ).replace("all August games", "all games in the source month")
            for caveat in contract["caveats"]
        ]
        write_json(contract_path, contract)
    datasets = read_json(destination / "config/datasets.json")
    datasets["analytical"] = plan
    write_json(destination / "config/datasets.json", datasets)
    target = (
        destination
        / "data/analytical"
        / (f"lichess-standard-rated-{plan['period']}-prefix-{plan['max_download_bytes']}.zst")
    )
    target.parent.mkdir(parents=True)
    try:
        os.link(source, target)
    except OSError:
        shutil.copy2(source, target)
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=project, text=True, capture_output=True, check=True
    ).stdout.strip()
    write_json(
        destination / "workspace-provenance.json",
        {
            "kind": "isolated M7 February project view; not another repository",
            "source_repo_commit": commit,
            "source_plan": "config/m7_february_source.json",
            "prefix_sha256": plan["compressed_prefix_sha256"],
            "copied_directories": list(DIRECTORIES),
            "copied_files": list(FILES),
            "main_repo": str(project),
        },
    )
    return destination


if __name__ == "__main__":
    result = create()
    print(json.dumps({"workspace": str(result)}))
