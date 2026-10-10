# 0002. Environment

- Status: accepted
- Date: 2026-10-03

macOS arm64; approximately 77 GiB available at inspection. System Python 3.9.6 is
not used. Existing uv-managed CPython 3.12.14 works. Pin that runtime and use uv.lock
for Python packages, including hashes. Pin the build backend. Python 3.12 and the
chosen chess/DuckDB/zstandard versions passed actual local compatibility tests.
Versions are conservative exact pins, not claims of latest releases.

The initial attempt to install a duplicate runtime failed due to sandbox DNS; the
existing runtime removed that need. Dependency acquisition succeeded with approved
network access. Initial package metadata omitted the explicit src package mapping;
fixed before acceptance. A macOS hidden flag on editable `.pth` files causes this
Python to skip them, even after a temporary `chflags` repair. Use a normal wheel
(`--no-editable`) instead; it passed import and CLI checks. Workspace-local uv cache
avoids writes to the sandbox-inaccessible default cache. No credentials inspected.
