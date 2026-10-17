# 0083. Maia corpus calibration plan

- Status: proposed, accepted on merge
- Date: 2026-10-17

## Motivation

`predict_human_moves` returns a rating-conditioned distribution, and ADR 0082
left the scoring functions without a caller. No played-move log-loss has been
computed. This record is the measurement plan John asked to review before any
of that is built. It does not add code, download games, or change the pinned
Maia-3 commit, the weight hashes, or `maia_v1`.

The question is how often Maia-3 puts probability on the move that was played,
on two populations that sit after the model's July 2025 blitz training window,
reported separately.

## Decision

Measure alias `23M` on two populations. Do not pool them.

1. The local November 2025 elite file already on John's Mac. The original PGN
   is `data/opening-sources/elite/lichess_elite_2025-11.pgn`. The opening
   corpus reads the adapted copy `data/elite/elite-2025-11-compatible.pgn`
   (adapter `elite-lichessurl-to-site-v1`). The receipt records 280,246 games
   in the original file, 278,481 rated accepted, and 1,765 unrated excluded.
   The training-index count of 240,086 is the completed games of at least 20
   plies in that month, not the length of the PGN. Dates in the receipt are
   2025-11-01 through 2025-11-30. Do not download this file again.
2. One public Lichess standard-rated prefix: August 2026, the first
   40,000,000 compressed bytes already pinned in `config/datasets.json`.
   Download it only after John approves. If that prefix is already on disk
   and the SHA-256 matches, `acquire` verifies the cache and does not
   download.

The public sample keeps Lichess blitz only, using `lichess_blitz`: estimated
time is base plus 40 times the increment, and blitz is 180 up to but not
including 480 seconds. `TimeControl` is parsed as `base+increment` by the
existing ingest. The elite receipt has no time-control split, and
[DATA_SOURCES](../DATA_SOURCES.md) records that file as having no clock
annotations. The elite headline is the curated month (publisher selection
2500+ versus 2300+, standard, excluding bullet). The implementation may count
how many elite games would pass `lichess_blitz` when a `TimeControl` header
is present. That count is a labeled subset. It does not replace the headline
and it is not pooled with the public sample.

For each selected game, score the first 12 plies, or fewer when the game is
shorter. Each query uses the mover's rating as `rating_self`, the opponent's
rating as `rating_opp`, and the UCI prefix so far. The adapter already keeps
the current board and at most seven earlier boards (`series[-8:]` in
`maia.py`). That is the 8-board history this plan means. Ratings stay on the
existing 0–5000 clamp. Record the played move's probability and its rank.
Rank is 1 plus the number of legal moves with a strictly higher probability.
Tied probabilities share a rank.

Score with the existing `score_played` and `reliability` helpers.
`score_played` is natural-log loss plus top-1 and top-3 rates. It rejects a
played probability that is not finite and positive, so the corpus caller
does not pass those rows into it. A played move the model scores at zero
counts as a top-1 miss and a top-3 miss, and stays out of log-loss only.
The report records `zero_probability_count` and `zero_probability_share`.
A share above 1% is a warning on stderr. `reliability` bins a predicted probability
against an observed frequency. Feeding it only the played move would make
every observation 1. The batch extractor therefore keeps every legal move's
probability, and each legal move is one reliability row: predicted is the
model probability, observed is 1 when that move was played and 0 otherwise.
The checked tool's display `top_k` is not the reliability input.

`predict_human_moves` starts one worker process per call, one position, with
a 30-second kill. Twenty thousand games times 12 plies is on the order of
240,000 process starts per population. That is the wrong loop for this
sample. `python -m chess_analytics.analyst.maia_corpus` loads the pinned
checkpoint once and scores many positions under the same CPU, float32, and
hash rules. Each forward pass is still one position.

