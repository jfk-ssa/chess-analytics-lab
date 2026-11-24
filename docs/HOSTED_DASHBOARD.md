# Pages dashboard

Open the [public dashboard](https://jfkbot.github.io/chess-analytics-lab/dashboard.html)
from the [site homepage](https://jfkbot.github.io/chess-analytics-lab/).
John accepted the deployed page as the Streamlit replacement on
2026-11-23 at 18:49 CT (America/Chicago), source `214a20b`,
[Pages run 45264591067](https://github.com/jfkbot/chess-analytics-lab/actions/runs/45264591067).
This is the accepted #105 main deployment, not a PR preview.

The site build exports the committed `data/public/dashboard_cube.parquet`
through `src/chess_analytics/dashboard_export.py`. It validates
`data/public/dashboard_extract.json` for a separately labelled extract
provenance panel. Neither the build nor the browser opens an analytical
warehouse, calls a model or downloads source data. Live-eval results are on
[their separate page](https://jfkbot.github.io/chess-analytics-lab/live-eval.html),
which reads the retained receipts directly.

Date, time control, color, rating band and opening family filter the grains
that carry those dimensions. Unsupported filters have captions; an unmatched
carried filter stays empty. Games/results/openings/periods use `rated_public`:
770,626 games after the cell floor, with nine period bars totaling 802,260.
Clock slices and samples retain the separate August prefix. All-color result
rates name White perspective. Comparable months show prior-period KPI deltas.
Count bars start at zero; rate bars start at 90% of the displayed minimum
and end at the highest displayed rate, with both bounds in the caption.

Drill opening family → line → position → continuations. Transposition cards
show published move orders and their remainder rules. Clock bands count
evaluable moves and reveal at most twelve matching public game samples.
The ten-game aggregate floor, permitted public game fields and sample caps
remain enforced by the cube/export tests.

Expand provenance to inspect the two inputs independently. Cube provenance
contains the Parquet byte hash, row/grain counts and site revision. Extract
provenance contains its validated build record and draw-rate receipt's mart
id; it does not establish cube-wide lineage. `site-build.json` records both
input hashes and generated output hashes.

For local HTTP previews, builds, export checks and the accepted deployment
record, follow [the site runbook](SITE.md#dashboard-acceptance-before-pr-3).
The cube and extract builders remain available for explicit rebuilds from
local inputs; the site build reads the committed files without rebuilding them.

The optional local six-view Streamlit dashboard still opens the local
warehouse. Keep using the [README local run commands](../README.md#five-minute-offline-demo)
and [demo guide](DEMO.md) for that app and fixture replay.

[ADR 0094](adr/0094-hosted-read-only-dashboard.md) records the former hosted
read-only app; [ADR 0101](adr/0101-hosted-bi-cube.md) records the public cube;
[ADR 0107](adr/0107-hosted-repository-source-reload.md) records the former reload
workaround. [ADR 0120](adr/0120-replace-hosted-streamlit-with-static-dashboard.md)
records replacement, deployed acceptance, retirement and rollback. Those ADRs
preserve historical URLs and deployment settings. This guide retains its
filename so existing repository links continue to resolve.

PR 3 removes the hosted repository app. Repository deletion does not remove
the Community Cloud deployment: John will delete it after merge, following
the official instructions linked in ADR 0120. That manual step is pending.
