# Architecture and boundaries

**HTML version:** [Read this guide on the documentation site](https://jfk-ssa.github.io/chess-analytics-lab/architecture.html).

Chess Analytics Lab uses one Python/SQL repository and local DuckDB files.
`chesslab` provides the foundation ingestion and two offline demos. The
analytical source command is `python -m chess_analytics.corpus`; the checked analyst is
`python -m analyst_m5`. These functional commands are the entry points while
historical package and report names remain stable for source hashes.

```text
Lichess fixed complete archive / fixed byte prefix / synthetic PGN
  → chess_analytics.ingest: caps, parser, normalization, dedup, quarantine
  → chess_analytics.warehouse: checked immutable snapshots + current pointer
  → chess_analytics.marts: local dbt copy, tests, published marts + recovery ledger
  → chess_analytics.corpus: selected moves, opening and clock definitions
  → analytics_m4: parameterized analysis and Streamlit views
  → analyst_m5: allowlisted read-only tools, bounded plan, evidence IDs
  → frozen references + scorer + preserved attempts and costs
```

The single writer lock protects data-changing CLI operations. A candidate is
validated before its current pointer is replaced. Foundation source manifests
bind normalized output to source bytes, code and lock hashes; the analytical
move publication also binds its extracted receipt to the checked source hash.
Source order, sampling selection, coverage and exclusions are in manifests.
The partial compressed prefix is hashed as retained bytes; it is never marked
as a fully verified publisher archive.

The optional Dagster assets and Prefect tasks call the same stage/publish/verify
functions and optional dbt mart transform. Neither is a production scheduler or
cloud dependency; [the orchestration guide](ORCHESTRATION.md) gives the exact
local commands and comparison evidence. Airflow remains a later option.

The analyst can list definitions, read coverage, query named metrics, compare
openings and inspect clock buckets. It cannot execute free-form SQL, files,
network access or extensions through its tool surface. Offline typed plans and
recorded fixture plans run without a key. A live provider path exists but
requires personal configuration, an explicit finite gross cap and named key;
its requests/results are logged separately. Evidence IDs bind tool name,
arguments, result and dataset ID. Scoring is external to the agent; historical
M5–M7 rubrics remain frozen and new fixture checks use `portfolio-1.0`.

The full demo copies only required code/contracts into an ignored project under
`work/portfolio-demo/project`, publishes a synthetic snapshot there and passes
that path to Streamlit with `CHESSLAB_PROJECT`. It never replaces the real
`data/` pointers. The dashboard marks synthetic data on every view.
