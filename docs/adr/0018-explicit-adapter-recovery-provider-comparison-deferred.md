# 0018. Explicit adapter recovery, provider comparison deferred

- Status: accepted
- Date: 2026-10-04

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
