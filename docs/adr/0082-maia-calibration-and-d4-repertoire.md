# 0082. Maia calibration limit and the 1.d4 reply view

- Status: proposed, accepted on merge
- Date: 2026-10-17

## Motivation

ADR 0081 added `predict_human_moves` and left two questions open. Is the
distribution trustworthy on games the model did not train on, and which
replies to White's 1.d4 should a player prepare for at a given rating? This
record answers those with the data this checkout actually has. It does not
change the pinned Maia-3 commit, the weights hashes, or the evidence-ID rule.

## Decision

Maia-3 trained on Lichess blitz from January 2023 through July 2025, so a
calibration set has to start in August 2025. The checked opening-corpus
report lists every training source inside that window:

| Period | Cohort | Games | Dates in the report |
|---|---|---:|---|
| 2025-11 | elite_reference | 240,086 | 2025-11-01 to 2025-11-30 |
| 2025-12 | rated_public | 89,878 | 2025-12-01 only |
| 2026-01 | rated_public | 90,161 | 2026-01-01 only |
| 2026-02 | rated_public | 89,181 | 2026-02-01 only |
| 2026-03 | rated_public | 89,404 | 2026-03-01 only |
| 2026-04 | rated_public | 88,747 | 2026-04-01 only |
| 2026-05 | rated_public | 88,119 | 2026-05-01 only |
| 2026-06 | rated_public | 89,061 | 2026-06-01 only |
| 2026-07 | rated_public | 88,869 | 2026-07-01 only |
| 2026-08 | rated_public | 88,840 | 2026-08-01 only |

That is 1,042,346 games, the whole training index. There is no August,
September, or October 2025 slice. The 2013-01 foundation source is not in
the training index. The DuckDB game index and the PGNs it points at are not
in this checkout (`/data/*` is gitignored and the paths are absent), so no
log-loss, top-1, top-3, or reliability figure was computed on those games.
`calibration_report` returns `opening_index_absent` unless the caller passes
rows that were actually extracted. Those rows are a game index, not a
metrics snapshot. A later run that has the files must also keep Lichess
blitz only: estimated time is base plus 40 times the increment, and blitz
is 180 up to 480 seconds. The November elite month excludes bullet and is
not a blitz sample.

`maia_v1` freezes four calls and compares displayed probabilities with
absolute tolerance `1e-4`. Thread and batch noise is about 1e-6, which is
under one displayed digit. The reference platform is `linux-x86_64`, torch
`2.14.1+cpu`, float32, one thread, alias `23M`. A missing config, a missing
`maia` extra, or any other platform skips. Tests do not download weights.
The frozen calls are the start position at 1500 and Black to move after
1.d4 at 1200, 1500, and 1800. On that machine the top reply to 1.d4 was d5
at 0.5485, 0.4910, and 0.4239. At 1500 the next replies were Nf6 0.1404,
e6 0.0943, and e5 0.0881.

The repertoire view calls the existing checked tool three times, once per
rating, with both players at that rating and the move list `d2d4`. It
copies `model_estimate_not_observation` and `blitz_trained_rating_scale`
onto the view. It does not add a planner tool and it does not merge corpus
counts into the probabilities.

## Impact

Offline tests cover the comparison math, the month inventory, the blitz
window, the skip gate, and the 1.d4 view against the fake distribution.
The weight comparison runs only when `config/maia.json` and the `maia`
extra are both present, and only on `linux-x86_64`. The historical planner
prompt is unchanged. No corpus accuracy claim is made.

## Implementation steps

1. Read `reports/opening-corpus.json` and keep training sources whose period is `2025-08` or later. Record the game counts. Leave `measured` false when the index file is absent.
2. Score played-move rows with log-loss and top-1/top-3, and score predicted-versus-observed pairs in ten probability bins. Test that math on synthetic rows.
3. Freeze `evals/cases/maia_v1.json` and `evals/references/maia_v1.json`. Compare with tolerance `1e-4`. Skip without config, without the extra, or on an unmeasured platform.
4. Build the 1.d4 view by calling `predict_human_moves`. Keep the existing caveats.

## Risks

A reader can treat the reply probabilities as counts of games. The caveats
say not to. The corpus months are held out from Maia-3's training window,
and this checkout still has not scored the model on them. Elite is a
different population from Lichess blitz. Apple Silicon numerics remain
unmeasured, so that platform does not pass or fail `maia_v1`. The pinned
internals can still move; this record does not repin them.
