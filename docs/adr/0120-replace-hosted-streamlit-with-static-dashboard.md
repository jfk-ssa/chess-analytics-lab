# 0120. Replace the hosted Streamlit app with a static Pages dashboard

- Status: Accepted for PR 2; deployed page accepted 2026-11-23; PR 3 retires the hosted app
- Date: 2026-11-22

## Context

The repository now ships three overlapping presentation layers:

- The Community Cloud app under `hosted/`, which queries
  `data/public/dashboard_cube.parquet` and still reads extract version 2
  for live eval ([ADR 0094](0094-hosted-read-only-dashboard.md),
  [ADR 0101](0101-hosted-bi-cube.md),
  [ADR 0107](0107-hosted-repository-source-reload.md)). The configured URL is
  https://chess-analytics-lab.streamlit.app/.
- The local Streamlit app at
  `src/chess_analytics/dashboard/dashboard.py`, which opens the local
  analytical warehouse and has six views: Overview and coverage,
  Opening comparisons, Clock pressure, Data quality, AI analyst, and
  Evaluation results.
- The GitHub Pages site built by `scripts/build_docs_site.py`, including
  the live-eval report and the transposition explorer.

The hosted app is the expensive surface. `hosted/requirements.txt` pins
nine packages. `tests/test_hosted_dashboard.py` includes
`test_hosted_streamlit_pin_matches_the_lock`, which breaks when a
Dependabot bump moves Streamlit, pandas, narwhals, or the other hosted
pins until the test, the requirements file, and often the docs are
updated together. Community Cloud reload quirks also produced
`hosted/repo_import.py` and the hand-bumped
`src/chess_analytics/build_info.py`, which only the hosted page and its
tests use.

`chesslab demo` does not launch Streamlit. It imports
`clock_analysis` and `opening_catalog` from
`src/chess_analytics/dashboard/analysis.py`. Checked analyst tools also
import coverage helpers from that module. The local six-view app is
exercised by
`tests/test_portfolio_demo.py::test_six_dashboard_views_and_empty_buckets`
and by `scripts/check_m4_dashboard.py`.

The committed cube is warehouse-less: 593,637 bytes and 35,100 rows at
this checkout, under the 10 MB budget from ADR 0101. Aggregate grains
omit game identifiers; `clock_game` permits the public eight-character
`lichess_id`, `white_rating`, and `black_rating`, plus the public game
fields allowed by [ADR 0106](0106-clock-band-game-sample.md). Player
names, `player_key`, header JSON, and fingerprints remain excluded.
JSON export must preserve that boundary, the ten-game count floor,
and the capped game sample. Pages already serves interactive charts
with Inter, paper, teal, and the shared site tokens
in `site/assets/site.css` ([ADR 0060](0060-inter-medium-selected-for-current-guides-and-dashboard.md),
[ADR 0065](0065-shared-outer-canvas-and-semantic-table-columns.md),
[ADR 0118](0118-portfolio-page-presentation.md)).

## Decision

Build a static, interactive `dashboard.html` on GitHub Pages from
`data/public/dashboard_cube.parquet`, then retire the Community Cloud
app once that page is live and reviewed. Keep the local Streamlit
dashboard as an optional warehouse tool. This record is the plan; the
implementation uses two separately merged pull requests.

The four-PR sequence is: 1 CI cleanup and pruning
([ADR 0119](0119-deduplicate-workflows-and-prune-stale-extras.md)),
2 static dashboard publish, 3 retire hosted Streamlit (both here),
4 scoped hash ([ADR 0121](0121-scoped-implementation-hash.md)).
PR 3 requires recorded acceptance of PR 2's deployed page.

The Pages dashboard is a CI artifact of the documentation workflow. The
build reads the committed cube, or a JSON view produced from it at
build time, and emits `dashboard.html` plus any small assets it needs.
It does not open a warehouse, call MetricFlow, or download. Filters and
charts follow the existing hosted cuts where the cube already supports
them: date, time control, color, rating band, and opening family on the
KPI strip, openings, transpositions, clock, and periods. Keep captions
for filters a grain cannot carry; never widen a carried filter's empty
cut to the full population. Live-eval
figures stay on `live-eval.html` and keep ignoring those dashboard
filters, as they do today. That page reads `reports/live-eval-receipt-*.json`
and the case set directly through `build_docs_site.live_eval`; it does
not read `dashboard_extract.json`.

Games, results, opening views and periods use only `rated_public`, including
date fallbacks and prior-period comparisons; never sum across cohorts. Default
dates use that cohort's bounds.
Clock slices and samples retain their separate `m3_august_prefix` population.
All-color result rates explicitly name White perspective. Count bars start at
zero; rate bars start at 90% of the displayed minimum and end at the highest
displayed rate, with both bounds in the caption.

