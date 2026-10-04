# M7 February v10 release gate — frozen before live scoring

March v9 stopped after 16 attempts. A correct Queen's Gambit Declined query
had an extra coverage action; an overlapping shorter family name prevented
the narrow semantic repair. A longest exact-family repair passes that case
in **offline replay**. An HTTP 400 succeeded on one logged retry, but a later
HTTP 400 failed after the single run-wide allowance was used. The March
live score and stop remain unchanged. The planner now uses a shorter
inaccessible-data boundary phrase instead of unnecessarily repeating
“private-file access”; all access constraints remain checked by the tools.
Up to three distinct cells in a run may get one logged exact transport retry
each. A final failure still stops the run.

The February source is exactly the first 40,000,000 compressed bytes of the
2026-02 Lichess standard-rated archive. It covers **February 1 only** and is
not a full archive or representative month sample. Of 100,000 complete PGNs,
99,585 were accepted, 415 excluded, with no quarantine or conflict. The
deterministic move sample selected 5,020 games and 335,854 move rows.
Independent raw-PGN checks agree with the published source draw rate, 12
opening families, four player cohorts and four clock buckets; a separate
raw-PGN reference tallied 25 opening families and four specified White
1400–1599 60+0 cohorts. All 50 offline checked-tool/oracle outcomes match.
These are data and harness checks, not model results.

The new dataset/date has 50 frozen cases: 41 answerable, nine
clarification/unsupported, five high-severity boundaries. Question concepts
and family names recur across months. This is a finite new-data/date gate,
not disjoint semantics or population accuracy. Case set, reference, code,
exact request hashes, model, prices and cap are frozen in
`reports/M7-February-v10-preflight.json` before any February model response
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
unmodified model plans in the final report.

Prior M7 accounted gross is **$0.107639170**. The February preflight reserves
**$0.098598875** per 50-cell run, including three maximum-sized transport
retry reservations. Three runs plus prior reserve **$0.403435795**, below
the approved **$0.50 cumulative gross cap**. Account credit does not alter
the cap. The runner checks remaining budget before each run and stops on
unknown cost or a budget violation.

## Observed result — gate not met

Repetition 1 completed all 50 requests and scored 47/50: 38/41 answerable,
9/9 boundary, 5/5 high severity and 50/50 evidence integrity. One ordinary
opening request succeeded on a logged HTTP 400 retry; its rejected
subattempt was fully reserved. One exact opening-usage response used the
logged deterministic semantic repair. Three scored misses are retained.
The run's accounted gross was $0.005584985.

Repetition 2 stopped at cell 26. Its first 25 completed calls all scored
passes and passed the evidence audit. The failed provider response contained
a complete valid JSON plan followed by 870 repeated fullwidth tilde
characters, marked incomplete at the 512-token output cap. The old parser
failed closed, and this attempt's known gross was $0.002023355. The
[checkpoint](../reports/M7-February-v10-checkpoint.json) keeps the three-run
gate failed. Cumulative M7 accounted gross is **$0.115247510**.

A bounded parser now accepts one complete plan followed by 64–4096 repeats
of a single non-ASCII punctuation or symbol character only when the provider
marks the response incomplete. It rejects prose, structured suffixes,
ASCII punctuation and oversized output, and logs the ignored count. The
retained February response passes **offline replay** under the new parser;
its original live failure remains unchanged. A new January data/date freeze
will test the correction live.
