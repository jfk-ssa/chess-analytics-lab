# M7 May v7 fresh-data gate — frozen before live holdout calls

The June v6 holdout is inspected and retired for a fresh-data claim. Two
attempted repetitions stopped at cells 32 and 33. Their preceding completed
cells scored 31/31 and 32/32, but the provider placed a complete JSON tool
argument object followed by unrelated text inside `args_json`. The old parser
failed closed. Both failures had known usage and remain scored failures in
their original runs. A later **offline replay**, not a live rescore, showed
that a bounded leading-object recovery would yield the correct checked-tool
result for both. The new parser logs the ignored suffix length, rejects an
additional structured object or oversized suffix, and still passes every
argument through allowlisted typed tools. Unit tests cover acceptance and
rejection. Historical live reports remain unchanged.

This holdout uses an isolated 40,000,000-byte prefix of the May 2026 standard
rated archive. Its 100,000 complete PGNs cover **May 1 only**, with 99,505
accepted games, 495 exclusions, and no quarantine or conflict. The publisher
full-archive checksum is not claimed; the exact prefix hash, range and
listing values are pinned in `config/m7_may_source.json`. The deterministic
move sample selected 4,927 games and 325,259 move rows. Independent raw-PGN
checks passed for source draw rate, 12 opening families, four player cohorts
and four clock buckets. A separate raw-PGN reference tallied 25 opening
families and four specified White 1400–1599 60+0 cohorts; all 50 offline
checked-tool/oracle outcomes matched. These are data and harness checks, not
model results.

The 50 frozen cases have 41 answerable, nine clarification/unsupported, and
five high-severity boundary questions. They use a new dataset and newly
worded questions, but some family names and task concepts recur across
months. The claim is a new data/date checkpoint, not fully disjoint task
semantics. The case set, independent expected values, dataset ID, source plan,
month-neutral contract hashes, prompt/recovery/scorer code, exact request
hashes, model, prices and cap are frozen in `reports/M7-May-v7-preflight.json`.
The product condition is `semantic_context` only; prior `schema_only` results
are an ablation. No May holdout model response had been scored at this freeze.

## Acceptance rule committed before live scoring

Three complete 50-request repetitions of the identical frozen preflight
must each score at least 37/41 answerable cases, all 9/9
clarification/unsupported cases, and all 5/5 high-severity cases. Every
completed answer must pass the evidence/access audit. Case IDs, request
hashes, ordering, dataset and resolved model must match the freeze. Accepted
repetitions may have no failed, unknown-cost or unattempted cell. All gross
provider costs must be known. Cumulative M7 gross, including full
reservations for historical unknown-cost attempts, must remain at or below
the approved **$0.50**. Preserve raw attempts, recovery markers and every
scored failure. Passing supports a bounded fixed-case checkpoint, not
population accuracy, a monthwide estimate, or a statistical-significance
claim.

Prior M7 accounted gross is **$0.088042005**. The May preflight conservatively
reserves **$0.092409625** per 50-cell repetition. Three reservations plus
prior accounted gross total **$0.365270880**, below the approved $0.50 cap.
The runner stops on a failed request, unknown usage, or exceeded budget
bound. Account credit is not treated as a cap.
