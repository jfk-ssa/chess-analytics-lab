# Reading your local game analysis

## Export and select your games

Export plain UTF-8 PGN files from Chess.com or Lichess and choose them above.
Chess.com provides individual and bulk PGN export; Lichess also exports games in
PGN. This feature accepts files already on your device. It does not download an
account's games or connect to a provider account.
[Chess.com export instructions](https://support.chess.com/en/articles/8705305-how-do-i-get-a-pgn-of-my-game),
[Lichess game export documentation](https://lichess.org/api#tag/Games/operation/apiGamesUser).

Select the player separately for each detected provider. Case-insensitive matching
uses normalized names within that provider; identical names on two platforms are
not linked automatically. Analyze White first. Matched Black games and unmatched
players appear in selection exclusions.

## What gets counted

The default denominator includes every selected valid completed Standard White
game after your explicit filters, including games shorter than the opening window.
The minimum-20-ply option gives a separately labeled comparison population. Missing
ratings do not exclude a game. Date-filtered undated games are excluded visibly;
unknown rated status stays unknown, rather than being guessed from the platform.

The import replays the entire mainline legally, not just the first ten moves.
Comments, variations and NAGs are ignored for mainline statistics. Unsupported
variants, setup boards, unfinished games, conflicting results, malformed headers
and illegal moves receive visible dispositions. Player names are trimmed and
Unicode-normalized before the empty, `?`, and 200-character checks. A Result
header that disagrees with the result token in the move text is rejected.
Castling may be written with letter O (`O-O`, `O-O-O`) or digit 0 (`0-0`, `0-0-0`). Parsing failures import no partial
file; cap violations, cancellation and timeouts keep no partial session.

Provider/native IDs distinguish games. Annotation-only duplicate copies count once.
Conflicting versions of the same ID withhold all copies; the system does not pick
a winner. Generic PGN falls back to a documented semantic fingerprint, which cannot
resolve every missing-ID ambiguity. Framed-record counts reconcile accepted unique
games, duplicate copies, conflicting copies and rejected records; failed files
have unknown unframed counts outside that reconciliation.

## Read the comparison carefully

Personal frequencies count a game's earliest eligible visit per board at plies
6–20. Repetition-prefix arrivals do not add acyclic routes. Alternative-route share
uses acyclic position games as its denominator. Full FEN is retained locally;
recognition keys exclude draw counters and repetition history.

Study-set coverage is a **union of games**, not the sum of position frequencies.
It matches only the selected published reference boards, with their bounded route
examples. No match means “not in this selected set.” It does not establish that a
position is unknown in chess, out of theory, or a poor choice.

Route comparison finds the first move differing from the selected examples while
those examples still prescribe a continuation. Reaching an example's end stops
comparison. A later matching White decision board counts as re-entry even through
a different order. Departures do not measure mistakes or engine quality.

Your sample and the public reference cohorts have different eligibility and
sampling. Compare counts descriptively. Learning gains, causal outcome effects,
engine recommendations and Black-side reference analysis remain separate work.

## Session data and downloads

Analysis runs in a local browser worker with bounded inputs and a 60-second
processing limit. No PGN is posted to a server, sent to a model or stored in browser
persistence. Clearing or reloading terminates the session. Downloading a summary
is an explicit action; downloaded files remain on your device after clearing.
The summary includes selected aliases, filters, source hashes and derived boards/routes;
it omits raw PGNs and their comments.

The authored example contains five synthetic games. Its tests and performance
checks are fixture evidence, rather than processing results on account history.
The pinned [chess.js library](../site/assets/vendor/chess-js-provenance.json)
retains its [BSD-2-Clause license](../site/assets/vendor/LICENSE.chess-js.txt).
See [the import contract](../contracts/imported_games.json),
[public Transpositions](TRANSPOSITIONS.md), and [Metrics & data](METRICS.md).
