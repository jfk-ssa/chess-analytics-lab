# Local data (ignored by Git)

raw/: verified archive, acquisition plan, partial attempts and failures.
staging/: immutable ingestion candidates, quarantine, failed build artifacts.
published/: checked Parquet/DuckDB snapshots and manifests.
DATASET-current.json: atomically replaced pointer to the checked snapshot.
DATASET-staged.json: pointer to the latest successfully parsed candidate.

Default data-directory allowance is 5 GB including retained failures and snapshots.
No automatic cleanup removes evidence. Choose `--data-dir` to relocate this tree.

`public/` is the committed aggregate extract. It is not a warehouse. See ADR 0092.

Mac rebuild from `~/Developer/chess-analytics-lab`, using the venv override below. The `dbt` extra is required for MetricFlow. The dashboard extra is not. The builder prints which receipts were relabeled and why the others were not.

```
UV_PROJECT_ENVIRONMENT=$HOME/.venvs/chess-analytics-lab uv run --directory $HOME/Developer/chess-analytics-lab --locked --no-editable --extra dbt python scripts/build_public_extract.py
```
