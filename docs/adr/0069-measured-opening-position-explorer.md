# 0069. Measured opening-position explorer

- Status: accepted
- Date: 2026-10-10

The owner authorized analyzing and exposing recurring/transposing positions with
opening breakdowns. Reuse the retained checked corpus rather than acquire games.
Start with White decisions after Black's moves 3–10. Keep the 240,086-game curated
Elite month and 802,260-game public prefix cohort separate.

Canonical identity uses normalized FEN's first four fields with legal en passant,
preserving turn and castling. Local visit shards retain full FEN, UCI arrival route,
source/game identities and next move. Hashes bind source bytes, checked game index,
plan, builder and artifacts. New derived outputs stay outside the original lab.
Resumable shards are checked before reuse; summary scratch tables stay outside
immutable publications. Existing frozen evaluations remain intact.

Count each game once per position and use its earliest window visit. Rank by game
frequency. Recurring requires two games; transposing requires two distinct arrival
prefixes without repeated canonical positions. Track repeated prefixes separately.
Top-10/top-20 coverage is a game union. Fixed-depth endpoint compression excludes
repetition prefixes. Recorded family/ECO labels describe games and never substitute
for exact board identity. Family-filter frequencies use family denominators.

Publish a compact checked JSON with up to twenty positions per ranking, three
route examples and five observed continuations. Provide all-opening views and up
to twelve largest eligible known families per cohort, plus complete family counts.
The static site loads JSON and generated SVG boards with accessible controls.
Publication rejects inconsistent counts, invalid legal routes and source drift.

Observed continuations are not best-move recommendations. Sampling differences,
recorded opening labels, bounded depth and first-visit counting limit inference.
No engine evaluation, model request, personalized weighting, strategic lesson
authoring or claim about improved learning is included. Deliver a reviewed branch
and PR; merge to main remains the existing Pages deployment trigger.
