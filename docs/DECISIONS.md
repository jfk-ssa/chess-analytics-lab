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

## 2026-10-04 — Retire inspected M7 v1; freeze fresh v2 under the same cap

The first v1 repetition stopped after 49 attempts (48 completed/scored passes)
on an HTTP 400 without usage. A separate diagnostic request of the same frozen
payload succeeded; it is not benchmark evidence. Charge the unknown attempt
its full $0.00096025 reservation. A new v1 repetition completed 95/100 with
100/100 evidence integrity; the next stopped after 20 attempts on two identical
valid plan chunks, 18/19 completed answers passing. Preserve all raw records
and reports. These inspected runs are development evidence; do not claim a
repeatable release from them. Known API gross is $0.014789635, cumulative
accounting including the unknown reservation is $0.015749885.

Accept repeated structured chunks only when their parsed plans are identical;
reject conflicting valid plans. Expose bounded HTTP error details in retained
failure logs. Freeze a new v2 code/case split after these offline fixes. Its 25
opening families are absent from inspected M5/M6/M7 v1 cases; independently
tally four new cohorts from retained raw PGNs. All 50 oracle cases match checked
tools. The v2 preflight reserves $0.13476325 per 100 calls, and three repeats
plus prior accounted gross equal $0.420039635 below the user-approved $0.50
cumulative M7 cap. The cap remains gross and includes failed/unknown attempts.
No v2 model result is claimed at this freeze.

## 2026-10-04 — Preserve failed M7 v2 gate and freeze a targeted v3 split

Three complete v2 repetitions scored 90/100, 96/100 and 92/100. The combined
answerable count was 224/246, but the first run's 72/82 was below the
per-repeat 90% gate. All 54 ambiguity/unsupported, 30 high-severity and 300
evidence-integrity checks passed; no execution failure occurred. Gross v2
cost was $0.025244195, cumulative M7 accounted gross $0.04099408.
Retain the failing gate and every miss, including an answer with correct
numbers but an extra final coverage tool route. Do not re-score inspected v2.

Repeated safe abstentions on specified clock-proxy questions justify one
narrow prompt revision. Freeze a third 50-case split using 25 more opening
families absent from inspected cases; select four nonempty (though small)
cohorts and independently tally raw PGNs. Rephrase questions and validate
all 50 checked-tool/oracle answers before model calls. The v3 conservative
reservation is $0.1395495 per 100 requests; three plus prior accounted gross
are $0.45964258, within the existing approved $0.50 cumulative M7 cap. No
provider or scorer change is claimed as a model-quality result before v3 live
evaluation.

## 2026-10-04 — Preserve v3 boundary miss; freeze one final v4 split

The v3 frozen repetitions scored 96/100, 95/100 and 98/100. Answerable
cases passed 238/246 with each run above 90%, but ambiguity/unsupported
was 16/18 in run 1 and 51/54 overall. The two run-1 misses were safe
`unsupported` responses to the same personal-style question whose frozen
reference expected clarification. Keep this failed gate and do not re-score.
All 30 high-severity and 300 evidence-integrity checks passed. Gross v3 cost
was $0.026632805; cumulative M7 accounted gross is $0.067626885.

For one final M7 evaluation, clarify that a fully specified, nonempty but
small opening cohort is answerable descriptively with a sample-size caveat.
Write new missing-filter questions whose clarification reference is less
ambiguous. Use 25 additional opening families absent every inspected split,
four independently tallied tiny cohorts, 50/50 offline oracle/reference
checks, and a fresh freeze before model calls. The v4 conservative quote is
$0.142884 per 100-request repeat; three repeats plus prior accounted gross
are $0.496278885 under the existing approved $0.50 cumulative cap. No v4
model outcome is claimed at this freeze.

Measure data depth without new acquisition: 40 MB compressed prefix,
236,533,866 extracted PGN bytes, 100,000 complete games, 111 seconds
source ingestion and August 1-only observed coverage. Raising the byte cap
alone while retaining the 100,000-game cap adds no observed date. Defer a
new-day acquisition until a bounded date-targeted method is demonstrated;
defer engine enrichment until a fixed, measured value test is defined.

## 2026-10-04 — Stop M7 v4 on provider rejection; keep M7 open

The final v4 split passed 50/50 offline oracle checks and was frozen before
live calls. Its first repetition stopped at attempt 59 when the provider
returned HTTP 400 `invalid_request_error` saying the prompt was flagged.
The failed request has no usage; charge its full $0.001043 reservation and
make no further calls on this split. Preserve 58 completed responses, 41
scored passes and 41 unattempted cells. In the first 29 completed pairs,
schema-only passed 12/29 and governed metric context 29/29. This is censored
evidence and does not establish a full-run or broad quality comparison.

