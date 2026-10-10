# Reading the transposition analysis

## What the numbers describe

The explorer measures White decision positions after Black’s moves 3–10 in two
separate public cohorts. A board’s frequency is its distinct-game count divided
by the eligible games in the selected cohort, recorded opening family, or lens.
These samples do not estimate an individual player’s encounter rate.

A **recurring** board occurs in at least two games. A **transposing** board has at
least two distinct acyclic arrival prefixes. Each game contributes its earliest
eligible visit to a board. Repetition prefixes contribute to frequency but do not
increase the acyclic route count.

**Alternative-route share** reports the proportion of acyclic position games
outside the leading arrival route. A board reached through eight routes may still
have almost all games following one route. Compare frequency, route count, and
route balance together. The route cards use all position games as their denominator;
the alternative-route metric uses acyclic games and labels that distinction.

**Coverage** is the union of games encountering one or more selected positions.
Adding frequencies would count overlapping games repeatedly. The coverage curve
uses the existing frequency ranking, with the number of additional games supplied
by each next board. It does not optimize a curriculum or establish learning benefits.

## Public fianchetto lenses

Choose a public lens in the opening-family selector. These lenses use played moves
within the first 20 plies, independent of recorded opening labels:

| Lens | Required moves, in addition to first White move d4 |
|---|---|
| 1.d4 with g3 | White plays g2g3 |
| Catalan-style fianchetto | White plays c2c4, g2g3, f1g2; Black plays e7e6 and d7d5 |
| King's Indian fianchetto | White plays c2c4, g2g3, f1g2; Black plays g8f6, g7g6, f8g7 and d7d6 |

These are versioned move-sequence facets, not exhaustive opening classifications.
Their denominators count only matching games. The explorer includes positions
before g3 as well as after it; the board detail reports how many arrivals have
already played g3. A possible next g3 move is a separate observed continuation.
No personal repertoire or account history contributes to these views.

## Opening labels and route comparisons

Family and ECO labels describe recorded games, sometimes using moves played after
the selected board. The detail panel counts all known families and ECO codes;
the five displayed family/ECO combinations are examples, not the complete list.
Unknown-family games are reported separately. Shared labels can reflect taxonomy
choices and are not evidence of strategic equivalence.

The route diagram joins the top three acyclic arrival orders at the displayed
board. Other acyclic arrivals and repetition-prefix games are counted separately.
The canonical key keeps pieces, side to move, castling rights, and legal en passant.
It does not merge boards with different legal rights, and it does not retain the
same draw-counter or repetition-history context for every contributing game.

<span id="getting-more-games"></span>
## Sources, provenance, and limits

The checked corpus has 1,042,346 selected games: 240,086 in the curated November
2025 Elite reference and 802,260 across nine ordered first-day public archive
prefixes. Both-player ratings, minimum game length, marked bots and time-control
exclusions are documented in the [learning guide](TRANSPOSITION_LEARNING.md#getting-more-games).
Full source files and derived visits remain local. Published reports bind their
source snapshot, configuration, implementation, and verification hashes.

The charts use a bounded White opening window. The depth comparison covers all
openings in both cohorts, regardless of the explorer’s family or lens filter.
The scatter shows only published ranked positions. Observed continuations are
choices, not recommendations; neither frequency nor outcomes establish move quality.

See [Metrics & data](METRICS.md#opening-position-metrics), the
[versioned contract](../contracts/opening_positions.json), the
[checked report](https://github.com/jfk-ssa/chess-analytics-lab/blob/c1e3040a3c9542626a3b8cb78e1e7475ea8bcdab/reports/opening-positions.json), and
[publication evidence](../reports/opening-positions-checkpoint.json).

## Learning comes next

The separate [Opening learning](TRANSPOSITION_LEARNING.md) page contains the
illustrative board, research rationale, lesson and drill design, and evaluation
proposal. Strategic lesson authoring, a learning experiment, public outcome
aggregation, and engine review remain separate extensions.

## Compare a local export

[Analyze games](GAME_IMPORT.md) compares selected White games from local
Chess.com/Lichess PGNs with these published study boards. The personal denominator
includes short games by default and stays separate from the public cohorts.
