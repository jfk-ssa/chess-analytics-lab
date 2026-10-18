# 0086. dbt tests, contracts, exposures, lineage, and slim CI

- Status: accepted on merge
- Date: 2026-10-18

## Motivation

[ADR 0085](0085-governed-semantic-layer-metricflow.md) put the core metrics
in MetricFlow. A reviewer looking for analytics-engineering work still has
to infer how a change is tested, what the mart columns are, who reads them,
and how the graph fits together. This record adds those checks on the models
this repository already builds. Each one uses the published game rules or a
real consumer. None of them is a sample project copied in beside the chess
data.

## Decision

### Unit tests

Three dbt 1.12 `unit_tests` live in `dbt/models/unit_tests.yml`. `dbt build`
runs them with the other tests. The tiny `transform` therefore runs them in
the offline workflow.

`int_game_eligibility` keeps the SQL rules. `metric_eligible` is a decisive
result (`1-0`, `0-1`, or `1/2-1/2`) and not `marked_bot`. A `*` result is
not eligible. `drawn` is only the draw result, including a marked-bot draw.
The mart numerator still requires both flags, which is why a bot draw is
`drawn` and not eligible.

`stg_games.opening_family` is the trimmed text before the first colon, null
when that text is blank. The fixture rows cover a null tag, `""`, whitespace,
`: Foo`, `  : Foo`, a padded `Sicilian Defense`, a tag with no colon, and
the family whose text is `None`. `game_key` is `provider || ':' || game_id`.

`stg_player_games` uses the same `game_key`. `player_game_key` appends the
color, so the two seats in one game do not share a key.

### Contracts

`contract.enforced` is true on `mart_game_outcomes`, `mart_player_outcomes`,
`games`, and `player_games`, with a name and a DuckDB type for every column
those models select. `metricflow_time_spine` stays uncontracted. It exists
so dbt can parse, and the analyst does not query it.

YAML is part of `model_hash`, so a contract edit changes `mart_id`. Tests
compare the live hash. The mart id in ADR 0085 is the receipt for that
revision. This record does not rewrite it.

`tests/test_dbt_contract.py` deletes `drawn_games` from a copy of
`mart_game_outcomes.sql` and runs `dbt build --select +mart_game_outcomes`
on empty source tables. The build must exit non-zero and name the contract
failure.

### Exposures

`dbt/models/exposures.yml` names two consumers that exist in this repository.
The owner is the git author, John Kennedy, `jfk-ssa`.

`governed_metric_analyst` is an application of medium maturity. Medium is
the honest level: `query_metric` and `compare_openings` read these metrics
when the published mart matches the analytical snapshot, and a mismatch
keeps the reviewed SQL. High would claim an unconditional production
reader. It depends on `games`, `player_games`, and the twelve governed
metrics. `chesslab mcp` serves the same tools. The URL is the MCP guide.
Clock, engine, and Maia tools do not read these models.

`portfolio_site` is an analysis of low maturity. The static site does not
query the warehouse, so high was inflated. `depends_on` lists the seven
models the generated catalog documents: both staging models, the
eligibility model, both aggregate marts, and both semantic views. The
catalog has eight nodes. The exposure omits `metricflow_time_spine`, which
exists so dbt can parse. The URL is the Pages path `/dbt-docs/`. The
Streamlit dashboard is not an exposure. It reads `fact_game`,
`fact_player_game`, and `fact_move` on the analytical snapshot.

### Lineage

`scripts/render_dbt_dag.py` reads `manifest.json` and writes
[docs/DBT_LINEAGE.md](../DBT_LINEAGE.md). The standard library is enough.
Output order is fixed, and the file has no timestamp. The diagram has
sources, staging, intermediate, marts, semantic models, metrics, and
exposures. Data tests are omitted. Semantic-model labels end in `semantic`
so they stay distinct from the view of the same name. The offline workflow
regenerates the file and fails if the committed copy differs.
[ARCHITECTURE.md](../ARCHITECTURE.md) links the diagram.

`dbt docs generate` runs in the Pages workflow after the site build, against
a copy of the tiny mart named `warehouse.duckdb`. `--target-path target` is
relative to the dbt project. dbt then stores compiled paths as
`target/compiled/...`. An absolute target path is stored as that absolute
path. `--log-path dbt/target/logs` is relative to the workflow directory, so
the log stays in gitignored `dbt/target/` and is not published. The workflow
publishes `index.html`, `manifest.json`, and
`catalog.json` at `/dbt-docs/` and does not commit them. It fails if
`games.compiled_path` does not start with `target/`. A local site build
writes a placeholder page. The architecture guide links the published
catalog. Header navigation is unchanged.

### Slim CI

The offline workflow still runs the full tiny `transform`. After that, it
checks out the pull request's base SHA, or the previous commit on a main
push, with the same pinned `actions/checkout` as the job. The checkout is
sparse to `dbt/`, with `persist-credentials: false`. It parses that project
and runs, on a copy of the tiny warehouse:

- `dbt ls --select state:modified+`
- `dbt build --select state:modified+`
- `dbt test --select test_type:unit,state:modified`