Across M7, known actual gross is $0.072358895; the two unknown-cost
attempts carry $0.00200325 in full reservations. Total accounted gross is
$0.074362145 below the user-approved $0.50 cumulative cap. This includes
the separate v1 diagnostic call. The v2 and v3 frozen quality gates failed,
and v4 did not complete. Keep M7 **in progress** with a measured negative
checkpoint, rather than treating the improved development scores as an
accepted release. No more calls on inspected cases. The next credible
quality gate needs independently referenced new data, a new untouched
holdout, and a bounded acquisition method. M8 Jev remains follow-up and
the recommender remains backlog.

## 2026-10-04 — Bounded cross-month M7 data and product-condition gate

Use exact 40,000,000-byte HTTP 206 prefixes from separate completed monthly
standard-rated archives, each capped at 100,000 complete games, to obtain
new source dates without scanning gigabytes farther into August. July, June
and May 2026 prefixes are each observed only on their first UTC day. Pin
their byte hashes and publisher listing values; do not claim full-archive
checksums, random samples, monthwide estimates or within-month trends.
Keep each candidate's data pointers in an ignored isolated project view and
retain the accepted August dashboard and snapshots. This adds local disk
use and ingestion time but no cloud service. Independent raw-PGN references
and checked-tool oracles must pass before any live holdout.

The product uses governed `semantic_context`, so M7's new-data release gate
tests that condition alone. The earlier paired `schema_only` results remain
an ablation. Precommit 50 cases, three complete repetitions, per-run
answerable >=37/41, boundary 9/9, high-severity 5/5, all evidence audits,
known gross cost and the existing $0.50 cumulative cap. This finite gate
does not estimate general model accuracy. Repeated opening family names
across months are transparent; new data/date identity, not family
disjointness, is the independence claim.

July v5 failed the first complete quality gate and later stopped on provider
HTTP 400; retain both. Its governed metric definitions contained August-only
caveats, a concrete incompatibility with July questions. Use month-neutral
opening and clock caveats in the isolated subsequent workspaces, without
rewriting the historical August contracts or altering accepted snapshot IDs.
Six inspected development templates passed twice on June data; they are
not held-out results. June v6 then stopped twice after provider-completed
plans placed a valid leading argument object followed by unrelated text
inside `args_json`. Keep the original live failures. Add a bounded parser
recovery that logs ignored suffix length, rejects an additional structured
object or an oversized suffix, and still requires allowlisted typed-tool
validation. The retained responses pass a separately labeled offline replay;
this does not retroactively change their live scores. Freeze this code on
a fresh May date/case set before evaluating again.

Stockfish remains unadopted: new source-date and cohort-support benefit is
measured without an engine, while selected source evaluations still limit
clock interpretation. A future fixed-node pilot needs a separate question
and measured accuracy/resource benefit before adoption.

## 2026-10-04 — M8 Jev route selection deferred to a narrow measured task

The user flagged Jev, `pg_jev`, and DuckDB's Jev support for M8. Record the
comparison in [M8.md](M8.md). After M7 acceptance and a concrete row-level
decision task, test a direct typed Jev adapter first, then the DuckDB
community extension as the natural SQL route in this local stack. Consider
`pg_jev` only if a PostgreSQL learning slice offers enough benefit to justify
operating a second database and its `plpython3u`/superuser setup. Check
current extension compatibility, API entitlement, prices and credential
behavior before any live M8 experiment. Recommend a specific gross cap with
a conservative quote then; do not infer access from a login or the existing
OpenAI credit. The personalized recommender remains backlog.

## 2026-10-04 — Preserve May/April failed gates; repair only unambiguous plans

The May v7 complete run scored 36/41 answerable, below the 37/41 gate; its
second run stopped on provider HTTP 400. Five exact source-family usage misses
pass a narrowly specified checked-tool routing **offline replay**. June's two
malformed `args_json` responses pass bounded leading-object recovery offline.
The April v8 new-date run scored 50/50 and 49/50 in its first two repetitions,
then stopped at cell 13 of the third when a provider response repeated the
same valid plan ten times and truncated another copy. Keep all original live
scores and failures. The April parser fix accepts only identical complete
objects, optionally followed by a duplicate prefix when the provider marks
an incomplete response. Reject conflicting objects, unrelated suffixes,
oversized text or excess repetitions; log recovery. The retained April
response passes offline replay. This is not live release evidence.

Use the March v9 bounded first-day source prefix and independently referenced
50-case freeze to test the parser in a new live run. The exact March range is
40,000,000 bytes of the 29,351,713,061-byte publisher listing; `counts.txt`
lists 90,074,196 games for the full archive. The original 5 GB *aggregate
local work* allowance rejected a new download before writing bytes because
retained historical workspaces used about 4.8 GB. Keep that zero-byte failed
attempt, raise only this acquisition allowance to 6 GB, and retain the 40 MB
fetch and 100,000-complete-PGN caps. The machine had about 69 GiB free.

