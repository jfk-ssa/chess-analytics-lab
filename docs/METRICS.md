# Metric registry — M1

`contracts/game_draw_rate.json` is the versioned definition and result schema.
`src/chess_analytics/metrics/draw_rate.sql` is the reviewed SQL implementation.

**Game draw rate 1.0.0:** completed eligible drawn games / completed eligible games,
one count per provider/game ID. Eligible = rated Standard, excluding marked bots.
Unknown results are excluded and reported separately; an empty denominator is null.
Marked bots and unknown results are separate non-overlapping exclusion counts
(bot status takes precedence). Missing rating does not exclude a draw-rate record.

Result includes exact numerator/denominator, fraction, metric/contract versions,
dataset snapshot ID, source hash and caveats. The tiny fixture's manually specified
expected result is 4/20. A separate header-tally script verifies the real corpus
without using the parser, analytical SQL or DuckDB; it does not verify move legality.
Only compare its denominator directly when ingestion reports zero quarantine/conflicts.

This is a descriptive foundation-data check. No uncertainty/population claim,
opening comparison, time-pressure analysis or model benchmark is attached to it.
