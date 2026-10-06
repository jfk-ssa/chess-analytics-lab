# Status — 2026-10-06

**M0–M7 accepted locally; M8 routing and end-to-end Jev comparisons measured, with no production promotion. Portfolio hardening verified locally and in a fresh export; GPL-3.0-or-later selected for original project code.** This is a new standalone local Git
repository; projects 1–3 remain together. The portfolio repository is public at
https://github.com/jfk-ssa/chess-analytics-lab.

## Phase tracker

Final publication review: the initial candidate export passed 90 tests with
13 expected real-data skips, Ruff and the full offline demo. The four
findings are now fixed offline: durable pending API reservations, explicit
Luna versus Sol comparison scope, nonzero incomplete-run exit, and
protection against overwriting an original report during rescore.
See [final review and resolution](FINAL_RELEASE_REVIEW.md) and the
[original review evidence](../reports/final-release-review.json). The
post-fix local suite passed 108 tests; a fresh locked export passed 95 tests
with 13 expected real-data skips, Ruff, and the full offline demo. The
post-fix source archive and wheel include the license and exclude ignored
payloads. Release commit `07c1344` and the `m7-baseline` tag were pushed.
GitHub Actions run [37371042615](https://github.com/jfk-ssa/chess-analytics-lab/actions/runs/37371042615)
passed both `offline` and `portfolio` jobs on `73b6dfc` after a runner delay.
The owner then explicitly approved public visibility; GitHub reports `PUBLIC`.
No new live model call occurred.

| Phase | State | Next gate |
|---|---|---|
| M0 bootstrap | Done | Accepted offline environment and fixtures |
| M1 vertical slice | Done | Accepted bounded foundation ingestion and reference metric |
| M2 reliable platform | Done | Accepted dbt/recovery/operational checks locally |
| M3 analytical corpus and metrics | Done | Accepted bounded prefix, observed coverage, independent checks, 12 draft dev cases |
| M4 analytics product | Done | Accepted local six-view dashboard and two reproducible memos |
| M5 analyst/eval harness | Done | Accepted checked typed tools, fixture replay and 50-case harness; no model result |
| M6 measured release | Done; typed-analyst release gates met | Three complete frozen v2 repetitions, 118/120 scored passes, all evidence audits and offline checks passed. See [release checkpoint](M6-RELEASE.md). |
| M7 depth | Done; December Sol v12 gate accepted | Three complete frozen repetitions scored 50/50 each with 150/150 evidence audits, no repairs/retries, and $0.35392836 cumulative accounted gross under the approved $6 cap. Earlier failed/stopped gates remain retained. See [December checkpoint](M7-DECEMBER.md). |
| M8 Jev | Routing and paired final-answer comparisons measured; no production promotion | [Route checkpoint](../reports/M8-routing-checkpoint.json): rules 35/40; Jev passes 39/40 and 37/40; existing analyst 33/40. [End-to-end checkpoint](../reports/M8-e2e-checkpoint.json): both arms 31/32 after versioned offline rescore; Jev costs slightly more. Eight new boundary labels received owner review. See [end-to-end lab](JEV_END_TO_END.md). Compatible DuckDB extension remains an optional isolated exercise. |
| Portfolio readiness | Integrity, offline demo, docs, clean export and license verified locally; hosted CI passed; repository public | [Implementation evidence](EVIDENCE_INDEX.md), [final review](FINAL_RELEASE_REVIEW.md) and [handoff record](PORTFOLIO_HANDOFF.md). |
| Personalized recommender | Backlog | Outside first-release scope |

An [auxiliary examples folder](../auxiliary-examples/README.md) now holds a
publicly adapted executive metric communication example and a data
observability screenshot. The examples are separate from Chess Analytics Lab;
the metric document uses synthetic financial cases and omits named people,
email addresses, customer identifiers, and internal ticket links.

## Portfolio hardening checkpoint

The budget validator now rejects non-finite values; analytical publication binds
the extracted receipt, source snapshot and configured plan; selected duplicate
games emit moves only once. A separate `portfolio-1.0` scorer rejects boolean and
non-finite numeric answers without changing M5–M7 rubrics. The dashboard renders
empty clock buckets and labels synthetic data. `chesslab demo --scope all` builds
a distinct ignored synthetic workspace and replays three checked analyst plans.
The final local dbt/dashboard suite passed **93 tests, none skipped**. A fresh locked export passed **81 tests with 12 expected real-data skips** and the complete synthetic demo. Its wheel and source archive contained no ignored local payloads. A read-only audit
of nine retained analytical source/receipt pairs found zero mismatches. No live
model request was made. The prior real snapshots remain retained; foundation
reporting and a fresh analytical move publication need a new ingest under this
changed implementation hash. The offline portfolio demo needs no real-data rebuild.
[Demo](DEMO.md), [source audit](../reports/portfolio-source-audit.json).
The expanded demo walkthrough was checked with a fresh offline demo and CLI
replay; its two focused tests passed, including all six Streamlit views.

## Completed acceptance

| Milestone | Implemented behavior | Verified evidence |
|---|---|---|
| M0 | Python 3.12.14, uv.lock, exact package/build pins, CLI, synthetic fixtures, table/metric contracts | Clean local clone + fresh environment installed offline from cache; all 21 tests and demo passed. Ruff check/format passed. |
| M1 | Bounded complete-source acquisition, legal PGN replay, provenance/quarantine, typed Parquet → DuckDB, checked snapshots, draw-rate metric | Publisher SHA256 verified; 121,332 accepted games and 242,664 participant rows; zero quarantine/conflicts; all quality checks passed. |
| M1 repeatability | Repeat full ingestion and repeat publication | Two full ingestions produced identical normalized-file hashes. An acquisition-only code change separates them; same-code repeat ingestion is also tested on tiny fixtures. Repeated foundation build preserves snapshot ID and metric. |
| M1 metric reference | Independent fixture arithmetic and real-source header tally | Tiny: 4/20 = 0.20. Foundation: 3,982/121,332 = 0.03281904196749415; DuckDB agrees exactly with the independent script. |
| Optional orchestrators | Thin Dagster asset graph and Prefect task flow over the existing pipeline; exact pins in separate optional extras | Same-input offline comparison: 3 assets and 3 tasks succeeded; both produced 22 accepted fixture games, 4/20 draws, and identical source/snapshot/metric records. [Machine-readable result](../reports/orchestrator-comparison.json). |
| M2 dbt | Five staging/intermediate/mart models over checked snapshots; isolated candidates, source-to-mart reconciliation, immutable published marts and lineage artifacts | Tiny and foundation each created 5 models and passed 19 dbt tests. Foundation mart: 121,332 games, 242,664 participant rows, 3,982 draws. [M2 evidence](M2.md). |
| M2 recovery | Failed dbt attempts and logs retained; pointer protected until checks pass; backfill by snapshot ID; validated rollback; operational ledger and source-version warnings | Injected failure preserved prior mart; retry matched clean run; failed dbt kept M1 snapshot usable; 23 offline tests passed in dbt-only environment. Dagster 4 assets and Prefect 4 tasks succeeded locally with dbt enabled. |
| M3 bounded source | Fixed 40,000,000-byte prefix of the August 2026 standard rated archive; complete-PGN extraction capped at 100,000; partial status and byte hashes retained | 100,000 complete PGNs; 99,467 accepted, 533 unrated excluded, zero quarantine/conflicts. Observed UTC coverage is **2026-08-01 only**. Full publisher archive checksum is not claimed. [Coverage](../reports/M3-coverage.json). |
| M3 analytical metrics | Source-tag opening usage/player score and a deterministic 5% game-ID-hash move sample with a clock/evaluation error proxy; versioned contracts and immutable analytical snapshot | 4,924 games selected, 330,956 move rows, including 10 zero-ply selections. Independent raw-PGN checks passed for 12 opening families, 4 player cohorts, 4 clock buckets and source draw rate. [Check](../reports/M3-reference-check.json). |
| M3 evaluation preparation | 12 draft development cases with dataset IDs, expected results, tolerances and caveats | Case file generated from independent reference; no agent or model response has been scored. M0–M2 tiny/foundation regressions rebuilt with 19 dbt tests each. [M3 evidence](M3.md). |
| M4 analytics product | Local Streamlit overview, opening, clock, quality, analyst and evaluation views; two short memos; exact figure inputs | Six views and a replay action ran without app exceptions in Streamlit AppTest. Two memo figures match independent raw-PGN opening/clock references; 400 seeded focal-player bootstrap repetitions per opening cohort. [M4–M5 evidence](M4-M5.md). |
| M5 offline analyst | Allowlisted read-only typed tools, four-step state machine, evidence IDs, fixture replay and separate scoring; disabled-by-default personal Responses adapter | 50 cases frozen (30 dev/20 test) across six categories; fixture-replay/scorer check 50/50. Ten plausible wrong-answer mutations rejected; raw SQL/file/network/extension attempts have no enabled tool. These are harness tests, **not model accuracy**. |
| M5 live gate | Personal config and positive cap required; only named personal key variable permitted | Disabled example config rejected a CLI live attempt before transport; failure retained in ignored local attempt log. No provider request occurred. |
| M6 offline preparation | Hard-deadline credential-free tool worker; 12-case/two-condition typed-planner pilot with whole-run budget reservation and frozen request hashes | Worker ran against the real checked snapshot; proposed 24-cell quote is $0.0198638 under hypothetical $1 cap. Fresh clone and cached offline tiny demo passed after filling missing macOS wheels. These are offline checks, not model outcomes. [M6 evidence](M6.md). |
| M6 actual development pilot | Four frozen prompt revisions; 32 API requests including stopped attempts; final two-condition run completed 24/24 | Frozen scorer 16/24: 8/12 answerable and 8/12 ambiguity/unsupported; both conditions 8/12. Corrected gross cost across attempts $0.0028105 under the first $0.10 cap. Release gates **not met**. [Actual model results](../reports/M6-live-pilot.json). |
| M6 development revisions | M6 2.0 scorer accepts an equivalent checked clock-pressure tool; prompt clarifies abstention and opening filters; 64 further actual requests | Revisions: 20/24, stopped at 16 after a two-chunk response, then 23/24 (11/12 answerable, 12/12 abstention). Corrected gross cost $0.00528149 under the separate $0.10 cap. One-shot development success is not held-out release evidence. [Progress and failures](../reports/M6-development-progress.json). |
| M6 new holdout preparation | 20 frozen cases (14 answerable, 6 ambiguity/unsupported) using eight opening families absent from M5 usage cases; raw-PGN cohort reference for two new families; separate M6 2.1 scorer | All 20 deterministic checked-tool answers matched independent references offline before live calls; 40 request hashes and 24 file hashes frozen. Conservative [preflight](../reports/M6-holdout-preflight.json) quote $0.0503635 at the documented Luna rates. |
| M6 actual family-split holdout | Three authorized repetitions of the same frozen 40-cell preflight; 72/120 planned requests attempted, all raw failures retained | First complete run 39/40: 27/28 answerable, 12/12 ambiguity/unsupported, 6/6 high-severity. Repeat 2 stopped at 10 (9 scored passes); repeat 3 stopped at 22 (20 scored passes). Gross total $0.0060692 below the $0.10 cumulative cap. Evidence integrity passed for all 70 completed answers; two attempts failed closed. **No repeatable release performance claim.** [Runs and censored cells](../reports/M6-holdout-variability.json). |
| M6 v2 measured release | Explicit unique-structured-chunk recovery and exact compare-opening wrapper normalization, both logged; new eight-family case split and raw-PGN cohort reference | 20/20 deterministic checked-tool/reference checks; 43/43 offline tests with optional dbt/dashboard extras; three complete 40-cell live repetitions: 40/40, 38/40, 40/40. Answerable 82/84; ambiguity/unsupported 36/36; high-severity 18/18; evidence integrity 120/120. Gross $0.009968525 under approved $0.10 cap. Two safe but incorrect abstentions retained. [Checkpoint](M6-RELEASE.md). |
| M7 first offline slice | Explicit prompt guidance for answerable clock evaluation coverage; 12 new development paraphrases and negative controls from the independent raw-PGN tally | Checked-tool/oracle replay 12/12: 8 answerable, 1 clarification, 3 unsupported. [M7 plan and evidence](M7.md). |
| M7 v1 live development | 50-case split, 100 cells per full run | First run stopped at 49 attempts with 48/48 completed passes; one HTTP 400 had unknown cost. Retry run completed 95/100 with 100/100 evidence integrity; next retry stopped at 20 attempts with 18/19 completed passes after duplicate valid chunks. Known gross $0.014789635; accounted gross $0.015749885 including full reservation for unknown cost. [Full run](../reports/M7-holdout-v1-complete-1.json). |
| M7 v2 fresh freeze | 50 new cases, 25 opening families absent from inspected M5/M6/M7 v1 cases; independent raw-PGN references | 50/50 checked-tool/oracle answers match. [Preflight](../reports/M7-holdout-v2-preflight.json) reserves $0.13476325 per 100-request run; three plus prior accounted gross total $0.420039635 of the approved $0.50 cap. No v2 model call at freeze. |
| M7 v2 measured result | Three complete 100-request frozen repetitions | Scored 90/100, 96/100, 92/100; answerable 224/246, ambiguity/unsupported 54/54, high severity 30/30, evidence integrity 300/300; no execution failures. Gross $0.025244195, cumulative M7 accounted $0.04099408. [Checkpoint](../reports/M7-holdout-v2-checkpoint.json) **fails** run-1 answerable gate. |
| M7 v3 fresh freeze | Prompt clarifies specified clock-proxy queries; 50 new cases and 25 further opening families absent inspected splits | Independent raw-PGN cohorts and 50/50 checked-tool/oracle pass. [Preflight](../reports/M7-holdout-v3-preflight.json) reserves $0.1395495 per 100-request repeat; three plus prior accounted gross total $0.45964258 of $0.50. No v3 model result at freeze. |
| M7 v3 measured result | Three complete frozen 100-request repetitions | Scored 96/100, 95/100, 98/100; answerable 238/246, ambiguity/unsupported 51/54, high severity 30/30, evidence integrity 300/300; no execution failures. Gross $0.026632805, cumulative accounted $0.067626885. [Checkpoint](../reports/M7-holdout-v3-checkpoint.json) **fails** run-1 ambiguity gate (16/18). |
| M7 v4 fresh freeze | Prompt clarifies small nonempty cohorts; 50 new cases, 25 more opening families, explicit missing-filter boundaries | 50/50 checked-tool/oracle pass against independent raw-PGN references. [Preflight](../reports/M7-holdout-v4-preflight.json) reserves $0.142884 per 100-request run; three plus prior accounted gross total $0.496278885 of $0.50. No v4 model result at freeze. |
| M7 v4 stopped live run | Frozen 100-request plan, stopped on provider HTTP 400 at cell 59 | 58/59 attempted cells completed, 41 scored passes, 41 cells unattempted. First 29 paired cases: schema-only 12/29, governed context 29/29. One failed request has unknown usage and is charged its full $0.001043 reservation. [Partial report](../reports/M7-holdout-v4-partial-1.json). |
| M7 cumulative checkpoint | Frozen failures and cost accounting across v1–v4 | Known actual gross $0.072358895 plus $0.00200325 full reservations for two unknown-cost attempts = **$0.074362145** of approved $0.50. [Checkpoint](../reports/M7-checkpoint.json) keeps M7 in progress; no broad quality claim. |
| M7 cross-month data depth | Six exact 40 MB first-day prefixes from July through February 2026, each capped at 100,000 complete PGNs in isolated local project views | [Resource and coverage comparison](../reports/M7-new-data-resource-cost.json); independent raw-PGN checks and 50/50 offline oracle results for each new-date holdout. No full-month or random-sample claim. |
| M7 July–May v5–v7 | New-date semantic-context holdouts; malformed argument recovery and exact-family routing developed from inspected failures | July 32/50 full-run passes then a stop; June stopped twice on malformed arguments; May 45/50 full-run passes then a stop. Original failures retained; [June argument replay](../reports/M7-argument-recovery-replay.json) and [May routing replay](../reports/M7-opening-repair-replay.json) are offline evidence only. |
| M7 April v8 | New-date 50-case freeze with three attempted live repetitions | 50/50 and 49/50 full runs; third stopped at cell 13 after repeated structured plan text. [Failed gate](../reports/M7-April-v8-checkpoint.json); [parser replay](../reports/M7-repeated-plan-replay.json) is offline only. |
| M7 March v9 | New-date 50-case freeze; one live run stopped after 16 attempts | 15 completed, 14 scored passes, one logged rescued HTTP 400 and one final HTTP 400. [Failed gate](../reports/M7-March-v9-checkpoint.json); [overlapping-family replay](../reports/M7-overlapping-family-replay.json) is offline only. Cumulative accounted gross before February: **$0.107639170**. |
| M7 February v10 | New-date 50-case freeze, 3-retry transport allowance | First run 47/50 with all per-run gates, one retry and one semantic repair; second stopped at cell 26 on malformed provider suffix. [Failed gate](../reports/M7-February-v10-checkpoint.json); [suffix replay](../reports/M7-inert-suffix-replay.json) is offline only. Cumulative accounted gross before January: **$0.115247510**. |
| M7 January v11 | New-date 50-case freeze and three-run Luna attempt | First run 48/50 with all per-run gates; second stopped at cell 26 on conflicting provider text. [Failed gate](../reports/M7-January-v11-checkpoint.json). Cumulative accounted gross before Sol diagnostic: **$0.120814360**. |
| M7 Sol development | Six inspected January cases with a separate frozen Sol request/price plan | Six actual calls completed and scored 6/6; gross **$0.017980600**. This is [development evidence](../reports/M7-Sol-development.json), not holdout performance. Cumulative M7 accounted gross **$0.138794960**. |
| M7 December Sol checkpoint | New-date source and 50-case holdout, three approved live repetitions | 99,307 accepted games from a 40 MB prefix; independent raw-PGN checks and 50/50 offline oracle passed. A sandbox DNS attempt failed before provider usage and its $0.0372375 reservation is retained. Three full Sol runs scored 50/50 each, with 150/150 evidence audits, zero retries/repairs, $0.1778959 actual gross across full runs and $0.35392836 cumulative M7 accounted gross under the approved $6 cap. [Checkpoint](../reports/M7-December-Sol-v12-checkpoint.json). |
| M7 data-depth feasibility | Measured current local source, disk and processing baseline | [Feasibility](../reports/M7-depth-feasibility.json): 40 MB compressed prefix, 236.5 MB extracted PGN, 111-second source ingestion, August 1 only. No second-day acquisition or engine benchmark; both deferred pending a bounded method/value test. |

Acceptance details: [reports/M0-M1.md](../reports/M0-M1.md), machine-readable
[acceptance.json](../reports/acceptance.json), [foundation manifest](../reports/foundation-manifest.json).
CI workflow exists; equivalent commands ran locally. No hosted CI run is claimed.

## Current dataset versions

- Foundation source: complete `lichess_db_standard_rated_2013-01.pgn.zst`,
  17,761,302 compressed bytes; 92,811,021 decompressed bytes scanned.
- Source SHA256: `aa40b3671fa3cf1072eb182892cd90b0e1e003a4a5943492f64b77e7f3fd1635`.
- Foundation snapshot: `b57f51ff70cc3c1637e641c7` in ignored `data/published/`.
- Tiny snapshot: `0fdc4ce15185898c10b4f155`; fabricated fixtures, never population data.
- M2 marts over those checked snapshots: foundation `3b34836ba025a78a54e96c46`,
  tiny `52810ff8c95a2c7f9b0acacd`. IDs also bind the dbt files and uv lock;
  a clean rebuild after a dependency change may use a new ID with the same counts.
- M3 partial source snapshot: `6cf51473f8da6ae6b12ea5c2`; analytical move
  snapshot: `84a38a404815ed2729917d76`. M3 data are ignored locally; manifests,
  contracts, references and cases are tracked. The source prefix and extracted
  PGNs must be reacquired to reproduce these data snapshots elsewhere.
- M4 figures and M5 cases use analytical ID `84a38a404815ed2729917d76`.
  M5 case-set SHA256 is in [the manifest](../evals/cases/m5_manifest.json).
- Observed foundation UTC dates: **2012-12-31 through 2013-01-31**, not inferred
  from the archive label. 218 participant ratings are missing and remain null.
- M1 metric/table contract version: 1.0.0; M3 metric contracts are versioned
  separately. The original M1 implementation commit was
  `a617582b7df05193485d07721c6f21cccda72df0`; M3 changed bounded-write
  handling and the partial-source manifest flag, so current snapshot IDs above
  supersede those in historical M1/M2 reports. Full code/lock hashes are in
  current manifests.

## Limitations and blockers

The personal key was loaded only by the named live adapter after explicit
caps. The M7 $6.00 cap applied cumulatively to the frozen December Sol gate;
the M6 caps are closed. Model/pricing defaults were last checked
against the official model page on 2026-10-04; account credit use itself was
not independently verified.
Normal wheel installation (`--no-editable`) resolves the observed
macOS hidden editable `.pth` issue; see DECISIONS.md. Initial package/bootstrap
failures are recorded there. Archive and dependencies were downloaded once with
network access; offline reproduction assumes installed or cached dependencies.

M1/M2 target fixed complete Lichess exports and one local writer. They do not claim
general PGN import, power-loss durability, full multi-source reconciliation,
unattended scheduling, or scaling benchmarks. Failed/old local runs are retained.
The 2013 archive provides ingestion evidence, not contemporary player or clock analysis.
M3's newer data are an ordered archive prefix, not a random sample or full month.
Opening labels come from provider tags. Clock/evaluation coverage is sparse and
selected; the >=200-centipawn deterioration measure is exploratory and supports
no causal claim about time pressure. The compressed-prefix checksum identifies
the retained bytes, not the publisher's full archive.
M4 intervals describe focal-player resampling within the observed prefix, not
uncertainty for the full month. M5 free-form SQL remains disabled because a
separate isolated benchmark worker has not been established. The held-out
v2 case labels were frozen before live calls and are now inspected; retire this
split before any future untouched model claim. The benchmark compares two
typed-planner prompt conditions, not the proposed restricted-SQL baseline.
M6 adds a killable 30-second worker for live model-driven tool execution; typed
fixture replay still uses the direct local path.
The optional orchestrators are local demonstrations, with no schedules or cloud
deployments. Prefect's local ephemeral API needs a localhost socket. The first
comparison attempt could not bind one inside the sandbox; a permitted local run
completed and its result was saved. See [run instructions](ORCHESTRATION.md).
Separate locked Dagster-only and Prefect-only environments installed from the local
uv cache and completed one-off tiny runs during M2. The current dbt-enabled
environment with optional dbt/dashboard extras passed **56 offline tests** at the reviewed baseline; the final portfolio revision passed **93 offline tests** (none skipped); Ruff check/format, Git whitespace check,
and `uv lock --check --offline` pass with the workspace cache. The current foundation
snapshot still reports 3,982/121,332. No hosted CI run is claimed.

## Next concrete work — publication verification

A tracked-files export installed the locked dbt/dashboard environment with a
one-time download of two missing cached wheels. It passed 81 tests; 12 optional
real-data tests skipped because their ignored archives/snapshots are absent.
The complete synthetic demo and Ruff passed in the export. [Release check](../reports/portfolio-release-check.json). A wheel and source
archive were inspected for ignored local payloads. The upload candidate and
33 reachable commits had no simple credential/personal-path pattern matches;
this is a bounded scan, not a guarantee. No hosted CI run or remote upload is
claimed. The owner selected GPL-3.0-or-later for original project code; the
license file and package metadata now declare it. The review/hardening changes
remain uncommitted and hosted CI remains unverified. After the license change,
the local dbt/dashboard suite passed 93/93; locked dependency resolution passed.
The rebuilt wheel declares `GPL-3.0-or-later` and includes LICENSE. The source
archive includes LICENSE and excludes ignored scratch `work/` content after an
explicit package exclusion was added. M8 now has a separate offline routing
experiment; it does not change this portfolio release candidate.

## M8 checkpoint and remaining gate

Do not reuse inspected splits for an untouched quality claim. The December
Sol new-date gate is accepted with three complete 50-case repetitions and
**$0.353928360** cumulative accounted M7 gross. Earlier Luna failures and
offline replays remain retained separately from live results. M8 research
ranks question intent/boundary routing first. The 80 new labels were authored
before model scoring, but have not had independent human adjudication. The
40-case rules test scored 35/40. Actual direct Jev passes scored 39/40 and
37/40; two decisions changed between identical runs. The existing structured
analyst scored 33/40. All paths detected five of five unsupported requests.
An offline DuckDB table replayed the rule score. The separately approved
cumulative gross caps were $0.05 TypeSafe and $0.10 OpenAI; actual accounted
M8 gross was $0.002000376 and $0.00417844, respectively. An OpenAI attempt
stopped after 20 completed cases because a checked clock comparison subtracted
null coverage; the failure and cost were retained, the tool was fixed and
regression-tested, and a fresh 40-case run completed. An earlier retry stopped
before transport on preflight dataset drift. A Jev community-extension install for pinned DuckDB
1.4.1/macOS arm64 returned HTTP 404, so SQL Jev execution awaits an isolated
compatible build. The original 80 route labels still lack independent human
review; the new eight end-to-end boundary labels received owner review.
See [M8 learning runbook](JEV_ROUTING_RUNBOOK.md).
After the live fix, the locked local suite passed **99 tests** with Ruff
check/format and `git diff --check`; the complete synthetic demo had passed
before the paid runs. A final source archive and wheel included the new M8
modules/reports but no ignored `work/`, local cache, or key file. The
[post-M8 upload audit](../reports/M8-upload-audit.json) found no matching
sensitive filenames; it is a bounded pattern scan, not a secret guarantee.
Stockfish enrichment remains conditional
on a measured value test. Consider OpenRouter or CheaperInference only if
inference costs rise materially. Restricted SQL and optional Airflow remain
follow-ups; the recommender stays backlog.

The fresh December 32-case end-to-end holdout has eight opening families
outside the prior M7 reference and independent raw-PGN numeric values.
Its eight boundary labels were shown to and approved by the owner before
new model calls. One complete paired live run scored 30/32 per arm under
the original rubric; an offline rescore of the saved answers corrected a
last-evidence-only false negative and gives **31/32 per arm** (23/24
answerable, 8/8 boundary). No model response was repeated for that rescore.
Both arms used Luna; the accepted M7 checkpoint used Sol. Jev avoided six
of 32 Luna analyst calls but gross cost was $0.002503882 versus
$0.00242630 Luna baseline, and summed per-case elapsed time was 86.11 versus
83.97 seconds. Actual gross TypeSafe $0.000804762 and OpenAI $0.00412542
were under newly approved $0.03/$0.20 caps; no unknown-cost reservation.
Both arms missed the same answerable coverage question. No Jev production
integration is justified by this one small Luna comparison; Sol pairing
remains unmeasured. Original
results, rescore, and [decision checkpoint](../reports/M8-e2e-checkpoint.json)
are distinct. The historical preflight will reject future source hash drift;
new caps and a fresh preflight are needed for any subsequent live study.
The locked local suite passed **103 tests** after the scorer regression,
with Ruff, format, lock and whitespace checks. The tracked checkpoint
reconciles to the retained actual report and offline rescore. The current
[upload candidate audit](../reports/M8-e2e-upload-audit.json) found no
matching sensitive filenames or personal paths; it is a bounded pattern
scan, not a fresh clean-export or hosted-CI run.

The actual M6 v2 model responses and two scored failures are retained. M5's 50/50
fixture replay is harness validation, not model accuracy. The provider example
is disabled by default; no workplace credential was used. Gross cost is reported
even if account credit covers it. No hosted CI run or broad model-performance
claim is made.
