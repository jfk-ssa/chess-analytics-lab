# 0121. Scope implementation_hash to pipeline and contract modules

- Status: Proposed
- Date: 2026-11-22

## Context

`implementation_hash()` in `src/chess_analytics/ingest/pipeline.py`
hashes every `src/**/*.py` file, every `src/**/*.sql` file, and every
`contracts/*.json` file. Ingest writes that digest as
`implementation_sha256` and folds it into `snapshot_id`:

```text
hash_json({source, plan, implementation, lock})[:24]
```

The analytical move snapshot is a further identity. In
`src/chess_analytics/corpus/publish.py`, `snapshot_identity()` hashes
the ingest `source_snapshot` id, the extracted source hash,
`analytics_hash(project)`, and `SAMPLE_MODULUS`. `analytics_hash` is
already narrow: `src/chess_analytics/corpus/*.py` plus
`contracts/*.json`. `CheckedTools.dataset_id` is
`current_snapshot(project).name`, and `current_snapshot` in
`src/chess_analytics/dashboard/analysis.py` reads
`data/analytical-moves-current.json` (`analytical_id`).
`quote_request` in `src/chess_analytics/analyst/provider.py` interpolates
`Dataset: {tools.dataset_id}` into the instructions text.
`instructions_sha256` is the SHA-256 of that literal string in
`live_runner._quote`.

A display-only edit under `src/` therefore changes
`implementation_hash`, the ingest `snapshot_id`, the analytical id, and
the instruction hash, even when the warehouse rows do not change. That
already happened: `eval_report.py` and `public_extract.py` changed the
hash between `e396cf4` and `15aaeb3`, so the grok-4.7 low ×5 receipt is
not strictly comparable with the later one-repeat effort trio
(`docs/STATUS.md`, `docs/EVALUATION.md`). The live-eval report keeps
hard-coded comparable-hash exceptions for that class of drift.

`src/chess_analytics/warehouse/snapshots.py` compares a staged or
published manifest's `implementation_sha256` to the current
`implementation_hash()`. A mismatch fails build with "implementation
changed after ingest; reingest before building", and report with
"snapshot implementation differs; reingest and build before reporting".

`live_runner.FROZEN_FILES` lists fourteen modules under
`src/chess_analytics/analyst/`. It does not include
`ingest/pipeline.py`. `tests/test_live_eval_receipts.py` compares those
frozen file hashes on `main`. Historical receipts and those frozen
hashes are not rewritten by this change.

This record is the plan. The implementation is a later pull request and
needs a cold review before merge.

## Decision

Change `implementation_hash()` to an explicit allowlist of pipeline and
contract modules that can change warehouse snapshot contents:

- `src/chess_analytics/ingest/`
- `src/chess_analytics/warehouse/`
- `src/chess_analytics/metrics/` (including `draw_rate.sql`, which
  publish already uses)
- `src/chess_analytics/common.py`, because ingest and warehouse use
  `hash_json`, `digest`, and `writer_lock` from
  `src/chess_analytics/common.py`
- `contracts/*.json`

Keep the same `hash_json({relative_path: digest})` shape over the
sorted file set. Do not put presentation helpers into `common.py`.

Leave `analytics_hash()` as the analytical-layer digest. Do not also
include `src/chess_analytics/corpus/` in `implementation_hash`: a
corpus-only edit should change `analytical_id` through
`analytics_hash`, not by minting a new ingest `snapshot_id` for
unchanged warehouse rows. Marts keep their own `mart_id` and stay out
of this hash. Presentation, reporting, and tooling stay out of it,
including `eval_report.py`, `public_extract.py`,
`dashboard_cube.py`, `dashboard/`, `analyst/`, `coach/`,
`orchestration/`, `portfolio_demo.py`, `build_info.py`, `game_import.py`,
and the routing modules.

Do not rewrite committed live-eval receipts, frozen receipt hashes, or
any file in `live_runner.FROZEN_FILES`. Do not backfill old
`snapshot_id` values. After this lands, a receipt is like-for-like with
another only when both were produced with the same hash function and
the same `dataset_id` rules. Existing exception notes in
`eval_report.py` stay until a later docs pass can point at this
record; this change does not invent new hash-pair exceptions.

Tests must show that editing a presentation module does not change
`implementation_hash` or a freshly computed ingest `snapshot_id`, and
that editing a file on the allowlist does. Local and CI snapshots are
rebuilt by the existing ingest path; gitignored warehouses are not
migrated in place.

## Consequences

Display-only edits stop invalidating warehouse identity and the
`Dataset:` line in live-eval instructions. Future evals that share a
dataset can stay comparable across dashboard or report changes.

Every existing staged or published local snapshot was hashed with the
old function. After this change, `build()` and `report()` will refuse
those manifests until the dataset is reingested. That is expected.
Reingest produces a new `snapshot_id` and, through
`snapshot_identity()`, a new `analytical_id`, so a new live eval will
not share `instructions_sha256` with receipts minted under the old
function. Historical receipts remain the record of those runs.

This is a data-model change. It is the riskiest of the three planned
implementation pull requests and gets a cold review. It does not by
itself authorize a live model call.

## Alternatives considered

Keep hashing all of `src/`, and record `dataset_id` on every receipt so
comparisons can ignore instruction-hash drift. Rejected: receipts
should still not change when a caption file changes, and older
receipts already omitted `dataset_id`. Recording the id is good
hygiene and does not fix snapshot identity.

Include `src/chess_analytics/corpus/` in the allowlist, as a broader
"pipeline" set. Rejected: `analytics_hash` already covers corpus
modules in `analytical_id`. Including them here would still retag
unchanged warehouse snapshots.

Version the hash function and accept old manifests that match either
digest. Rejected: that keeps two identities for one snapshot and
complicates `build()` and `report()`. A one-time reingest is clearer.

Rewrite historical receipts so their hashes look current. Rejected:
frozen evidence is not rewritten.

## Planned commits

1. `fix(ingest): scope implementation_hash to pipeline and contract modules`
2. `test(ingest): assert presentation edits do not change snapshot_id`
