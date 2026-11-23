# 0122. Harden CI workflows and trial module-scoped dbt test distribution

- Status: Accepted for PR A; PR B remains proposed
- Date: 2026-11-22

## Context

ADR 0100 made `Offline integrity` the required gate: every PR runs every
job, path-based selection happens inside jobs, and `main` pushes run
everything. ADR 0119 removed duplicate workflows. Timing data from the
last 40 Actions runs and from the `--durations=15` output of the last
three green `offline` and `offline-core` runs (#100 PR runs at `50d68db`
and `13bc819`, and the `main` push at `5633279`) shows:

- The PR critical path is `changes` (median 6s) then `offline` (median
  152s, p90 155s). `offline-core` (median 100s) and `portfolio` (46s)
  finish earlier.
- `pytest_dbt` is 16 tests on `-n 4` and takes 54–72s. Two test bodies
  set its floor: `test_m2.py::test_dbt_recovery_backfill_and_drift`
  (29–39s) and
  `test_incremental_player_games.py::test_incremental_matches_full_refresh_until_the_key_or_filter_breaks`
  (28–39s). Fixture setup that repeats across workers adds about
  25–35s, mostly the two `test_eval_gate.py` mart setups (10–13s each)
  and three `test_semantic_layer.py` setups (6–11s each).
- `offline-core` (638 passed, 56 skipped, 72–101s) is dominated by test
  bodies in `test_live_eval_runner.py` and `test_grok_live_eval.py`
  (4–26s each), not fixtures.
- No job outside `live-eval.yml` sets `timeout-minutes`, so a hang such
  as the `chess.engine.id` wait recorded in ADR 0113 would hold a PR for
  GitHub's 360-minute default.
- `offline.yml` and `pages.yml` set `cancel-in-progress: true` on
  `github.ref`, so back-to-back merges cancel a running `main` full
  suite or a Pages deploy.
- No `astral-sh/setup-uv` step enables its cache.
- `pytest_dbt` still requires `setup_node` in
  `scripts/ci_offline_catalog.py`, left over from before ADR 0113. No
  `-m dbt` test calls Node.
- Generated steps have an `id` but no `name`, so `semantic` and
  `dbt_slim` both appear in Actions as `Run set -euo pipefail`.

## Decision

Two PRs, built after ADR 0120 PR 2 merges (that PR also edits
`pages.yml` and the catalog) and rebased on it.

### PR A — `ci: add job timeouts, keep main runs, and cache uv`

1. Set `timeout-minutes` on every job in `offline.yml`, `pages.yml` and
   `pr-title.yml`: `changes` 5, `offline` 15, `offline-core` 15,
   `portfolio` 10, Pages `build` and `deploy` 10, `pr-title` 5. These
   are about 5x the observed p90.
2. Set `cancel-in-progress: ${{ github.ref != 'refs/heads/main' }}` in
   `offline.yml` and `pages.yml`. PR pushes still cancel stale PR runs.
3. Set `enable-cache: true` with a per-job `cache-suffix` on every
   `setup-uv` step outside `live-eval.yml`, and add `--no-sync` to the
   `uv run` calls in `offline-core`, `portfolio` and `pages.yml` that
   follow an explicit sync.
4. Remove `setup_node` from `pytest_dbt.requires`; Node stays for
   `site`, `pytest_game_import`, `offline-core` and full runs.
5. Emit `name:` for every generated step in
   `scripts/ci_offline_generate.py`.

Managed `offline.yml` blocks change only through the catalog and
`scripts/ci_offline_generate.py`. ADR 0100's guarantees are unchanged:
no `paths` filters on required workflows, fallback and full runs still
select everything, and the Pages deploy guard is untouched.

### PR B — `perf(tests): keep dbt test modules on one xdist worker`

Change only the `pytest_dbt` command from `-n 4` to
`-n 4 --dist loadscope`, so each module's tests share one worker and its
module- and session-scoped fixtures build once. Keep the change only if
the median of three hosted `pytest_dbt` runs falls by at least 10s with
identical passed and skipped counts. Otherwise revert it, record the
numbers here, and don't build cross-worker file locks without a new
decision. Expected result is about 45–50s, because the two long test
bodies set a floor near 40s.

## Consequences

- Expected savings are modest: about 15–25s off the PR critical path
  and 0.5–1 billable minute per code PR. The main gain is reliability:
  bounded hangs, `main` runs and deploys that are never cancelled, and
  less PyPI exposure.
- `loadscope` can unbalance workers. The gate in PR B catches that.
- The uv cache adds an Actions cache entry per job, well inside the
  repository cache quota.

## Alternatives considered

- **Cross-worker fixture locking with `fcntl.flock`** (proposed in an
  external Gemini 4 Neon plan). Rejected for now: 150–250 lines for a
  gain bounded by the two long test bodies.
- **Sharing fixtures in `offline-core`.** Rejected: its time is in test
  bodies. Speeding those means changing eval-runner bootstrap or repeat
  counts, which touches eval logic and needs its own decision.
- **Replacing CodeQL default setup with a path-filtered workflow.**
  Deferred: it saves billable minutes, not critical path, and needs a
  repository settings change by the owner.
- **Skipping the Pages artifact upload on PRs.** Rejected: ADR 0120 PR 2
  uploads a PR preview build.
- **`paths` filters on `offline.yml`, a fourth job, or larger runners.**
  Rejected by ADR 0100 or overbuilt for this repository.

## Planned commits

PR A:

1. `ci: add job timeouts and keep main runs uncancelled`
2. `ci: cache uv and skip redundant syncs`
3. `ci: drop Node from dbt tests and name generated steps`

PR B:

1. `perf(tests): keep dbt test modules on one xdist worker`

Verification for both: `ruff check`, `ruff format --check`,
`scripts/ci_offline_generate.py --check`,
`scripts/ci_offline_changes.py --audit`,
`pytest -q tests/test_ci_offline_changes.py`, the full suite on the PR,
and before and after medians from hosted `--durations=15` output.
