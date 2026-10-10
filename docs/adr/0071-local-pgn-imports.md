# 0071. Analyze exported games locally in a bounded browser worker

- Status: accepted
- Date: 2026-10-10

The owner requested local-game capability as the second reviewed, unmerged PR,
based on the public-insights PR. Username/API downloads are dropped for now.
Use exported UTF-8 Chess.com/Lichess or generic PGN files, not account credentials
or live game collection. Development uses authored fixtures only.

A pinned, license-preserved chess.js 1.4.0 module replays whole Standard mainlines
inside a worker. Legal canonical FEN keys match independent Python normalization
and checked public reference IDs. Keep the historical corpus normalizer untouched.
Comments/variations/NAGs do not create visits. Reject unsupported variants/setup,
unfinished/conflicting results and illegal mainlines with visible dispositions.

Provider/native identities and generic semantic fallbacks distinguish file hashes
from game identity. Annotation duplicates count once. Any conflicting same-ID copy
withholds all versions. Optional metadata comes from the first equivalent copy.
Choose a player explicitly per provider; do not automatically link platform names.
The personal denominator includes all selected valid completed White games after
filters, including short games. The minimum-20-ply comparison is a labeled option.

Publish a bounded reference subset in the static page. Coverage counts a union,
and route departures stop at published-example endpoints. A later canonical hit
is convergence, not move-quality evidence. Unknown in the selected set is not
unknown in the corpus. No engine work, account acquisition or outcomes inference.

Enforce 20 files, 10 MiB, 5,000 framed games, 1,000 plies/game, 32 variation levels
and a 60-second worker deadline. A cap violation rejects the session. Failed
framing admits no partial file; legal failures reject individual records. Clearing,
cancellation, reload and deadline expiry terminate the worker. No persistence or
runtime connection; import-page CSP blocks connections. An explicit summary
export includes aliases, filters and source hashes but no raw PGNs/comments.

Offline CI runs Node 24 unit tests and Python/browser parity. Performance evidence
uses 100/1,000/5,000 authored 20-ply games; it cannot establish device/long-game
performance. Browser interaction checks complement pure logic tests. Independent
reviewer approval, physical devices and screen-reader validation are separate.
