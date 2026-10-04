# Status — 2026-10-04

**M0–M6 accepted locally; M7 in progress.** This is a new standalone local Git
repository; projects 1–3 remain together. No remote repository or hosting created.

## Phase tracker

| Phase | State | Next gate |
|---|---|---|
| M0 bootstrap | Done | Accepted offline environment and fixtures |
| M1 vertical slice | Done | Accepted bounded foundation ingestion and reference metric |
| M2 reliable platform | Done | Accepted dbt/recovery/operational checks locally |
| M3 analytical corpus and metrics | Done | Accepted bounded prefix, observed coverage, independent checks, 12 draft dev cases |
| M4 analytics product | Done | Accepted local six-view dashboard and two reproducible memos |
| M5 analyst/eval harness | Done | Accepted checked typed tools, fixture replay and 50-case harness; no model result |
| M6 measured release | Done; typed-analyst release gates met | Three complete frozen v2 repetitions, 118/120 scored passes, all evidence audits and offline checks passed. See [release checkpoint](M6-RELEASE.md). |
| M7 depth | In progress; 50-case live preflight frozen | Three 100-request repetitions fit the user-approved $0.50 cumulative gross cap conservatively. Score and audit actual responses before accepting. Provider alternatives only if inference costs rise. [Plan](M7.md). |
| M8 Jev | Follow-up | Fair, measured integration experiment |
| Personalized recommender | Backlog | Outside first-release scope |

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
| M7 first offline slice | Explicit prompt guidance for answerable clock evaluation coverage; 12 new development paraphrases and negative controls from the independent raw-PGN tally | Checked-tool/oracle replay 12/12: 8 answerable, 1 clarification, 3 unsupported. No M7 model response or larger holdout yet. [M7 plan and evidence](M7.md). |
| M7 larger holdout preflight | 50 new cases: 41 answerable, 9 clarification/unsupported, 5 high-severity; 25 opening families absent from inspected M5/M6 cases; new raw-PGN cohort reference | 50/50 checked-tool/oracle answers match independent references. Frozen [100-request preflight](../reports/M7-holdout-preflight.json) reserves $0.13475275 per run or $0.40425825 for three, under approved $0.50 cumulative cap. No M7 model response yet. |

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
$0.10 caps for the completed evaluation rounds. The v2 authorization is fully
used and closed; any further live run needs a new explicit cap. Model/pricing defaults were last checked
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
environment with optional dbt/dashboard extras passes **43 offline tests** (none skipped); Ruff check/format, Git whitespace check,
and `uv lock --check --offline` pass with the workspace cache. The current foundation
snapshot still reports 3,982/121,332. No hosted CI run is claimed.

## Next concrete work — M7

Strengthen clock-coverage routing without sacrificing unsupported-case
abstention. The prompt refinement, 12-case development replay, and 50-case
family split are offline only so far; no new model quality claim exists. Run
the frozen evaluation under the approved cap, then audit every failure and
paired result. Study bounded source and
engine depth only with measured coverage, runtime and disk benefit. Evaluate
OpenRouter or CheaperInference only if inference costs rise materially. The
restricted-SQL baseline remains deferred until isolation is proved. Optional
Airflow remains deferred unless its local stack has a measured benefit. M8 Jev
is follow-up; the recommender remains backlog.

Every future live-cap request will include a specific recommended gross cap,
fresh conservative preflight and prior actual-cost evidence. The user approved
$0.50 cumulative for the frozen M7 evaluation; the exact three-repeat
reservation is $0.40425825. This cap does not authorize any other live run.

The actual v2 model responses and two scored failures are retained. M5's 50/50
fixture replay is harness validation, not model accuracy. The provider example
is disabled by default; no workplace credential was used. Gross cost is reported
even if account credit covers it. No hosted CI run or broad model-performance
claim is made.