Provenance has two distinct inputs. The cube supplies chart rows and
has no mart id, source snapshot, or build hashes in its columns.
Validate `data/public/dashboard_extract.json` and read its `build`
record (source snapshot, model, lock, semantic-manifest hashes) and
the `game_draw_rate` metric receipt's mart id for a labelled **extract
provenance** panel. These do not establish the origin of every cube
grain. Cube provenance records the committed Parquet path, byte
SHA-256, row count, grain counts, and site source revision; name its mixed
published populations and do not invent a cube-wide mart id. Record
both input paths and byte hashes in `site-build.json.sources`, and
their separate provenance scopes and extract build fields in that
manifest. Record generated JSON hashes in `site-build.json.outputs`.
Tests must detect either input changing and prevent extract metadata
being presented as cube-wide lineage. Keep the extract after retirement
for this provenance panel, independently of the live-eval page.

Charts and layout reuse the Pages visual system: Inter, `--paper`,
`--ink`, `--teal`, `--accent`, `--line`, the 1120px canvas, and the
existing chart patterns in `site/assets/`. Do not add a new font, a
new palette, or a Streamlit-like chrome. Prefer the client-side
patterns already used on the transpositions and live-eval pages over a
new Python charting dependency in the Pages job.

Keep `src/chess_analytics/dashboard/analysis.py`. Keep
`src/chess_analytics/dashboard/dashboard.py` and the dashboard extra
for local use. `chesslab demo` continues to call the analysis
functions and does not start Streamlit. The local app stays useful
because it queries the local warehouse, including fixture replay on the
AI analyst view, which a public cube page cannot do. After the hosted
app is retired, the dashboard extra no longer has to satisfy the
Community Cloud pin contract; leftover hosted-only pins can shrink in
the retirement commit.

Rollout uses separate merge gates:

1. **PR 2 — publish.** Add `dashboard.html`, its assets, provenance,
   navigation, and current guide links. Keep hosted code and coverage.
   Ship Python build/export tests and JavaScript tests in this PR,
   wired into `.github/workflows/pages.yml`, `offline.yml`, and the
   shared classifier catalog from PR 1. The existing Node command
   names only `tests/js/game_import.test.mjs`; extend the catalogued
   command to include the dashboard tests. Select Node setup and those
   tests for dashboard assets/templates/tests, builder/analysis changes,
   and either public input (`dashboard_cube.parquet` or
   `dashboard_extract.json`), including cube-only diffs. Select the
   Python cube/export tests on those diffs too. Update outputs,
   support dependencies, ordering checks, and classifier tests atomically.
   Test filter parity against `dashboard_cube.py` for all supported
   cuts, unsupported-grain captions, empty cuts without population
   widening, KPI prior-period deltas, opening family/line/position
   drills and breadcrumbs, and clock-band game sample filters/caps.
   Keep the August fallback and eligible/evaluable labels explicit.
   Cover missing/invalid inputs and the public-field boundary.
   Verify docs-only skips and full/failure selections still follow
   ADR 0100. Run build tests in Pages CI and the selected Node tests
   in offline CI; adding test files alone is insufficient.
   Upload a downloadable PR-time artifact of `work/docs-site`,
   including `site-build.json`, with local HTTP preview instructions.
   Keep the Pages deploy guard: PR builds preview as artifacts; only
   the existing main/non-PR path deploys. After merge and successful
   deployment, John reviews the public page on desktop and mobile,
   including filters, empty cuts, drills, and provenance. Record his
   acceptance, deployed URL, source revision, and build/run link in
   PR 3 before merging retirement; the PR preview is not this gate.
2. **PR 3 — retire.** After that recorded acceptance, delete `hosted/`,
   `src/chess_analytics/build_info.py`, and
   `tests/test_hosted_dashboard.py` (including the pin contract).
   In the same commit, remove that test from `offline.yml`'s explicit
   `pytest_portfolio` command and the shared catalog, and update audit
   fixtures. Keep local portfolio/demo tests and the new static
   coverage selected, including cube-only changes. Keep the cube,
   builders, and extract. Shrink hosted-only pins after checking local
   app needs. Update current links in README, portfolio, site sources,
   status, and guides to
   `https://jfkbot.github.io/chess-analytics-lab/dashboard.html`;
   preserve historical ADR URLs and receipts. Make
   `docs/HOSTED_DASHBOARD.md` the current Pages guide with the ADR trail.
   Before the deletion merges, John manually removes the deployment
   from his Community Cloud workspace: open the app's overflow menu,
   choose Delete, enter the required confirmation string, and confirm.
   Record completion in PR 3. Repository deletion does not perform
   this operation. Follow the official
   [delete-your-app instructions](https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app/delete-your-app).
   The old URL ceases to serve the dashboard; do not promise a redirect
   or a residual notice after deletion.