The report gives log-loss, top-1, and top-3, each with the position count,
the game count, and a 95% interval. The interval is a percentile bootstrap
that resamples games and keeps every scored ply of a drawn game, 400
repetitions, the same repetition count the M4 focal-player bootstrap uses.
`score_played` does not compute intervals. `maia_report.py` adds them beside
that helper and renders the Markdown. It does not import torch. The same
figures are split by the mover's rating band and by ply. Bands match the opening-corpus labels already in
`reports/opening-corpus.json`: 1000–1599, 1600–1999, 2000–2299, and 2300+,
plus a below-1000 band when a mover is below 1000. A small band is reported
with its own `n`. It is not dropped and not merged into another band.

Fixed seed `20251017`, sample games without replacement, then take the prefix
of each selected game. The seed is written into the report. No extra rating
floor is applied on top of the file. "Mid-rated" in this plan means the
public prefix as distinct from the elite cohort, not a new 1200–1800 filter.

## Recommended public prefix

Use the analytical plan already in `config/datasets.json`. It is the only
public month with a committed URL, byte range, prefix SHA-256, measured
extraction size, and an acquire command.

| Item | Value |
|---|---|
| Month | 2026-08 |
| URL | `https://database.lichess.org/standard/lichess_db_standard_rated_2026-08.pgn.zst` |
| Range | bytes 0–39999999 inclusive |
| Compressed download | 40,000,000 bytes |
| Prefix SHA-256 | `c3bde12f35297b50b31199e87baade846044b88ae48bf0800a1c423acd3347dc` |
| Archive listing, not downloaded | 91,912,325 games, 30,145,862,359 bytes, listing checked 2026-10-03 |
| Extracted PGN, measured | 236,533,866 bytes, 100,000 complete games, source SHA-256 `26b999b2a346d5b42d309fa434d27f9e74ccd036e5ab5d41c7927548ff00fb7a` |
| Accepted rated games | 99,467 (533 unrated excluded) |
| Observed UTC date | 2026-08-01 only |
| Caps if a full M3 rebuild is also run | 500 MB compressed, 500 MB decompressed, 5 GB generated |

The calibration run reads the extracted PGN. It does not require `ingest`,
`moves`, or `report`. Those commands stay the M3 sequence. The prefix hash
is a range hash, not the publisher's full-archive checksum.

Rating figures the repository already has for this prefix, from
`reports/retained-rating-inventory.json`, are floors rather than bands:

| Floor | Games |
|---|---:|
| Accepted rated | 99,467 |
| Both players at least 1000 | 92,288 |
| Both players above 1000 | 92,255 |
| Opening-eligible, 1000 floor | 88,840 |
| Opening-eligible, 2000 floor | 19,968 |

There is no blitz count and no 1200–1800 count for this prefix. The clock
buckets in the M3 coverage report are move-clock proxies, not Lichess speed
classes. The `rating_bands` object in `reports/opening-corpus.json`
(1000–1599: 329,407; 1600–1999: 316,668; 2000–2299: 121,100; 2300+: 275,171)
is the whole training index of 1,042,346 games, elite included. It is not an
estimate for the August prefix.

Other retained public months (December 2025 through July 2026) are also
first-day prefixes of about 100,000 games. They are not the `datasets.json`
command. September and October 2025 are not in the corpus. A larger August
range would be a new pin, not a change to `corpus acquire`.

## Open decisions

John can change any of these before the implementation pull request. The
recommendation is the row this plan will follow if he does not.

| Decision | Recommendation | Why |
|---|---|---|
| Sample size | About 20,000 games per population, after the public blitz filter. If the filtered population is smaller, score all of it and set `sample_target_met` false. | Matches the approved scope. The August prefix cannot be assumed to contain 20,000 blitz games. |
| Plies | First 12 plies, with the adapter's current board plus at most seven earlier boards. | Matches the approved scope. Ply 12 is still an opening position. Later plies are a different question. |
| Public month | 2026-08, the pinned 40,000,000-byte prefix above. | Only month with a URL, range, hash, measured size, and command. Still after July 2025. Download only after approval. |

