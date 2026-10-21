# Status — 2026-10-10

**M0–M7 accepted locally; M8 routing and end-to-end Jev comparisons measured, with no production promotion. Portfolio hardening verified locally and in a fresh export; GPL-3.0-or-later selected for original project code.** Projects 1–3 remain together. The public repository is
https://github.com/jfk-ssa/chess-analytics-lab.
Decision records are indexed in [DECISIONS.md](DECISIONS.md). Milestone counts and retained failures are in the [evidence index](EVIDENCE_INDEX.md). The previous long verification log in this file remains in Git history.

## Checkout structure — 2026-10-10

Milestone packages live under `src/chess_analytics/` as `marts`, `corpus`, `dashboard`, `analyst`, and `orchestration`. Plan recovery, pricing, and frozen preflight sit beside the Responses adapter. `provider` and `experiment` still re-export the functions tests and scripts import. The twelve copied month and holdout builders are one `chesslab m7 --campaign` command. Historical preflight JSON still names the old scripts. Offline CI runs on pushes to `main` and on pull requests, with Ruff format checking, basedpyright on `src/`, and Actions pinned to commit SHAs.

With the dashboard and docs extras installed, the locked offline suite passed **121 tests** and skipped 15. Ruff check, Ruff format, and basedpyright passed. The tiny source hash stayed `130df65e85d18e78bbafd89daf6696c2596e03abf939adf47f2dcbdc4d33e75b` and the draw rate stayed 0.2. The snapshot id is `bcdba5157163d9fd032a50fa` because the implementation hash includes the moved modules. No live calls.

101 report files that nothing in the checkout names were removed. They remain on tag `archive/reports-before-main-prune-2026-10-10` at `2fa1fbb`. December Sol runs, the M6 v2 run and audit triples, and every eval case file stay.

## Current state

