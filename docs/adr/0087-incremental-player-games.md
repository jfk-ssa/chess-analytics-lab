# 0087. Incremental player_games, measured and not adopted

- Status: accepted on merge
- Date: 2026-10-18

## Motivation

[ADR 0086](0086-dbt-engineering-depth.md) left an incremental `player_games`
as the next record: `unique_key` `player_game_key`, a test that a full
refresh matches the incremental result, and a timing on the large corpus.
Keep the model only if the saving justifies giving up the checksummed
from-scratch rebuild.

The large corpus is not in this checkout and was not downloaded. The
numbers below are from a deterministic synthetic stand-in. They measure
the rebuild mechanic. They are not the Lichess distribution and they are
not a claim about the 2013 archive or the August prefix.

## How a mart is built today

`build_mart` in `src/chess_analytics/marts/pipeline.py` copies one immutable
snapshot warehouse into a new attempt directory and runs `dbt build` there.
The snapshot file is not modified. On success the attempt warehouse is
copied again, checksummed, and published under a mart id. The id is the
first 24 hex characters of the hash of three values: the snapshot id, the
`model_sha256` of the dbt SQL and YAML, and the `uv.lock` digest. If that
directory already exists, the publisher validates it and returns it. It
does not rebuild.

`player_games` is a view. The snapshot tables are `fact_game` and
`fact_player_game`. The view is created during that one build. Nothing in
the snapshot is a persistent `player_games` target.

## How an incremental model would interact

An incremental model keeps a table and, on a later run, processes a
filtered batch. `is_incremental()` is false when the target relation is
missing. The publisher's first action on a new mart id is to copy a
snapshot that has no `player_games` table, so the incremental branch does
not run. The first build is a full create. A second build of the same
mart id does not happen: the existing directory is returned.

A new snapshot is a new directory. It supersedes the previous snapshot
for the current pointer and contains that snapshot's full fact tables.
It is not a delta of games appended to the previous warehouse. Rows that
were "new" relative to an older snapshot are simply rows in the new file.
`source_ordinal` is the position inside that snapshot's source, not a
load sequence that continues from the previous snapshot.

If the snapshot id changes, the mart id changes, and the new attempt
starts from the new copy. If `model_sha256` or the lock changes, the mart
id changes the same way. Historical rows in the new snapshot can also
differ from the previous snapshot. An incremental filter that inserts
keys missing from a carried-forward table would keep stale values for
keys that changed and would keep rows the new snapshot dropped.

Carrying `player_games` forward from the previous mart would make the new
warehouse depend on that previous mart. The mart id does not name the
previous mart. The first directory published for an id is the one later
callers reuse. A carried-forward result and a from-scratch result would
have to match before that reuse is safe.

The measurement below is the hypothetical the publisher does not run: one
DuckDB file, a base table already built, then new fact rows appended, then
an incremental `dbt build`. It is the case where incremental has a chance
to win.

## Strategies

dbt-duckdb 1.11.0 on DuckDB 1.5.6 reports four strategies: `append`,
`delete+insert`, `merge`, and `microbatch`. The probe and the 1% delta
timings are in the receipt.

`append` inserts the batch. The adapter's default append macro does not
read `unique_key`. A replayed batch that the filter emits again inserts
those rows a second time.

`delete+insert` deletes target rows whose `unique_key` appears in the
batch, then inserts the batch. A replayed key replaces the stored row.
The configured key is `player_game_key`. `on_schema_change` is `fail`
because the enforced contract rejects the default `ignore`.

`merge` also matches on `unique_key` and rewrites the matched row. At
this shape the batch replaces the whole row, so merge and delete+insert
do the same logical work.

`microbatch` deletes and inserts by `event_time` window. The adapter
raises if `unique_key` is set. The probe's error line was:
`microbatch incremental strategy does not support 'unique_key'.`

`delete+insert` is the strategy that satisfies `unique_key` without the
merge configuration. The 1% timings below show it is close to append and
to merge. The choice is the key behavior, not a speed gap.

The published-column filter, used for the decision timings, is:

```sql
{% if is_incremental() %}
where p."player_game_key" not in (
    select "player_game_key" from {{ this }}
)
{% endif %}
```

A second, optimistic filter keeps the same columns and keeps only
`source_ordinal` values above a `loaded_through` var. That var is the
caller telling the model the cutoff. It is an upper bound on a monotonic
in-file append. It is not a property of a replacement snapshot.

## Method

`scripts/measure_incremental_player_games.py` creates `fact_game` and
`fact_player_game` with the column names and types in
`contracts/tables.json`. Row `i` is a pure function of `i`: no random
generator, two player rows per game, scores that sum to 1 unless the
result is `*`. The script copies `dbt/` to a temp directory from
`tempfile.mkdtemp` and rewrites only that copy of `player_games.sql`.
The published project is not modified.