Rollback: revert PR 3's repository changes, including workflow/catalog
edits. John must manually redeploy in Community Cloud from `main`,
entrypoint `hosted/dashboard.py`, Python 3.12, using the restored
`hosted/requirements.txt`; select the old subdomain if available and
verify the page. A git revert alone does not recreate the deleted app.
If PR 3 has not landed, reverting PR 2 leaves hosted Streamlit intact.

## Consequences

Dependabot bumps of Streamlit, pandas, and narwhals stop breaking a
hosted pin test. Community Cloud reload workarounds go away. The public
dashboard becomes a static Pages artifact next to the rest of the lab
site, reviewed with the existing documentation suite.

The Streamlit URL stops resolving as a dashboard. Anyone with an old
link depends on the updated repository links to find Pages. Historical
ADRs retain the old URL as evidence. The local six-view app remains,
so the dashboard extra and some Streamlit tests stay until a later decision
retires that optional tool.

PR 2 may exceed the 400-line guideline for the page and its tests;
PR 3 contains the later hosted deletion. Generated output stays outside
that count. Retirement cannot be bundled into the publication merge.

## Alternatives considered

Retire both Streamlit apps and keep only Pages. Rejected: the local
app is the warehouse-backed six-view product, it is already tested, and
`chesslab demo` plus the analyst tools still need
`dashboard/analysis.py`. A public cube page is not a substitute for
local replay.

Rebuild the hosted app as a Streamlit page on Pages, or as a "Claude
dashboard" that calls a model. Rejected: the cube is already static,
Pages already has a visual system, and a live model is out of scope
for this product surface.

Keep Community Cloud and add the Pages dashboard beside it. Rejected:
that leaves the pin contract and the three-way overlap this record
exists to end. The hosted app stays only until the static page is
reviewed.

## Planned commits

PR 2 (merge and deploy before acceptance):

1. `feat(pages): publish the cube dashboard with scoped provenance and CI tests`
2. `ci(pages): upload a downloadable PR preview build`
3. `docs: link the Pages dashboard and record the acceptance procedure`

PR 3 (only after recorded deployed-page acceptance):

1. `docs: record deployed acceptance and John's manual Cloud deletion`
2. `chore(hosted): retire app and pins with workflow and catalog updates`
3. `docs: replace current hosted links and preserve historical ADR URLs`

PR 1 is CI cleanup and pruning; PR 4 is the scoped hash change.

## PR 2 acceptance and PR 3 implementation evidence

John accepted the deployed Pages dashboard as the Streamlit replacement on
**2026-11-23 18:49 CT (America/Chicago)**.

- Deployed URL: https://jfkbot.github.io/chess-analytics-lab/dashboard.html
- Site root: https://jfkbot.github.io/chess-analytics-lab/
- Source revision from live `site-build.json`: `214a20b`
  (full SHA `214a20bdadd9bcbd34deac219d9408a59cbd7088`).
- [Pages workflow run 45264591067](https://github.com/jfkbot/chess-analytics-lab/actions/runs/45264591067),
  [build job](https://github.com/jfkbot/chess-analytics-lab/actions/runs/45264591067/job/138008025403),
  [deploy job](https://github.com/jfkbot/chess-analytics-lab/actions/runs/45264591067/job/138008690925).

This is the #105 main deploy, a CI-only change after #103's dashboard
publication at `bb65063`. John accepted the currently deployed page, not a
PR preview. This satisfies PR 3's deployed-page acceptance gate.

### Rollout and rollback

The actual sequence differs from the original Decision's pre-merge Cloud
deletion step: **John will delete the Community Cloud app after PR 3 merges**,
following the official
[delete-your-app instructions](https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app/delete-your-app).
Repository deletion does not remove the Cloud app. Cloud deletion is pending;
no completion date is recorded. Do not promise a redirect from the old URL.

PR 3 removes the hosted code, reload label and pin tests, keeping the local
six-view Streamlit app, its dashboard extra, demo and analysis helpers, cube,
extract and builders. Revert PR 3's repository changes to roll back; if John
has already deleted the app, he must also manually redeploy with the restored
entrypoint and requirements described in the original Decision. A revert
alone cannot restore a deleted Cloud deployment. PR 4 remains proposed.