## Report file

Each run writes one JSON file and one Markdown file for one population.
There is no `populations` list and no pooled score. Both paths are
gitignored (`/reports/maia-corpus-calibration-*`):

- `reports/maia-corpus-calibration-elite.json` and `.md`
- `reports/maia-corpus-calibration-public.json` and `.md`

No measured corpus score is committed. `null` below means no positions were
scored. The public file is the example. The elite file uses the same keys,
with `id` `elite_2025_11`, `blitz_filter` false, and without the one-day
caveat.

```json
{
  "kind": "maia_corpus_calibration",
  "measured": false,
  "reason": "no_eligible_games",
  "seed": 20251017,
  "plies": 12,
  "sample_target_games": 20000,
  "model": {
    "alias": "23M",
    "weights_sha256": "bce6cd1af5f0399ac7eed33fabb7a6a2ef6193662c2740f262bf93af7bfb3569",
    "weights_bytes": 91799307,
    "code_commit": "1e13597c42d4858b7cfd7cfdae01e297263364b2",
    "device": "cpu",
    "dtype": "float32",
    "threads": 1,
    "platform": null
  },
  "bootstrap": {
    "repetitions": 400,
    "unit": "game",
    "interval": "percentile_95"
  },
  "population": {
    "id": "public_2026_08_blitz",
    "source_file": "data/analytical/complete-2026-08-first-100000.pgn",
    "blitz_filter": true,
    "sample_target_met": false,
    "n_games": 0,
    "n_positions": 0,
    "zero_probability_count": 0,
    "zero_probability_share": null,
    "log_loss": null,
    "log_loss_interval": null,
    "top1": null,
    "top1_interval": null,
    "top3": null,
    "top3_interval": null,
    "by_rating_band": [],
    "by_ply": [],
    "reliability": []
  },
  "paper_top1_context": {
    "range": [0.55, 0.57],
    "role": "context_only",
    "pass_fail": false
  },
  "caveats": [
    "elite_high_rated_curated_month",
    "months_are_after_the_training_window_not_a_designed_sample",
    "platform_unmeasured_outside_linux_x86_64",
    "same_machine_only",
    "populations_not_pooled",
    "public_sample_is_the_2026-08-01_prefix"
  ]
}
```

Each `by_rating_band` and `by_ply` entry carries `n_games`, `n_positions`,
the three scores, and the three intervals. The Markdown tables for those
splits print the intervals too. `reliability` entries are the ten bins from
the existing helper: `low`, `high`, `count`, `mean_predicted`,
`mean_observed`. A played probability of zero increments
`zero_probability_count` and counts as a top-1 and top-3 miss. It is not a
log-loss row. The public Markdown also says the sample is the ordered
2026-08-01 prefix, not a full month.

## Reproduction commands

Weights, from the repository root. The file is 91,799,307 bytes. The script
checks the SHA-256 and refuses any other bytes. It does not run on import,
in tests, or in CI.

```sh
uv sync --locked --extra maia --extra dbt
uv run --locked --no-editable python scripts/fetch_maia_weights.py \
  --alias 23M --dest data/models --write-config
```

`--write-config` writes `config/maia.json`. It refuses to overwrite that file
unless `--force` is set, and it checks that before downloading. The JSON
document is on stdout. The install hint and the do-not-commit line are on
stderr. The hint is `uv sync --locked --extra maia --extra dbt`.

Public prefix, already approved with this plan. From the repository root:

```sh
uv run --locked --no-editable python -m chess_analytics.corpus acquire
uv run --locked --no-editable python -m chess_analytics.corpus extract
```

`acquire` writes
`data/analytical/lichess-standard-rated-2026-08-prefix-40000000.zst` and
`data/analytical/acquisition.json`. `extract` writes
`data/analytical/complete-2026-08-first-100000.pgn`. A cached prefix with the
pinned hash is reused. These commands are manual. Nothing in import or test
collection downloads data.

