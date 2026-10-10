# Status — 2026-10-10

**M0–M7 accepted locally; M8 routing and end-to-end Jev comparisons measured, with no production promotion. Portfolio hardening verified locally and in a fresh export; GPL-3.0-or-later selected for original project code.** Projects 1–3 remain together. The public repository is
https://github.com/jfk-ssa/chess-analytics-lab.
Decision records are indexed in [DECISIONS.md](DECISIONS.md). Milestone counts and retained failures are in the [evidence index](EVIDENCE_INDEX.md). The previous long verification log in this file remains in Git history.

## Checkout structure — 2026-10-10

Milestone packages live under `src/chess_analytics/` as `marts`, `corpus`, `dashboard`, `analyst`, and `orchestration`. Plan recovery, pricing, and frozen preflight sit beside the Responses adapter. `provider` and `experiment` still re-export the functions tests and scripts import. The twelve copied month and holdout builders are one `chesslab m7 --campaign` command. Historical preflight JSON still names the old scripts. Offline CI runs on pushes to `main` and on pull requests, with Ruff format checking, basedpyright on `src/`, and Actions pinned to commit SHAs.

With the dashboard and docs extras installed, the locked offline suite passed **121 tests** and skipped 15. Ruff check, Ruff format, and basedpyright passed. The tiny source hash stayed `130df65e85d18e78bbafd89daf6696c2596e03abf939adf47f2dcbdc4d33e75b` and the draw rate stayed 0.2. The snapshot id is `bcdba5157163d9fd032a50fa` because the implementation hash includes the moved modules. No live calls.

101 report files that nothing in the checkout names were removed. They remain on tag `archive/reports-before-main-prune-2026-10-10` at `2fa1fbb`. December Sol runs, the M6 v2 run and audit triples, and every eval case file stay.

## Publication and presentation

### Public transposition insights — 2026-10-10

Branch-local implementation separates Transpositions from Opening learning and
adds the opening-position metric registry, dynamic definition count, metadata and
sitemap. Report 1.1.0 adds alternative-route share, N=1..20 union coverage and
marginal gains, complete family/ECO breadth, and three public move-sequence lenses.
Coverage/depth charts, a bounded ranked-position scatter, and route comparisons
share accessible tables and keyboard controls. Existing cohort/family figures,
arrival routes and continuations reconcile exactly with the earlier report.

The d4/g3 lens contains 16,647 Elite and 20,745 public games. Independent raw-visit
checks pass for 64 rankings, 1,280 curve points and 668 position details. The first
independent query exceeded its 2GB temporary-storage cap; the bounded retry passes
without raising the cap. That failure remains in the receipt. No source corpus,
frozen evaluation, engine work, personal collection or live provider call changed.

Locked docs/dashboard offline suite: **137 passed, 15 skipped**. Ruff check/format
and basedpyright pass. The seven-page build checks **303 links**. Browser checks
cover all 64 cohort/family/lens/ranking views, charts, board updates, keyboard chart
selection, metric search and learning-page separation, with zero console errors.
A 487-CSS-pixel narrow viewport has no page-wide overflow. Screen-reader and
physical-phone behavior remain untested. Hosted CI and deployment are separate.
[ADR 0070](adr/0070-public-transposition-insights.md) records this delivery scope.

### Measured opening-position explorer — 2026-10-10

Implemented a separate White opening visit publication over all **1,042,346**
selected games: **8,338,768** visits at plies 6–20, with full FEN, canonical keys,
complete UCI arrival prefixes, next moves and source/game lineage. The immutable
derived snapshot is `bd299fb6ebbced2145f1161b`, based on checked opening corpus
`00e7a73fbf67c401e23b4b4b`. Published visit artifacts occupy **436,694,803 bytes**.
Original corpus and frozen evaluations remain intact; no new acquisition or live calls.

The [position report](../reports/opening-positions.json) separates the **240,086**
Elite games and **802,260** public prefix games. Top 20 transposing positions reach
**56,861** distinct Elite games (**23.68%**) and **115,042** public games (**14.34%**).
Each game counts once per board; repeated-position arrival prefixes do not add
acyclic move orders. Family views use their own recorded-label denominators.
The website adds rankings for recurring/transposing boards, twelve opening-family
filters per cohort, boards, route shares, observed continuations, complete family
counts and convergence by depth. Strategic lessons and measured learning benefits
remain proposed. [ADR 0069](adr/0069-measured-opening-position-explorer.md) records scope.

