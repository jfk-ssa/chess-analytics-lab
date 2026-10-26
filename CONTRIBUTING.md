# Contributing

## Commits

Use [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/)
with an optional scope:

```text
type: subject
type(scope): subject
```

Types used here: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`,
`build`, `ci`, `chore`, and `revert`. A `!` before the colon marks a breaking
change.

Make one logical, revertible commit per change. Lint and tests are green on
that commit before the next change starts.

Keep generated data and reports out of code commits. A generator change and a
measured receipt are separate commits when both need to land.

The local `commit-msg` hook checks the message. Install it with the commands
in the README [development checks](README.md#development-checks).

## Pull requests

Write the pull request title in Conventional Commits form. Squash merge uses
that title as the commit message.

Keep one theme per pull request, with a soft limit of about 400 lines of real
code. Generated files and vendored files sit outside that count.

Fill in the pull request template: why, what changed, how it was tested, and
risk or rollback. Keep fixture, replay, and live results distinct.

A pull request stacked on another open pull request stays a draft. Its
description says `Stacked on #N, merge after`.

This repository accepts squash merges only, and GitHub deletes the head branch
after the merge. Both settings are already enabled.

Name branches `type/short-topic`, for example `docs/commit-conventions`.

## Offline integrity

`.github/workflows/offline.yml` runs on every pull request, on pushes to
`main`, on `workflow_dispatch`, and on `merge_group`. The jobs `offline`,
`offline-core`, and `portfolio` always report a conclusion. The workflow has
no `paths` or `paths-ignore` filter, because a skipped required check stays
pending. The required check names stay `offline` and `portfolio`. The no-dbt
pytest job does not set a display name, so its check name is
`Offline integrity / offline-core`.

A `changes` job reads the pull request diff and
`scripts/ci_offline_changes.py` chooses steps. That script is the filter
config. Pushes to `main`, manual runs, merge-group runs, and a schedule, if
one is added later, run every step. A pull request also runs every step when
the diff cannot be read, the diff is empty, a file matches no category, or
the diff touches any of:

- `.github/**`
- `pyproject.toml`
- `uv.lock`
- `scripts/ci_offline_changes.py`
- `tests/test_ci_offline_changes.py`

Docs-only, site, and hosted diffs skip the long pytest steps. `offline-core`
still succeeds on those diffs, with its pytest step skipped.
`THIRD_PARTY_NOTICES.md` is hosted, because the hosted dashboard test reads
the Streamlit pin from it. `docs/METRICS.md` is a frozen analyst preflight
input, so it also runs the analyst guards. Changes under
`src/chess_analytics/analyst/`, `evals/`, `reports/live-eval-receipt-*`, the
live-eval fixture, and the public extract still run the checks that guard
them. The full no-dbt `pytest` step is the `offline-core` job. It covers
`tests/test_public_extract.py` and `tests/test_game_import.py`. That import
test shells out to Node, so `offline-core` sets up Node with the step. The
narrower pytest commands stay in `offline` and stay off when the full file
set already runs. The `CHESSLAB_REQUIRE_DBT=1` pytest step stays in `offline`.
Other pytest paths stay in the full run; test ownership outside those two
files is not narrow enough to select.

`python3 scripts/ci_offline_changes.py --audit` checks that every workflow
step and every tracked path stays mapped. The offline job runs that audit on
every pull request. Pytest covers the same map. A new tracked path needs a
category pattern or a `FAIL_OPEN_PATHS` entry. Fail-open paths run the full
suite. The measured step times and the per-category savings are in
[ADR 0100](docs/adr/0100-change-aware-offline-integrity.md).

## Decisions

New decisions go only into [docs/adr](docs/adr/). Add the next number and a row
in [docs/DECISIONS.md](docs/DECISIONS.md).

[docs/STATUS.md](docs/STATUS.md) stays a short current-state summary: headline,
checkout structure, phase tracker, dataset versions, and limits. Do not append
measurement logs there. Put measured evidence in the relevant receipt under
`reports/` and, when the choice should outlive the chat, in an ADR.

## Changing the eval baseline

`python -m chess_analytics.analyst gate` compares a fresh scorecard with
`evals/baselines/analyst_gate_v1.json`. Replay is deterministic, so the
scorecard must match exactly. A difference fails. The report labels each
one `REGRESSION`, `IMPROVEMENT`, `ADDED`, `REMOVED`, or `PATH-CHANGED`.
Removing a case is a diff, so coverage cannot shrink without a review.
Editing a case or a replay plan fails the load with `hash changed`.

Rewrite the baseline only when the new scorecard is the intended behavior:

```text
uv run --locked --offline --no-editable --extra dbt python -m chess_analytics.analyst gate --update
```

Run that command with the `dbt` extra installed. The committed baseline
records `governed` for the MetricFlow cases, and a run without a mart
records `reviewed_sql` for those cases. `--update` rewrites only that JSON
file. It refuses when `CI` is present in the environment, including an
empty value. The file is
canonical JSON: sorted keys, two-space indent, a trailing newline, and no
timestamps. Leave out dataset ids, evidence ids, elapsed time, and node
counts. Numeric result values keep the scorer's existing 1e-6 tolerance.
The scorecard itself has no extra tolerance.

Explain every diff in the pull request. The gate does not measure LLM
quality. Live model evals stay out of CI.
