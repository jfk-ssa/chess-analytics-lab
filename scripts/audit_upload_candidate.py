"""Report candidate and reachable-history patterns without printing any matched text."""

import argparse
import json
import re
import subprocess
from pathlib import Path

SENSITIVE = re.compile(
    rb"sk-(?:proj-)?[A-Za-z0-9_-]{24,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
)
LOCAL_PATH = re.compile(rb"/Users/[A-Za-z0-9._-]+/")


def git(*args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, check=True).stdout


def audit(project: Path) -> dict:
    tracked = [item for item in git("ls-files", "-z", cwd=project).decode().split("\0") if item]
    untracked = [
        item
        for item in git("ls-files", "--others", "--exclude-standard", "-z", cwd=project)
        .decode()
        .split("\0")
        if item
    ]
    names = sorted(set(tracked + untracked))
    sensitive = []
    local_paths = []
    for name in names:
        payload = (project / name).read_bytes()
        if SENSITIVE.search(payload):
            sensitive.append(name)
        if LOCAL_PATH.search(payload):
            local_paths.append(name)
    revisions = [
        item for item in git("rev-list", "--all", cwd=project).decode().splitlines() if item
    ]
    history_sensitive = []
    history_local_paths = []
    if revisions:
        for pattern, output in (
            (
                r"sk-(proj-)?[A-Za-z0-9_-]{24,}|-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----",
                history_sensitive,
            ),
            (r"/Users/[A-Za-z0-9._-]+/", history_local_paths),
        ):
            match = subprocess.run(
                ["git", "grep", "-I", "-l", "-E", pattern, *revisions],
                cwd=project,
                capture_output=True,
                check=False,
                text=True,
            )
            if match.returncode not in (0, 1):
                raise RuntimeError("history pattern scan failed")
            output.extend(sorted(set(line.split(":", 1)[-1] for line in match.stdout.splitlines())))
    return {
        "kind": "candidate and reachable-Git-history filename-only pattern audit",
        "candidate_file_count": len(names),
        "candidate_bytes": sum((project / name).stat().st_size for name in names),
        "reachable_commits": len(revisions),
        "candidate_sensitive_pattern_paths": sensitive,
        "history_sensitive_pattern_paths": history_sensitive,
        "candidate_personal_path_paths": local_paths,
        "history_personal_path_paths": history_local_paths,
        "forbidden_payload_paths": [
            name
            for name in names
            if name.startswith(("work/", ".venv/", ".uv-cache/", "artifacts/"))
            or (name.startswith("data/") and name != "data/README.md")
        ],
        "remote_configured": bool(git("remote", cwd=project).strip()),
        "limitations": [
            "Pattern scan, not a comprehensive secret detector",
            "Does not inspect ignored local files or unreachable Git objects",
            "No remote upload or hosted CI run",
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = audit(args.project.resolve())
    if args.out:
        args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
