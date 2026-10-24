# 0106. Clock-band game sample

- Status: accepted on merge
- Date: 2026-10-24

## Motivation

A clock band on the hosted page counted evaluable moves, then opened a
table of slices. A slice is a rating band, a time control, and a phase.
The page said so, and the bars were still easy to read as games. The
band is seconds left on the clock before the move. Time control is a
sidebar filter, not the band.

[ADR 0101](0101-hosted-bi-cube.md) kept the cube at aggregate grain and
forbade a game list: a full game table would miss the 10 MB budget and
would republish identifiers the public extract refuses. The drill still
needs to open games.

## Decision

`clock_game` rows live in `data/public/dashboard_cube.parquet`. One row
is one game, one mover color, and one clock band. The bar still counts
evaluable moves. The list is games that have at least one eligible move
in that band: a previous same-player clock, zero increment, a finished
non-bot game, and a rating for that color. An eligible move is not the
same as an evaluable move. The caption says which is which.

The sample is the same mod-20 game-id hash `fact_move` uses, taken from
the first 100,000 complete games of the pinned August 2026 prefix
(`reports/M3-source-manifest.json`, compressed prefix SHA-256
`c3bde12f35297b50b31199e87baade846044b88ae48bf0800a1c423acd3347dc`).
`scripts/build_clock_games.py` reads a local prefix or a `fact_move`
warehouse. It does not download. The warehouse path does not apply the
hash again, because `fact_move` is already that sample.

Each cell is a clock band, a time control, a rating band, and a color.
The cell keeps at most six games, from the six opening families with
the most qualifying games in that cell. Ties on the family count break
on the family name. Inside a family, and again when the page orders the
list, the key is the SHA-256 of the Lichess id. The lower digest wins.
The page shows at most twelve matching games, the twelve with the lowest
digest, not the twelve lowest id strings. The list names the mover side:
White, Black, or Both when each color had a move in the band. Color,
rating, time control, and opening apply to the list. The date window follows the bars, including the August
fallback when the selected range does not contain that day. Sidebar
choices still come from the aggregate grains, so the sample does not
add filters.

Published fields are the ones already on the public PGN header, and not
the ones the extract still refuses:

- `lichess_id`, the eight-character site id. The page links to
  `https://lichess.org/{id}`.
- `white_rating` and `black_rating`. The table headers are White and
  Black. Names are not stored.
- `result`, `time_control`, `opening_line`, `opening_family`, `eco`,
  and the game date.

`games` and `moves` stay null on these rows. The ten-game floor still
applies to every stored count. Player names, `player_key`,
`headers_json`, and fingerprints stay out. This supersedes the ADR 0101
statement that there is no game list. It does not change the aggregate
grains or the live-eval extract.

`build_dashboard_cube.py` replaces the file and drops `clock_game`.
Run `build_clock_games.py` after it. `build_warehouse_cube.py` keeps
`clock_game`, because that grain is not a warehouse aggregate.

## Measurement

`scripts/build_clock_games.py --pgn` on the pinned prefix printed:

| | Bytes | Rows |
|---|---:|---:|
| Before | 569,634 | 34,084 |
| After | 593,637 | 35,100 |

The added grain is 1,016 rows and 409 distinct games. By band, the rows
are under 10s 234, 10–29s 258, 30–59s 243, and 60s+ 281. Distinct games
in those bands are 191, 202, 183, and 168. The file is under the 10 MB
budget. All 409 ids pass the mod-20 check. No opening family and no
time control appears only on `clock_game`. `game_cell` still covers
1,009,445 games. The full-range KPI strip is unchanged: 1,009,445 games,
White win rate 49.2%, draw rate 5.1%, loss rate 45.7%, clock error
2,128 / 22,978, rating diff +0.1, game length 72.8 ply.

## Consequences

A rare opening inside a cell can be absent from the list. The caption
names the August prefix, the six-opening cell rule, and the SHA-256
order of the rows on the page. Rebuilding
from the prefix needs the local 40 MB archive prefix; the script does
not fetch it. A later `fact_move` warehouse can refresh the same grain
with `build_clock_games.py --warehouse`.
