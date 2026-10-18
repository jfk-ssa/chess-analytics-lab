# 0084. Maia corpus calibration results

- Status: accepted on merge
- Date: 2026-10-17

## Motivation

[ADR 0083](0083-maia-corpus-calibration-plan.md) planned the Maia-3 corpus
calibration and committed no measured scores. Both runs are now done on
John's Mac. John approved committing the numbers in this record. That
approval supersedes only the sentence in ADR 0083 that no measured corpus
score is committed. The JSON and Markdown reports stay gitignored
(`reports/maia-corpus-calibration-*`).

## Decision

1. The public blitz result is the headline. The elite result is a labeled
   secondary result on a curated 2300+ month.
2. The paper's 55–57% top-1 range stays context only. Public top-1 is 51.1%.
   Elite top-1 is 60.3%. That range is not a pass/fail gate for either
   population.
3. Keep the default `--read-timeout` of 600 s. A batch needs well under 1 s
   of actual time.
4. `maia_v1` still skips on Darwin with `platform_unmeasured`. The reference
   platform stays `linux-x86_64`. These Mac numbers leave Linux parity
   unmeasured.
5. The figures of record for games passing `lichess_blitz` are 38,323
   (public) and 236,282 (elite). Those counts apply this repository's rated
   and eligibility filters. Earlier pre-run unfiltered counts, 38,565 and
   262,257, may appear in discussion. The filtered counts replace them.

Populations are never pooled.

## Results

Both runs used the same machine and the same checkpoint.

- Machine: Apple Silicon, `darwin-arm64`
- Torch: 2.14.1
- Device, dtype, threads: CPU, float32, 1
- Alias: `23M`
- Weights SHA-256: `bce6cd1af5f0399ac7eed33fabb7a6a2ef6193662c2740f262bf93af7bfb3569`
- Code commit: `1e13597c42d4858b7cfd7cfdae01e297263364b2`
- Seed: `20251017`
- Plies: first 12
- Interval: 400-repetition game-cluster bootstrap (percentile 95%)

### Public blitz

`public_2026_08_blitz`. Ordered 2026-08-01 prefix. File
`data/analytical/complete-2026-08-first-100000.pgn`. Blitz filter on.

| Count | Value |
|---|---:|
| Games seen | 100,000 |
| Eligible and passing `lichess_blitz` | 38,323 |
| Sampled | 20,000 |
| Positions | 238,457 |
| Zero played probability | 0 (0.0%) |

| Score | Estimate | 95% interval |
|---|---:|---|
| log-loss | 1.4828 | 1.4766–1.4887 |
| top-1 | 0.5110 | 0.5088–0.5129 |
| top-3 | 0.8030 | 0.8011–0.8047 |

Top-1 and log-loss by the mover's rating band. A game is counted in each
band that contains one of its movers, so the game column does not sum to
20,000. The 2300+ band is 4,722 positions.

| Band | Games | Top-1 | Log-loss |
|---|---:|---:|---:|
| below-1000 | 1,503 | 0.4594 | 1.7511 |
| 1000–1599 | 9,034 | 0.4988 | 1.5431 |
| 1600–1999 | 8,546 | 0.5189 | 1.4381 |
| 2000–2299 | 2,964 | 0.5417 | 1.3271 |
| 2300+ | 488 | 0.5817 | 1.2198 |

By ply, top-1 is 0.598 at ply 1. Ply 2 is the hardest at 0.410. Plies 4–12
sit between about 0.48 and 0.53.

Maia scoring time was 2,009.8 s, about 8.4 ms/position. Wall time was
37 min 04 s, including the PGN scan.

### Elite month

`elite_2025_11`. November 2025 curated month. File
`data/opening-sources/elite/lichess_elite_2025-11.pgn`. Blitz filter off, so
the headline covers all time controls.

| Count | Value |
|---|---:|
| Games seen | 280,246 |
| Eligible | 243,667 |
| Passing `lichess_blitz` | 236,282 |
| Sampled | 20,000 |
| Sampled and passing `lichess_blitz` | 19,399 (97%) |
| Positions | 239,688 |
| Zero played probability | 0 (0.0%) |

| Score | Estimate | 95% interval |
|---|---:|---|
| log-loss | 1.1163 | 1.1115–1.1212 |
| top-1 | 0.6027 | 0.6007–0.6047 |
| top-3 | 0.8903 | 0.8890–0.8917 |

The only populated rating band is 2300+. All games in this file are elite
by construction.

By ply, top-1 is 0.446 at ply 1, where elite first moves vary. Ply 2 is
0.419, ply 3 is 0.631, and ply 6 is 0.646.

Maia scoring time was 2,223 s, about 9.3 ms/position. Wall time was about
43.5 min.

### Calibration

Each bin is a range of predicted probability. Predicted is the mean model
probability of the legal moves in that bin. Observed is the share of those
moves that were played.

Public:

| Bin | Predicted | Observed |
|---|---:|---:|
| 0.0–0.1 | 0.008 | 0.008 |
| 0.1–0.2 | 0.142 | 0.143 |
| 0.2–0.3 | 0.246 | 0.246 |
| 0.3–0.4 | 0.345 | 0.341 |
| 0.4–0.5 | 0.448 | 0.438 |
| 0.5–0.6 | 0.550 | 0.534 |
| 0.6–0.7 | 0.643 | 0.628 |
| 0.7–0.8 | 0.748 | 0.738 |
| 0.8–0.9 | 0.850 | 0.849 |
| 0.9–1.0 | 0.952 | 0.948 |

Elite:

| Bin | Predicted | Observed |
|---|---:|---:|
| 0.0–0.1 | 0.005 | 0.005 |
| 0.1–0.2 | 0.142 | 0.142 |
| 0.2–0.3 | 0.247 | 0.245 |
| 0.3–0.4 | 0.351 | 0.343 |
| 0.4–0.5 | 0.453 | 0.445 |
| 0.5–0.6 | 0.545 | 0.546 |
| 0.6–0.7 | 0.651 | 0.648 |
| 0.7–0.8 | 0.751 | 0.755 |
| 0.8–0.9 | 0.849 | 0.844 |
| 0.9–1.0 | 0.957 | 0.958 |

The model is well calibrated on both populations. The largest public gap is
about 1.6 points, with the model slightly overconfident between 0.4 and 0.7.
The largest elite gap is about 0.8 points.

## Caveats

The public sample is one day, the 2026-08-01 prefix, not a month. Games
within a day are not independent draws from all players. The intervals
resample games within the sample. They do not capture month-to-month
variation.

The elite file is a curated month and 2300+ only. Maia was trained on
Lichess blitz, so the public blitz population is the favourable case.

Both runs are the same machine. They leave `maia_v1` unchanged.

The weights licence is still open. This record does not resolve it. See
[MAIA](../MAIA.md#licence).

Populations are not pooled.

## Consequences

Readers cite the public blitz headline and the labeled elite result from
this record. The gitignored report files remain local artifacts. ADR 0083
keeps the sample rule and the reproduction commands. `--read-timeout` stays
600 s. `maia_v1` stays skipped on Darwin with `platform_unmeasured`.
