# Data dictionary

**HTML version:** [Read this guide on the documentation site](https://jfk-ssa.github.io/chess-analytics-lab/metrics.html).

The explicit storage types are in contracts/tables.json.

- **fact_game:** one provider/game ID. Source ordinal is one-based within the
  uncompressed export. Original headers are JSON text. Result is 1-0, 0-1,
  1/2-1/2, or unknown (*). Standard/rated eligibility is checked during ingestion;
  source-marked bots are retained for visible metric exclusion. Fingerprint covers
  the trimmed source record, including annotations. Move count is validated by
  legal replay. M3 persists a separate sampled move table.
- **fact_player_game:** exactly two rows per accepted game (white, black). Rating
  and opponent rating are nullable values recorded at that game, not current
  ratings. Lichess uses Glicko-2 despite PGN “Elo” names. Score is 0, 0.5, 1, or null
  for unknown result. Missing/anonymous player keys stay null, never one shared ID.
- **UTC date / played_at:** date and nullable TIMESTAMPTZ with precision marker.
  Source timestamp uses UTC; missing UTC time is not imputed. Source Date headers
  remain in raw metadata but are not assumed to be UTC.
- **Time control:** original text retained, base/increment parsed only for simple
  integer base+increment. No guessed speed categories.
- **Source opening/ECO:** provider tags only. Unknown is null. No derived label.
- **Manifest:** one ingestion attempt with source/implementation/config/lock hashes,
  versions, limits, ordinal counts, rejection reasons, date coverage, missingness,
  elapsed time, artifact hashes, and status/error. Complete input SHA256 does not
  mean every input was accepted; reconciliation records exclusions/quarantine.
- **Quarantine JSONL:** source ordinal, non-overlapping disposition and primary
  reason, full original PGN. Raw archive remains the source for accepted records.

Reconciliation: seen = accepted + duplicate + excluded + quarantine + conflict.
For conflicts, the whole candidate is withheld, even though first occurrences are
present in staging. Failed framing/byte-limit runs may have only a lower-bound
scanned byte count (last yielded record); no failed run claims full reconciliation.

Source manifests/run records live in JSON during M1; warehouse dimensions, dbt
lineage and recovery records are added in M2.

M3 adds `fact_move` with the explicit types in
[m3_tables.json](../contracts/m3_tables.json): one selected provider/game ID and
ply, side to move, SAN/UCI, after-move clock and source evaluation, previous
same-player clock, and derived before/after centipawn values. Missing annotation
values stay null; mate scores are separate from centipawns. A selected zero-ply
game has no `fact_move` row but remains in the sample manifest. The M3 source
manifest and move manifest explicitly mark the archive partial and retain
source/implementation/contract hashes. Only the observed prefix, not the full
publisher archive, has a verified compressed-byte hash.


## Opening-position publication

Local visit shards retain source/provider/game identity, cohort, decision ply,
full FEN, canonical position key and SHA-derived ID, complete UCI prefix, a
repeated-position-prefix flag, next move, and recorded family/ECO. Per-position
aggregation uses a game's earliest eligible visit. The compact tracked report
publishes bounded rankings and examples; it is not the full visit database.

Each view records its game denominator, distinct/recurring/transposing board
counts, positions and frequency rankings. Each ranking includes a cumulative
union-coverage curve with covered games, share and additional games for N=1..20.
Position details retain acyclic games, leading-route games, alternative-route
share, route remainder, complete known-family/ECO breadth and unknown-family
counts. Public lenses have versioned move-sequence rules and matching-game
denominators; white_g3_played_games distinguishes arrivals before and after g3.

The report, configuration, contract, source and implementation hashes are checked
by the site builder. Local full FEN preserves draw counters; the recognition key
uses pieces, turn, castling and legal en passant only.


## Session-only imported games

Imported PGN records are held in a browser worker, separate from the immutable
public corpus. Grain: one completed legal Standard game per provider/native ID
or provider/fallback semantic identity. Fields include normalized players, date,
result, optional rated/time-control metadata, full legal UCI mainline and White
visits at plies 6–20. Each visit retains full FEN, canonical first-four-field key,
24-character SHA-derived ID, route, repetition-prefix flag and next move.

File SHA256 identifies bytes separately from semantic game identity. Equivalent
annotation copies count once; differing semantic fingerprints withhold all copies
of that identity. Explicit player selection is scoped to the provider. An exported
summary contains selected aliases, filters, source hashes and derived metrics and
routes, rather than raw PGNs/comments. Records are not persisted or published.
See [the contract](../contracts/imported_games.json) and [guide](GAME_IMPORT.md).
