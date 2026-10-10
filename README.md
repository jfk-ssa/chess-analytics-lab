# Chess Analytics Lab

A local learning and portfolio project connecting a reliable chess data platform,
opening/time-pressure analytics, and an evaluated AI analyst in one repository.
The default demo runs all three on synthetic games without API keys or real-data
downloads. Recurring infrastructure target: **$0**; paid experiments are optional
and have separately recorded spending caps.

**Website:** [documentation homepage](https://jfk-ssa.github.io/chess-analytics-lab/)
· [published comparison](https://jfk-ssa.github.io/chess-analytics-lab/comparison.html).

**Start here:** [documentation guide](docs/README.md) · [offline demo](docs/DEMO.md)
· [classifier results](docs/CLASSIFIER_COMPARISON.md) · [current status](docs/STATUS.md).

What you can explore: opening frequency and player score, descriptive opening
comparisons, clock-bucket error proxies and evaluation coverage. The analyst
executes checked plans and returns evidence-bound answers; the demo replays
recorded plans and does not generate a new model response. This is chess data
analysis, not a playing engine or personalized opening coach.

```text
Lichess archive / tiny synthetic PGN
  → bounded ingestion + source hash + quarantine
  → immutable Parquet/DuckDB snapshot → dbt marts (optional)
  → opening and clock metrics → Streamlit dashboard
  → allowlisted analyst tools → evidence IDs → frozen evaluation
```

## Five-minute offline demo

Prerequisites: Git and [uv](https://docs.astral.sh/uv/). The lock targets Python
3.12; uv can obtain the pinned interpreter during installation. Development has
been checked on macOS, with hosted CI on Ubuntu. The implementation uses Unix
advisory locks; native Windows execution is not supported by those lock imports.

Clone the repository, then run from its root:

```sh
git clone https://github.com/jfk-ssa/chess-analytics-lab.git
cd chess-analytics-lab
uv sync --locked --no-editable --extra dashboard
uv run --locked --offline --no-editable --extra dashboard chesslab demo --scope all
CHESSLAB_PROJECT="$PWD/work/portfolio-demo/project" \
  uv run --locked --offline --no-editable --extra dashboard \
  streamlit run src/chess_analytics/dashboard/dashboard.py
```

Dependency installation may require a one-time download; subsequent demo and
tests run offline. The demo reads six **authored synthetic** PGN records, accepts
four unique games, excludes one casual game and deduplicates one identical game.
It publishes 24 sampled moves, two opening families, clock annotations, and three
analyst fixture plans. The checked opening result is Sicilian Defense 2/4 known
eligible games. Its white score is 1/2, versus French Defense 1.5/2. In the
30–59 second pre-turn bucket, 3/6 evaluable moves meet the exploratory >=200 cp
proxy; 8 moves are eligible. These are fixture arithmetic, not player behavior.
The dashboard flags the source as synthetic. See the [demo guide](docs/DEMO.md)
for replay and verification commands.

The existing `chesslab demo` remains the smaller foundation fixture path:
26 records seen, 22 accepted, 4/20 eligible draws. `chesslab demo --scope all`
uses ignored `work/portfolio-demo` and never changes the real `data/` pointers.

## Measured evidence and scope

The M7 accepted checkpoint used a frozen 50-case December 1 archive-prefix
holdout with independent references. Three live repetitions each scored 50/50;
all 150 evidence/access audits passed. The three complete runs cost $0.1778959
gross; cumulative accounted M7 gross, including prior attempts and an unknown-cost
reservation, was $0.35392836. Earlier failed and stopped experiments are retained.
This is a fixed-case result, not general model accuracy. The [evaluation guide](docs/EVALUATION.md)
separates fixture harnesses, replay and live results.

The dashboard analysis used an ordered August 2026 archive prefix covering
August 1 only; the accepted M7 analyst used a separate December 2025 prefix
covering December 1 only. Neither prefix represents a full month. Opening labels
are provider tags. Source engine evaluations are sparse and selected, so the clock proxy is exploratory;
no causal or full-month claim follows. The complete 2013 archive establishes
reliable ingestion, not contemporary chess behavior. See [data sources](docs/DATA_SOURCES.md),
[metric contracts](docs/METRICS.md), and the two checked [analysis memos](docs/M4-M5.md).

## Explore next

| Goal | Start with |
|---|---|
| Understand the pipeline and code | [Architecture](docs/ARCHITECTURE.md) and [repository map](docs/README.md#repository-map) |
| Understand findings and denominators | [Opening memo](docs/M4-OPENINGS.md), [clock memo](docs/M4-CLOCK.md), [metrics](docs/METRICS.md) |
| Analyze local game exports | [Local PGN guide](docs/GAME_IMPORT.md): browser-only White-game analysis with explicit provider/player selection |
| Design opening lessons | [Opening learning](https://jfk-ssa.github.io/chess-analytics-lab/opening-learning.html) and [maintained rationale](docs/TRANSPOSITION_LEARNING.md) |
| Explore measured transpositions | [Interactive HTML](https://jfk-ssa.github.io/chess-analytics-lab/transpositions.html); public position rankings, route balance, coverage, fianchetto lenses and [definitions](docs/TRANSPOSITIONS.md) |
| Evaluate the AI claims | [Evaluation guide](docs/EVALUATION.md), [evidence index](docs/EVIDENCE_INDEX.md) |
| Compare rules, Jev and Decisions | [GitHub-readable results](docs/CLASSIFIER_COMPARISON.md) |
| Run optional components or acquire data | [Runbook](docs/RUNBOOK.md), [orchestration](docs/ORCHESTRATION.md), [sources](docs/DATA_SOURCES.md) |

HTML comparison reports under `reports/` are local browser artifacts; GitHub
shows their source. The Markdown results above are readable directly on GitHub.
Milestone files (`M0`–`M8`) and the original brief are historical records; you do
not need to read or execute them all to use the current demo.

## Development checks

```sh
uv sync --locked --no-editable --extra dbt --extra dashboard
uv run --locked --offline --no-editable --extra dbt --extra dashboard pytest -q
uv run --locked --offline --no-editable --extra dbt --extra dashboard ruff check .
uv run --locked --offline --no-editable --extra dbt --extra dashboard ruff format --check .
uv run --locked --offline --no-editable --extra dbt --extra dashboard basedpyright
```

Tests requiring ignored real archives skip in a fresh clone. After source edits,
reinstall with the same extras and `--reinstall-package chess-analytics-lab`.
The offline suite checks the opening-publication pin without requiring the
generated rankings file. The separate [documentation checks](docs/SITE.md#build-and-preview-locally)
require the `docs` extra and explicit restoration of that file before testing or building.
See [demo troubleshooting](docs/DEMO.md#if-a-step-fails) for cache and snapshot issues.

## Detailed guides and historical records

- [Architecture](docs/ARCHITECTURE.md) and [evidence index](docs/EVIDENCE_INDEX.md)
- [Local runbook](docs/RUNBOOK.md), [decision records](docs/DECISIONS.md), and [project brief](docs/PROJECT_SPEC.md)
- [Dagster and Prefect local adapters](docs/ORCHESTRATION.md); Airflow is a follow-up
- [First-visit documentation review](docs/DOCUMENTATION_REVIEW.md); [historical repository review](docs/REPOSITORY_REVIEW.md) and [hardening plan](docs/PORTFOLIO_HANDOFF.md)
- [Jev question-routing learning lab](docs/JEV_ROUTING_RUNBOOK.md), [measured comparison](reports/M8-routing-comparison.html), and [paired final-answer lab](docs/JEV_END_TO_END.md)
- [OpenAI Decisions classifier lab](docs/DECISIONS_ROUTING_RUNBOOK.md), [comparison](reports/decisions-routing-comparison.html), and [measured checkpoint](reports/decisions-checkpoint.json)
- [Separate business communication and data observability examples](auxiliary-examples/README.md)

The default analyst path is offline typed-tool execution or fixture replay. A
personal provider key, explicit model/prices and run cap are required for any
future live run; no live request is part of the demo. M8 Jev routing is an
isolated experiment; the personalized recommender stays on the backlog.
Data source: [Lichess open database](https://database.lichess.org/),
CC0. Copyright (C) 2026 Chess Analytics Lab contributors. Original project code is licensed under
[GPL-3.0-or-later](LICENSE); dependencies retain their own licenses, listed in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
