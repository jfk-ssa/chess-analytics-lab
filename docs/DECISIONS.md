# Decisions

## 2026-10-03 — Scope and repository

The task workspace was empty (only empty work/ and outputs/ directories), with no
ancestor AGENTS.md or Git repository. Created an isolated local Git repository in
outputs/chess-analytics-lab. Keep projects 1–3 together. No remote or hosting was
provisioned. The attached brief is copied unchanged into PROJECT_SPEC.md; its
embedded kickoff text is reference context, not separate authorization. The source
ChatGPT project mirror remains untouched; its unrelated job-pipeline rules do not
apply to this repository.

Implement M0/M1 first. Subsequent milestones stay explicit backlog rather than empty
framework scaffolds. The demo currently demonstrates the data path; analyst replay
is an M5 deliverable. No fabricated benchmark or placeholder model result.

## 2026-10-03 — Environment

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

## 2026-10-03 — First vertical slice

Plain Python + reviewed SQL, DuckDB, Parquet, python-chess (`chess` distribution),
zstandard; no pandas/PyArrow or second database needed. DuckDB reads explicitly
typed JSONL into Parquet and then materializes its local tables. Pros: few packages,
no server cost. Limits: single local writer; M1 supports full fixed Lichess exports,
not arbitrary PGN imports or newer partial streams. dbt and Dagster follow in M2.

Source plan pins the official January 2013 URL, 121,332 expected records, and SHA256
published at https://database.lichess.org/standard/sha256sums.txt (checked 2026-10-03).
Caps: 1 GB compressed, 1 GB decompressed, 150,000 games, 1 MB/record, 5 GB data
directory allowance. Smaller foundation-specific expanded/game caps are compatible
with the brief's maximums. Download retries: 3; socket timeout: 30 seconds.
Partial downloads and failed runs are retained and count against the allowance.

PGN framing requires an Event header per game as used by Lichess. Missing optional
data stays null. Required malformed fields and illegal moves are quarantined.
Unsupported variants/casual/nonstandard-start games are excluded, with reasons.
Unknown results and marked bots stay in facts but are excluded and counted by the
metric. UTC date precision is preserved; absent times never become midnight.
No opening classifier or clock/evaluation interpretation is attempted in M1.

Identity: provider + game ID. Fingerprint the full trimmed PGN, including comments;
whitespace differences inside a record conservatively count as conflicts. Identical
records deduplicate; any conflict blocks the entire candidate. Each ingestion is a
full replacement candidate, not an append. Multi-source reconciliation is M2+.

Snapshot identity includes source, plan, implementation/contracts and lock hashes.
Artifact hashes catch staging or published-file tampering. An exclusive local file
lock serializes CLI writers. Only checked snapshots update an atomic current pointer.
Reporting rejects implementation drift instead of silently applying new semantics.
These are process-interruption guarantees, not certified power-loss durability.

## 2026-10-03 — Cost, AI and licensing

No cloud resources, subscriptions, live SDK, API key discovery, Jev adapter or
recommender. Provider config is disabled and remains inert in M0/M1.
M5 must implement personal-account and explicit monetary-cap validation before any
live adapter can execute. Unknown provider usage/cost must never be treated as zero.

Lichess standard archive: CC0. python-chess is GPL-3.0-or-later; do not claim all
dependencies are permissive. Repository distribution license remains undecided
pending review before public distribution; no license guessed from data licensing.
