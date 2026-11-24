# 0121. Scope implementation_hash to pipeline and contract modules

- Status: Implemented locally, pending cold review
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

The broad ingest hash currently also covers analytical/tool code that
the narrower `analytics_hash` misses. `dashboard/analysis.py` computes
adjusted opening scores and bootstrap intervals; `analyst/semantic.py`
selects and computes governed results. Neither is in `FROZEN_FILES`.
`current_snapshot()` validates stored artifacts but does not compare
the stored analytical implementation digest with current code.

`marts.pipeline.model_hash()` covers dbt SQL/YAML and `analytics_hash`,
but not `marts/pipeline.py` itself. That file prepares `fact_move`
before dbt runs. `build_mart()` reuses an existing publication when the
computed `mart_id` directory exists. Excluding materialization code
from ingest without binding it elsewhere would preserve stale results.

Use four implementation PRs in order: 1 CI cleanup and pruning
([ADR 0119](0119-deduplicate-workflows-and-prune-stale-extras.md)),
2 static dashboard publish, 3 retire hosted Streamlit
([ADR 0120](0120-replace-hosted-streamlit-with-static-dashboard.md)),
4 scoped hash (this record). PRs 2 and 3 merge separately, with recorded
deployed-page acceptance before PR 3. PR 4 needs a cold review before
merge. This record alone does not start implementation.

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

Before narrowing ingest coverage, extend `analytics_hash()` to bind
result-producing code to `analytical_id`:

- Keep `src/chess_analytics/corpus/*.py` and `contracts/*.json`.
- Add `src/chess_analytics/dashboard/analysis.py` and
  `src/chess_analytics/analyst/**/*.py`. The latter conservatively
  covers `semantic.py` and the checked tools' engine, Maia, opening,
  position, catalog, and worker helpers, including future Python files.
  Hashing frozen files does not permit editing them.
- Include the raw `marts/pipeline.py` file digest and the same
  non-generated dbt SQL/YAML inputs used by `model_hash()`. Governed
  model/materialization changes must also invalidate the analytical id
  used by checked tools and the `Dataset:` instructions line. Hash
  raw inputs here, not `model_hash()` or `mart_id()`, to avoid recursion:
  `model_hash()` already calls `analytics_hash()`.

Bind `marts/pipeline.py` explicitly into `model_hash()` alongside dbt
definitions and the analytical digest, before removing it from ingest
coverage. Its digest must reach `model_sha256` and hence `mart_id`,
including the stored manifest and model-hash sidecar. Keep generated
`dbt/target`, `logs`, and `dbt_packages` excluded. An unchanged source
with changed move-input preparation must build a new mart, never take
the old publication's reuse branch.

Keep corpus, analytical tools, and marts out of `implementation_hash`:
their changes invalidate downstream identities without minting a new
ingest `snapshot_id` for unchanged source rows. Pure presentation
modules such as `eval_report.py`, `public_extract.py`,
`dashboard_cube.py`, and `dashboard/dashboard.py` stay outside both
ingest and analytical digests. Other presentation/CLI wrappers and
routing code stay outside ingest; do not classify all of `dashboard/`
or `analyst/` as presentation.

In the unfrozen `dashboard.analysis.current_snapshot(project)` path,
require the stored `analytics_implementation_sha256` to match the
current digest and recompute `snapshot_identity()` from the manifest's
source snapshot and source SHA. Reject stale/missing digests or ids
before `CheckedTools` can answer or quote a request; rebuild the
analytical publication and matching mart first. Retain the semantic
layer's current model-hash mismatch check. Do not change frozen
`tools.py`, `provider.py`, or `live_runner.py` to enforce this boundary.

Do not rewrite committed live-eval receipts, frozen receipt hashes, or
any file in `live_runner.FROZEN_FILES`. Do not backfill old
`snapshot_id` values. After this lands, a receipt is like-for-like with
another only when both were produced with the same hash function and
the same `dataset_id` rules. Existing exception notes in
`eval_report.py` stay until a later docs pass can point at this
record; this change does not invent new hash-pair exceptions.

Mutation/invalidation tests run on isolated fixture copies:

- Presentation edits leave ingest/analytical digests, fresh snapshot
  ids, and quoted instructions unchanged. Ingest allowlist edits
  change `implementation_hash` and fresh `snapshot_id`; build/report
  reject old manifests. Cover Python, SQL, and contract inputs.
- Mutate corpus code, `dashboard/analysis.py` calculations, and
  `analyst/semantic.py` independently. Each changes `analytics_hash`
  and fresh `analytical_id`, leaves ingest identity unchanged, and
  rejects an old current pointer through `CheckedTools` and quoting.
  Rebuild, then prove `dataset_id` and `instructions_sha256` change.
  Check additional analyst helpers cannot escape the digest.
- Mutate `marts/pipeline.py` move preparation and a dbt definition
  independently. Each changes `model_hash`/`mart_id` and analytical
  identity without changing ingest identity. With an old publication
  present, assert `build_mart()` builds under the new id, preserves
  the old bytes, and writes matching manifest/sidecar hashes. Verify
  stale semantic marts are rejected; generated dbt files change none
  of these identities.
