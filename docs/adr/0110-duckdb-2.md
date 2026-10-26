# 0110. DuckDB 2.0

- Status: accepted on merge
- Date: 2026-10-26

## Motivation

DuckDB 2.0.0 was uploaded to PyPI on 2026-10-21. The grouped Dependabot
update [#70](https://github.com/jfk-ssa/chess-analytics-lab/pull/70)
moved `duckdb` from 1.5.6 to 2.0.0, with ruff and pandas. It failed
three tests. Two in `tests/test_opening_positions.py` raised
`ResourceInUseException: connection has an unfinished result from
execute()` at `relation.create_view` in
`scripts/summarize_opening_positions.py`. The third,
`test_hosted_streamlit_pin_matches_the_lock`, still expected
`duckdb==1.5.6`. #70 was closed.

In 2.0, `execute()` results stream. A `fetchone()` reads one row and
leaves the result open. Until that result is drained, or ended with
`complete()` or `abort()`, any other call on the connection is refused,
including a relation call such as `table()`, `sql()`, `read_parquet()`,
or `create_view()`. A later `execute()` replaces the open result, on 1.5
and on 2.0. `summarize_view` built its view through the relational API
after its callers had read single-row counts with `fetchone()`.

Checked on 2026-10-25 against this checkout, on Python 3.12.14:

- With `duckdb==2.0.0` and no other change, `uv lock` moved only
  duckdb. dbt-duckdb 1.11.0 declares `duckdb>=1.0.0` and stays. ruff,
  ruff format, and basedpyright pass. `pytest -q` with
  `CHESSLAB_REQUIRE_DBT=1` fails the same three tests as #70.
- `summarize_view` now creates `selected_visits` with `execute()`.
  The two opening-position tests then pass on 1.5.6 and on 2.0.0.
- With the pins updated, the full suite matches 1.5.6: the eight
  `tests/test_docs_site.py` tests that need
  `reports/opening-positions.json` fail on both versions, and nothing
  else fails. The hosted tests pass (75). The tiny dbt transform,
  `dbt parse`, the semantic smoke check, the analyst gate (89/89),
  `chesslab demo`, and `chesslab demo --scope all` pass.
- A clean pip install of `hosted/requirements.txt` ran the hosted
  AppTest with no exception and no error element.
- The repository does not call the APIs 2.0 removed: no Arrow or
  polars output, no `fetchone()` on a relation, no expression API, no
  `overwrite=False`, no `Decimal` parameter, no connection shared
  across threads. The SQL and dbt models use no single-arrow lambda,
  `~` regex operator, integer division, untyped `NULL` column, or
  `MERGE INTO`.

Storage changed. A database file that 2.0 creates uses storage version
69, and DuckDB 1.5.6 refuses it ("can only read versions between 64 and
68"). 2.0 reads and writes 1.5 files, and they stay 1.5-readable. A file
created with `storage_compatibility_version` `v1.5.0` stays 1.5-readable.
Parquet written by 2.0 is read by 1.5 with the same rows. Rewriting the
committed cube with 2.0 gave 589,962 bytes, against 593,637 bytes from
1.5.6, so a rebuild changes the committed bytes without changing rows.
The committed cube is left as written by 1.5.6. This record does not
change the byte counts in [ADR 0101](0101-hosted-bi-cube.md). The DuckDB
1.5.6 pin and 21,568,087-byte wheel sentences in that record, around
lines 26 and 137, are superseded by this ADR.

No `.duckdb` file is committed, and the hosted app opens only the
committed Parquet cube in memory. Snapshot and mart identities include
the `uv.lock` digest, so 2.0 publishes into new directories. A rollback
to 1.5.6 rebuilt the demo, the tiny mart, and the portfolio demo
without opening a 2.0 file. Scratch databases under `work/` and
pointer files that outlive a rebuild are the exceptions.

dbt-duckdb 1.11.0 is the newest release on PyPI. 1.11.1 is not
released. Upstream merged two 2.0 fixes after 1.11.0
([duckdb/dbt-duckdb#858](https://github.com/duckdb/dbt-duckdb/pull/858)):
a `fetchone()` before `register()` for plugin sources with `save_mode`,
and for Python models on DuckLake. This project uses one local file,
`threads: 1`, SQL models only, and no plugins, so neither path runs
here. The `dbt` extra stays `dbt-duckdb==1.11.0`.

## Decision

`pyproject.toml`, `uv.lock`, and `hosted/requirements.txt` pin
`duckdb==2.0.0`. The pin test and `THIRD_PARTY_NOTICES.md` follow.
dbt-duckdb stays 1.11.0 until a release carries #858.

Code reads every `execute()` result to its end before it calls the
relational API on the same connection, or uses `execute()` for DDL. A
single-row count may still use `fetchone()` when the next call on that
connection is `execute()`.

The pinned opening-position publication stays
`31a395044203532224cbb387475ef0bb790c8e88faac98bc9b2a12f5d500c46e`.
The docs gate hashes the generator, so
`reports/opening-positions-checkpoint.json` records the new digest of
`scripts/summarize_opening_positions.py`. The rankings are not
regenerated, and the checkpoint's recorded DuckDB 1.5.6 runtime stays
the runtime that wrote those bytes.

Database files are written in the 2.0 default format. Every local
`.duckdb` file is rebuilt from committed or recorded sources, and the
lock digest separates the 1.5 and 2.0 directories. This record does not
set `storage_compatibility_version`.

Dependabot is not given an ignore for duckdb major updates. The 2.0
pin is that major, so an ignore is not added. `dependabot.yml` is
unchanged.

## Consequences

Community Cloud reinstalls the environment on the push that changes
`hosted/requirements.txt`. The cp312-abi3 manylinux x86_64 wheel is
24,371,005 bytes, against 21,568,087 for 1.5.6. A 2.0 connection starts
async I/O threads: on an 8-core box it opened 40 threads in 42 ms, where
1.5.6 opened 15 in 8 ms. The hosted page opens one connection per rerun.
This record does not tune `async_threads`.

After that reinstall, open
[the hosted page](https://chess-analytics-lab.streamlit.app/) and check
the cube cards. The committed Parquet is unchanged, so the full range
should still show Games 1,009,445, White win 49.2%, draw 5.1%, loss
45.7%, clock error 2,128 / 22,978, and 256 positions. A reader error or
a blank card fails the deploy.

Rollback is reverting this pull request, then deleting `work/*.duckdb`
scratch files before the next 1.5.6 command. A checkout that returns to
1.5.6 cannot open a database file 2.0 created (storage version 69).
Delete those scratch files and rebuild published snapshots, rather than
reusing them. The next cube rebuild changes the committed Parquet
bytes and keeps the same rows. Reports that record `duckdb.__version__`
record 2.0.0 when regenerated. Python 3.10 is not supported by 2.0,
and this project requires 3.12. This record does not authorize a live
model call.
