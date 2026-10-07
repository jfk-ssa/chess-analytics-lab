# Portfolio implementation handoff

Start with [the review](REPOSITORY_REVIEW.md), `AGENTS.md`, `STATUS.md`,
`DECISIONS.md`, and the original `PROJECT_SPEC.md`. The reviewed production baseline
is commit `26f675b80ef91f29406ebfb707d13b9f2004cde0`; accepted experimental baseline
tag is `m7-baseline` (`f814377`). These identify different things intentionally.
The owner selected this plan for implementation. Steps 1–5 are implemented and the step 6 clean-export checks passed.
The owner subsequently selected GPL-3.0-or-later for original project code;
this is the preserved hardening handoff, not the current publication state.
The repository subsequently became public; see [STATUS](STATUS.md). Do not
create a new repository or split the three projects.

## Suggested execution order

Keep each step small enough for an independent diff and acceptance report. Record
completed behavior, tests, limitations and next step in STATUS; record decisions
in DECISIONS. Never mark a step complete solely because code was written.

| Step | Scope | Completion evidence |
|---|---|---|
| 1. Financial and source integrity | R1 finite values; R2 source binding; R3 move deduplication | Focused regression tests fail on baseline/pass after fixes; matching input succeeds; prior pointers unchanged on rejection; full offline suite passes |
| 2. Presentation and scoring boundaries | R4 empty states; R5 typed numerical scoring | Empty/unevaluable/zero/nonzero UI tests; public scorer rejects bool/nonfinite mutations; frozen rubric unchanged or explicitly versioned |
| 3. Complete offline product demo | R6 synthetic annotated source and isolated demo workspace | One documented sequence runs all three projects from tracked files, without personal config, network, or real data; reference arithmetic, repeatability, six UI views, replay and refusals pass |
| 4. Current product documentation | R7 README, demo, runbook, evidence and architecture navigation | All published commands tested in exported checkout; working local links; explicit data coverage/cost/failure labels; no stale current-state assertions |
| 5. Conservative naming cleanup | Functional entry points/tests/docs first; immutable experiment history retained | Old commands remain supported; new commands documented/tested; frozen checkpoint validation still passes; no unrelated hash-bound rewrites |
| 6. Release packaging | Clean install/CI, archive inventory, history secret scan, license decision | Export reproduced; CI results accurately reported; owner license decision resolved; package contains only intended source/docs/compact evidence; no private configuration or bulk data |

Steps 1–2 precede the synthetic demo so its edge cases exercise corrected behavior.
Steps 3–4 can land together if keeping commands/docs coherent requires it. Step 5
must not turn into a broad refactor. Runtime package migration is optional later
work, not a prerequisite for a strong portfolio.

## Detailed acceptance contract

### Integrity changes

Use synthetic sources under temporary directories and the real publication code.
Test source A/source B with matching game IDs and ply counts but different annotation
bytes; rejection must happen before publication. Include identical duplicate selected
games, selected zero-ply games and a conflicting-source control. Preserve the
upstream rule that conflicts reject the candidate rather than silently pick a winner.

Budget validation tests must never read a key or call transport. Cover each supported
monetary field, including optional cache rates, with finite positives and invalid
NaN/infinity/bool/zero/negative values. Check preflight/accounting entry points for
finite inputs without assuming a fixed provider price. Historical configs/results
must remain unchanged. Version scorer behavior where necessary.

Read retained analytical receipts and source manifests to determine whether the
R2 mismatch ever occurred in existing local data. Record how many pairs were checked
and any unavailable pairs; do not infer historical contamination from a synthetic
probe or imply all historical inputs were checked when some are missing.

### Complete offline demo

Suggested functional command: `chesslab demo --scope all` (or a comparably clear
new subcommand), while retaining the existing tiny demo. Select the exact interface
as a routine documented choice. It must use committed synthetic PGNs, a separate
workspace under ignored work/, explicit source_kind and deterministic IDs. Never
overwrite a user's real analytical pointer or frozen report.

The fixture should include two useful opening families, sufficient hand-computable
cohorts, clocks and centipawn/mate/missing annotations, empty clock buckets, low
support, duplicates and exclusions. Do not pad it to resemble a real population.
Keep expected values independent of production query output. Verify:

1. Ingestion, publication and repeat execution reconcile counts and stable IDs.
2. Opening numerator/denominator and player-score perspectives match a reference.
3. Clock proxy uses prior same-side time and correct mover evaluation perspective.
4. Analyst evidence binds to the fixture snapshot; ambiguous/unsupported requests
   produce the intended boundary result, and wrong-answer mutations fail scoring.
5. All six dashboard views work against the fixture, including empty selections;
   UI explicitly distinguishes fixture replay from retained live experiments.
6. Test/demo succeed without .env, provider JSON, ignored real data or network.

Dashboard project resolution needs an explicit supported way to point at this
isolated workspace. Avoid hardcoded user paths or a silent fallback to real data.
The existing partial patch proposes one approach, but it is not an accepted design.

### Portfolio documentation structure

