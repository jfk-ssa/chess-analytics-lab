# 0062. Public quality corpus and manageable local storage

- Status: accepted
- Date: 2026-10-09

The owner requested more public games, a 1000 rating floor, Elite consideration,
and publication of the learning HTML. Require both players at least 1000,
completed results, no marked bots, and at least 20 plies. Keep January 2013 in
the inventory but exclude it from current training. Default to the curated
November 2025 Elite reference cohort: both players 2300+, one 2500+, excluding
bullet. Keep Elite and general-public frequency denominators separate; no
personal history is required. White remains the initial learner color.

Reuse the current ingestion and legal validation, adapting Elite's `LichessURL`
identity to `Site` with a versioned, retained-source adapter. Publish a new game
index in the existing DuckDB/Parquet format, linked to source PGNs by immutable
snapshot and ordinal. No new database engine or combined full PGN is needed.
The checked report gives 1,295,879 unique retained games, 1,232,182 with both
ratings at least 1000, and 1,042,346 training games, including 240,086 Elite.
Source/download receipts and full-month versus prefix distinctions remain
explicit. Ratings alone do not establish move quality.

The index occupies about 234 MB across DuckDB and Parquet; the retained
multi-format game artifacts total about 9.15 GB. Only compact corpus summaries
enter Git and Pages. Derive the first 20 plies next; deeper positions and engine
enrichment need measured value before multiplying storage/CPU. There were no
paid model calls. An interrupted ingestion and two index build failures remain
retained locally. Compact game-key deduplication replaced a wide row sort after
a bounded temporary-disk failure; the final build caps RAM at 1 GB and temporary
disk at 2 GB, requiring 3 GB free before starting.
