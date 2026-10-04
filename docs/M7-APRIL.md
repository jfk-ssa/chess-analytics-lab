# M7 April v8 release gate — frozen before live scoring

The July v5, June v6, and May v7 evaluations remain inspected, failed or stopped
evidence. The May complete run scored 36/41 answerable cases, below the
precommitted 37/41 gate. Five exact opening-usage misses were corrected by a
narrow, logged checked-tool route and passed **offline replay**; historical live
scores have not been changed. Two June malformed argument responses likewise
passed offline recovery replay only. This April v8 holdout is the first live
test of both corrections on a new source date.

The source is an exact 40,000,000-byte prefix of the April 2026 Lichess
standard-rated archive, not the full archive or a random monthly sample. It
contains 100,000 complete PGNs covering **April 1 only**. 99,578 were accepted,
422 excluded, with no quarantine or conflict. The deterministic move sample
has 5,016 selected games and 333,642 moves. The independent raw-PGN check
agrees with the published source draw rate, 12 opening families, four player
cohorts and four clock buckets. A separate raw-PGN reference tallied 25
opening families and four specified White 1400–1599 60+0 cohorts. All 50
offline checked-tool/oracle outcomes match their references. These are data
and harness checks, not model results.

The 50 frozen cases comprise 41 answerable, nine clarification/unsupported,
and five high-severity boundary questions. The dataset ID is new; question
concepts and many family names recur. The claim is a new observed source-date
checkpoint, not disjoint semantics or population accuracy. The case set,
independent values, code, exact request hashes, model, prices and cap are
frozen in `reports/M7-April-v8-preflight.json`. Product `semantic_context`
is the only condition. No April model response had been scored at freeze.

## Acceptance rule committed before live scoring

Three complete repetitions of the identical 50-request preflight must each
score at least 37/41 answerable cases, all 9/9 clarification/unsupported
cases, and all 5/5 high-severity cases. Every completed answer must pass the
evidence/access audit. Case IDs, request hashes, order, dataset and model
must match the freeze. Each repetition may use at most one *logged* exact
transport retry for `provider HTTP 400: invalid_request_error: Invalid prompt`.
The first subattempt's full reserved price is counted as unknown gross even
if the second succeeds. Final attempts must all complete with known usage.
No other execution failure or unattempted cell is accepted. Preserve raw
subattempt failures, semantic repairs and scored misses. The resulting
metric is end-to-end checked-analyst performance; separately report how many
answers used deterministic semantic repair rather than attributing them to
the model alone.

Prior M7 gross accounted is **$0.094620415**, including full reservations for
unknown-cost attempts. The April preflight reserves **$0.094273125** per
repetition, including one maximum-sized transport retry. Three full
reservations plus prior account for **$0.377439790**, under the approved
**$0.50 cumulative gross cap**. Account credit does not change this cap.
The runner checks remaining budget before each repetition and stops on a
failed final attempt, unknown usage, or budget violation.

## Observed result — gate not met

Repetition 1 completed 50/50 scored passes: answerable 41/41, boundary 9/9,
high severity 5/5, evidence audit 50/50, gross $0.003762745.
Repetition 2 completed 49/50: answerable 40/41, boundary 9/9,
high severity 5/5, evidence audit 50/50, gross $0.002996155.
The one scored miss selected the wrong tool/filters for a `10_to_29` clock
proxy question. Repetition 3 stopped at cell 13: 12/13 attempts completed,
12 scored passes, 37 cells unattempted. A provider response repeated the same
valid JSON plan ten times inside one text chunk, then truncated an eleventh
copy at the 512-token output cap. The existing unique-plan parser failed
closed. The final response carried known usage, so gross was $0.00100738.
No transport retry occurred. The [checkpoint](../reports/M7-April-v8-checkpoint.json)
records a failed three-run gate. Cumulative M7 accounted gross is
**$0.102386695** of $0.50.

A bounded parser now accepts only multiple *identical* complete JSON plans,
with an optional trailing prefix of one already seen plan when the provider
marks the response incomplete. It rejects a conflicting complete plan,
unrecognized prose, or excess length and logs the recovery. The retained
April response passes an **offline replay** under that parser; the failed
live attempt remains failed. A new March dataset and v9 case freeze will
test the correction live.