Prior M7 accounted gross through April is $0.102386695. The March preflight
reserves $0.094273125 per 50-cell repetition, including one logged and fully
charged transport retry; three plus prior reserve $0.385206070 under the
existing $0.50 cumulative gross approval. The gate remains three complete
runs, answerable >=37/41 each, boundaries 9/9, high severity 5/5, all
integrity checks, no final failure or unknown cost. Report any deterministic
semantic repairs and text recoveries separately from unmodified model plans.

## 2026-10-04 — Retire stopped March v9; freeze February v10 under the same cap

March v9 stopped after 16 attempts: 15 completed, 14 scored passes, with
one HTTP 400 rescued by the single logged retry and a later HTTP 400 stopping
the run. Two unknown-cost subattempts are charged at full reservations.
Cumulative M7 accounted gross is $0.107639170. The overlapping Queen's
Gambit Declined family repair passes offline replay, but the original live
miss remains. Do not claim a three-run gate from partial results.

For the February v10 freeze, retain the same checked-tool boundary behavior
while shortening the planner's inaccessible-data phrase. Allow at most three
logged HTTP 400 transport retries on distinct cells per run, one retry per
cell. This is a measured response to repeated provider rejections on ordinary
opening questions; every rejected subattempt is charged at its full
reservation, and any final failed request stops. The fresh February first-day
40 MB source prefix yielded 99,585 accepted of 100,000 complete PGNs,
5,020 selected games and 335,854 move rows. Independent raw-PGN and 50/50
offline oracle checks passed. Its preflight reserves $0.098598875 per run
including three retries, or $0.403435795 for three plus all prior M7 spend,
under the existing $0.50 cumulative gross cap. Preserve failures and
separate model results from offline replay and deterministic repairs.

## 2026-10-04 — Retire February v10 and prepare new January source

February v10 repetition 1 met all per-run gates (47/50 total, 38/41
answerable, 9/9 boundary, 5/5 high severity, 50/50 evidence integrity),
with one logged HTTP 400 retry and one deterministic semantic repair.
Repetition 2 stopped at cell 26 after 25 completed scored passes: the
provider returned a complete plan plus 870 repeated non-ASCII punctuation
characters and marked the response incomplete at the output cap. Preserve
the original stopped result. The new parser accepts a complete plan followed
only by a bounded single non-ASCII punctuation/symbol repetition when the
provider declares the response incomplete; all other suffixes fail closed.
The retained response passes offline replay, not a live rescore. Cumulative
M7 accounted gross through February is $0.115247510. The new January first-day
40 MB source prefix will receive independent references and a new frozen
holdout before any further live evaluation. The aggregate local work-data
allowance for January acquisition was raised to 8 GB to retain historical
failed workspaces; the network range remains exactly 40 MB and free disk was
about 68 GiB.

## 2026-10-04 — Freeze January v11 after bounded suffix recovery

January's 40 MB first-day prefix yielded 99,799 accepted games from 100,000
complete PGNs, 4,996 selected games and 331,779 move rows. Independent
raw-PGN and 50/50 offline oracle checks passed. Freeze the 50-case new-date
holdout and product semantic-context requests before live calls. The same
three-complete-run gate applies, with answerable >=37/41, boundaries 9/9,
high severity 5/5, all evidence audits and known final usage. At most three
logged exact HTTP 400 retries on distinct cells per run may occur; reserve
and account each at full cell cost. Prior M7 accounted gross is $0.115247510.
The January preflight conservatively reserves $0.098593250 per run, or
$0.411027260 for three plus all prior spend, under the existing $0.50
cumulative gross approval. Historical February scores remain unchanged by
its separate offline suffix replay.

## 2026-10-04 — Retire January Luna gate; test Sol on inspected cases

January v11 repetition 1 met all per-run gates: 48/50 scored,
39/41 answerable, 9/9 boundary, 5/5 high severity, 50/50 evidence audit,
no retry or semantic repair. Repetition 2 stopped at cell 26 after 25
completed scored passes. The provider mixed a valid opening-score plan with
a fabricated tool transcript, then a separate evidence-free `answered`
plan. The checked core rejected it. Keep the original result stopped rather
than choosing a plan arbitrarily. Cumulative M7 accounted gross through the
January gate is $0.120814360.

Official OpenAI documentation lists `gpt-6-sol` with Responses structured
outputs and per-million-token prices of $2 input, $0.20 cached input,
$2.50 cache writes and $10 output. A six-case inspected January diagnostic
was frozen with a $0.223097500 whole-run reservation under the existing
$0.50 cumulative cap. All six actual calls completed and scored passes,
including the previously troublesome opening-score and boundary requests,
with $0.017980600 gross and no malformed response. This is development
evidence only. Cumulative M7 accounted gross is now $0.138794960. Prepare
a new December dataset, independent references and full Sol preflight
before requesting a higher cumulative cap; make no full-holdout Sol calls
under the current approval.

## 2026-10-04 — Freeze December Sol v12; request a cumulative cap only after offline checks

