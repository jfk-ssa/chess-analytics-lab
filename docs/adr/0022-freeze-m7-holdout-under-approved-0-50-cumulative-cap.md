# 0022. Freeze M7 holdout under approved $0.50 cumulative cap

- Status: accepted
- Date: 2026-10-04

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