Keep README short: project purpose, architecture, three capabilities, two findings
with denominator/coverage limits, measured evaluation checkpoint, quickstart,
screenshot if reproducibly generated, and links to deeper docs. Explain that most
archive prefixes cover only one observed day. Infrastructure target is $0 recurring;
paid historical evaluation cost is separate from that target.

Recommended current navigation (create only pages that add distinct value):

| Document | Content |
|---|---|
| README.md | Portfolio overview and fastest verified demo |
| docs/ARCHITECTURE.md | Data → checked snapshots → analytics → typed tools → evaluated analyst; local boundaries and orchestrator roles |
| docs/DEMO.md | Five-minute offline walkthrough, then optional real-data walkthrough |
| docs/DATA_SOURCES.md | Source discovery links, chosen archives/prefixes, caps, checksums, coverage, missingness, independent reference procedure |
| docs/RUNBOOK.md | Install, data paths, repeat ingestion, dbt/recovery, dashboard/replay, provider incidents and cost accounting |
| docs/EVALUATION.md | Harness/replay/live definitions; frozen splits, references, scoring, failures, repeats, actual/accounted costs, latest accepted gate |
| docs/EVIDENCE_INDEX.md | Map each claim to report, generating/checking command, inputs and reproduction limits |
| docs/STATUS.md and docs/DECISIONS.md | Current phase state and rationale for later chats |
| Existing M*.md and reports/M* | Historical evidence, retained with original meaning and identity |

Document actual CLI/module commands from code, not proposed commands from the brief.
Keep personal key names documented (`CHESSLAB_OPENAI_API_KEY`) without values. Fix
legacy example wording without enabling anything by default. Explain where local
raw responses live and which compact redacted reports are committed. A reader must
be able to find both accepted M7 evidence and failed/stopped runs without reading
all of DECISIONS. Link the optional Dagster and Prefect demos; Airflow stays follow-up.

### Naming policy

Milestone names are useful for project history and evidence provenance. They are
less useful as the primary API users learn. Prefer functional nouns for stable
interfaces and responsibility-based test names. Do not mass-rename hash-bound data.

| Current naming | Planned treatment |
|---|---|
| `platform_m2` | Document as platform/marts; retain import compatibility; eventual functional package migration separately versioned |
| `analytics_m3`, `analytics_m4` | Expose extraction/metrics/dashboard through functional commands first; avoid immediate package move |
| `analyst_m5` | Functional analyst/replay/evaluate entry points with existing module commands retained |
| `tests/test_m2.py` … `test_m7.py` | Rename/split by behavior when editing, e.g. marts, move metrics, provider budgets, frozen gates; avoid mixing renames with unrelated logic |
| `docs/M*.md`, `reports/M*.json`, frozen case and replay paths | Preserve; provide functional index and historical badges |
| Repeated monthly experiment scripts | Keep original evidence-producing versions; extract reusable runner only for a future experiment |

The source and analytical hash functions include relative paths and file contents.
A rename can require a new snapshot or invalidate a preflight even if logic is
unchanged. Do not “repair” old hashes to hide a rename. Prove compatibility before
moving packages/contracts/scripts; keep frozen workspaces isolated.

### Release packaging and decisions

Run a fresh locked installation with a complete cache or explicitly permitted
one-time dependency download. The review's offline install stopped at missing
Pygments; do not call that a lock defect or claim it passed. Then run commands in a
tracked-only export. Add a CI dashboard-extra job with the complete synthetic demo.
Hosted CI remains unverified until a real run exists. Report optional real-data
skips separately from required fixture acceptance.

Inspect the upload candidate and reachable Git history for secrets, personal paths,
bulk data and raw private traces. Never print matched credentials. Current inventory
has no tracked work/data payloads and no simple key-pattern matches, but this is
not a history scan. Preserve historical failures in compact reviewed reports; don't
sweep them away to make the portfolio look successful. Keep generated local logs,
.env files, virtual environments and caches out of an upload/archive.

The repository license is the one substantive owner decision before public release.
Ask about it with the concrete dependency notice context; do not silently choose a
license. No remote/upload target is currently configured. Prepare a reviewable
archive or commit set first; publish only on explicit instruction. If the next model
needs tools beyond existing dependencies, justify the addition before expanding
scope. No new provider or orchestration service is needed for this work.

## Copyable implementation prompt

> Implement the bounded portfolio hardening plan in docs/PORTFOLIO_HANDOFF.md using
> docs/REPOSITORY_REVIEW.md and reports/repository-review.json as the review evidence.
> Read AGENTS.md and preserve existing work. Start with steps 1–2 and use meaningful
> regression checks; then complete the offline demo and current documentation.
> Keep M0–M7 historical evidence and frozen hashes intact. Do not apply the saved
> partial patch blindly. Do not make live model calls, acquire larger datasets,
> enable Jev, provision cloud resources, or publish/upload. Keep STATUS and DECISIONS
> current, report verification and limits per step, and ask only for unresolved
> owner decisions such as the distribution license. Use functional naming at the
> public interface; defer sweeping package renames. Finish with a reviewable change
> set and clean-export acceptance evidence.

The quoted prompt is the instruction that triggered this implementation. Consult
STATUS.md for current acceptance and remaining release work.
