# M7 March v9 release gate — frozen before live scoring

The April v8 three-run gate failed because repetition 3 stopped after a
provider response repeated the same valid JSON plan ten times inside one
text chunk and truncated an eleventh copy. The original live failure and
37 unattempted cells remain in the April checkpoint. A bounded parser now
accepts identical complete repetitions and, only for a provider-marked
incomplete response, a trailing prefix of a previously seen plan. It logs
the recovery and rejects conflicting plans, unrelated prose, oversized
chunks and excessive repetitions. The retained April response passes an
**offline replay**, not a retroactive live rescore.

The new source is exactly the first 40,000,000 compressed bytes of the March
2026 Lichess standard-rated archive. It is **March 1 only**, not a complete
archive, random sample, or whole-month estimate. Of 100,000 complete PGNs,
99,555 were accepted and 445 excluded, with no quarantine or conflict. The
deterministic move sample selected 5,048 games and 333,505 moves. The
independent raw-PGN check agrees with source draw rate, 12 opening families,
four player cohorts and four clock buckets. A separate raw-PGN reference
tallied 25 opening families and four specified White 1400–1599 60+0 cohorts.
All 50 offline checked-tool/oracle outcomes match their references. No
March model response had been scored at this freeze.

The 50 frozen cases comprise 41 answerable, nine clarification/unsupported,
and five high-severity boundary questions. The dataset ID and observed date
are new; question concepts and family names recur. The claim is a fixed
new-data/date checkpoint, not disjoint semantics or population accuracy.
The case set, reference, code, exact request hashes, model and prices are
frozen in `reports/M7-March-v9-preflight.json`; product `semantic_context`
is the only condition.

## Acceptance rule committed before live scoring

Three complete repetitions of the identical 50-request preflight must each
score at least 37/41 answerable, all 9/9 clarification/unsupported, and
all 5/5 high-severity cases. Every completed answer must pass the
evidence/access audit. The frozen case IDs, hashes, order, dataset and
resolved model must match. Each repetition may use at most one logged exact
transport retry for the specified provider HTTP 400 prompt error; its first
subattempt is charged at the full cell reservation. No other failed,
unknown-cost or unattempted cell is accepted. All gross cost, repairs,
recoveries and scored misses are retained. Report end-to-end analyst scores
and disaggregate deterministic semantic repairs and recovered provider text
from unmodified model plans.

Prior M7 gross accounted is **$0.102386695**, including full reservations
for historical unknown-cost attempts. The March preflight reserves
**$0.094273125** per run, including one maximum-sized transport retry.
Three full reservations plus all prior spend total **$0.385206070**, below
the approved **$0.50 cumulative gross cap**. Account credit does not alter
the cap. The runner checks remaining budget before each run and stops on a
failed final attempt, unknown usage, or budget violation.

## Observed result — gate not met

The first repetition stopped after 16 attempted cells: 15 completed, 14
scored passes, and 34 unattempted. One exact Queen's Gambit Declined usage
question received a correct opening query followed by an unnecessary coverage
action; the answer result was therefore wrong. The overlapping shorter
family name blocked the original semantic repair. A longest exact-family
repair now passes that retained case in **offline replay**, leaving the live
score unchanged. One provider HTTP 400 on an ordinary opening question
succeeded on the single logged retry. A later HTTP 400 on another opening
question failed closed after the run-wide retry allowance was exhausted.
The final failed call has unknown usage. Known gross was $0.001551475; two
unknown-cost subattempts are charged $0.003701 in full, for $0.005252475
accounted this run and **$0.107639170** cumulative M7 accounted gross.
The [checkpoint](../reports/M7-March-v9-checkpoint.json) is a failed live
gate, not a release result. All 15 completed answers passed the evidence
audit. A shorter boundary phrase in the planner prompt and up to three
logged, fully reserved transport retries per future run will be tested on
a fresh February date. Each cell still gets at most one retry; a final
failure stops the experiment.
