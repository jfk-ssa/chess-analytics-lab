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

## 2026-10-03 — M4 local product and uncertainty

Use the specification's Streamlit default as a separate pinned optional extra,
version 1.50.0; the base ingestion environment remains lighter. A local
read-only DuckDB connection powers every view. Built-in charts and tables
suffice, so no custom frontend or hosting is added. The six pages share the
checked analytical ID and observed UTC dates. AI/evaluation pages initially
show offline M5 evidence and cannot imply a live model result.

The opening memo uses the supported Black 1400–1599 exact 60+0 cohort. Apply
pooled common weights across player-minus-opponent rating strata and use a
seeded 400-repetition focal-player cluster bootstrap. This gives a within-prefix
uncertainty description, not a probability interval for all August games;
opponent dependence and confounding remain. The clock memo emphasizes sparse
source-evaluation coverage and omits a naive independent-move interval.
Figure JSON, memos and a raw-PGN cross-check are tracked.

## 2026-10-03 — M5 bounded analyst and evaluation instrument

Keep deterministic typed tools and their SQL separate from interpretation,
provider transport, replay and scoring. Four steps maximum; each answer has
checked snapshot identity and content-derived evidence IDs. There is no
free-form SQL tool: read-only database mode alone is insufficient isolation,
and a separate worker is not justified for the initial offline path. File,
network, extension, multi-statement and unpublished-table attempts are
rejected at the tool boundary. Invalid plans fail rather than being silently
repaired; a semantic repair loop is a measured future extension.

Freeze 50 cases, 30 development and 20 test, with the six requested categories.
Generate reference values from the independent raw-PGN script and store replay
plans separately. The 50/50 replay result validates the harness and checked
tools; it is not a model benchmark. Once test labels are inspected for tuning,
retire this split from claims of untouched held-out model performance.

