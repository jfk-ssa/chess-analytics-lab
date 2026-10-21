# 0100. Change-aware offline integrity

- Status: accepted on merge
- Date: 2026-10-21

## Motivation

The Offline integrity workflow took about nine minutes on pull requests that
did not change Python, dbt, or the frozen analyst files. The required checks
are the job names `Offline integrity / offline` and
`Offline integrity / portfolio`. A workflow-level `paths` filter would leave
those checks pending, so a docs or display change could not merge while the
ruleset requires them and requires the branch to be up to date.

## Decision

Pull requests select steps inside the existing jobs. The job ids stay
`offline` and `portfolio`, and neither job sets a display name. A `changes`
job checks out the history and runs `scripts/ci_offline_changes.py`. That
script is the filter config. Each selected step uses

`needs.changes.result != 'success' || needs.changes.outputs.<step> == 'true'`.

If classification fails, the changes job still emits every step, and a failed
changes job makes the two downstream jobs run every step. There is no
`paths` or `paths-ignore` key. The owner does not edit the ruleset: the
required check names are unchanged. Do not add `Offline integrity / changes`
as a required check. On 2026-10-21,
`GET /repos/jfk-ssa/chess-analytics-lab/rulesets/24828352` showed
`main-protection` with enforcement disabled, an empty
`required_status_checks` list, and
`strict_required_status_checks_policy` true. That stored list has nothing to
update. If the owner later requires the two existing names, those names
already match this workflow.

Only a `pull_request` event is selective. `push` to `main`,
`workflow_dispatch`, `merge_group`, and `schedule` run every step. There is
no cron. Adding one later still runs the full suite, because any event other
than `pull_request` does.

A file that matches no category runs every step. An empty diff does too,
the same as a diff that could not be read. So do changes to `.github/**`,
`pyproject.toml`, `uv.lock`, this classifier, and
`tests/test_ci_offline_changes.py`. `reports/**` other than
`reports/live-eval-receipt-*` is an explicit fail-open prefix with the same
effect. The audit fails when a tracked path is neither classified nor listed
there.

| Category | Paths | Steps a pull request runs |
|---|---|---|
| docs | `docs/**`, root `*.md` except `THIRD_PARTY_NOTICES.md`, `LICENSE`, `auxiliary-examples/**` | Checkout, the map audit, and the selection record |
| site | `site/**`, `scripts/templates/**`, `biome.json`, `tests/js/**`, import fixtures, `scripts/check_game_import.mjs` | Biome, the Node import checks, and `tests/test_game_import.py` |
| hosted | `hosted/**`, `data/public/**`, `data/README.md`, `.streamlit/**`, `THIRD_PARTY_NOTICES.md` | Ruff, Ruff format, basedpyright, `tests/test_public_extract.py`, and the portfolio job |
| python | `src/**`, Python and shell scripts, `tests/**/*.py`, `config/**`, most of `tests/fixtures/**` | Node setup, both pytest steps, Ruff, format, basedpyright, the demo, the MCP protocol test, the tiny transform, semantic validation, and the analyst gate |
| dbt | `dbt/**`, `contracts/**`, `docs/DBT_LINEAGE.md` | Node setup, both pytest steps, the tiny transform, semantic validation, the analyst gate, and slim dbt state selection |
| analyst | `src/chess_analytics/analyst/**`, `evals/**`, `reports/live-eval-receipt-*`, the live-eval fixture, `docs/METRICS.md` | Node setup, both pytest steps, the analyst gate, semantic validation, the tiny transform, and the portfolio job |

`src/chess_analytics/analyst/**` also matches python, so an analyst code
change runs the python set. The full pytest step includes
`tests/test_public_extract.py` and `tests/test_game_import.py`, so those
narrower commands stay off when it runs. The import test shells out to Node,
so Node setup runs whenever the full pytest step does. Other tests stay on
the full run. Ruff, format, and basedpyright run for python and hosted
changes. They are not the time.

The public-extract size budget is `tests/test_public_extract.py`. Hosted and
`data/public/**` changes run that file. `THIRD_PARTY_NOTICES.md` is hosted
too, because the hosted dashboard test reads the Streamlit pin from it.
`src/chess_analytics/public_extract.py` and
`scripts/build_public_extract.py` are python, so they run the full pytest
step, which includes the same test. `docs/METRICS.md` is a frozen preflight
input, so it is analyst as well as docs and runs the gate and both pytest
steps. Analyst, eval, and live-eval receipt changes run the gate, both pytest
steps, and the portfolio job. Those guards are not skipped.

`python3 scripts/ci_offline_changes.py --audit` checks the workflow against
the catalog, and the offline job runs it even when the other steps are
skipped. Pytest repeats that audit and the category fixtures.

## Evidence

Ten successful runs on 2026-10-21, jobs `offline` and `portfolio`. The run
ids are 39573039885, 39569744454, 39565639588, 39564289206, 39564222989,
39553723369, 39550522492, 39545491973, 39543070270, and 39541953315. The
median offline wall was 530 seconds (range 358–559). The median portfolio
wall was 25 seconds. GitHub records whole seconds. The two pytest steps are
the critical path: median 156.5 seconds without the dbt extra and 294.5
seconds with `CHESSLAB_REQUIRE_DBT=1`. The sum of the median command times
in the offline job is 516 seconds. Checkout and job setup make up the rest
of the 530.

Skipped time below is the sum of those historical medians for steps the
category does not run. Portfolio time was parallel with the offline job, so
it is not added again. The new `changes` job is one full-history checkout
and is not in those ten runs. Narrow pytest files were not separate steps in
those runs, so their duration is not a median here.

| Category | Measured offline seconds skipped | Critical-path minutes saved |
|---|---:|---:|
| docs | 516 | 8.6 |
| site | 498 | 8.3, minus `tests/test_game_import.py` |
| hosted | 348.5 that are not replaced, plus up to 156.5 from the full pytest step | at least 5.8, up to 8.4 |
| python | 25 | 0.4 |
| dbt | 20 | 0.3 |
| analyst, evals, receipts | 34 | 0.6 |
| workflow, lockfile, unknown path, `main`, manual, merge group, schedule | 0 | 0 |

Hosted keeps Ruff, format, basedpyright, and the portfolio job, and it
replaces the 156.5-second pytest step with `tests/test_public_extract.py`.
The 5.8 minutes are the dbt pytest step and the other offline steps that
hosted does not run. Python and dbt keep both full pytest steps because
those files do not have a narrower owner. Analyst paths keep the gate and
both pytest steps on purpose. Node setup is one historical second, so python,
dbt, and pure analyst skip one second less than a suite that left Node off.

This pull request changes the workflow and the classifier, so its own run
selects every step. The unit fixtures are the category proof. No live model
call was made.
