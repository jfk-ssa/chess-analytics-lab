"""Restore reports/opening-positions.json from its immutable publication blob.

The rankings are produced by replaying a local corpus that is not in Git and
must not be downloaded by CI. The bytes that the site publishes were introduced
in PUBLICATION_COMMIT and remain in Git history. This script fetches that blob
and checks the SHA-256 recorded in the publication checkpoint. Tests and the
site builder do not call it; they read the restored file.
"""

import hashlib
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "reports" / "opening-positions.json"
PUBLICATION_COMMIT = "c1e3040a3c9542626a3b8cb78e1e7475ea8bcdab"
EXPECTED_SHA256 = "31a395044203532224cbb387475ef0bb790c8e88faac98bc9b2a12f5d500c46e"
SOURCE_URL = (
    "https://raw.githubusercontent.com/jfk-ssa/chess-analytics-lab/"
    f"{PUBLICATION_COMMIT}/reports/opening-positions.json"
)


def main() -> None:
    if TARGET.is_file() and hashlib.sha256(TARGET.read_bytes()).hexdigest() == EXPECTED_SHA256:
        print(f"{TARGET.relative_to(ROOT)} already matches {EXPECTED_SHA256}")
        return
    with urllib.request.urlopen(SOURCE_URL, timeout=60) as response:
        payload = response.read()
    actual = hashlib.sha256(payload).hexdigest()
    if actual != EXPECTED_SHA256:
        raise SystemExit(f"Opening rankings hash mismatch: {actual}")
    TARGET.write_bytes(payload)
    print(f"Wrote {TARGET.relative_to(ROOT)} ({len(payload)} bytes)")


if __name__ == "__main__":
    main()
