# Local runbook

Run commands from the repository root (or pass `chesslab --project /path/to/repo`).
Use README setup and ingestion commands. All data-changing CLI commands take the
same exclusive advisory lock. Calling Python pipeline functions directly requires
the caller to take `writer_lock`.

## Recovery

1. **Download failure:** inspect data/raw/acquisition-failures.json and retained
   attempt-N.part files. Retry ingest. Existing complete files are reused only after
   checksum verification. Failed partial files are not resumed or published.
2. **Corrupt cached source:** ingest refuses it. Preserve/rename it for diagnosis,
   then run ingest again to acquire the exact configured source. Never update a
   checksum to make corrupted data pass.
3. **Parser/data failure:** inspect data/staging/RUN/manifest.json and quarantine.jsonl.
   Each run is retained. Conflicting duplicate IDs block publication; resolve the
   source/contract deliberately, then reingest. Never select a silent winner.
4. **Disk/record/byte limit:** failure is explicit. Archived failed runs count against
   the allowance. Review before deleting obsolete staging or raising a documented
   limit. Build reserves a conservative workspace before DuckDB work and caps memory
   at 256 MB, threads at 2 and spill at 512 MB. These are configured limits, not
   measured whole-process RAM guarantees. Writer must be on a local filesystem.
5. **Interrupted build:** prior current pointer remains usable. Repeat build for the
   latest successful staging run. Failed build directories and attempt records stay
   available. `kill -9` may leave status running; re-run explicitly after verifying
   the process is gone. File locks release on process exit.
6. **Rollback:** select a previously verified directory in data/published and run
   `validate_snapshot(path)` before changing the dataset-current.json pointer with
   `write_json` under `writer_lock`. A convenience rollback CLI is planned for M2.
7. **Schema/code drift:** report/build refuses an implementation mismatch. Reingest
   with the new locked code; do not relabel an older snapshot as a new version.

Tests cover interruption immediately before publication and retry versus clean run.
Power-loss/fsync of whole directories, general multi-source merging, operational
backfill UI and exhaustive source-drift handling are M2 work, not M1 claims.

## Environment and offline verification

This host uses a workspace-local uv cache when default-cache access is blocked:
`UV_CACHE_DIR=/path/to/work/uv-cache uv sync --locked --no-editable`.
Tests block Python socket connection attempts. The CLI demo uses only committed
synthetic PGNs. Python provider credentials are never read; no .env loader exists.

Use `uv sync --locked --no-editable --reinstall-package chess-analytics-lab` after
source edits. The no-editable flag avoids macOS hidden .pth files that this Python
ignores. CI runs on Linux with the same locked packages.

## Later provider incidents

Live provider runs, replay, budgets and evaluation are not implemented until M5.
There is no live command to invoke in this release. At that milestone, document
timeouts, unknown usage reservations, exhausted caps and trace replay before enabling
any live run. Personal configuration and explicit spending authorization are required.
