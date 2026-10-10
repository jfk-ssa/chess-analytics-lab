# Data sources, limits and references

Find the public exports at the [Lichess open database](https://database.lichess.org/).
The `standard` section contains monthly standard rated PGN archives and the
publisher checksum listing. The project uses exactly the URLs, date labels,
byte limits and pinned hashes in [config/datasets.json](../config/datasets.json).
Do not substitute a newer archive when a pinned source is unavailable. Lichess
labels these game exports CC0. No broadcast data or engine binary is included.

| Tier | Where to find it | What is verified | Analytical limit |
|---|---|---|---|
| Tiny foundation fixture | [tiny.pgn](../tests/fixtures/tiny.pgn), [expected.json](../tests/fixtures/expected.json) | Authored file, hand tally | 26 seen, 22 accepted, 4/20 eligible draws; no population inference |
| Portfolio fixture | [annotated PGN](../tests/fixtures/portfolio_annotated.pgn), [expected values](../tests/fixtures/portfolio_expected.json) | Authored file, independent expected arithmetic | Six records, four unique accepted games; clock and opening demonstration only |
| January 2013 complete archive | `foundation` in [datasets.json](../config/datasets.json) | Publisher SHA256, bounded download, normalized hash, repeated build | 121,332 accepted; historical ingest/metric proof, no current clock claim |
| August 2026 prefix | `analytical` in datasets.json | Exactly 40,000,000 retained compressed bytes, pinned prefix SHA256, complete-PGN extraction | 100,000 complete PGNs, 99,467 accepted; observed August 1 only |
| November 2025 Elite complete curated file | [Lichess Elite Database](https://database.nikonoel.fr/), [ingestion receipt](../reports/elite-2025-11-ingestion.json) | Local ZIP/PGN SHA256 receipts, identity adapter, full legal replay, immutable snapshot checks | 280,246 records; 278,481 rated accepted, 1,765 unrated excluded; covers November 1–30; no clock annotations |
| M7 December 2025 prefix | Frozen [December report](M7-DECEMBER.md) and isolated ignored workspace | Prefix/source hashes, independent raw-PGN reference and frozen case manifest | 100,000 complete PGNs, 99,307 accepted; observed December 1 only |

Other month prefixes were used in M7 development and remain documented in
[M7.md](M7.md). They are ordered prefixes, not random month samples. A game-ID
hash selects about 5% of **accepted games in a prefix** for move extraction;
it does not make a monthwide sample. Opening names come from source PGN tags.
Clock and evaluation annotations are incomplete and selected. The >=200 cp
measure compares consecutive source evaluations from the moving side's
perspective and uses the prior same-side clock; it is an exploratory proxy,
not a verified blunder or causal time-pressure effect. [Metric definitions](METRICS.md)
record grain, denominator, exclusions and missingness.

To locate the retained local files after acquisition, use `data/raw/` for the
complete archive and `data/analytical/` for compressed prefixes, extracted
complete PGNs and extraction receipts. Current pointers are `data/*-current.json`;
immutable snapshots are in `data/published/` and `data/analytical/published/`.
All are ignored by Git. The exact source, plan, counts, hashes and observed UTC
range are in each manifest. The fixture demo has its own ignored
`work/portfolio-demo/project/data/` tree. The default checkout does not include
any real archive.

With network access and sufficient disk space, the bounded foundation sequence
is `chesslab ingest --dataset foundation`, then `build`, `validate`, and
`report` for that dataset. The analytical sequence is `python -m analytics_m3
acquire`, `extract`, `ingest`, `moves`, then `report`. Check
[RUNBOOK.md](RUNBOOK.md) for exact commands and recovery. Acquisition is manual;
no import or test collection downloads data. The 40 MB prefix is a range
request, not a publisher full-file checksum claim.

Independent references are separate from production metric SQL:
[reference_draw_rate.py](../scripts/reference_draw_rate.py) tallies real
foundation PGN headers; [M3 reference evidence](../reports/M3-reference-check.json)
checks raw-PGN opening/player/clock cohorts against the published snapshot;
[M7 December evidence](../reports/M7-December-Sol-v12-checkpoint.json) binds
held-out cases and audited responses. Fixture expected values are authored in
JSON and checked against a fresh pipeline run. The read-only
[source/receipt audit](../reports/portfolio-source-audit.json) checked nine
locally retained pairs and found zero mismatches; ignored data must be present
to repeat that audit. It does not assert that uninspected data are correct.

## Opening-training corpus — October 9, 2026

[The checked corpus report](../reports/opening-corpus.json) combines eleven retained
sources by provider/game ID: **1,295,879 unique accepted games**, with no overlaps.
Both players meet the inclusive 1000 floor in **1,232,182** games; both exceed
1000 in **1,231,872**. The training index contains **1,042,346** completed games
of at least 20 plies, excludes marked bots and unknown/below-floor ratings, and
excludes the historical foundation. Its default Elite cohort has **240,086**
games; the broader public cohort has **802,260**. The latter includes nine
first-day prefixes from December 2025 through August 2026, not full months.
The [earlier inventory](../reports/retained-rating-inventory.json) remains
pre-expansion evidence.

Elite's publisher currently lists November 2025 as its latest file. Its selection
since December 2021 is 2500+ versus 2300+, excluding bullet. We enforce those
ratings and event exclusions for the reference cohort. The publisher does not
provide a checksum in this acquisition; locally computed hashes bind retained
bytes, with ZIP member size/CRC handling and full legal replay supplying separate
checks. A versioned adapter maps the original `LichessURL` to `Site`; original
files and annotations remain retained. Ratings are Lichess ratings, and marked-bot
exclusion does not certify all remaining players as human.

Reuse the existing ingestion and snapshot validation with the manual
[acquisition](../scripts/acquire_elite.py), [adapter/ingestion](../scripts/ingest_elite.py),
and [corpus builder](../scripts/build_opening_corpus.py). Selection and bounds are
in [opening-corpus.json](../config/opening-corpus.json). The game index points to
full legal PGNs by snapshot/file/ordinal; opening position visits are the next
step, not an implemented graph. Local payloads remain ignored under `data/` and
`work/`; a fresh clone contains receipts and code, not the real games.

The new index uses 141.8 MB DuckDB plus 91.9 MB Parquet. All retained game-artifact
files across `data/` and `work/` occupy about 9.15 GB, including source formats,
working copies, and retained failed attempts. No hosted database or model API
call was required. See [storage and operating cost](TRANSPOSITION_LEARNING.md#storage-and-operating-cost).