Each invocation passes `--no-partial-parse`. The publisher also uses a
fresh target directory, so the wall times include a full parse. Model
time is dbt's `execution_time` for `model.chess_analytics.player_games`.
Process wall is `time.perf_counter` around the `dbt build` subprocess.
`elapsed_time` is dbt's own timer in `run_results.json`.

Builds and the seed use the profile settings: dbt `threads: 1`, DuckDB
`memory_limit` 256MB, `max_temp_directory_size` 512MB. The profile does
not set DuckDB's worker threads. This machine's default was 4. The
opening-score query uses a read-only connection with DuckDB's default
memory limit, which is how `semantic.py` opens the mart. That default
here was 12.5 GiB.

Scales are 100,000 games (200,000 player rows) and 1,000,000 games
(2,000,000 player rows). Deltas are 1% and 10% new games appended after
the base build. Model scenarios use 5 repeats. The full `dbt build` of
the published view project, including tests, uses 3 repeats. No repeat
was dropped. The median is the middle sample. Spread is max minus min.
Every sample is in
[reports/incremental-player-games.json](../../reports/incremental-player-games.json).

Equivalence is the SHA-256 of the ordered `player_games` content. DuckDB
casts each column to varchar, and the script hashes those strings in
chunks of 8,000 rows ordered by `player_game_key`. The cast stays inside
the engine, so the comparison does not import `pytz`. `pytz` is absent
from the base install and appears only as a transitive dependency of the
dbt extra. The comparison is two builds on this machine in one run. It is
not a hash to pin across DuckDB versions.

The `sha256` strings in the committed receipt were produced by an earlier
form of this function that hashed Python's `repr` of the fetched values.
That run had the dbt extra, so `pytz` was importable. A rerun with the
current function will not reproduce those hex strings. The match flags,
row counts, byte sizes, and timings in the receipt are from that run.

Machine, from this run's receipt and `lscpu` on the same VM: Linux
6.12.94+, x86_64, 4 CPUs, Intel Xeon (family 6, model 207),
16,780,574,720 bytes of RAM, Python 3.12.14, DuckDB 1.5.6, dbt-core
1.12.5, dbt-duckdb 1.11.0. The script's own wall clock for both scales
was 771.8 s.

Times below are seconds, rounded to the nearest millisecond from that
receipt.

## Results

### 1,000,000 games

Facts-only file: 45,887,488 bytes. Seeding those rows took 2.577 s.
Copying that file, 5 times: median 0.036 s, spread 0.023 s.

Full-refresh table of `player_games`, 5 repeats:

- execution median 0.921 s, min 0.886 s, max 0.991 s, spread 0.106 s
- dbt elapsed median 1.075 s
- process wall median 4.076 s
- file size after the table: 90,976,256 bytes

The published view, 5 repeats:

- execution median 0.045 s, spread 0.003 s
- process wall median 3.191 s
- file size stayed 45,887,488 bytes, the same as the facts file

Opening-score aggregate (`sum(eligible_score)`, `sum(score_eligible)`,
`sum(eligible_win)`), 5 queries:

- on the view: median 0.110 s, spread 0.058 s
- on the table: median 0.002 s, spread 0.004 s

`delete+insert`, anti-join filter. The initial build is the full create
of the base, which is what a fresh snapshot copy would do.

1% new games (10,000 on a base of 990,000), 5 repeats:

- initial execution median 0.912 s
- delta execution median 1.081 s, min 0.980 s, max 1.138 s, spread 0.158 s
- delta process wall median 4.285 s
- rerun with no new rows, execution median 0.975 s
- ordered-content SHA-256 matched the full refresh of all 1,000,000 games
- one replay of the delta keys: execution 0.223 s, hash matched

10% new games (100,000 on a base of 900,000), 5 repeats:

- initial execution median 0.896 s
- delta execution median 1.301 s, min 1.286 s, max 1.406 s, spread 0.119 s
- delta process wall median 4.445 s
- rerun execution median 0.993 s
- hash matched the same full refresh
- one replay: execution 0.552 s, hash matched

The anti-join delta is slower than rebuilding the whole table. The rerun,
which adds nothing, is in the same range as the full refresh. The
persistent table is the extra ~45,088,768 bytes between the facts file
and the full-refresh table file (90,976,256 − 45,887,488).

Ordinal `loaded_through` filter, 1% only, 5 repeats:

- delta execution median 0.212 s, min 0.205 s, max 0.239 s, spread 0.034 s
- rerun execution median 0.207 s
- hash matched the full refresh

That filter is the fast case. It still sits inside a multi-second process
wall, and the publisher never reaches it.

Strategy comparison on the 1% anti-join delta, execution median of a
separate 5-repeat set. Its `delete+insert` median is not the 1.081 s
sample set above. The two medians sit inside each other's spread:

- `append` 0.980 s, spread 0.081 s
- `delete+insert` 1.018 s, spread 0.096 s
- `merge` 1.032 s, spread 0.054 s