Permissions stay `contents: read`. An artifact of the main manifest would
need `actions: read` to download another workflow's artifact, so this job
does not use one. A missing base checkout (the all-zero `before` SHA on a
new branch, or a base commit with no `dbt/` directory) prints a skip line
and exits 0. A base project that exists and fails to parse fails the job.

The copy is named `warehouse.duckdb`. dbt-duckdb uses the file stem as the
catalog, and the published views qualify `warehouse`, as ADR 0085 requires
for MetricFlow.

### Publisher

Exposures finish as `no-op`. The publisher counts `pass`, `success`, and
`no-op`. Any other status, including skip, warn, or error, still blocks
publication.

## Out of scope

dbt snapshots are not built. A published game snapshot is immutable: a new
snapshot id is a new directory, and the previous directory stays. A dbt
snapshot would record changes the publication model refuses to make.

Source freshness is not built. `published.fact_game` and
`published.fact_player_game` have no `loaded_at` column. The corpus is a
fixed historical PGN. The tiny snapshot manifest does have `started_at`,
`finished_at`, and `published_at` (the local publication clock, measured
here as `2026-10-18T17:57:42.295574+00:00` on the tiny snapshot). That clock is not a source arrival time.
`utc_date` is when the game was played. A freshness check would be a
warning about history or about a local rebuild, not about a failed load.

An incremental `player_games` is a separate follow-up. The candidate is
`unique_key` `player_game_key`, a test that a full refresh matches the
incremental result, and a timing on the large corpus. Keep it only if the
saving justifies giving up the checksummed from-scratch rebuild. This
record does not add the model.

## Results

The timings and file sizes below are one local run on 2026-10-18, on this
checkout, Linux, dbt 1.12.5, dbt-duckdb 1.11.0. They are not a performance
budget. Process wall times include uv and dbt startup. The `Finished
running` lines are dbt's own timers. The manifest's byte size changes with
the target path, so this record does not pin it.

Unit tests, copy of the published tiny warehouse named `warehouse.duckdb`:

- `dbt test --select test_type:unit` found 3 unit tests, PASS=3, finished
  in 0.27s. Process wall 3.686s.
- Dropping `and not marked_bot` failed in 0.09s. Both bot rows changed
  `metric_eligible` from False to True. Exit 1. Process wall 3.224s.
- Replacing the opening expression with the raw tag failed in 0.13s. The
  diff showed `: Foo`, the padded Sicilian tag, and the blank and
  whitespace tags. Exit 1. Process wall 3.381s.
- Dropping color from `player_game_key` failed in 0.09s. Both colors
  collapsed to `lichess:aaaaaaaa`. Exit 1. Process wall 3.256s.

The SQL files were mutated only under `/tmp` and were restored by using
copies. `git diff` of the three model files was empty afterward.

Contract break, empty sources, `drawn_games` removed, `dbt build --select
+mart_game_outcomes`: exit 1, dbt finished in 0.50s, process wall 3.508s.
The error was `This model has an enforced contract that failed.` The row
was `drawn_games`, definition type empty, contract type `BIGINT`,
mismatch `missing in definition`.

Tiny publication after the exposure maturity edit, `chesslab demo` then
`transform --dataset tiny`. Transform process wall 4.423s. That rebuild
is the exposure YAML change. The semantic manifest digest did not change.

- Snapshot `9ac0cb862154fac93d2a87e5`, source SHA-256 unchanged
  (`130df65e85d18e78bbafd89daf6696c2596e03abf939adf47f2dcbdc4d33e75b`)
- Mart `bf2de24d91a4dc8e201634a5`
- `model_sha256` `707aa83395a023e4b49756ef355271232871f9c413a82bd98168cd13d830f4b3`
- dbt results: passed 42, created 8, no-op 2
- Observed: accepted 22, eligible 20, drawn 4, unknown 1, bots 1,
  player rows 44

Passed 42 is 39 data tests plus 3 unit tests. Created 8 is the model count
`dbt build` reports. No-op 2 is the two exposures.

`dbt docs generate --target-path target` on a copy named `warehouse.duckdb`,
after the exposure edit: `index.html` 1,818,461 bytes, `catalog.json`
15,869 bytes. The manifest byte size is omitted because it changes with
the target path. Catalog nodes: 8, and the eighth is
`metricflow_time_spine`. The `portfolio_site` exposure lists the other
seven. Database name `warehouse`. `games` is a view with 18 columns:
`game_key` VARCHAR, `eligible_game` INTEGER, `utc_date` DATE,
`opening_family` VARCHAR. Every catalogued node had `has_stats` false.
`compiled_path` for `games` was
`target/compiled/chess_analytics/models/marts/games.sql`. The manifest,
`index.html`, and `catalog.json` contained no `/tmp`, `/workspace`, or
`/home`. An earlier absolute target, `/tmp/dbt-docs`, had process wall
3.481s and did embed `/tmp`.

`dbt ls --select state:modified+` against a parse of `origin/main`:
process wall 3.152s. The base parse wall was 2.959s. The selector listed
37 nodes:

