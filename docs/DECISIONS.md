# Decisions

Each accepted choice is a short record in [docs/adr/](adr/). Add the next number
when a choice should outlive the chat that made it. [Status](STATUS.md) records
the latest measured state.

| Number | Date | Record |
|---|---|---|
| 0001 | 2026-10-03 | [Scope and repository](adr/0001-scope-and-repository.md) |
| 0002 | 2026-10-03 | [Environment](adr/0002-environment.md) |
| 0003 | 2026-10-03 | [First vertical slice](adr/0003-first-vertical-slice.md) |
| 0004 | 2026-10-03 | [Cost, AI and licensing](adr/0004-cost-ai-and-licensing.md) |
| 0005 | 2026-10-03 | [Parallel orchestration learning path](adr/0005-parallel-orchestration-learning-path.md) |
| 0006 | 2026-10-03 | [M2 dbt and mart recovery](adr/0006-m2-dbt-and-mart-recovery.md) |
| 0007 | 2026-10-03 | [M3 partial corpus and exploratory analytics](adr/0007-m3-partial-corpus-and-exploratory-analytics.md) |
| 0008 | 2026-10-03 | [M4 local product and uncertainty](adr/0008-m4-local-product-and-uncertainty.md) |
| 0009 | 2026-10-03 | [M5 bounded analyst and evaluation instrument](adr/0009-m5-bounded-analyst-and-evaluation-instrument.md) |
| 0010 | 2026-10-03 | [M6 offline release preparation](adr/0010-m6-offline-release-preparation.md) |
| 0011 | 2026-10-03 | [Shorter local key variable](adr/0011-shorter-local-key-variable.md) |
| 0012 | 2026-10-03 | [Optional M6 provider JSON](adr/0012-optional-m6-provider-json.md) |
| 0013 | 2026-10-03 | [First actual M6 development pilot](adr/0013-first-actual-m6-development-pilot.md) |
| 0014 | 2026-10-03 | [Further M6 development, still below release gate](adr/0014-further-m6-development-still-below-release-gate.md) |
| 0015 | 2026-10-03 | [Development gate reached, release gate untested](adr/0015-development-gate-reached-release-gate-untested.md) |
| 0016 | 2026-10-04 | [Freeze a new M6 family-split holdout before live scoring](adr/0016-freeze-a-new-m6-family-split-holdout-before-live-scoring.md) |
| 0017 | 2026-10-04 | [Holdout accuracy passed once; release held on repeatability](adr/0017-holdout-accuracy-passed-once-release-held-on-repeatability.md) |
| 0018 | 2026-10-04 | [Explicit adapter recovery, provider comparison deferred](adr/0018-explicit-adapter-recovery-provider-comparison-deferred.md) |
| 0019 | 2026-10-04 | [Accept the bounded M6 typed-analyst release](adr/0019-accept-the-bounded-m6-typed-analyst-release.md) |
| 0020 | 2026-10-04 | [Start M7 with error-driven depth; defer provider alternatives](adr/0020-start-m7-with-error-driven-depth-defer-provider-alternatives.md) |
| 0021 | 2026-10-04 | [Always recommend a spend cap with an estimate](adr/0021-always-recommend-a-spend-cap-with-an-estimate.md) |
| 0022 | 2026-10-04 | [Freeze M7 holdout under approved $0.50 cumulative cap](adr/0022-freeze-m7-holdout-under-approved-0-50-cumulative-cap.md) |
| 0023 | 2026-10-04 | [Retire inspected M7 v1; freeze fresh v2 under the same cap](adr/0023-retire-inspected-m7-v1-freeze-fresh-v2-under-the-same-cap.md) |
| 0024 | 2026-10-04 | [Preserve failed M7 v2 gate and freeze a targeted v3 split](adr/0024-preserve-failed-m7-v2-gate-and-freeze-a-targeted-v3-split.md) |
| 0025 | 2026-10-04 | [Preserve v3 boundary miss; freeze one final v4 split](adr/0025-preserve-v3-boundary-miss-freeze-one-final-v4-split.md) |
| 0026 | 2026-10-04 | [Stop M7 v4 on provider rejection; keep M7 open](adr/0026-stop-m7-v4-on-provider-rejection-keep-m7-open.md) |
| 0027 | 2026-10-04 | [Bounded cross-month M7 data and product-condition gate](adr/0027-bounded-cross-month-m7-data-and-product-condition-gate.md) |
| 0028 | 2026-10-04 | [M8 Jev route selection deferred to a narrow measured task](adr/0028-m8-jev-route-selection-deferred-to-a-narrow-measured-task.md) |
| 0029 | 2026-10-04 | [Preserve May/April failed gates; repair only unambiguous plans](adr/0029-preserve-may-april-failed-gates-repair-only-unambiguous-plans.md) |
| 0030 | 2026-10-04 | [Retire stopped March v9; freeze February v10 under the same cap](adr/0030-retire-stopped-march-v9-freeze-february-v10-under-the-same-cap.md) |
| 0031 | 2026-10-04 | [Retire February v10 and prepare new January source](adr/0031-retire-february-v10-and-prepare-new-january-source.md) |
| 0032 | 2026-10-04 | [Freeze January v11 after bounded suffix recovery](adr/0032-freeze-january-v11-after-bounded-suffix-recovery.md) |
| 0033 | 2026-10-04 | [Retire January Luna gate; test Sol on inspected cases](adr/0033-retire-january-luna-gate-test-sol-on-inspected-cases.md) |
| 0034 | 2026-10-04 | [Freeze December Sol v12; request a cumulative cap only after offline checks](adr/0034-freeze-december-sol-v12-request-a-cumulative-cap-only-after-offline-checks.md) |
| 0035 | 2026-10-04 | [Accept December Sol v12 after three complete frozen repetitions](adr/0035-accept-december-sol-v12-after-three-complete-frozen-repetitions.md) |
| 0036 | 2026-10-04 | [M8 research ranks semantic routing above cost routing](adr/0036-m8-research-ranks-semantic-routing-above-cost-routing.md) |
| 0037 | 2026-10-04 | [Pin M7 baseline and isolate M8 variants within one repository](adr/0037-pin-m7-baseline-and-isolate-m8-variants-within-one-repository.md) |
| 0038 | 2026-10-04 | [Review first; defer implementation and Jev](adr/0038-review-first-defer-implementation-and-jev.md) |
| 0039 | 2026-10-04 | [Portfolio integrity and offline release path](adr/0039-portfolio-integrity-and-offline-release-path.md) |
| 0040 | 2026-10-04 | [Clean-export acceptance and publication boundary](adr/0040-clean-export-acceptance-and-publication-boundary.md) |
| 0041 | 2026-10-05 | [Portfolio code license](adr/0041-portfolio-code-license.md) |
| 0042 | 2026-10-05 | [Executable offline walkthrough](adr/0042-executable-offline-walkthrough.md) |
| 0043 | 2026-10-05 | [M8 routing study and DuckDB isolation](adr/0043-m8-routing-study-and-duckdb-isolation.md) |
| 0044 | 2026-10-05 | [M8 live routing results and no production promotion](adr/0044-m8-live-routing-results-and-no-production-promotion.md) |
| 0045 | 2026-10-05 | [M8 paired final-answer study](adr/0045-m8-paired-final-answer-study.md) |
| 0046 | 2026-10-05 | [Final publication review gate](adr/0046-final-publication-review-gate.md) |
| 0047 | 2026-10-05 | [Publication fixes after review](adr/0047-publication-fixes-after-review.md) |
| 0048 | 2026-10-05 | [Private portfolio repository](adr/0048-private-portfolio-repository.md) |
| 0049 | 2026-10-05 | [Public portfolio publication](adr/0049-public-portfolio-publication.md) |
| 0050 | 2026-10-06 | [Separate public business examples](adr/0050-separate-public-business-examples.md) |
| 0051 | 2026-10-07 | [Optional OpenAI Decisions classifier](adr/0051-optional-openai-decisions-classifier.md) |
| 0052 | 2026-10-07 | [Lead the comparison with results](adr/0052-lead-the-comparison-with-results.md) |
| 0053 | 2026-10-07 | [First-visit documentation and publication](adr/0053-first-visit-documentation-and-publication.md) |
| 0054 | 2026-10-07 | [Reviewed changes published](adr/0054-reviewed-changes-published.md) |
| 0055 | 2026-10-09 | [Static documentation publication](adr/0055-static-documentation-publication.md) |
| 0056 | 2026-10-09 | [Shared typography and presentation](adr/0056-shared-typography-and-presentation.md) |
| 0057 | 2026-10-09 | [Inter throughout](adr/0057-inter-throughout.md) |
| 0058 | 2026-10-09 | [Try Sora throughout](adr/0058-try-sora-throughout.md) |
| 0059 | 2026-10-09 | [DM Sans approved after compact reading comparison](adr/0059-dm-sans-approved-after-compact-reading-comparison.md) |
| 0060 | 2026-10-09 | [Inter Medium selected for current guides and dashboard](adr/0060-inter-medium-selected-for-current-guides-and-dashboard.md) |
| 0061 | 2026-10-10 | [One M7 campaign command](adr/0061-one-m7-campaign-command.md) |
| 0062 | 2026-10-10 | [Functional package names](adr/0062-functional-package-names.md) |
| 0063 | 2026-10-10 | [Analyst modules by responsibility](adr/0063-analyst-modules-by-responsibility.md) |