Downstream of the published views, one `dbt build` of
`mart_player_outcomes`, `games`, `player_games`, and
`metricflow_time_spine`, tests excluded, 5 repeats. None of
`mart_player_outcomes` or `games` refs `player_games`.

- process wall median 3.873 s
- `mart_player_outcomes` execution median 0.602 s, spread 0.041 s
- `games` execution median 0.046 s
- `player_games` view execution median 0.038 s
- `metricflow_time_spine` execution median 0.061 s

Full `dbt build` of the published project, tests included, 3 repeats:

- process wall median 6.258 s, min 6.185 s, max 6.270 s, spread 0.085 s
- dbt elapsed median 3.270 s
- slowest model node: `mart_player_outcomes` median 0.562 s
- `player_games` view median 0.039 s

### 100,000 games

Full-refresh table execution median 0.317 s, spread 0.067 s, process wall
median 3.442 s. Facts file 4,730,880 bytes.

`delete+insert` anti-join, execution median:

- 1% delta (1,000 games): 0.163 s, rerun 0.160 s, delta wall 3.299 s
- 10% delta (10,000 games): 0.192 s, rerun 0.160 s, delta wall 3.356 s

Both hashes matched the full refresh, including one replay each. The
ordinal 1% delta execution median was 0.127 s.

Full published `dbt build`, 3 repeats: process wall median 4.484 s, dbt
elapsed median 1.516 s.

At this scale the anti-join delta is faster than the table rebuild by
about 0.154 s of model time (0.317 − 0.163). The process wall stays about
3.3 s either way.

## Decision

The incremental model stays out of the published project. `player_games`
stays a view. `build_mart` stays a from-scratch `dbt build` on a fresh
snapshot copy. The mart id formula is unchanged.

The 1,000,000-game anti-join, which is the filter that can see "keys not
already stored" without a caller-supplied cutoff, took longer than the
full table rebuild (1.081 s versus 0.921 s). A rerun that inserted nothing
took 0.975 s. The optimistic ordinal filter did save model time (0.212 s
versus 0.921 s). That saving is smaller than the process wall, the
publisher does not run the incremental branch, and `source_ordinal` does
not identify new games across replacement snapshots.

At 100,000 games the anti-join saves 0.154 s of model time. A full
published build at 1,000,000 games has process wall 6.258 s, of which the
`player_games` view is 0.039 s. Changing that view into an incremental
table would not move the build that publishes a mart id.

Equivalence did hold for this synthetic append. Initial build, appended
games, rerun, and a replayed batch produced the same ordered-content
SHA-256 as a from-scratch table, at both scales. That is necessary and it
is not sufficient. The publisher would still be paying a full create, and
a carried-forward table would tie the mart bytes to a previous mart the
id does not name.

An opt-in model file under `dbt/` would change `model_sha256` even if the
model were disabled, and the mart id would change with it. The incremental
SQL stays in the measurement script. The CI test builds it in a scratch
project.

## Tests

`tests/test_incremental_player_games.py` checks three things on every dbt
extra run.

The synthetic seeder at 25 games matches the contract column names, writes
two player rows per game, keeps score sums at 1 when the result is not
`*`, uses 8-character game ids, and is deterministic.

The published `player_games.sql` still contains `materialized='view'` and
does not contain `is_incremental`.

At 40 games the scratch `delete+insert` model matches a from-scratch table
on ordered content after the initial load, after a 4-game append, after a
rerun, and after a replay that selects the appended keys again. Dropping
`unique_key` and replaying those keys grows the table from 80 rows to 88.
Replacing `not in` with `in` leaves the table at the 72 base rows. One run
of this file on the measurement machine took 29.53 s. The 100,000-game and
1,000,000-game timings are not part of CI.

Contracts, the semantic manifest check, `model_hash`, and the MCP allowlist
are unchanged because `dbt/` and the tool list are unchanged.

## Limits and when to revisit

Synthetic rows repeat a small set of openings, results, and ratings. A
real corpus can change bytes per row and the cost of the string split in
`opening_family`. It does not change the publisher's fresh-copy behavior.

DuckDB file size moved between the full-refresh table (90,976,256 bytes)
and the incremental files (91,500,544 bytes after the 1% run, 90,451,968
after the 10% run). Those are file sizes after different build histories.
The equality claim is the ordered-content hash, not the file bytes.

Repeats ran one after another on one machine. Later repeats can hit the
page cache. The spread includes that, and the first sample is in the
median's input.

Revisit this when a from-scratch `player_games` build on a real snapshot
takes minutes, and when publication grows one warehouse instead of copying
an immutable snapshot. Re-measure with the same script shape: 5 repeats,
median and spread, a 1% and a 10% append, and an ordered-content hash
against a full refresh. The anti-join at 1,000,000 synthetic games was
slower than the full refresh, so a future win needs a filter that skips
the historical scan and a snapshot story in which that filter means "new
games". The ordinal upper bound saved about 0.709 s of model time here
(0.921 − 0.212). That is the number to beat with a real watermark, not a
reason to adopt one now.