The exact 40 MB December 2025 source prefix contains 100,000 complete PGNs,
99,307 accepted games and one observed date, December 1. Independent raw-PGN
source/cohort references and all 50 checked-tool oracle cases passed. Freeze
50 new-date cases and the single product semantic-context condition with
zero transport retries. Three complete repetitions must each meet 37/41
answerable, 9/9 boundary and 5/5 high-severity thresholds with full evidence
audits. Any failed, unknown-cost or unattempted cell fails the gate. Retain
all raw attempts and distinguish deterministic repairs from model plans.

The frozen Sol preflight reserves $1.859967500 per run; three plus prior
$0.138794960 accounted M7 gross require at most $5.718697460. Recommend a
$6.00 **cumulative gross** ceiling, subject to explicit user approval. The
six-case development diagnostic cost $0.017980600; its simple scaled estimate
for 150 calls is about $0.449515, but that is not a guaranteed upper bound.
The existing $0.50 cap remains in force until approval; no December live call
has been made. A local provider file contains the proposed cap and prices but
no secret, and the named personal key remains in an ignored env file.

## 2026-10-04 — Accept December Sol v12 after three complete frozen repetitions

The user approved the recommended $6.00 cumulative gross cap. The first
sandboxed invocation failed DNS at cell 1 before provider usage was returned.
Keep the failed raw and key-free partial reports and charge the entire
$0.037237500 reservation. A new network-enabled invocation used the same
frozen preflight and a separate ledger. All three 50-case repetitions
completed and scored 50/50, with 41/41 answerable, 9/9 boundary, 5/5 high
severity and 50/50 evidence integrity in each. There were no retries or
repairs. Gross charges for the completed runs were $0.068096900,
$0.055506700 and $0.054292300. Add these to the earlier $0.138794960
accounted M7 gross and the DNS reservation: total **$0.353928360**,
below the approved $6.00 cap. The independent checkpoint gates all pass.

Mark M7 accepted for a fixed-case, new-date, three-repetition quality
checkpoint only. This does not establish general accuracy, monthly trends,
or a model comparison. Retain all earlier stopped Luna gates. The original
retry runner used a generic exported summary filename, which the second
invocation overwrote; the original failed summary survives in its raw
attempt directory and the key-free partial report. Change future exports
to include the ledger stem so separate invocations cannot collide.

## 2026-10-04 — M8 research ranks semantic routing above cost routing

The accepted December Sol gate scored 150/150 fixed cases at $0.177895900
gross for completed calls, so saving fractions of that expense is not yet a
strong reason to add a classifier. Rank narrow Jev opportunities as:
(1) question intent plus clarification/unsupported routing, (2) analytical
wording review, (3) candidate metric/evidence relevance, and (4) cost-aware
execution routing. Keep exact numeric checks and source opening classification
in deterministic code. The first SQL extension benchmark should classify a
bounded table of analyst questions on the same rank-1 task, not send raw game
rows without a compelling semantic target.

Use the direct TypeSafe API first for the product experiment, an isolated
DuckDB Jev extension second for SQL learning, and pg_jev only if a local
PostgreSQL slice adds value. The current DuckDB 1.4.1/macOS-arm64 lock is not
confirmed compatible with the published community extension; no extension
was installed. Personal Jev API entitlement remains unverified. Current
published `jev-1.13.0` pricing is $0.042 per million input tokens and free
output; a provisional $0.25 gross pilot recommendation must be replaced by
an exact frozen preflight before requesting a separate M8 live cap. No Jev
model calls or benchmark results are claimed. See [the M8 research](M8.md).

## 2026-10-04 — Pin M7 baseline and isolate M8 variants within one repository

Tag accepted M7 commit `f814377` as `m7-baseline`. Keep the checked-tool
core and baseline evaluation runnable without Jev. Add each candidate Jev
decision as an explicit, separately scored mode on frozen inputs, with one
intervention active at a time. Use temporary branches for development as
needed, but do not maintain independent repository forks or duplicate the
data pipeline; that would make drift harder to separate from Jev's effect.
Use the same scorer and log code revision, model/version, thresholds, cost,
latency and fallback. The personal TypeSafe key belongs only in an ignored
named local env file; API login is not proof of entitlement, and no Jev
inference is authorized before a separate frozen M8 cap.

## 2026-10-04 — Review first; defer implementation and Jev

The owner requested an end-to-end portfolio review, then explicitly asked for a
fix plan to pass to a lower model. Preserve production code at reviewed commit
`26f675b`; save and reverse the interrupted five-file implementation diff under
ignored `work/repository-review/proposed-fixes.patch`. It is untested and incomplete.
Only review artifacts and status/decision documentation change in this pass.

