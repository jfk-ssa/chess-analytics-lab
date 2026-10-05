# Repository review — 2026-10-04

This is the preserved pre-fix review. The selected handoff was subsequently
implemented; [current status](STATUS.md) and the [evidence index](EVIDENCE_INDEX.md)
identify post-fix checks. The findings below describe the reviewed baseline.

Review target: `26f675b80ef91f29406ebfb707d13b9f2004cde0` on `main`.
**Review only: implementation fixes are not applied.** M0–M7 remain historical
accepted checkpoints; public portfolio readiness is a separate gate. M8/Jev is
deferred by the owner. Execute the [handoff plan](PORTFOLIO_HANDOFF.md) next.

The baseline has useful separation between ingestion, checked publication,
parameterized analysis, typed analyst tools, and optional orchestration. Recovery,
resource limits, independent metric references, evidence audits and retained failed
experiments are substantial strengths. A wholesale rewrite is unwarranted.
The principal gaps are source integrity edge cases and reproducibility of the
complete product from committed fixtures.

## Verification and scope

| Check | Observed result |
|---|---|
| Existing local suite, dbt/dashboard extras | 56 passed, 0 skipped, 40.52 seconds |
| Tracked-only export, existing installed dependency runtime, exported source on PYTHONPATH | 44 passed, 12 skipped, 10.07 seconds |
| Exported tiny demo | Passed; 4/20 draw rate, 22 accepted games |
| Fresh exported environment, locked cache-only install | Incomplete: cached `pygments==2.21.0` wheel absent; no fresh-install success claimed |
| Ruff check and format check | Passed; 115 Python files formatted at baseline |
| Lock check, Git whitespace | Passed |
| Committed inventory | 467 files, 7,742,256 bytes; largest file uv.lock at 296,076 bytes |
| Relative Markdown file links | No missing targets found by simple link scan; anchors/external URLs not checked |
| Tracked payload/credential pattern check | No work/data payloads or key/private-key pattern matches; not a complete secret/history audit |
| Additional probes | Confirmed findings R1–R5 below; entirely offline |

Commands for the local suite were `UV_CACHE_DIR=.uv-cache uv run --locked --offline
--no-editable --extra dbt --extra dashboard pytest -q -ra`, Ruff check/format,
`uv lock --check --offline`, and `git diff --check`. An initial command without
workspace cache failed on sandbox access to the default cache, before testing.
The exported-source run used the existing `.venv/bin/python -m pytest` with
`PYTHONPATH=src:.`; it is a source-isolation check, not a fresh-install check.
Twelve exported tests skip because they depend on ignored M6/M7 data/config.
The retained December gate reconciliation and tampered-request-hash test passed.

Review covered acquisition and PGN normalization, snapshots, dbt/recovery,
orchestration boundaries, analytical extraction/metrics, dashboard, analyst
configuration/tools/scoring/experiment accounting, tests, CI, and portfolio docs.
No new archive downloads, orchestrator services, model calls, or paid experiments
were run. No hosted CI, fresh Linux/macOS matrix, full Git-history secret scan,
or comprehensive security certification is claimed. Existing tests block Python
socket connections in their process; that is not OS-level network isolation.

Machine-readable observations: [review evidence](../reports/repository-review.json).
Reproduction scripts are diagnostics, not production changes or new acceptance tests:

```sh
# Run from the repository root with existing installed dependencies.
mkdir -p work/repository-review
PYTHONPATH=src:. .venv/bin/python docs/review/reproduce_findings.py
# Requires dashboard extra and the existing local analytical dataset:
PYTHONPATH=src:. .venv/bin/python docs/review/reproduce_dashboard_empty_bucket.py
```

Use a new scratch directory or preserve/rename `work/repository-review/probe-data`
before repeating the first diagnostic. Both write only under ignored `work/`.

## Findings, ordered by implementation priority

### R1 — P1: non-finite budget and pricing values pass validation

`analyst_m5/provider.py:90` accepts NaN and positive infinity because it checks
numeric type and `<= 0` only. The diagnostic accepted both values for the cap,
input price and output price. NaN defeats ordinary ordered comparisons, and
infinity removes a meaningful finite bound. These values can reach Python through
its permissive JSON parser. The disabled example still fails closed; normal finite
historical configurations are not shown to be affected.

Plan: require finite positive monetary values, including optional cache prices,
and check finite accounting values at the relevant provider/preflight boundaries.
Reject invalid input before key lookup or transport. Add parameterized negative
tests for NaN, infinities, booleans, zero and negative values, plus valid finite
controls. Do not revise prices or authorize any live spend in this fix.

### R2 — P1: analytical publication does not bind both inputs to one source

`analytics_m3/publish.py:154–160` checks the extracted PGN against its receipt and
validates the source snapshot separately, without requiring their source hashes
to match. An isolated real publication succeeded with the same game ID and ply
count in two PGNs: source A had +0.10 evaluations; source B had +9.90. Published
moves contained 990 cp, while the manifest recorded source A's hash.