Independent raw-visit checks reconcile game counts and top-10/top-20 union coverage
for all **52** published rankings. The locked docs/dashboard offline suite passes
**135 tests**, with 15 skips; Ruff check/format and basedpyright pass. Site build
checks **242** links and generates 420 board SVGs. Browser checks cover cohort and
family filters, ranking mode, keyboard row selection, board updates and console
errors. Checked desktop/narrow widths are 1500/487 CSS pixels with no page-wide
overflow; narrow row selection moves focus to the board panel. Screen-reader use
and a physical phone were not tested. See the [publication receipt](../reports/opening-positions-checkpoint.json).
Hosted checks/deployment remain separate from these local results.

### Site review improvements — 2026-10-09

Implemented an evidence-led portfolio homepage, explicit opening-learning status,
fixed moved source links, offline path/anchor validation, readable comparison
disclosure, mobile navigation and darker accent text. All six current guides have
distinct metadata, canonical/share tags and local favicon/sharing assets. Original
comparison report bytes remain intact. Retained routing predictions reconcile to
the published 35/40 rules, 39/40 and 37/40 Jev, 39/40 Decisions historical scores,
and 8/24 rules versus 23/24 Decisions fresh scores. The fresh 0.70 gate accepts
17/24 with zero observed accepted errors. No new live evaluation or ingestion.

The locked docs/dashboard offline suite passed **123 tests**, with 15 skips for
absent real data or optional components. Ruff check and format passed. The site
build checks **229** links. Browser verification covered all six guides, keyboard
pipeline/board/disclosure controls, search and denominator updates. At the narrow
browser viewport (443 CSS pixels), the header is non-sticky and checked pages
have no page-wide overflow. Screen-reader behavior and a physical phone were not
tested. See [site review verification](../reports/site-review-verification.json).
These are branch-local results; new hosted CI and deployment are separate gates.

The documentation site is [public](https://jfk-ssa.github.io/chess-analytics-lab/).
Current guides and the dashboard use Inter Medium; see [the visual guide](DESIGN.md)
and [the website runbook](SITE.md). Pages deployment
[37939389092](https://github.com/jfk-ssa/chess-analytics-lab/actions/runs/37939389092)
and offline integrity CI
[37939389093](https://github.com/jfk-ssa/chess-analytics-lab/actions/runs/37939389093)
passed on `814ffe9`. GitHub reports the repository `PUBLIC`.

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

- Current tiny demo on this checkout: snapshot `bcdba5157163d9fd032a50fa`, source SHA-256 `130df65e85d18e78bbafd89daf6696c2596e03abf939adf47f2dcbdc4d33e75b`, draw rate 0.2. Snapshot ids include the implementation hash, so a source-tree change produces a new id.
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

Live model calls stay disabled until personal configuration and an explicit spending cap exist for that run. The M7 December Sol gate closed at **$0.35392836** cumulative accounted gross under the approved $6 cap. Earlier failed gates stay in the reports. The M6 caps are closed. Model and pricing defaults were last checked against the official model page on 2026-10-04.

Install with a non-editable wheel. The environment pin and the macOS editable-path failure are in [ADR 0002](adr/0002-environment.md). Offline reproduction uses installed or cached dependencies.

M1 and M2 cover fixed complete Lichess exports and one local writer. The 2013 archive is ingestion evidence. M3 and the later month sources are ordered archive prefixes. Opening labels come from provider tags. Clock and evaluation coverage is sparse; the >=200-centipawn deterioration measure is exploratory. M4 intervals describe focal-player resampling inside the observed prefix. M5 free-form SQL stays disabled. Inspected holdouts stay retired for any future untouched model claim. Optional Dagster and Prefect adapters are local demonstrations. Stockfish enrichment, OpenRouter, restricted SQL, and the recommender stay follow-ups. No new live study is authorized by this checkout.