[Review](REPOSITORY_REVIEW.md) records confirmed offline defects, 56 local passing
tests, 44 passing/12 skipped exported-source tests, and a missing-cache-wheel
limitation on fresh installation. [Handoff](PORTFOLIO_HANDOFF.md) prioritizes finite
budget validation and source binding before a complete synthetic product demo.
Use functional public interfaces while retaining immutable milestone/version
evidence; broad package/path renames need explicit hash/compatibility handling.
License selection remains an owner decision. No live spend, new model task,
Jev implementation, cloud service or repository upload is authorized by this plan.

## 2026-10-04 — Portfolio integrity and offline release path

Implement the selected handoff in this repository. Reject non-finite personal
budget/rates before provider transport. Bind analytical receipt source hash and
plan to the checked source snapshot before candidate publication. Emit selected
duplicate games once; keep upstream conflict rejection. Historical M5–M7 scoring
functions/results remain frozen; use a new `portfolio-1.0` strict numeric rubric
for synthetic demonstrations.

Use a six-record authored PGN with separate expected arithmetic and an isolated
`work/portfolio-demo/project` for the complete offline three-project command. The
dashboard accepts that project only through explicit `CHESSLAB_PROJECT`, and labels
its source synthetic on every view. Retain the original tiny CLI demo. Preserve
milestone names for hash-bound historical evidence; offer functional public
commands/docs without a broad package rename. A read-only audit found 9/9 locally
retained analytical source/receipt pairs matched their hashes and plans. Local
dbt/dashboard verification passed 91 tests; hosted CI and fresh export are not yet
claimed. No live spending, Jev integration, cloud resources or remote upload.

## 2026-10-04 — Clean-export acceptance and publication boundary

A tracked-source export installed the locked dbt/dashboard environment after a
one-time fetch of missing Pygments and Ruff wheels. It passed 81 tests with 12
expected skips for ignored real data, then the full synthetic demo and Ruff. The
local full suite passed 93/93 with no skips; lock, format and whitespace checks
passed. A wheel and source archive omitted ignored work, cache, env and bulk-data
payloads. A filename-only candidate/history pattern audit found no matching
credential or personal path in 33 reachable commits; it is not a proof of absence.
Hosted CI has not run, and no Git remote or upload exists. The owner still needs to
choose a repository distribution license before public publication.

## 2026-10-05 — Portfolio code license

The owner approved GPL-3.0-or-later for original Chess Analytics Lab code.
This aligns with the direct python-chess dependency (`chess==1.11.2`), which is
GPL-3.0-or-later. Add the full GPLv3 license text, declare the SPDX expression
in package metadata, and update README and third-party notices. This decision
does not relicense dependencies or Lichess CC0 data. Use the collective project
name for attribution pending any optional personal-name preference. Historical
review and release-check reports retain their original pre-decision state.
The source archive initially admitted `.env.example` files from ignored
clean-checkout scratch directories; an explicit sdist `work/**` exclusion removed
them. The wheel and source archive both include the selected license.

## 2026-10-05 — Executable offline walkthrough

Keep DEMO.md focused on the tracked synthetic three-project path. Spell out
the locked install, isolated workspace, expected JSON fields, six dashboard
views, exact CLI replay and common local failures. Link optional real-data and
orchestrator procedures to their existing guides rather than implying that
the default offline command runs those components. A fresh offline demo,
CLI replay and focused dashboard/demo tests verified the documented path;
no provider request or archive download occurred.

## 2026-10-05 — M8 routing study and DuckDB isolation

Implement the owner's selected rank-1 Jev learning opportunity in the same
repository, leaving the M7 checked-tool baseline intact. Freeze 80 newly
authored, balanced question/route labels, with 40 development and 40 test
cases. The labels precede model scoring but lack independent human
adjudication, so report exploratory route accuracy, not general accuracy or
end-to-end answer correctness. Freeze the small rule baseline after using
development cases; its first test score is 35/40 with 5/5 unsupported recall.
Keep mock transport tests, offline DuckDB replay, and actual provider results
explicitly distinct. The direct TypeSafe Choice adapter and existing OpenAI
analyst comparator require separate named local key files, finite caps,
matching preflights, raw attempt retention, and usage accounting. Never infer
spending authorization from available credits.

An actual `INSTALL jev FROM community` on DuckDB 1.4.1/macOS arm64 returned
HTTP 404 for the extension binary. The public listing and source README
disagree about installation; source instructions currently require matching
DuckDB 1.5.5. Do not change the production lock or use the production read-only
analyst connection for this experiment. Provide an offline question table and
an explicit SQL preview; run extension-based classification only in an
isolated compatible environment with a separate cost control. The extension's
row/character limits and estimated `jev_stats()` are not a hard dollar cap.
The educational [runbook](JEV_ROUTING_RUNBOOK.md) gives the reproduce/interpret
sequence and identifies the separate future end-to-end gate.

## 2026-10-05 — M8 live routing results and no production promotion

