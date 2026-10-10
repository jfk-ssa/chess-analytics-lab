# 0003. First vertical slice

- Status: accepted
- Date: 2026-10-03

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
Follow-up hardening gives each acquisition job its own immutable attempt paths;
retries share the job allowance. An EOF probe can read one byte beyond the retained
byte limit to detect an oversized response. This is a retained-byte guard, not a
measurement of network protocol overhead or bytes hidden inside transport failures.

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