- Keep receipt byte pins, case/fixture hashes, and all current
  `FROZEN_FILES` hashes unchanged. Do not regenerate historical
  expectations to make mutation tests pass.

Local and CI snapshots rebuild through existing publication paths;
gitignored warehouses and old manifests are not migrated in place.

## Consequences

Pure presentation edits stop invalidating warehouse identity and the
`Dataset:` line in live-eval instructions. Analytical/tool and mart
logic changes still invalidate downstream identities. Future evals can
stay comparable across display-only dashboard or report changes.

Every existing staged or published local snapshot was hashed with the
old function. After this change, `build()` and `report()` will refuse
those manifests until the dataset is reingested. That is expected.
Reingest produces a new `snapshot_id` and, through
`snapshot_identity()`, a new `analytical_id`, so a new live eval will
not share `instructions_sha256` with receipts minted under the old
function. Existing analytical publications also fail the new current
digest check until rebuilt, even where ingest rows are reusable.
Historical receipts remain the record of those runs.

This is a data-model change, PR 4 of the four planned implementation
pull requests, and gets a cold review. It does not authorize a live
model call.

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

Both commits belong to PR 4, after PR 3 retires hosted Streamlit.

1. `fix(identity): bind analytical tools and mart materialization with invalidation tests`
2. `fix(ingest): narrow implementation hash with mutation and frozen-evidence checks`

Land expanded coverage and stale-publication guards before narrowing
the ingest hash; tests ship with each change. Commit 1 proves downstream
invalidation under the broad ingest hash; commit 2 adds the identity
isolation assertions with narrowed ingest coverage. Never rewrite
historical receipts, their hashes, or any `FROZEN_FILES` bytes.

## Implementation evidence — 2026-11-23

Isolated offline fixtures showed that presentation edits preserve the ingest and
analytical IDs and quoted instructions. Corpus, tool, and mart mutations change
downstream identities while reingesting the same rows yields the same source ID.
Mart rebuilds preserve prior publication bytes and agree with the model-hash
sidecar. The portfolio demo stages dbt definitions before publishing its snapshot.
The receipt test passed against the existing pins for six receipts and all 14
frozen modules. No live requests were made.
The targeted offline suite passed 93 tests. Ruff lint and format checks and
basedpyright passed. Engine, replay-gate and MCP tests stalled in the sandbox.

The PR 4 cold-review follow-up matched all three base digest algorithms on
identical Linux input files. Isolated checks verified sorted dbt definitions,
root-only generated dbt exclusions in demo staging, cache exclusion in the
warehouse digest, and errors for absent required files. Non-dbt fixtures cover
malformed pointers, bad source fields, and stale pointers after mart input edits.
The scoped identity, semantic layer, receipt, and portfolio demo suites passed
44 offline tests with dbt required. Ruff lint and format and basedpyright passed.

## Amendment (2026-11-23)

Cold review Major #1: `build()` and `report()` already refuse a warehouse
manifest whose `implementation_sha256` does not match `implementation_hash()`,
but `current_snapshot()` only compared `analytics_implementation_sha256` with
`analytics_hash()`. Ingest, warehouse, and metrics edits change
`implementation_hash()` without changing `analytics_hash()` or
`snapshot_identity()`, so an already published analytical snapshot stayed
servable. `CheckedTools` and `quote_request` both obtain the dataset through
`current_snapshot()`, and would still quote that stale `Dataset:` id.
`common.py` was on the ingest allowlist only. Its `digest` and `hash_json`
helpers feed every digest, including the analytical one, so a helper change
could also leave `analytical_id` unchanged.

`analytics_hash()` now includes `src/chess_analytics/common.py` in the same
explicit way `implementation_hash()` does. A change to those helpers changes
the analytical digest and therefore `analytical_id`.

The serving guard does not add a field to the analytical manifest. It reads
the hash ingest already stores, `implementation_sha256`, from the source
snapshot manifest named by `source_snapshot_id`. When that file exists, a
missing or unequal value raises before the analytical-digest and identity
checks:

```text
stored ingest implementation is missing or differs; reingest and rebuild the analytical snapshot and mart
```

That refusal is what `CheckedTools` and `quote_request` see, so neither serves
or quotes the snapshot. Checking the ingest hash first matters for `common.py`
and `contracts/*.json`, which sit in both digests: the message tells the user
to reingest, not only to rebuild. A missing source manifest raises the same
error once the analytical id still recomputes. A malformed source id keeps the
existing identity-mismatch error. Unchanged code still returns the current
snapshot. This does not edit frozen analyst modules, historical receipts, or
`uv.lock`. The amendment leaves `implementation_hash()` unchanged. Publications
from PR 4 before the amendment (`b0d6af6`) require an analytical snapshot and mart
rebuild. Pre-PR-4 publications from `main` require reingest and rebuild.