The owner approved separate cumulative gross caps of $0.05 for two frozen
TypeSafe passes and $0.10 for one structured-analyst comparison. The explicit
personal TypeSafe key authenticated; its model-list endpoint showed aliases,
but the pinned `jev-1.13.0` completed both 40-case passes. Actual scores were
39/40 and 37/40; two routes changed between identical passes. Their total
gross cost was $0.002000376. The existing structured analyst completed a
40-case pass at 33/40 and $0.00226205. It also had a stopped 20-completed-case
attempt at $0.00191639 after `compare_clock_buckets` subtracted null evaluation
coverage. Fix only that null arithmetic, retain its failure and charge, and
verify the regression offline before the complete pass. An earlier preflight
dataset-ID mismatch prevented transport and incurred no charge. OpenAI's M8
cumulative accounted gross was $0.00417844, below its separate cap.

These results compare semantic routes on authored, not independently
human-adjudicated labels. The structured analyst executed checked tools over
the small synthetic demo, while Jev received a compact catalog. The
coverage/error and cost table can support learning, but does not establish
end-to-end numerical answer quality or a production improvement. Its
Jev-plus-analyst fallback table is a post hoc replay using observed per-case
costs, not an executed combined system. Keep Jev isolated and the M7 baseline
available until fresh independent references and an end-to-end evaluation
show a practical benefit. DuckDB Jev remains an isolated extension exercise.

## 2026-10-05 — M8 paired final-answer study

Use a narrow Jev boundary gate, not a full semantic route replacement, as the
first integrated test. Jev may end only `clarify` or `unsupported` questions
at probability at least 0.70; every other decision falls through to the
unchanged checked analyst. This protects numerical calculations and keeps
the baseline directly comparable. The owner reviewed and approved all eight
new boundary labels before live scoring; opening and clock values come from
independent raw-PGN references. One paired 32-case run had separate newly
approved cumulative gross caps of $0.03 TypeSafe and $0.20 OpenAI.

The original live report scored both arms 30/32. Its inherited rubric
required the expected checked tool to be the **last** evidence item, wrongly
rejecting an answer that used the expected clock metric followed by an
additional checked coverage metric. Keep that original report, add a focused
regression, and rescore the saved answers offline under `m8-e2e-1.1`, which
accepts the expected tool anywhere in the integrity-checked evidence. Both
arms then score 31/32; no model call was repeated. The shared failure is an
answerable UTC-date coverage question that the analyst marked unsupported.

Both arms used `gpt-6-luna`; the accepted M7 checkpoint used `gpt-6-sol`.
The gated arm saved six analyst calls but made 32 Jev calls. Measured gross
was $0.002503882 gated versus $0.00242630 baseline; summed per-case elapsed
time was 86.11 versus 83.97 seconds. TypeSafe gross $0.000804762 and OpenAI
gross $0.00412542 remained under their caps with no unknown usage. Retain
Jev as a learning lab and do **not** integrate the gate into the product:
this Luna pairing has no measured final-answer quality, cost, or latency
benefit. A Sol pairing was not evaluated.
The result is one small paired run, not a stability or population estimate.
Future Jev work needs a concrete higher-value trigger, fresh independent
cases, and new spending approvals.

## 2026-10-05 — Final publication review gate

Review the full working-tree upload candidate, including new files, in a
clean export before creating a remote. The export passed 90 tests with 13
expected real-data skips, Ruff and the complete offline demo; package
inventory included the selected license and excluded ignored payloads.
Keep publication pending the four fixes in FINAL_RELEASE_REVIEW.md. The
M8 comparator was Luna, whereas the accepted M7 checkpoint used Sol; the
observed no-benefit conclusion is limited to the Luna experiment. No new
live experiment is required to correct that scope. A mock interruption
proved a missing durable request reservation, and inspection found a
success exit for incomplete runs and a rescore overwrite path. This turn
records review evidence and acceptance criteria only, without code fixes
or publication.

## 2026-10-05 — Publication fixes after review

Resolve the four findings with no new model calls. Persist a pending cost
reservation before each provider transport, reconcile pending/settled
records after an interrupt, and accept previous attempt directories when
enforcing a cumulative cap on retry. A pending record may conservatively
reserve a call that never reached the provider; that is safer than treating
unknown usage as free. Return nonzero for incomplete runs. Require a fresh
rescore destination outside the original attempt. Name the Luna pairing in
M8's conclusion and leave Sol integration unclaimed. Preserve frozen run
reports, hashes and raw attempts; any future live run must re-preflight
under a newly approved cap.

## 2026-10-05 — Private portfolio repository

The owner chose the personal `jfk-ssa` account, repository name
`chess-analytics-lab`, and private-first visibility. GitHub CLI browser
authentication completed into the macOS keyring. The full reviewed candidate
was committed as `07c1344` with the account's no-reply commit address,
then pushed to `main` with the historical `m7-baseline` tag. The remote is
private. GitHub Actions was enabled and the workflow triggered, but jobs
were queued at last check while GitHub reported hosted-runner assignment
delays. Do not mark hosted CI passed or change visibility based on local
tests alone.