- 2 exposures
- 12 metrics
- 4 models: `games`, `mart_game_outcomes`, `mart_player_outcomes`,
  `player_games`
- 2 semantic models
- 14 data tests
- 3 unit tests

It did not list `stg_games`, `stg_player_games`, `int_game_eligibility`,
or `metricflow_time_spine`.

`dbt build --select state:modified+` on that state: process wall 3.753s,
dbt finished in 0.48s, PASS=18, NO-OP=2, TOTAL=20 (4 models, 14 data
tests, 2 exposures). The progress line said `of 23`. The three unit tests
were in that count and were not executed. `dbt test --select
test_type:unit,state:modified` then ran them: PASS=3, finished in 0.25s,
process wall 3.478s. The same selector against a state parsed from the
unchanged project warned `does not match any enabled nodes` and
`Nothing to do`, and exited 0.

A one-line SQL comment in a copy of `player_games.sql`, compared with a
parse of the current project, selected both exposures, the seven
player-score metrics, `player_games`, its semantic model, and its five
data tests. It did not select `games`, the game metrics, staging, or the
aggregate marts.

`scripts/render_dbt_dag.py --check` against the docs manifest exited 0.
The committed diagram counts are sources 2, staging 2, intermediate 1,
marts 5 (the time spine is in `models/marts`), semantic models 2, metrics
12, exposures 2.

`tests/test_dbt_contract.py` and `tests/test_dbt_lineage.py`: 4 passed
in 3.70s.

The offline quality bar on the same machine, in workflow order:

- Biome checked 10 files and applied no fixes. Node game-import tests: 10
  passed.
- `ruff check` passed. `ruff format --check`: 293 files already formatted.
  `basedpyright`: 0 errors, 0 warnings, 0 notes.
- pytest without the dbt extra: 229 passed, 26 skipped, in 26.39s.
- MCP protocol tests: 8 passed in 2.99s.
- `chesslab demo`: process wall 0.231s, snapshot
  `9ac0cb862154fac93d2a87e5`, source SHA-256 unchanged, draw rate
  denominator 20, numerator 4, value 0.2.
- pytest with the dbt extra and `CHESSLAB_REQUIRE_DBT=1`: 236 passed, 19
  skipped, in 62.08s.
- Before the exposure maturity edit, `transform --dataset tiny` reused
  the then-current mart (process wall 0.213s). That wall is not a dbt
  build. The edit republished mart `bf2de24d91a4dc8e201634a5` in 4.423s.
- `validate-configs` printed `ERRORS: 0`. `smoke-draw-rate` printed
  `4,20,0.2`. The lineage `--check` exited 0.
- Docs site tests, after `materialize_opening_positions.py`: 17 passed in
  6.63s.
- `pre-commit run --all-files` passed, including gitleaks and `uv-lock
  --check`.

## Limits

On the tiny fixture the extra slim step does not make CI faster. The full
transform still runs, and the sum of the four slim process walls above is
13.342s, almost all startup. dbt's own build timer was 0.48s. Slim
selection pays off when it replaces a full build that takes minutes and
the change is one model. It does not pay off as a second build of a
fixture that already finished in seconds.

`dbt build --select state:modified+` on dbt 1.12.5 counts modified unit
tests whose parent model is unmodified and does not run them. The separate
`dbt test` selector does. A future dbt that runs those tests inside
`build` would make the extra command redundant. Until then, removing it
would hide a unit-test failure on an unmodified model whose YAML test
changed.

A copy named `chesslab-measure.duckdb` still lists `stg_games`. Selecting
from that view fails with `Catalog "warehouse" does not exist`. On that
copy, only the eligibility unit test errors, because it introspects
`stg_games`. The two source unit tests still pass, because `fact_game` and
`fact_player_game` are tables in that file. An empty `warehouse.duckdb`
errors all three: dbt-duckdb introspects the live relation first, and this
run reported `relation doesn't exist` for `stg_games`, `fact_game`, and
`fact_player_game` (PASS=0, ERROR=3). CI and the runbook keep the filename
`warehouse.duckdb`.

The Pages catalog describes the tiny fixture's column names and types.
It has no row counts. It is not the 2013 corpus. With `--target-path
target`, compiled paths in the published manifest stay relative. An
absolute target path would publish that directory name.

dbt's unit-test diff renders the opening family `None` as `NULL`. The
unmutated test passed against the SQL, which returns the string `None`
for `None: Example`. The expectation stays the string.

`portfolio_site` is low maturity and depends on models the static site
does not query. The arrow means the published catalog documents those
seven models. The catalog's eighth node, `metricflow_time_spine`, is not
an exposure dependency.

`tests/test_m2.py` pins `dbt_results` to passed 42, created 8, no-op 2.
Adding a data test, a model, or an exposure fails that assertion until
the counts are updated. The semantic path still requires the live
`model_sha256`. An external pin of mart `b7a77b24a77ae29ca5d7aef8` is
the ADR 0085 receipt, not the current mart.

The implementation hash includes `pipeline.py`. A checkout that already
had a tiny snapshot must run `chesslab demo` again before `transform`
after this change. The source SHA-256 does not change.
