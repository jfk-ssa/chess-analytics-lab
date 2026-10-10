# 0027. Bounded cross-month M7 data and product-condition gate

- Status: accepted
- Date: 2026-10-04

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