## 2026-10-05 — Public portfolio publication

The delayed GitHub Actions run [37371042615](https://github.com/jfk-ssa/chess-analytics-lab/actions/runs/37371042615)
completed successfully on `73b6dfc`: both `offline` and `portfolio` jobs passed.
The owner explicitly authorized changing `jfk-ssa/chess-analytics-lab` to public,
including its full Git history and the previously disclosed local author address.
The visibility change succeeded, and GitHub reports `PUBLIC`. Keep the frozen
M0–M8 evidence and historical private-first decision as the record of sequence.

## 2026-10-06 — Separate public business examples

Place the owner-supplied executive metric communication text and data
observability screenshot in `auxiliary-examples/`, outside the chess package and
evidence chain. Adapt the text for public sharing: replace observed financial
figures with labeled synthetic worked examples, remove named people, email
addresses, customer identifiers, internal ticket links, and production change
history. Retain the supplied dashboard screenshot because it shows no visible
financial amounts or named people. Link the folder from the repository README
so both artifacts have stable, direct public URLs, and exclude the folder from
Python distributions because it is not part of the application.

## 2026-10-07 — Optional OpenAI Decisions classifier

Add a separate Decisions API learning experiment; keep rules, Jev and the existing
checked analyst intact. Use the standard global Decisions endpoint, gpt-6-luna,
one fixed eight-choice route question, and standard-library HTTP. Official pricing
checked today is $0.10 per million input tokens. No new dependency or infrastructure.

All historical cases are inspected development evidence. Select and freeze the
0.70 chosen-option probability threshold from 40 development responses before
fresh scoring. The owner approved 24 new labels and a simplified private-history
question before any holdout call. Label review is independent of the authoring
agent, but is owner review rather than external expert adjudication. Three identical
repetitions scored 23/24 each; do not count them as 72 independent examples or tune
the rubric against the repeated error without retiring this holdout.

All six runs used one durable locked campaign ledger and the approved $0.05
cumulative Decisions cap. Actual recorded usage totals $0.0068145 for 184 requests,
with no unknown reservations, transport failures, retries or refusals. Retain raw
attempts under ignored work; compact scored reports and the checkpoint are public
artifacts. Usage-based gross is not a provider invoice settlement. Future paid
runs need a new explicit estimate, recommended cap and approval; remaining credits
and unused cap are not an authorization for another campaign.

Compare retained Jev/analyst runs only on the same historical split; no fresh
TypeSafe or Responses call was authorized or made. The 32-case historical
retained-answer replay scores 31/32 with 26 fallbacks, unchanged from baseline,
and raises simulated cost from $0.0024263 to $0.003363135. It has no combined live
latency and proves no benefit for the accepted M7 Sol analyst. Keep Decisions
optional; a fresh paired final-answer test needs separate provider estimates and
caps before considering integration. See [runbook](DECISIONS_ROUTING_RUNBOOK.md)
and [checkpoint](../reports/decisions-checkpoint.json).

## 2026-10-07 — Lead the comparison with results

The owner requested an upfront results section in the Decisions comparison.
Render a checkpoint-backed summary before the detailed tables, highlighting
routing accuracy, frozen gate behavior, gross spend, retained-answer replay and
the recommendation to keep Decisions optional. Require matching report hashes
when rendering the checkpoint summary. Preserve classifier runs and avoid new
paid calls for this presentation change.

Clarify “baseline” in the report: rules are the simple routing baseline; the
existing Luna analyst is the final-answer baseline. Show baseline, Jev and
Decisions side by side on shared historical cases, separating actual paired
results from Decisions retained-answer replay. Mark Jev/analyst fresh results
as not measured rather than comparing different case sets.

## 2026-10-07 — First-visit documentation and publication

The owner requested a repository review with a focus on first-time navigation
and authorized confident changes to be pushed. Add a goal-based documentation
guide and repository map, a GitHub-readable classifier summary, clone/setup
steps, platform notes and development checks. Distinguish current guides from
historical milestone evidence, define the two baselines, preserve repeated Jev
results and label Decisions final-answer replay. Keep all original live scores,
frozen cases, package names and spending rules intact. Historical provider prices
are dated research, not current quotes. No new paid calls or infrastructure.

The local dbt failures were traced to 133 identical, unrecorded duplicate dependency
files in the ignored environment. Preserve them under work/dependency-diagnostic
and rerun verification; do not change tracked SQL to accommodate this defect.
See [documentation review](DOCUMENTATION_REVIEW.md) and its measured checks.

The owner identified the numbered dependency duplicates as cloud-synced copies.
They are not project source; the publication candidate contains none. Preserve
the ignored diagnostics without adding broad filename exclusions that could hide
intentional future files.

## 2026-10-07 — Reviewed changes published

The owner-authorized Decisions experiment and first-visit documentation were
pushed to public main in commit `4411e17`. The full local suite passed 115 tests
after preserving the ignored cloud-sync copies, with Ruff and the offline demo
passing. The publication candidate contained no numbered cloud-copy paths or
matching sensitive/path patterns. Use the account's existing GitHub no-reply
identity for new commits. A new Actions result must be verified independently
of the previous successful run. No new live model calls were made for review
or publication.

## 2026-10-09 — Static documentation publication

The owner requested the existing comparison report, a homepage and HTML versions
of comparison, architecture, metrics/data and demo guides. Use GitHub Pages with
a generated static artifact. Keep Markdown and contracts canonical, preserve the
frozen report bytes, and publish only named assets. Add an optional pinned docs
extra instead of a new application dependency. The site interactions use saved
classifications and hypothetical denominator examples; they cannot call providers.
Actual synthetic-demo screenshots illustrate replay, not new model responses.
The metrics prose now explicitly matches the known-opening denominator contract.
A dedicated workflow builds and checks pull requests, and deploys only main.
No live inference, new ingestion or cloud service was provisioned. See SITE.md
and the documentation-site checkpoint for execution and publication evidence.

Publication was verified on `814ffe9`: Pages and offline integrity CI passed;
all public guide/report URLs returned HTTP 200 and the original report bytes
were preserved. Keep deployment evidence separate from model-evaluation claims.

## 2026-10-09 — Shared typography and presentation

The owner approved trying the proposed Inter UI/body and Source Serif 4 guide
heading pairing. Use a small documented visual style guide, shared palette and
supported Streamlit theme configuration. Bundle pinned Fontsource 5.3.0 Latin
variable font files with original OFL licenses and provenance; keep fonts local.
Use Inter alone in the analytical dashboard and serif headings in learning guides.
Refresh actual synthetic-demo screenshots and limit previews to 760px with full-size
links. Preserve the original frozen comparison report and all scoring evidence.
No additional paid calls or data acquisition are part of this visual update.

## 2026-10-09 — Inter throughout

The owner rejected the mixed serif/Inter pairing and prefers Inter. Guide headings
now use the same Inter family as body text and the dashboard. Remove the unused
Source Serif font, license and active provenance entry; its original experiment
remains in Git history and the preceding decision. Update the current visual
guide and notices to match. Preserve the original comparison report styling.

## 2026-10-09 — Try Sora throughout

The owner selected Sora after the in-chat font comparison. Replace Inter in the
current guides and Streamlit theme with pinned Fontsource Sora 5.3.0, locally
hosted under its original OFL license. Keep size/weight roles and the shared
palette; refresh the actual synthetic demo screenshots. Add source-revision
queries to stylesheet/script URLs so a new deployment refreshes those assets.
Earlier typeface trials remain in Git history and the decision log. Frozen
comparison report styling and all benchmark evidence remain unchanged.

## 2026-10-09 — DM Sans approved after compact reading comparison

The owner shortlisted Inter, DM Sans and Sora at 14px with 0.01em letter
spacing, then approved DM Sans in the guide-layout comparison. Use locally
hosted Fontsource DM Sans 5.3.0 with its original OFL license and pinned hashes
in both the guides and dashboard. Guide body text uses 14px/1.55, 0.01em
tracking and a roughly 70-character prose measure; reduce oversized guide
headings to match the compact reading preference. Streamlit uses its native
spacing with a 14px base. Refresh the actual synthetic demo images, preserve
frozen reports, and retain earlier font experiments in Git history. This is
a presentation update with no new dataset or live model requests.

## 2026-10-09 — Inter Medium selected for current guides and dashboard

After comparing the same page in Inter Open, Regular and Medium, the owner
selected Medium and requested updating all current surfaces. Use Inter at
weight 500 for body text, navigation and tables, with 600–650 emphasis and
headings. Keep the approved 14px guide body, 1.55 line height and 0.01em
tracking; use Streamlit's native spacing with base weight 500. Bundle pinned
Fontsource Inter 5.3.0 locally with OFL license/provenance. Refresh the actual
synthetic demo images and current style documentation. Earlier trials and
frozen report styling remain historical evidence, not active design choices.

## 2026-10-10 — One M7 campaign command

The per-month pin, workspace, reference, case, and gate scripts differed by
source pin, opening families, question wording, and checkpoint accounting.
Those differences now live in `config/m7_campaigns.json`. `chesslab m7` runs
`pin`, `workspace`, `reference`, `cases`, and `check` for a campaign id.
New preflights hash that config and `src/chess_analytics/m7_campaign.py`.
Published preflight files keep their original script hashes. A prefix hash
mismatch raises instead of rewriting a per-month JSON. New workspaces record
`config/m7_campaigns.json` as the source plan. Question text was compared with
every frozen case file before the copied scripts were removed. Shared
checkpoint, clock-dev, and repetition scripts stay.
