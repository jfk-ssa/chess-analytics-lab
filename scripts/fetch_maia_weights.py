"""Download one pinned Maia-3 checkpoint. Importing this file does not download anything.

The weights are not committed. Run this script only when you mean to fetch them.
Tests call `fetch_weights` with a fake HTTP body and never open the network.
"""

import argparse
import hashlib
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

from chess_analytics.analyst.maia_pins import CODE_COMMIT, CODE_REPO, PINS, RATING_SCALE

INSTALL_LINE = "uv sync --locked --extra maia"


def weights_url(pin: dict) -> str:
    return f"https://huggingface.co/{pin['hf_repo']}/resolve/{pin['hf_revision']}/{pin['filename']}"


def config_document(alias: str, weights: Path, pin: dict) -> dict:
    model = {
        "alias": alias,
        "bytes": pin["bytes"],
        "code_commit": CODE_COMMIT,
        "code_repo": CODE_REPO,
        "device": "cpu",
        "dtype": "float32",
        "family": "maia3",
        "hf_repo": pin["hf_repo"],
        "hf_revision": pin["hf_revision"],
        "rating_scale": RATING_SCALE,
        "sha256": pin["sha256"],
        "threads": 1,
        "weights_path": str(weights.resolve()),
    }
    return {"default_alias": alias, "models": {alias: model}, "version": "1"}


def fetch_weights(alias: str, dest: Path, opener, pins: dict | None = None) -> dict:
    """Download `alias`, check the pinned size and SHA-256, then move the file into place."""
    table = PINS if pins is None else pins
    if alias not in table:
        raise ValueError("unsupported maia model")
    pin = table[alias]
    dest.mkdir(parents=True, exist_ok=True)
    final = dest / pin["filename"]
    partial = dest / f".{pin['filename']}.partial"
    partial.unlink(missing_ok=True)
    try:
        with opener(weights_url(pin)) as response:
            status = getattr(response, "status", 200)
            if status != 200:
                raise ValueError("maia download failed")
            digest = _write_and_hash(response, partial, pin["bytes"])
        if digest != pin["sha256"]:
            raise ValueError("maia weights hash mismatch")
        partial.replace(final)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    return config_document(alias, final, pin)


def _write_and_hash(response, partial: Path, expected_bytes: int) -> str:
    hasher = hashlib.sha256()
    size = 0
    with partial.open("wb") as handle:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            if not isinstance(chunk, bytes):
                raise ValueError("maia download failed")
            size += len(chunk)
            if size > expected_bytes:
                raise ValueError("maia weights hash mismatch")
            hasher.update(chunk)
            handle.write(chunk)
    if size != expected_bytes:
        raise ValueError("maia weights hash mismatch")
    return hasher.hexdigest()


def path_is_gitignored(project: Path, path: Path) -> bool:
    completed = subprocess.run(
        ["git", "check-ignore", "-q", "--", str(path)],
        cwd=project,
        check=False,
    )
    return completed.returncode == 0


def alias_from_config(path: Path) -> str:
    if not path.is_file():
        raise ValueError("pass --alias or a config/maia.json with default_alias")
    alias = json.loads(path.read_text()).get("default_alias")
    if alias not in PINS:
        raise ValueError("config default_alias is not a pinned Maia-3 model")
    return alias


def main(argv: list[str] | None = None, opener=None) -> int:
    parser = argparse.ArgumentParser(
        description="Download pinned Maia-3 weights into an ignored directory."
    )
    parser.add_argument("--alias", choices=tuple(PINS))
    parser.add_argument("--config", type=Path)
    parser.add_argument("--dest", type=Path)
    parser.add_argument("--project", type=Path)
    args = parser.parse_args(argv)
    project = (args.project or Path.cwd()).resolve()
    try:
        alias = args.alias or alias_from_config(args.config or (project / "config" / "maia.json"))
        dest = args.dest or Path("data/models")
        dest = dest if dest.is_absolute() else project / dest
        final = dest / PINS[alias]["filename"]
        if not path_is_gitignored(project, final):
            raise ValueError(f"refusing to write {final}: path is not gitignored")
        document = fetch_weights(alias, dest, opener or urllib.request.urlopen)
    except ValueError as exc:
        print(f"maia download refused: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(document, indent=2, sort_keys=True))
    print(INSTALL_LINE)
    print("Do not commit the weights. Do not put this tool behind a public service.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
