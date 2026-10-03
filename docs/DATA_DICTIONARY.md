# Data dictionary — M1, contract 1.0.0

The explicit storage types are in contracts/tables.json.

- **fact_game:** one provider/game ID. Source ordinal is one-based within the
  uncompressed export. Original headers are JSON text. Result is 1-0, 0-1,
  1/2-1/2, or unknown (*). Standard/rated eligibility is checked during ingestion;
  source-marked bots are retained for visible metric exclusion. Fingerprint covers
  the trimmed source record, including annotations. Move count is validated by
  legal replay; no move table is persisted yet.
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
lineage, full operational metrics and move/evaluation tables are later milestones.