The documentation site is [public](https://jfk-ssa.github.io/chess-analytics-lab/).
Guides and the dashboard use Inter Medium; see [the visual guide](DESIGN.md)
and [the website runbook](SITE.md). Opening rankings, transposition views, the
site review, and local PGN import are recorded in ADRs 0068–0072 and their
receipts under `reports/`. Generated opening rankings are restored by the pinned
publication hash rather than stored on the branch tip. Default offline checks
validate the pin; the documentation gate restores and verifies the publication
bytes separately (ADR 0074).
The shared header shows five primary guides and a visible Lab strip, with no
Menu or dropdowns (ADR 0076). Checked tools can also be served read-only over
stdio to an external MCP client (`chesslab mcp`, optional `mcp` extra); see
[MCP](MCP.md) and [ADR 0077](adr/0077-stdio-mcp-checked-tools.md). Guarantees
are per call. On-demand local engine checks and opening-continuation lookups
are checked tools ([ADR 0078](adr/0078-engine-grounded-checked-tools.md));
engine_v1 measures those tools on fixed cases ([ADR 0079](adr/0079-engine-tool-evaluation.md))
as harness and tool behavior, not model accuracy, and corpus-wide Stockfish
enrichment remains a follow-up. A recorded session on the real August prefix
is in [the worked example](MCP_EXAMPLE.md) ([ADR 0080](adr/0080-mcp-worked-example.md)).
`predict_human_moves` estimates a rating-conditioned legal-move distribution
from a local Maia-3 checkpoint
([ADR 0081](adr/0081-human-move-prediction-maia3.md)). The weights are not in
the repository. `maia_v1` checks four displayed probabilities with tolerance
1e-4 on the measured platform
([ADR 0082](adr/0082-maia-calibration-and-d4-repertoire.md)).
The measurement plan for the local November 2025 elite file and one pinned
public prefix is [ADR 0083](adr/0083-maia-corpus-calibration-plan.md).
Measured scores from the two runs are in
[ADR 0084](adr/0084-maia-corpus-calibration-results.md).
`python -m chess_analytics.analyst.maia_corpus` scores one of those
populations at a time and writes one gitignored JSON file and one gitignored
Markdown file.

Holdout periods and game counts are the opening-corpus training index in
[opening-corpus.json](../reports/opening-corpus.json). No played-move log-loss
has been computed from those games.

Core draw-rate, opening-usage, and opening-score metrics read a matching published mart and otherwise keep the reviewed SQL ([ADR 0085](adr/0085-governed-semantic-layer-metricflow.md)).
Unit tests, enforced mart contracts, exposures, a committed lineage diagram, and slim state selection are in [ADR 0086](adr/0086-dbt-engineering-depth.md).
An incremental `player_games` was measured on synthetic scale and not adopted; publication stays a from-scratch rebuild ([ADR 0087](adr/0087-incremental-player-games.md)).
An offline gate replays the deterministic analyst stack and fails when the scorecard differs from the committed baseline; it does not measure LLM quality ([ADR 0088](adr/0088-offline-analyst-eval-regression-gate.md)).
The live-eval plan, fixture, and 48-case set have an offline scorer, runner, and statistics, and a manual `workflow_dispatch` job ([ADR 0089](adr/0089-llm-quality-evaluation.md), [ADR 0090](adr/0090-live-eval-scorer-runner-stats.md), [ADR 0091](adr/0091-manual-live-eval-workflow.md)). The first two artifact receipts are committed under `reports/` ([ADR 0093](adr/0093-first-live-eval-receipts.md)). The documentation site renders those receipts, and any later `reports/live-eval-receipt-*.json`, as the Lab page [live eval](https://jfk-ssa.github.io/chess-analytics-lab/live-eval.html) ([ADR 0096](adr/0096-published-live-eval-report.md)). This checkout does not call a model. Push and pull-request CI do not run the live job, and there is no schedule.
A later hosted read-only dashboard will read the committed aggregate extract in `data/public/dashboard_extract.json` ([ADR 0092](adr/0092-public-aggregate-extract.md)). The opening-corpus training count and the August prefix counts stay separate lineage stages. On 2026-10-20 the extract was rebuilt with MetricFlow from mart `9d3ca923a6f1cd06d82a8645`: `game_draw_rate`, `opening_usage`, and `opening_player_score` are `metricflow`, and the four clock buckets are `reviewed_sql`. Adjusted score, bootstrap, and lineage counts stay `committed_report`. Re-ingestion after an implementation-hash change produced source snapshot `7764247e6bdb0b6e73420253` from the same pinned prefix, and the live counts matched the committed M3 reference exactly.

This file stays a short summary: checkout structure, phase tracker, dataset
versions, and limits. New decisions go only into [docs/adr](adr/). Do not append
measurement logs here. Earlier verification logs remain in Git history.

## Phase tracker

| Phase | State | Next gate |
|---|---|---|
| M0 bootstrap | Done | Accepted offline environment and fixtures |
| M1 vertical slice | Done | Accepted bounded foundation ingestion and reference metric |
| M2 reliable platform | Done | Accepted dbt/recovery/operational checks locally |
| M3 analytical corpus and metrics | Done | Accepted bounded prefix, observed coverage, independent checks, 12 draft dev cases |
| M4 analytics product | Done | Accepted local six-view dashboard and two reproducible memos |
| M5 analyst/eval harness | Done | Accepted checked typed tools, fixture replay and 50-case harness; no model result |
| M6 measured release | Done; typed-analyst release gates met | Three complete frozen v2 repetitions, 118/120 scored passes, all evidence audits and offline checks passed. See [release checkpoint](M6-RELEASE.md). |
| M7 depth | Done; December Sol v12 gate accepted | Three complete frozen repetitions scored 50/50 each with 150/150 evidence audits, no repairs/retries, and $0.35392836 cumulative accounted gross under the approved $6 cap. Earlier failed/stopped gates remain retained. See [December checkpoint](M7-DECEMBER.md). |
| M8 Jev | Routing and paired final-answer comparisons measured; no production promotion | [Route checkpoint](../reports/M8-routing-checkpoint.json): rules 35/40; Jev passes 39/40 and 37/40; existing analyst 33/40. [End-to-end checkpoint](../reports/M8-e2e-checkpoint.json): both arms 31/32 after versioned offline rescore; Jev costs slightly more. Eight new boundary labels received owner review. See [end-to-end lab](JEV_END_TO_END.md). Compatible DuckDB extension remains an optional isolated exercise. |
| M8 Decisions extension | Measured optional classifier; no production promotion | Owner-reviewed 24-case language holdout: 23/24 on each of three repetitions; rules 8/24. Development-selected 0.70 threshold accepts 17/24 with zero observed errors. Historical retained-answer replay stays 31/32 and costs more. Six live Decisions runs / 184 requests cost $0.0068145 gross under $0.05. [Runbook](DECISIONS_ROUTING_RUNBOOK.md), [checkpoint](../reports/decisions-checkpoint.json). Fresh paired Jev/analyst evaluation remains a separate optional gate requiring new estimates and caps. |
| Portfolio readiness | Integrity, offline demo, docs, clean export and license verified locally; hosted CI passed; repository public | [Implementation evidence](EVIDENCE_INDEX.md), [final review](FINAL_RELEASE_REVIEW.md) and [handoff record](PORTFOLIO_HANDOFF.md). |
| Documentation website | Published; deployment and integrity CI passed | Homepage + four guides; original report preserved; [runbook](SITE.md), [checkpoint](../reports/docs-site-checkpoint.json). |
| Personalized recommender | Backlog | Outside first-release scope |

An [auxiliary examples folder](../auxiliary-examples/README.md) holds a
publicly adapted executive metric communication example and a data
observability screenshot. The examples are separate from Chess Analytics Lab.
The metric document uses synthetic financial cases and omits named people,
email addresses, customer identifiers, and internal ticket links.

## Current dataset versions

- Current tiny demo on this checkout: snapshot `f2541bd7776d980764465e4b`, source SHA-256 `130df65e85d18e78bbafd89daf6696c2596e03abf939adf47f2dcbdc4d33e75b`, draw rate 0.2. `chesslab demo` on 2026-10-18 printed this id. The source checksum is unchanged. Snapshot ids include the implementation hash, and `gate.py` is part of that hash.
- Foundation source: complete `lichess_db_standard_rated_2013-01.pgn.zst`, 17,761,302 compressed bytes; 92,811,021 decompressed bytes scanned.
- Source SHA256: `aa40b3671fa3cf1072eb182892cd90b0e1e003a4a5943492f64b77e7f3fd1635`.
- Foundation snapshot: `b57f51ff70cc3c1637e641c7` in ignored `data/published/`.
- Earlier recorded tiny snapshot: `0fdc4ce15185898c10b4f155`. Fabricated fixtures, never population data.
- M2 marts over those checked snapshots: foundation `3b34836ba025a78a54e96c46`, tiny `52810ff8c95a2c7f9b0acacd`. IDs also bind the dbt files and uv lock; a clean rebuild after a dependency or source change may use a new ID with the same counts.
- M3 partial source snapshot: `6cf51473f8da6ae6b12ea5c2`; analytical move snapshot: `84a38a404815ed2729917d76`. M3 data are ignored locally; manifests, contracts, references and cases are tracked. The source prefix and extracted PGNs must be reacquired to reproduce these data snapshots elsewhere.
- M4 figures and M5 cases use analytical ID `84a38a404815ed2729917d76`. M5 case-set SHA256 is in [the manifest](../evals/cases/m5_manifest.json).
- Observed foundation UTC dates: **2012-12-31 through 2013-01-31**, counted from the games rather than the archive label. 218 participant ratings are missing and remain null.
- M1 metric/table contract version: 1.0.0; M3 metric contracts are versioned separately. The original M1 implementation commit was `a617582b7df05193485d07721c6f21cccda72df0`. Full code/lock hashes are in current manifests.

## Limits

Live model calls stay disabled until personal configuration and an explicit spending cap exist for that run. The manual live-eval workflow reads `CHESSLAB_OPENAI_API_KEY` from the `live-eval` environment when John dispatches it. This repository does not contain that key. The M7 December Sol gate closed at **$0.35392836** cumulative accounted gross under the approved $6 cap. Earlier failed gates stay in the reports. The M6 caps are closed. Model and pricing defaults were last checked against the official model page on 2026-10-20. The recorded Luna and Sol rates matched that page. `gpt-6.1-sol` does not accept `reasoning.effort` of `none`, so the live-eval id stays `gpt-6-sol`.

Install with a non-editable wheel. The environment pin and the macOS editable-path failure are in [ADR 0002](adr/0002-environment.md). Offline reproduction uses installed or cached dependencies.

M1 and M2 cover fixed complete Lichess exports and one local writer. The 2013 archive is ingestion evidence. M3 and the later month sources are ordered archive prefixes. Opening labels come from provider tags. Clock and evaluation coverage is sparse; the >=200-centipawn deterioration measure is exploratory. M4 intervals describe focal-player resampling inside the observed prefix. M5 free-form SQL stays disabled. Inspected holdouts stay retired for any future untouched model claim. Optional Dagster and Prefect adapters are local demonstrations. Stockfish enrichment, OpenRouter, restricted SQL, and the recommender stay follow-ups. No new live study is authorized by this checkout.