Add a small [Responses API](https://developers.openai.com/api/docs/guides/structured-outputs)
planner rather than an SDK dependency. It returns a structured tool plan; the
same checked local tools compute all numbers. The adapter reads only an
explicitly named personal key variable after a supplied config enables calls
and names a model, prices and positive run cap. One request is preflighted
against a conservative byte/token cost bound, with no retries; missing usage
fails closed. No model ID, price, account entitlement or benchmark result is
assumed current or established by this offline milestone.

## 2026-10-03 — M6 offline release preparation

Implement a disposable subprocess for live model-selected checked tool calls,
with a 30-second wall-clock timeout and a credential-free environment. The
allowlist remains the tool API; this process boundary enforces time limits and
keeps the provider key out of tool execution, but is not an OS-level sandbox.
Free-form SQL remains disabled.

Use the 30 development cases only for the first measured pilot; select 12 across
numerical, ambiguity, missing-data and access categories. Compare two typed
planner prompts using the same model/tools/settings and add metric definitions
only in the semantic-context condition. Do not call this the specification's
SQL baseline or an untouched holdout. The existing test references were
inspected during harness validation. A later held-out result requires a new
unseen family split.

Propose GPT-6 Luna at the official listed Standard text prices on 2026-10-03
($0.10/M input, $0.50/M output), 512 maximum output tokens, and a hypothetical
$1 total cap solely for the offline quote. This does not enable the tracked
provider config or authorize spend. Before a live run, reverify personal
entitlement, exact model/prices, and the user's cap, then freeze request and
code hashes. Reserve each entire request bound against the total cap. Retain
all responses/failures; stop after a failure with uncertain usage. Do not infer
zero cost from a transport error. No model request or result has occurred.

## 2026-10-03 — Shorter local key variable

Use `CHESSLAB_OPENAI_API_KEY` as the one allowed environment variable for a
personal API key. The user requested removing `PERSONAL` from the variable
name. Personal-account acknowledgement, explicit configuration, and the total
run spending cap remain separate required gates. The former longer variable
is not read as a fallback. No key value was accessed or migrated.

## 2026-10-03 — Optional M6 provider JSON

For the first M6 pilot, allow `--max-run-usd` instead of a separate personal
provider JSON. This deliberately invokes the same personal-key gate using the
GPT-6 Luna model and Standard text prices verified in official documentation
on 2026-10-03. A future run must reverify current terms. The cap stays
mandatory: an account credit balance is not a run budget, and gross API cost
is recorded even if credit covers it. The live command can load only the named
key from `work/.env` without sourcing other variables or shell code. Keep
`--config` for later model/pricing overrides. No request has occurred yet.

## 2026-10-03 — First actual M6 development pilot

The user chose a $0.10 gross-spend cap; the account's stated $9 credit did not
set the cap. The named personal key in ignored `work/.env` was loaded for the
live run without printing or committing it. Four prompt revisions were frozen
separately. The first three stopped after an unsupported extra tool argument,
invented filter keys, and a title-case color value, respectively. Their actual
responses and failures were retained. The final 24-cell run completed with
zero execution exceptions and 16/24 frozen-scorer passes. Across all 32 API
requests the gross recorded cost was $0.0046302. This is not an untouched
holdout or a repeatability result.

The $0.0046302 figure above is the originally recorded simple-rate estimate,
preserved as historical evidence. A cache-aware recalculation from every
retained provider usage record gives **$0.0028105** gross for the same 32
requests, including $0.0018115 for the final 24 cells. The frozen 16/24 score
does not change. GPT-6 Luna's official Standard rates checked on 2026-10-03
are $0.10/M regular input, $0.125/M cache writes, $0.01/M cached input and
$0.50/M output. If cache detail is absent, charge all input at the highest
applicable input rate for conservative accounting. Future preflights freeze
all four rates, and the runner stops if reported cost exceeds a reservation.

Do not adjust the frozen 16/24 result after inspection. Two proxy answers used
an equivalent checked tool and produced the expected numbers, but failed the
strict tool-choice rubric; discuss this discrepancy alongside, not in place
of, the original score. Multi-step comparison and unsupported-status handling
also failed. The 90% numerical and ambiguity gates are unmet, so M6 remains
in progress and the analyst stays experimental. A later release evaluation
requires development fixes, an unseen family-based split and manual review of
analytical failures. See `reports/M6-live-pilot.json` for response and cost
evidence and `reports/M6-live-preflight.json` for final frozen requests.

## 2026-10-03 — Further M6 development, still below release gate

The user approved a separate $0.10 gross cap for the next M6 evaluation.
Use the M6 2.0 scorer on subsequent runs to accept the equivalent checked
clock-pressure wrapper when numerical evidence matches; keep the original
M5-frozen 16/24 result. Clarify supported filters and refusal categories in
the planner instructions, without expanding the tool allowlist. A complete
24-cell revision scored 20/24, but answerable cases were only 9/12, below the
90% release target. The next revision stopped at 16 cells after a provider
response contained two output-text chunks, one malformed. Retain that full
response as a failed attempt and do not select a favorable chunk. These
40 requests cost $0.00361867 gross using cache-aware usage accounting, well
under the new $0.10 cap. The results are inspected development data, not a
held-out benchmark. M6 remains in progress; a new family-split holdout is
still needed after development quality reaches the gate.

## 2026-10-03 — Development gate reached, release gate untested

After correcting price accounting and freezing all four token rates, run one
further 24-cell development revision with a $0.04 per-run cap inside the
separate user-authorized $0.10 evaluation cap. It completed 24/24 with no
execution failures: 23/24 total, 11/12 answerable and 12/12
ambiguity/unsupported. Gross API cost was $0.00166282. The semantic-context
opening comparison still asked for clarification and failed. Do not claim
repeatability or held-out accuracy from this inspected set. The next M6 step
is a fresh unseen opening-family split, frozen before model execution, with
independent references and separate reporting of all failed attempts.

## 2026-10-04 — Freeze a new M6 family-split holdout before live scoring

Retire the inspected M5 test set for untouched model claims. Use eight new
opening-usage families and independently tallied raw-PGN White cohorts for
Zukertort Opening and King's Pawn Game. Freeze 20 cases: 14 answerable and
6 ambiguity/unsupported, including high-severity access and unsupported
claim requests. Keep the development prompt unchanged. Version the holdout
rubric to M6 2.1 so the checked clock wrapper is accepted for equivalent
evaluation-coverage evidence, provided values and filters match. Do not
retroactively rescore earlier development runs. Offline checked-tool/reference
validation passed all 20 cases; it is harness validation, not model accuracy.

Recheck the official GPT-6 Luna Standard rates on 2026-10-04 and freeze a
40-request preflight with conservative quote $0.0503635 and file/request
hashes. No holdout model response exists yet. The prior $0.10 cap covered
the development evaluation; request a separate gross cap before live holdout
execution. This first held-out run will be one-shot and cannot establish
repeatability. The SQL baseline remains deferred because safe free-form SQL
isolation is not implemented; label the comparison accordingly.

## 2026-10-04 — Holdout accuracy passed once; release held on repeatability

With explicit user authorization, execute the frozen 40-cell family-split
holdout and two identical repetitions under one $0.10 cumulative gross cap.
The first run completed 40/40 and scored 39/40, including 27/28 answerable,
12/12 ambiguity/unsupported, and 6/6 high-severity cases. Independent
post-run evidence audit found 40/40 completed responses internally traceable.
The one scored miss returned a real second-family metric instead of the
requested opening comparison.

Preserve both stopped repetitions. The second made 10 requests and stopped
on a two-chunk provider-format response; the third made 22 and stopped when
`compare_openings` lacked a `filters` wrapper. The third also made one
incorrect clarification refusal. No attempt was retried. Across 120 planned
request slots, 72 were attempted and 48 never attempted. All attempt costs
are known; total gross cost was $0.0060692, under the cap. Report missing
cells explicitly and do not use attempted-only scores as repeatability
estimates. The first run's accuracy gates passed, but a measured release
requires reliable completion; keep M6 in progress and the analyst labeled
experimental. This holdout is now inspected and retired for future untouched
model claims. Remediate on development cases and freeze a new holdout before
trying another live release evaluation. The typed-planner contrast remains
separate from the unimplemented restricted-SQL baseline.

## 2026-10-04 — Explicit adapter recovery, provider comparison deferred

Repair only two narrow, observed transport/argument structures before another
release check. If a provider response contains multiple output text chunks,
accept it only when exactly one chunk parses as the strict structured plan;
record the chosen index/hash and discarded chunks. If `compare_openings` has
exactly its six known flat filter fields, wrap them under `filters` and record
the normalization. Leave ambiguous plans, extra fields and invalid checked
tool arguments as failures. Retain raw responses and keep the prior held-out
scores frozen. The prior holdout is now development evidence; do not rerun it
as an untouched release case.

Use a second new opening-family split for release evaluation. The 20 v2 cases
passed offline checked-tool/reference checks. Freeze model, prompt, case hash,
all 40 requests, dataset and four price rates in `reports/M6-holdout-v2-preflight.json`.
The user approved up to three repetitions under a new $0.10 cumulative gross
cap. A one-run conservative reservation is $0.05214725; verify actual usage
and the remaining conservative bound before each later repetition. No v2
model outcome has been scored yet.

Direct OpenAI remains the M6 baseline. OpenRouter and CheaperInference may be
compared in M7 after direct-provider release gates are met, or sooner only if
a materially different model or spending level justifies a controlled paired
experiment. Current spend is cents, so routing savings are immaterial. See
`docs/PROVIDERS.md` for current provider claims and the required comparison.

## 2026-10-04 — Accept the bounded M6 typed-analyst release

The user authorized up to three frozen v2 40-request repetitions under a
$0.10 cumulative gross cap. All three completed, with scored passes 40/40,
38/40 and 40/40. Answerable numerical cases passed 82/84 overall (each repeat
at least 26/28); ambiguity/unsupported passed 36/36; high-severity passed
18/18; evidence integrity passed 120/120. No attempt crashed or lacked known
usage cost. Gross cost was $0.009968525. The two misses were safe but incorrect
abstentions on answerable clock-coverage questions in one semantic-context
repeat. Preserve them and the first holdout's stopped runs; do not tune the
frozen scorer retroactively. The second split is now inspected and retired.

Accept M6 locally for this bounded typed-tool product because its frozen
release gates passed and the locked full offline suite passed 43/43. This is a
small descriptive benchmark, not broad model accuracy. The experiment does
not include the proposed restricted-SQL baseline or three-arm contrast;
free-form SQL stays disabled pending a proven isolated worker. No additional
live cap is active. M7 is next, initially focused on clock-coverage routing
and a new split if another release claim is needed. Provider comparison is
deferred until a concrete cost or model-choice reason exists.

## 2026-10-04 — Start M7 with error-driven depth; defer provider alternatives

The user clarified that OpenRouter or CheaperInference should be considered
**only when costs rise**. This supersedes earlier wording that allowed a
model-choice reason by itself. The M6 accepted holdout cost less than one cent;
do not build a router comparison now. No new live run is authorized by M6's
closed $0.10 cap.

Start M7 from the two inspected clock-coverage abstentions. Add an explicit
planner instruction that a specified bucket's evaluation coverage is answerable
from checked eligible/evaluable counts despite sparse evaluation availability.
Keep missing-bucket clarification, causal claims, private data and full-month
projection unsupported or clarified as before. This instruction is a development
change only; it is not evidence of improved model accuracy. Next build new
independent development and held-out cases before seeking a new live cap.

The depth order is evaluation quality first, then bounded data-extension
feasibility, then optional controlled engine enrichment. The current 40 MB
prefix covers August 1 only and Stockfish is not installed locally. Do not
start an unbounded download or engine run; adopt either only after measuring
coverage benefit and resource cost. See `docs/M7.md`.

The initial 12-case clock development set uses the independent M3 raw-PGN
tally for four buckets and includes missing-bucket, private-data, causal and
full-month negative controls. Its checked-tool/oracle replay passed 12/12.
Those are harness results, not model responses; they do not justify a new
quality claim or reuse of the inspected M6 v2 holdout.

## 2026-10-04 — Always recommend a spend cap with an estimate

The user wants a concrete recommendation whenever a live-run spending limit
is needed. Before asking, present the exact frozen request count, current
official model rates, the run's conservative preflight reservation, comparable
actual usage-based costs, uncertainty from cache/output/failures, and a
recommended **gross** cumulative cap. State that account credit is not the
cap. Do not ask for an unexplained number or infer authorization from these
planning figures.

For M7 planning only, scaling the M6 v2 shape gives ~$0.1304 conservative
reservation versus ~$0.0083 actual-cost forecast for 100 calls, and ~$0.3911
versus ~$0.0249 for 300 calls. Recommend **$0.15 for one 50-case/two-condition
pass** or **$0.45 cumulative for three passes**, conditional on a new exact
preflight that fits. These are not M7 quotes or approvals. See `docs/M7.md`.

## 2026-10-04 — Freeze M7 holdout under approved $0.50 cumulative cap

The user authorized a $0.50 **cumulative gross** limit for M7. Build 50 new
cases before calling the model: 41 answerable, 9 clarification/unsupported,
and 5 high-severity. Opening usage uses 25 families absent from inspected
M5/M6 cases. Independently tally those families and four new White 1400–1599
60+0 cohorts from raw PGNs; reuse the independent M3 clock reference. The
checked-tool oracle matches all 50 before live calls. Freeze 100 requests,
24 code/data/contract hashes, model, prices, dataset and scorer in
`reports/M7-holdout-preflight.json`.

The exact conservative reservation is $0.13475275 per 100-request repeat,
$0.40425825 for three. The approved $0.50 cap fits three, conditional on
rechecking the freeze and remaining gross budget before each. A failed or
unknown-cost attempt stops later calls and keeps its raw record. Do not tune
on this split after inspection and call it untouched again. No model result
is claimed at this preflight checkpoint.
