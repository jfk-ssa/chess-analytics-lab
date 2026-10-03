# Memo 2 — Clock pressure and evaluation coverage

**Question.** What can the source evaluations say about the >=200 cp
deterioration proxy as pre-turn clock time falls?

**Method.** Use snapshot `84a38a404815ed2729917d76`. Games are selected by
game-ID hash within the August 1 prefix, independently of annotation presence.
Only completed, non-marked-bot zero-increment games and moves after a player's
first recorded clock are eligible. The previous same-player clock defines the
pre-turn bucket. Comparable centipawn evaluations define the rate denominator;
mate transitions and missing evaluations are excluded from it. A separate
stratified table by exact time control, rating band and phase is in the figures.

| Clock before turn | Eligible | Evaluable | Coverage | Proxy errors / evaluable | Proxy rate |
|---|---:|---:|---:|---:|---:|
| under_10 | 20,978 | 1,191 | 5.7% | 230/1,191 | 19.3% |
| 10_to_29 | 41,003 | 3,183 | 7.8% | 385/3,183 | 12.1% |
| 30_to_59 | 78,167 | 6,053 | 7.7% | 470/6,053 | 7.8% |
| 60_plus | 118,217 | 12,567 | 10.6% | 1,047/12,567 | 8.3% |

**Interpretation and uncertainty.** The under-10-second bucket has the largest
observed proxy rate, but its evaluation coverage is only
5.7%. Annotation availability is
selected, moves within a game are dependent, and player strength, game phase and
position may vary by bucket. No independent-move confidence interval or causal
time-pressure effect is claimed. This is an exploratory source-evaluation proxy,
not an official Lichess blunder label. The ordered source prefix covers only
2026-08-01; no monthly estimate follows.

**What would change the conclusion.** A predeclared position sample evaluated
with one fixed engine configuration, broader dates, and sensitivity checks for
the deterioration threshold and player/game strata would reduce the main
selection and measurement concerns.

Reproduce: `PYTHONPATH=. .venv/bin/python scripts/build_m4_report.py`.
Exact inputs: [M4 figures](../reports/M4-figures.json).
