# 0105. KPI deltas on the hosted strip

- Status: accepted on merge
- Date: 2026-10-24

## Motivation

The hosted strip lists games, win rate, draw rate, loss rate, clock
error, published positions, rating diff, and game length. The only
delta was `+N vs prior` on the published-month Games card. That path
is skipped once `game_cell` is present
([ADR 0101](0101-hosted-bi-cube.md)). The committed cube has
`game_cell`, so the page showed no change versus a prior window.

## Decision

The KPI comparison does not change the cube schema and does not require
a rebuild. The published file's byte size and row count after the
clock-game sample are in [ADR 0106](0106-clock-band-game-sample.md).
`game_cell` still covers 1,009,445 games.

The strip order is Games, Win rate, Loss rate, Draw rate, Positions,
Rating diff, Game length, Clock error. From 600px of strip width that is
two rows of four equal cards, so Positions sits directly under Games.
A 1024px window with the sidebar open
leaves about 622px of strip, so it is four columns. Below 600px,
including a 390px page, it is two equal cards per row in the same
order. The other card rows keep the 256px track.

The date range selects the periods that sit fully inside it, the same
rule the card value already uses. The delta compares that block with
the immediately preceding block of the same number of periods. Time
control, color, rating band, and opening family apply to both blocks.
Both blocks have to be contiguous `YYYY-MM` periods, the prior block
has to end the month before the current block starts, and every period
in both blocks has to share one cohort and one span length. A missing
block, a gap, a mixed block, or a different kind of period leaves the
detail as it was. The card does not print zero, and it does not print
`no prior period`, for that case.

That is the equal-length comparison this grain can support. There is
no daily series inside a prefix. A shift of the filter by the same
number of calendar days does not. June 1 through August 1 is 62 days
and contains the three rated-public prefix days `2026-06`, `2026-07`,
and `2026-08` (256,031 games). The preceding 62 days, March 31 through
May 31, contain only April 1 and May 1, because March 1 sits outside
that window. Comparing three prefix days with two would mostly measure
how many prefixes the window happened to catch. The page compares
those three days with March, April, and May (255,941 games), which is
`+90 vs prior`.

November is the elite month, 2025-11-01 through 2025-11-30. December
through August are one-day rated-public prefixes. December does not
compare with November. The full range mixes those two kinds of period,
so it shows no delta. A filter that matches nothing stays on
`no cells for this cut` and does not gain a delta. A card that had to
ignore the date range does not gain one either.

Counts are the integer difference, `+N vs prior`. Rates are the
difference of the one-decimal percentages the card already shows,
`+N pp vs prior`, so the text reconciles with the two displayed rates.
Means are the difference of the one-decimal means. The clause is
appended after ` · `, which is where the card detail is allowed to
break.

Clock error is the August `clock_slice` snapshot, period `2026-08-01`.
Published positions are one span per cohort. Neither is a month
series, so those cards do not show a delta.

On 2026-06-01 through 2026-08-01, with the other filters open, the
White result cells move from 49.8% / 3.7% / 46.5% to 49.5% / 3.7% /
46.8% (`-0.3 pp`, `+0.0 pp`, `+0.3 pp`). Rating diff moves from +0.2
to +0.3 (`+0.1 vs prior`). Game length moves from 69.3 to 69.5 ply
(`+0.2 vs prior`). `60+0` games move by `+7,303`. Black French Defense
games move by `+430`. August 1 alone is `+194` games versus July 1.

The published-month Games card, used only when `game_cell` is absent,
still says `+N vs prior` or `no prior period`.

## Consequences

This supersedes the ADR 0101 bullet that the Games card does not
repeat a prior-period delta once `game_cell` is present. The other
ADR 0101 rules are unchanged. The 10 MB budget is untouched because
the Parquet file is untouched.
