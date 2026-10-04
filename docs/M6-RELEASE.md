# M6 measured-release checkpoint — 2026-10-04

**Accepted locally for the bounded typed-tool analyst.** The frozen second
opening-family holdout met every proposed release gate without changing its
scorer or excluding failed attempts. This is descriptive evidence for one
20-case split, two prompt conditions, one resolved model (`gpt-6-luna`), and
three repetitions. It is not a broad accuracy or superiority estimate.

| Measure | Repeat 1 | Repeat 2 | Repeat 3 | Pooled |
|---|---:|---:|---:|---:|
| Completed / planned requests | 40/40 | 40/40 | 40/40 | 120/120 |
| Scored passes | 40/40 | 38/40 | 40/40 | 118/120 |
| Answerable numerical passes | 28/28 | 26/28 | 28/28 | 82/84 (97.6%) |
| Ambiguity / unsupported passes | 12/12 | 12/12 | 12/12 | 36/36 |
| High-severity passes | 6/6 | 6/6 | 6/6 | 18/18 |
| Evidence-integrity audit | 40/40 | 40/40 | 40/40 | 120/120 |
| Gross API cost (USD) | 0.003663685 | 0.003115655 | 0.003189185 | **0.009968525** |
| Median request latency (s) | 2.179 | 1.857 | 1.846 | Per-run values only |

The approved cumulative gross cap was **$0.10**. Cost is based on reported
provider usage for every attempt, including failures; account credits were not
subtracted. All three repetitions were checked against the same 40-request
preflight and case-set hash. The [gate check](../reports/M6-release-checkpoint.json)
checks complete attempt order and request hashes, per-run 90% thresholds, all
high-severity outcomes, every evidence audit, no unhandled execution failures,
and total spend. The [variability report](../reports/M6-holdout-v2-variability.json)
preserves the paired outcome of every case and condition, cache usage, latency,
cost per passed answer, and the actual normalization events.

The only scored misses were `h2_clock_10_to_29_coverage` and
`h2_clock_30_to_59_coverage` in repeat 2's semantic-context condition. Both
were answerable selected-move evaluation-coverage questions. The model returned
`unsupported` with no tool action or evidence even though the checked clock
metric could answer them. This was a safe but incorrect abstention, not a
fabricated number. Both full model texts, usage, response IDs and frozen score
failures remain in [repeat 2](../reports/M6-holdout-v2-run-2.json). The other
two repetitions answered these cells correctly. All ambiguity and high-severity
cases were individually inspected through the [evidence audits](../reports/M6-holdout-v2-audit-1.json),
[repeat 2 audit](../reports/M6-holdout-v2-audit-2.json), and
[repeat 3 audit](../reports/M6-holdout-v2-audit-3.json); none failed.

Offline acceptance used the locked environment with dbt and dashboard extras:
**43 tests passed, none skipped**; Ruff, lock check, and the tiny offline demo
passed. The demo accepted 22/26 fixture games and reproduced 4/20 draws. The
repeatable [offline demo script](../scripts/demo_m6_offline.sh) runs the tiny
pipeline and rechecks the retained release reports without a provider call.
All 20 deterministic checked-tool answers matched independent references before
live scoring; the [preflight](../reports/M6-holdout-v2-preflight.json) retained
40 request hashes and 24 file hashes. The earlier [fresh-clone check](../reports/M6-fresh-clone.json)
remains valid. This is local verification; hosted CI was not run.

To reproduce the local checks after installing the locked optional extras:

```sh
UV_CACHE_DIR=.uv-cache uv sync --locked --offline --no-editable --extra dbt --extra dashboard --reinstall-package chess-analytics-lab
.venv/bin/pytest -q -rs
.venv/bin/ruff check .
.venv/bin/ruff format --check .
UV_CACHE_DIR=.uv-cache uv lock --check --offline
UV_CACHE_DIR=.uv-cache scripts/demo_m6_offline.sh
```

The release checker also rejected an intentionally altered frozen request hash
in a local negative check. The demo requires the locked dependencies to be
installed or available in the uv cache; it does not download the analytical
archive or call a model.

Scope limits remain material. The experiment compares schema-only and
metric-semantic **typed-planner prompts** with the same checked tools. It does
not implement the specification's restricted-SQL baseline or its three-arm
comparison; free-form SQL remains disabled until isolation is proved. The
semantic condition's two misses do not establish a meaningful condition
difference on this small split. The v2 holdout has now been inspected and must
be retired before further untouched claims. Source coverage is only the
observed one-day August 2026 archive prefix, with sparse selected-move
clock/evaluation data. Live calls remain disabled by default, and any new live
run needs a fresh explicit cap.

M7 should test clock-coverage routing on development cases, preserve the
unsupported boundary, and freeze a new holdout if a new model claim is sought.
Provider routing or a cheaper model is worth a paired test only when expected
savings or model choice justifies the extra billing and failure surface. See
[provider decision](PROVIDERS.md). M8 Jev remains follow-up; the personalized
recommender stays backlog.
