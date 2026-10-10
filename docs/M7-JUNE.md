# M7 June fresh-data release gate — frozen before live holdout calls

The July v5 holdout is inspected and failed: its first complete run scored
32/50 (answerable 23/41, boundaries 9/9, high severity 5/5). A second run
stopped after 23 attempted cells on provider HTTP 400 with unknown usage.
The earlier sandbox DNS failure and both v5 runs are retained. Unknown-cost
attempts count their full conservative reservations in cumulative gross
accounting. July's observed date is July 1 only, not a full month.

The new source is a separate fixed 40,000,000-byte prefix of the June 2026
standard-rated archive, with observed **June 1** coverage only. The exact
range, source listing and prefix SHA256 are in the `june` entry of `config/m7_campaigns.json`.
The publisher's full-archive checksum is not claimed. June has 100,000
complete PGNs, 99,530 accepted games, 470 exclusions and zero quarantine or
conflicts. Its deterministic game-ID-hash sample selected 5,087 games and
341,250 moves. Independent raw-PGN checks passed for 12 opening families,
four player cohorts, four clock buckets and source draw rate. A separate
reference tallied 25 opening families and four White 1400–1599 60+0 cohorts
for the holdout. All 50 checked-tool/oracle outcomes matched offline. Those
are data and harness checks, not model accuracy.

The isolated June workspace uses month-neutral wording for the opening-usage
and clock-proxy caveats; the historical August contracts and accepted August
dashboard remain intact. Two six-request live development smokes on
previously inspected July templates passed 6/6 each on June data, gross
$0.000888095 and $0.000334320. Those cases and their responses are development
evidence and are excluded from the holdout score. The analyst prompt also
directs exact opening-family usage questions to the checked metric instead of
inferring family support. Raw development attempts remain in ignored local
work files; a key-free summary is tracked.

The June v6 holdout has 50 frozen new-data cases: 41 answerable, nine
clarification/unsupported, and five high-severity boundaries. Family names
and some task templates recur across months; the claim is a **new data/date
holdout**, not a family- or template-disjoint test. The questions, expected
June numbers, dataset ID, case-set SHA256, source plan, contract hashes,
prompt/scorer code, model, request hashes, prices and cap are frozen in
`reports/M7-June-v6-preflight.json`. The product condition is
`semantic_context` only; earlier `schema_only` evaluations remain an ablation.

## Acceptance rule committed before live scoring

Three complete 50-request repetitions of the identical preflight must each
pass at least 37/41 answerable cases, all 9/9 clarification/unsupported
cases (integer interpretation of at least 90%), and all 5/5 high-severity
cases. Every completed answer must pass the evidence and access audit. Case
and request hashes, ordering, dataset and resolved model must match the
preflight. There may be no failed, unknown-cost, or unattempted cell in an
accepted run. Each provider gross cost must be known. Cumulative M7 gross,
including full reservations for historical unknown-cost attempts, must not
exceed the approved **$0.50**. Retain every raw response and scored failure.
This is a finite task-set checkpoint, not a statistical claim about all
chess questions or the full June/August populations.

Prior M7 accounted gross is **$0.083854345**. The June preflight reserves
**$0.092240125** per 50-cell repetition. Three conservative reservations
plus prior accounted gross total **$0.360574720**, below the approved
$0.50 cumulative cap. Actual usage and gross costs are recorded for each
call. Stop on a failed request, unknown usage or exceeded bound and preserve
partial runs. Credits are not treated as spend authorization.

The first June repetition stopped at cell 32 because the provider appended
prose after a structured JSON plan. The adapter rejected it; 31 completed
cells scored 31/31, and the failed cell had known usage. Its $0.002186995
gross cost is retained. The unchanged frozen plan may be repeated, with
updated prior accounted gross **$0.086041340** and a three-repeat conservative
total of **$0.362761715**. This partial run is not an accepted repetition.