Plan: reject source/receipt hash mismatch before constructing a candidate; bind
source identity, receipt and plan consistently. Test mismatched annotations on the
same IDs/ply counts, with an existing current pointer, and verify pointer and
artifacts remain unchanged. A matching-source control must publish successfully.
Assess retained manifests/receipts read-only before drawing any conclusion about
historical data. This probe is not evidence that historical reports are wrong.

### R3 — P2: duplicate accepted games are extracted twice for moves

`analytics_m3/moves.py:119–132` scans raw records without a processed-game set.
The probe's source had two identical copies of one selected game: ingestion
correctly accepted one and counted one duplicate, but move extraction counted two
selected games and emitted eight moves instead of four. Later reconciliation
withholds publication, so this is a valid-input reliability failure, not demonstrated
silent double-counting in a published snapshot.

Plan: emit each accepted selected game once, preserving conflict rejection in
upstream ingestion. Test identical duplicates, excluded records, and conflicting
records; verify move keys, selected-game counts and metrics match a deduplicated
control and a failed candidate cannot replace the prior pointer.

### R4 — P2: empty clock bucket crashes the dashboard

`analytics_m4/dashboard.py:118–120` formats `evaluation_coverage` as a percentage
unconditionally. The metric legitimately returns None for zero eligible moves.
Streamlit AppTest with an injected empty bucket raised
`unsupported format string passed to NoneType.__format__`.

Plan: render explicit no-eligible/no-evaluable states, preserve zero as zero, and
check all bucket selections with empty, unevaluable and populated fixture data.
Use actual synthetic metric results in the acceptance test, not only a mock.

### R5 — P2: numeric scorer accepts booleans as exact numbers

`analyst_m5/evaluation.py:13–22` accepts True for both expected 1 and expected 1.0
(and corresponding False/zero cases) through Python numeric equality. The
reproduction confirms the scalar helper behavior. Existing independent evidence
audits provide additional checks; this finding alone does not invalidate a score.

Plan: define strict result types, reject booleans for numerical expectations, and
reject non-finite numbers. Add mutations exercising the public scorer. Preserve
historical rubric code/results; version a new rubric if score semantics change.
Any retrospective re-score must be labeled with its new rubric and compared to,
not overwrite, the frozen original.

### R6 — P1 for portfolio release: clean checkout cannot demonstrate all three projects

The supported `chesslab demo` covers ingestion and the foundation metric only.
The dashboard and analytical replay require an ignored analytical snapshot.
Twelve tests skip in the tracked-only export even with optional extras available.
CI has base/dbt jobs but no complete synthetic dashboard/analyst acceptance path.
This is a coverage/product-demo gap, not a failure of the tests that did run.

Plan: add a small hand-checked synthetic annotated PGN and a separate bounded demo
workspace exercising ingestion, analytical publication, opening and clock metrics,
checked analyst replay, evidence and explicit refusal/clarification. Include empty
and low-support data. Label synthetic data visibly; never imply model accuracy.
Add a dashboard-extra CI job and fresh-install/export acceptance. Keep expensive
real-data tests separate and report their skips accurately.

### R7 — P1 for portfolio release: onboarding and visible results are stale

`README.md:6` calls M7 in progress; `docs/DEMO.md:22` says the dashboard/analyst demo
is future work. `docs/RUNBOOK.md:31,46,54` describes M2 rollback and M5 provider
features as unimplemented. The CLI help also says replay is planned for M5.
The dashboard evaluation page shows only M5 harness results. `.env.example`
contains a legacy live-enabled placeholder, not an explanation of the current
named-key/config/cap workflow. The historical milestone docs themselves are useful;
the missing layer is an accurate current entry point.

Plan: replace stale current-state prose, introduce a concise evidence index, and
show fixture/replay/live results with dataset, split, revision and limitations.
Document discovery of sources, bounded acquisition, tool inventory, agent flow,
provider setup without secret values, recovery, and exact offline/live distinctions.
Link M7's retained successes AND failures. Do not present 150/150 as general model
accuracy or combine unrelated datasets into one benchmark statistic.

### R8 — Publication decision and maintainability work

`THIRD_PARTY_NOTICES.md` explicitly leaves the project license undecided. No LICENSE
is tracked. The owner must select the distribution license with dependency
compatibility considered; an implementation model must not silently select a
permissive grant. No remote is configured. Upload is a later explicit action.

Milestone prefixes in stable package names and current how-to docs make discovery
harder, but mass renaming is unsafe: snapshot and preflight hashes include paths
and implementation files. Keep milestone/version names on immutable historical
reports, cases and experiment scripts. Add functional entry points and navigation
first; defer package migration until compatibility and hash-version handling are
specified. Repeated monthly scripts can be generalized for future runs without
rewriting the scripts that produced frozen evidence.

## Handoff state

The interrupted implementation's five-file diff was saved to ignored
`work/repository-review/proposed-fixes.patch`, then reversed. It is incomplete and
untested; do not apply it wholesale. Production source is at the reviewed baseline.
Only review documentation, diagnostic scripts, evidence summary, and status/decision
notes are added by this review. Full diagnostic logs remain under ignored
`work/repository-review/`. No fixes, mass renames, new live runs, or upload occurred.
