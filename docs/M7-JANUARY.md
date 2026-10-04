# M7 January v11 release gate — frozen before live scoring

February v10 stopped in repetition 2 when a provider response appended 870
repeated fullwidth tilde characters after a complete valid JSON plan and
marked the response incomplete. Its first run passed the per-run thresholds,
but the three-run gate failed. The original failure remains. A bounded
parser now accepts one complete plan before a 64–4096-character suffix made
of one repeated non-ASCII punctuation or symbol character, only for a
provider-marked incomplete response. It logs ignored length and rejects
prose, structured suffixes, ASCII filler and oversized text. The retained
February response passes **offline replay**, not a retroactive live score.

The January source is exactly the first 40,000,000 compressed bytes of the
2026-01 Lichess standard-rated archive. It covers **January 1 only**, not
the full archive or a representative monthly sample. Of 100,000 complete
PGNs, 99,799 were accepted and 201 excluded, with no quarantine or conflict.
The deterministic move sample selected 4,996 games and 331,779 move rows.
Independent raw-PGN checks agree with source draw rate, 12 opening families,
four player cohorts and four clock buckets; a separate raw-PGN reference
tallied 25 opening families and four specified White 1400–1599 60+0
cohorts. All 50 offline checked-tool/oracle outcomes match. These are data
and harness checks, not model results.

The new dataset/date has 50 frozen cases: 41 answerable, nine
clarification/unsupported, five high-severity boundaries. Question concepts
and many family names recur across months. This is a finite new-data/date
checkpoint, not disjoint semantics or population accuracy. The case set,
independent values, code, exact request hashes, model and prices are frozen
in `reports/M7-January-v11-preflight.json` before any January model response
is scored. The product `semantic_context` condition is the only condition.

## Acceptance rule committed before live scoring

Three complete repetitions of the identical 50-request preflight must each
score at least 37/41 answerable, all 9/9 clarification/unsupported, and
all 5/5 high-severity cases. Every completed answer must pass the
evidence/access audit. Case IDs, hashes, order, dataset and resolved model
must match the freeze. Each repetition may use at most three logged exact
transport retries on distinct cells for the specified provider HTTP 400;
each failed subattempt is charged at its full cell reservation. Final
attempts must all complete with known usage; any other failed or unattempted
cell fails the gate. Retain all responses, repairs and scored misses.
Disaggregate deterministic repairs and provider-text recoveries from
unmodified model plans.

Prior M7 accounted gross is **$0.115247510**. The January preflight reserves
**$0.098593250** per 50-cell run, including three maximum-sized transport
retry reservations. Three runs plus prior reserve **$0.411027260**, below
the approved **$0.50 cumulative gross cap**. Account credit does not alter
the cap. The runner checks remaining budget before each run and stops on
unknown cost or a budget violation.

## Observed result — gate not met

Repetition 1 completed 50/50 requests and scored 48/50: 39/41 answerable,
9/9 boundary, 5/5 high severity, and 50/50 evidence integrity. It used no
transport retry or semantic repair and cost $0.003895885 gross. Repetition
2 stopped at cell 26 after 25 completed scored passes. The provider mixed a
valid opening-score plan with a fabricated tool transcript, then emitted a
separate `answered` plan with no actions. The parser selected that unique
valid JSON chunk, but the checked core rejected the evidence-free answer.
The failed response has known usage; repetition 2 cost $0.001670965.
The [checkpoint](../reports/M7-January-v11-checkpoint.json) remains a failed
three-run gate. Cumulative M7 accounted gross is **$0.120814360**.

This is a different ambiguity from the earlier suffix failures: there are
conflicting apparent plans. Keep failing closed rather than choosing a plan
from the malformed provider text. Official OpenAI documentation lists
`gpt-6-sol` as supporting Responses structured outputs at $2 input,
$0.20 cached input, $2.50 cache write and $10 output per million tokens.
A six-case inspected-data development smoke has a $0.223097500 conservative
reservation; with all prior M7 spend, the bound is $0.343911860 under the
existing $0.50 cap. This is development diagnosis, not a new holdout or a
model quality claim. A full three-run 50-case Sol gate will require a
separately recommended cap if the model proves useful.
