# Metric registry — M1–M3

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

M3 metrics use the checked partial analytical snapshot and are descriptive only:

- [Opening usage](../contracts/opening_usage.json): source Opening tag family
  count divided by completed, rated Standard, non-marked-bot games. Unknown
  results do not enter the denominator. Missing/unknown source tags are shown,
  never silently inferred.
- [Opening player score](../contracts/opening_player_score.json): one player-game
  in a specified color, rating range and exact time control. Reports wins,
  draws, losses, win rate and half-point score rate with explicit denominator.
- [Clock pressure error proxy](../contracts/clock_pressure_error_proxy.json):
  deterministic game-ID-hash selection within the source prefix; zero-increment
  games only. Prior same-player clock determines the bucket. Among eligible
  moves with comparable source centipawn evaluations, the numerator counts
  >=200 cp mover-perspective deterioration. Missing/mate evaluation counts and
  [coverage](../contracts/evaluation_coverage.json) accompany the rate.

These definitions are versioned, and [M3's independent raw-PGN check](../reports/M3-reference-check.json)
confirms selected arithmetic. Source annotations are not independently
engine-verified. No monthly, population, or causal interpretation is warranted.
