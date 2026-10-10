# Metric registry

**HTML version:** [Read this guide on the documentation site](https://jfk-ssa.github.io/chess-analytics-lab/metrics.html).

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
  count divided by eligible completed, rated Standard, non-marked-bot games
  with a nonempty source opening family. Unknown
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

M4 adds [opening adjusted score](../contracts/opening_adjusted_score.json):
common pooled weights across three focal-minus-opponent rating-difference
strata, with a seeded focal-player cluster bootstrap. The M4 dashboard and
analyst tool use the same implementation. Its interval describes dependence
within the observed prefix, not uncertainty for all August games.


## Opening-position metrics

[Transpositions](TRANSPOSITIONS.md) uses the checked opening-position publication,
with definitions in [opening_positions.json](../contracts/opening_positions.json).

| Metric | Numerator / definition | Denominator / interpretation |
|---|---|---|
| Frequency | Distinct games reaching a canonical board at an eligible White decision | Eligible games in selected cohort, recorded family, or public lens |
| Acyclic routes | Distinct complete earliest-arrival UCI prefixes without repetition | Count, not a percentage or measure of move quality |
| Alternative-route share | Acyclic position games outside the largest route | Position games minus repetition-prefix games; null if zero |
| Study-set coverage | Union of games hitting at least one first-N ranked board | Eligible view games; a game counts once across the set |
| Marginal coverage | Newly covered games when the next ranked board is added | Report count as well as total coverage |
| Endpoint compression | 1 minus distinct endpoints / distinct acyclic routes at one ply | Same nonrepeating visits at that ply; descriptive convergence |
| Recorded-label breadth | Complete distinct known families and known ECO codes, counted separately | Recorded game tags can reflect later play; five examples are not exhaustive |

The two cohort denominators stay separate. Lens frequencies use only matching games;
family filters use recorded-family game counts. Repetition arrivals contribute to
position frequency but not acyclic routes. Route-card shares use all position games,
while alternative-route share uses acyclic games. Draw counters and repetition
history are outside the canonical recognition key.

In the Elite report, the leading Sicilian board has 8,465 games and eight routes,
but 99.29% of acyclic arrivals use one route. The QGD example has 6,431 games and
28 routes, with only 33.28% on its leading route. Frequency and route count alone
would hide that difference. Their alternative-route shares are 0.71% and 66.72%.

Charts and rankings describe selected public games. They do not establish learning
improvement, personal encounter rates, engine quality, or causal outcome differences.


## Local imported-game metrics

[The import contract](../contracts/imported_games.json) defines a separate personal
population. Selected valid completed Standard White games include short games by
default; matched Black games, unmatched players and explicit filter exclusions
are reported separately. No public rating floor is silently applied.

| Metric | Definition | Interpretation |
| --- | --- | --- |
| Personal board frequency | Earliest eligible board visits / selected White games | Plies 6–20; short games remain in the denominator |
| Study-set coverage | Union of White games reaching the first N selected published boards / selected White games | N=1..20; selected set only, not full-corpus novelty |
| Personal alternative-route share | 1 − leading acyclic route games / acyclic position games | Repetition-prefix arrivals excluded; null for no acyclic arrivals |
| First departure and re-entry | First differing move while selected examples define a continuation; later selected canonical-board hit | Stops at example endpoints; not move quality or a mistake count |

Counts reconcile imports, duplicates, conflicts, rejections and failed files.
Unknown date/time/rated metadata stays unknown. Personal results do not change
public reports. See [the local game guide](GAME_IMPORT.md).
