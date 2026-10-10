# M7 July independent-data checkpoint

This checkpoint uses a fixed 40,000,000-byte prefix of the July 2026 standard
rated archive, kept in an isolated local workspace. Its 100,000 complete PGNs
cover **July 1 only**. The prefix SHA256 is recorded in
the `july` entry of `config/m7_campaigns.json`; it is not a checksum of the full publisher archive.
The existing August snapshot, dashboard and memos remain the accepted product
data. July is an independent evaluation slice, not a representative second day
of August or a monthly sample.

The July source ingested 99,740 accepted games, with 260 exclusions and no
quarantines or conflicts. A deterministic game-ID-hash sample selected 4,982
games and produced 329,672 move rows. Independent raw-PGN checks passed for
12 opening families, four cohorts, four clock buckets and draw rate. Twenty-five
popular July opening families and four nonempty, specified White cohorts were
independently tallied for the new 50-case holdout. Its checked-tool/offline
oracle matched 50/50 expected outcomes. This is harness validation only.

The holdout contains 41 answerable and nine clarification/unsupported cases,
including five high-severity access, causal, full-month, personality and
guarantee boundaries. It is disjoint from all inspected splits by **dataset
ID**; opening family names may recur. The frozen case hash, request hashes,
code, July plan, references, model, prices and cap are in
`reports/M7-July-v5-preflight.json`. The product uses the `semantic_context`
condition, so this release gate tests that condition only. Earlier schema-only
results remain a documented ablation, not the release criterion. The `m7-1.0`
scorer and evidence audit are unchanged before live calls.

## Gate committed before live evaluation

Three complete, identical 50-request repetitions must each pass at least
37/41 answerable cases, 9/9 clarification/unsupported cases (the integer
interpretation of at least 90% of nine), and 5/5 high-severity cases. Every
completed answer must pass the evidence/access audit. Frozen request hashes,
case identities and resolved model must match, with no unknown-cost, failed,
or unattempted cell. Each gross provider cost must be known; the cumulative
M7 gross total, including full reservations for historical unknown-cost
attempts, must stay at or below the approved $0.50 cap. Keep all scored
failures and raw attempts. Passing this finite holdout supports a bounded
checkpoint, not population accuracy or statistical significance.

The conservative bound is $0.090877625 per 50-request repetition. Three
repetitions plus $0.074362145 previously accounted gross total
**$0.346995020**, below the approved $0.50 cumulative cap. Actual costs may
be lower; credits are not used as a cap. Abort a run on a provider failure,
unknown usage or budget-bound error and preserve the partial run.

The first live attempt stopped before provider DNS resolution in the sandbox;
usage is unknown, so its full $0.001817625 reservation is accounted. The
network-permitted retry starts at **$0.076179770** prior accounted gross; three
conservative repeat reservations would total **$0.348812645** cumulatively.
The failed attempt and its zero completed answers remain retained.

No engine enrichment is adopted in this checkpoint. The July source adds
independent date and stronger opening-cohort support at a measured bounded
resource cost. Source evaluations remain sparse and selected, so Stockfish
would add a second measurement system but could not make the source sample
representative. A controlled engine pilot needs a separately defined question,
fixed binary/version and node budget, and measured benefit before adoption.
