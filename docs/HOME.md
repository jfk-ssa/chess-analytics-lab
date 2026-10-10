# Reliable data. Inspectable analytics. Measured AI.

The project connects three pieces: a bounded chess-game ingestion pipeline,
opening and clock analytics with explicit denominators, and a read-only AI
analyst whose answers carry snapshot-bound evidence. Local DuckDB and Parquet
keep the system reproducible; dbt models and recovery checks demonstrate how
the data is validated before publication.

The dashboard runs locally. The website lets you inspect recorded results,
explore measured opening positions and move orders, try illustrative controls,
and follow the offline demo.

## What the comparison teaches

Jev is TypeSafe AI's typed decision model. OpenAI Decisions is the optional
classifier studied alongside it. Both select task routes; neither replaces
the checked calculations that produce a chess metric.

Better routing did not establish better final answers. The retained paired
experiment found equal correctness and a higher cost with the Jev gate.
The later Decisions final-answer comparison uses saved-answer replay rather
than a new live pairing. These are small, dated experiments, with failures
and limitations retained alongside their results.

## Read further

| Question | Evidence and guide |
|---|---|
| How does the pipeline work? | [Architecture](ARCHITECTURE.md) |
| How are metrics defined? | [Definitions and denominators](METRICS.md) |
| What do the models demonstrate? | [Measured comparison](CLASSIFIER_COMPARISON.md) |
| Which opening positions recur across move orders? | [Transposition analysis](TRANSPOSITIONS.md) and [learning design](TRANSPOSITION_LEARNING.md) |
| Can I reproduce a small example? | [Offline walkthrough](DEMO.md) |
| What is complete and what comes next? | [Current project status](STATUS.md) |

The [documentation guide](README.md) indexes operational runbooks, analytical
memos and historical evidence. The [repository](https://github.com/jfk-ssa/chess-analytics-lab)
contains the maintained code and contracts. Project author:
[jfk-ssa on GitHub](https://github.com/jfk-ssa).
