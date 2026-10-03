# Local data (ignored by Git)

raw/: verified archive, acquisition plan, partial attempts and failures.
staging/: immutable ingestion candidates, quarantine, failed build artifacts.
published/: checked Parquet/DuckDB snapshots and manifests.
DATASET-current.json: atomically replaced pointer to the checked snapshot.
DATASET-staged.json: pointer to the latest successfully parsed candidate.

Default data-directory allowance is 5 GB including retained failures and snapshots.
No automatic cleanup removes evidence. Choose `--data-dir` to relocate this tree.
