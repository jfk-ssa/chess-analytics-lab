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

## 2026-10-03 — Cost, AI and licensing

No cloud resources, subscriptions, live SDK, API key discovery, Jev adapter or
recommender. Provider config is disabled and remains inert in M0/M1.
M5 must implement personal-account and explicit monetary-cap validation before any
live adapter can execute. Unknown provider usage/cost must never be treated as zero.

Lichess standard archive: CC0. python-chess is GPL-3.0-or-later; do not claim all
dependencies are permissive. Repository distribution license remains undecided
pending review before public distribution; no license guessed from data licensing.

## 2026-10-03 — Parallel orchestration learning path

User requested Dagster and Prefect versions in this repository, with Airflow a
possible later exercise. Keep the M1 pipeline as the single implementation and
put thin framework adapters outside `src/`, so neither can redefine ingestion or
the governed metric. Pin Dagster 1.13.25, dagster-webserver 1.13.25, and Prefect
3.8.7 as separate optional extras in the same uv lock. Use synthetic fixture
data by default, isolated local data directories, no automatic schedules, and
local UI/server only. Prefect rejects inherited API keys or remote API URLs; both
disable telemetry in the adapter's local invocation. This is an M2 learning slice,
not evidence that the dbt/recovery milestone is complete.

The framework comparison checks same-source published results rather than relying
on run-status messages alone. It produced matching fixture snapshot identity,
counts and 4/20 metric; these are harness results, not AI responses, production
reliability evidence, or a hosted orchestration benchmark. The first Prefect run
could not bind its ephemeral local API in the sandbox; a local-loopback-permitted
run succeeded. Preserve the failure in status instead of hiding it.

Airflow is deferred until after M2 dbt work supplies meaningful transformed assets
to orchestrate. Its extra server/database/install cost is not justified for the
current three-step tiny path. Reassess if learning a DAG/operator model still adds
value then. No Airflow installation or cloud infrastructure now.

## 2026-10-03 — M2 dbt and mart recovery

Pin `dbt-duckdb==1.10.1` as a separate optional extra. The resolved local
combination includes dbt-core 1.12.5 and existing DuckDB 1.4.1; it actually built
the tiny and foundation models. Keep five SQL models and generic/singular data
tests in `dbt/`, with one local DuckDB profile and one thread. No hosted dbt
service or remote connection is required. dbt usage telemetry is disabled for
the wrapper's subprocess.

Retain M1 snapshots as immutable sources. M2 copies the checked DuckDB file to
an attempt directory, executes dbt there, reconciles mart counts with the M1
metric contract, and publishes a separate immutable mart only after success.
The mart identity includes M1 snapshot, dbt model files, and uv lock hashes.
Store dbt lineage/result artifacts with the published mart and keep failure logs
with attempts. A historical backfill does not switch the current mart pointer;
rollback selects only a validated prior mart. The one-writer lock covers mart
publication. This adds local disk cost (the foundation mart database was 30 MB)
but no recurring service charge.

Source drift severity remains simple and explicit: a configured publisher
checksum mismatch fails ingestion; multiple observed hashes for an unpinned
local dataset produce an operational warning. This is not a full schema-evolution
system. The process-level injected failures and recovery tests passed; power-loss
durability, general multi-source reconciliation, process peak-memory measurement,
and unattended scheduling remain outside the claim. Both existing orchestrators
gain an opt-in fourth dbt step, preserving their small default demonstrations.

## 2026-10-03 — M3 partial corpus and exploratory analytics

The newer complete monthly archive is too large for a low-cost personal build.
Use a fixed 40 MB compressed byte prefix of the August 2026 Lichess standard
rated archive, pinned by SHA256, then retain at most 100,000 complete PGNs.
Verify the server's partial-content response for a fresh download; a local
cache must match the pinned prefix hash. Do not equate that hash with a
publisher checksum of the full archive. Label every result partial and report
the observed UTC date range; the first 100,000 complete games cover only
August 1. No monthly extrapolation or random-sample inference is valid.

Reuse the M1 legal replay, normalized facts and publication checks. Give the
bounded source its own M1 snapshot, and publish move annotations in a separate
immutable analytical snapshot. A game-ID hash selects roughly 5% of accepted
games for move replay independent of clock/evaluation annotation presence.
Retain selected zero-ply games in the sample count even though they have no
move rows. Source Opening tags define opening families; do not invent an ECO
classifier. Version the opening, player-score, move-table and clock contracts.

Clock-before means the player's previous own recorded clock in zero-increment
games. Count a >=200 cp mover-perspective evaluation deterioration as an
exploratory error proxy only when both adjacent source evaluations are
centipawn values. Missing and mate evaluations are separate coverage losses.
This is not an official engine-quality classification or causal time-pressure
effect. The observed low evaluation coverage must accompany any rate.

Raw-PGN reference code independently tallies key opening and clock results.
Keep 12 draft development cases tied to the published analytical ID, including
questions that should be clarified or declined. They are input/rubric fixtures,
not model evaluations. No live provider or personal spending setup is needed
for M3; M5/M6 safeguards remain required before live calls.