Score one population per command. On macOS, prefix the scorer with
`caffeinate -i`. Elite and public can run in two terminals. Stderr prints
progress every 10 batches (done/total positions, elapsed, and an ETA after
the first batch) and a finished line.

```sh
caffeinate -i uv run --locked --no-editable python -m chess_analytics.analyst.maia_corpus \
  --pgn data/opening-sources/elite/lichess_elite_2025-11.pgn \
  --population elite \
  --json reports/maia-corpus-calibration-elite.json \
  --markdown reports/maia-corpus-calibration-elite.md
caffeinate -i uv run --locked --no-editable python -m chess_analytics.analyst.maia_corpus \
  --pgn data/analytical/complete-2026-08-first-100000.pgn \
  --population public \
  --json reports/maia-corpus-calibration-public.json \
  --markdown reports/maia-corpus-calibration-public.md
```

Smoke the public scorer before the full sample. Multiply that elapsed time
by about 200 for the 20,000-game run:

```sh
uv run --locked --no-editable python -m chess_analytics.analyst.maia_corpus \
  --pgn data/analytical/complete-2026-08-first-100000.pgn \
  --population public \
  --sample-size 100 --bootstrap 20 \
  --json /tmp/maia-corpus-smoke.json \
  --markdown /tmp/maia-corpus-smoke.md
```

## Impact

Readers can see the two files, the sample rule, the scores, and the limits
before any measurement exists. Offline tests are unchanged. The historical
planner prompt is unchanged. No corpus accuracy number is produced here.

## Implementation steps

1. Accept or amend this plan. Do not start the extractor before that.
2. On the measurement machine, install the `maia` extra and run
   `scripts/fetch_maia_weights.py` for alias `23M`.
3. After explicit approval, run `acquire` and `extract` for the pinned
   August 2026 prefix. Skip the download when the verified cache is present.
   Read the elite games from the local original PGN, using the adapted file
   when the caller needs the corpus `Site` header.
4. The batch extractor is `maia_corpus`. One process loads the checkpoint.
   It returns the played move's probability and rank, and the full legal
   distribution used by `reliability`. It does not call
   `predict_human_moves` once per ply.
5. Draw the fixed-seed sample. Keep public games inside `lichess_blitz`.
   Keep the elite headline on the curated month. Write one report object per
   population, with sample sizes, bootstrap intervals, rating-band splits,
   and ply splits. Do not add a pooled object.
6. Compare nothing to a pass/fail bar. The 55–57% top-1 range is context in
   the report file and is not a gate.

## Risks

The elite file is a high-rated curated month. The publisher selection is
2500+ versus 2300+. John asked the report to say it is mostly 2400+. This
repository has no count of games at or above 2400, so the report must not
invent one. The file is not a Lichess blitz sample.

November 2025 and 1 August 2026 are simply after the July 2025 training
window. The public file is an ordered first-day prefix, not a random month.
A result on that day does not estimate the rest of August.

Apple Silicon (`arm64` macOS) speed and numerics are unmeasured. `maia_v1`
skips there with `platform_unmeasured` because the frozen reference platform
is `linux-x86_64`. A calibration run on John's Mac is a same-machine result.
It does not update `evals/references/maia_v1.json`, and it is not comparable
bit for bit with the Linux reference. How long the batch extractor takes on
that machine is unknown until it is run.

The paper's 55–57% top-1 figure is not stored in this repository. It is
context only. Missing it is not a failed check.

The number of blitz games inside the 40 MB prefix is unknown. Twenty thousand
blitz games may not be there. The plan does not enlarge the download to find
out. The M3 source manifest records 342 marked bots on this prefix. The
sample drops those games. It does not also require the training index's
20-ply minimum or the both-players-at-least-1000 floor. Shorter games
contribute the plies they have, and rating bands are reported instead of
applying another floor.

The model's own `cfg.history` length lives in the pinned Maia code. The
worker already truncates to it. This plan does not restate that length.
