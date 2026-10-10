# 0007. M3 partial corpus and exploratory analytics

- Status: accepted
- Date: 2026-10-03

The newer complete monthly archive is too large for a low-cost personal build.
Use a fixed 40 MB compressed byte prefix of the August 2026 Lichess standard
rated archive, pinned by SHA256, then retain at most 100,000 complete PGNs.
Verify the server's partial-content response for a fresh download; a local
cache must match the pinned prefix hash. Do not equate that hash with a
publisher checksum of the full archive. Label every result partial and report
the observed UTC date range; the first 100,000 complete games cover only
August 1. No monthly extrapolation or random-sample inference is valid.

Reuse the M1 legal replay, normalized facts and publication checks. Give the
bounded source its own M1 snapshot, and publish move annotations in a separate
immutable analytical snapshot. A game-ID hash selects roughly 5% of accepted
games for move replay independent of clock/evaluation annotation presence.
Retain selected zero-ply games in the sample count even though they have no
move rows. Source Opening tags define opening families; do not invent an ECO
classifier. Version the opening, player-score, move-table and clock contracts.

Clock-before means the player's previous own recorded clock in zero-increment
games. Count a >=200 cp mover-perspective evaluation deterioration as an
exploratory error proxy only when both adjacent source evaluations are
centipawn values. Missing and mate evaluations are separate coverage losses.
This is not an official engine-quality classification or causal time-pressure
effect. The observed low evaluation coverage must accompany any rate.

Raw-PGN reference code independently tallies key opening and clock results.
Keep 12 draft development cases tied to the published analytical ID, including
questions that should be clarified or declined. They are input/rubric fixtures,
not model evaluations. No live provider or personal spending setup is needed
for M3; M5/M6 safeguards remain required before live calls.
