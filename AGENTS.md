# Repository instructions

Read docs/STATUS.md, the decision records under docs/adr/ (indexed by docs/DECISIONS.md), and docs/PROJECT_SPEC.md before extending this project.
Work in milestone order. Preserve failures and distinguish fixture tests, replay and live results.
Never read workplace credentials. Live calls stay disabled until personal configuration and an
explicit run spending cap exist. Do not infer permission or budgets from API credits.
Use `uv sync --locked --no-editable`, `uv run --locked --no-editable pytest`,
and `uv run --locked --no-editable ruff check .`. Reinstall the project wheel after
source edits with `--reinstall-package chess-analytics-lab`; see README for details.
Tests and demo must work offline after installation. No downloads on imports or test collection.
Keep bulk data out of Git, record provenance, and update status and decisions with measured evidence.
