"""Keep saved live evidence intact when making a versioned offline rescore."""

import json
import subprocess
import sys

from chess_analytics.routing_study import _sha


def test_rescore_refuses_original_and_existing_destinations(tmp_path, project):
    source = tmp_path / "evals/cases/jev_e2e_v1.json"
    source.parent.mkdir(parents=True)
    source.write_text(json.dumps([{"id": "boundary"}]))
    attempt = tmp_path / "attempt"
    attempt.mkdir()
    row = {
        "id": "boundary",
        "used_analyst": False,
        "passed": True,
        "failures": [],
        "gross_cost_usd": {"jev": 0.0, "openai": 0.0},
    }
    original = {
        "kind": "m8_paired_e2e_actual_attempt",
        "complete": True,
        "case_sha256": _sha(source.read_bytes()),
        "outcomes": {"baseline": [row], "gated": [row]},
        "scores": {},
    }
    report = attempt / "report.json"
    report.write_text(json.dumps(original))
    original_bytes = report.read_bytes()

    def invoke(destination):
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "scripts.replay_jev_e2e",
                "--repo",
                str(tmp_path),
                "--attempt",
                str(attempt),
                "--output",
                str(destination),
            ],
            cwd=project,
            capture_output=True,
            text=True,
            check=False,
        )

    assert invoke(report).returncode == 2
    assert report.read_bytes() == original_bytes
    output = tmp_path / "rescore.json"
    assert invoke(output).returncode == 0
    assert json.loads(output.read_text())["rescore_rubric"] == "m8-e2e-1.1"
    assert invoke(output).returncode == 2
    assert report.read_bytes() == original_bytes
