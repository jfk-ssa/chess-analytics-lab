# Memo 1 — Opening score in one observed cohort

**Question.** How did Black's score rate compare for Sicilian Defense and French Defense
among players rated 1400–1599 at exactly 60+0?

**Method.** Use completed non-marked-bot games in analytical snapshot
`84a38a404815ed2729917d76`. Score is wins plus half draws, divided by player-games.
For a descriptive adjustment, restrict to games with opponent ratings, split
player-minus-opponent rating into below −100, −100 to 99, and 100+ strata, then
weight both openings by the same pooled stratum distribution. The interval is a
seeded 400-repetition focal-player cluster bootstrap over this observed cohort.

**Result.** Sicilian Defense: 153 wins, 8 draws,
163 losses in 324 games;
score rate 48.5%. French Defense:
114 wins, 8 draws,
117 losses in 239 games;
score rate 49.4%. Adjusted score rates are
48.0% (bootstrap interval
42.1%–53.3%)
and 50.3% (interval
44.7%–56.1%), respectively.
All three rating-difference strata are represented; 563
player-games entered the common-weight comparison.

**Interpretation.** These differences are small relative to within-prefix
uncertainty. They do not show that choosing either opening changes outcomes.
The ordered archive prefix covers only 2026-08-01, opening labels are source
tags, and player experience/opponent behavior may confound the comparison.
Bootstrap intervals reflect player clustering within this prefix, not uncertainty
from sampling the whole month. Opponent dependence remains unmodeled.

**What would change the conclusion.** A broader date sample, repeated-player
coverage, stronger controls for opponent and position, and stable results across
time controls would be needed before a general claim.

Reproduce: `PYTHONPATH=. .venv/bin/python scripts/build_m4_report.py`.
Exact inputs: [M4 figures](../reports/M4-figures.json).
