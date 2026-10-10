# 0019. Accept the bounded M6 typed-analyst release

- Status: accepted
- Date: 2026-10-04

The user authorized up to three frozen v2 40-request repetitions under a
$0.10 cumulative gross cap. All three completed, with scored passes 40/40,
38/40 and 40/40. Answerable numerical cases passed 82/84 overall (each repeat
at least 26/28); ambiguity/unsupported passed 36/36; high-severity passed
18/18; evidence integrity passed 120/120. No attempt crashed or lacked known
usage cost. Gross cost was $0.009968525. The two misses were safe but incorrect
abstentions on answerable clock-coverage questions in one semantic-context
repeat. Preserve them and the first holdout's stopped runs; do not tune the
frozen scorer retroactively. The second split is now inspected and retired.

Accept M6 locally for this bounded typed-tool product because its frozen
release gates passed and the locked full offline suite passed 43/43. This is a
small descriptive benchmark, not broad model accuracy. The experiment does
not include the proposed restricted-SQL baseline or three-arm contrast;
free-form SQL stays disabled pending a proven isolated worker. No additional
live cap is active. M7 is next, initially focused on clock-coverage routing
and a new split if another release claim is needed. Provider comparison is
deferred until a concrete cost or model-choice reason exists.
