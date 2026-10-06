# Chess Analytics Lab

A local portfolio connecting a checked chess data platform, opening and clock
analysis, and a measured AI analyst. Projects 1–3 share one repository. The
recurring infrastructure target is $0; historical live evaluation had separately
recorded gross API cost. [Current phase status](docs/STATUS.md).

```text
Lichess archive / tiny synthetic PGN
  → bounded ingestion + source hash + quarantine
  → immutable Parquet/DuckDB snapshot → dbt marts (optional)
  → opening and clock metrics → Streamlit dashboard
  → allowlisted analyst tools → evidence IDs → frozen evaluation
```

## Five-minute offline demo

Install [uv](https://docs.astral.sh/uv/) and run from the repository root:

```sh
uv sync --locked --no-editable --extra dashboard
uv run --locked --offline --no-editable --extra dashboard chesslab demo --scope all
CHESSLAB_PROJECT="$PWD/work/portfolio-demo/project" \
  uv run --locked --offline --no-editable --extra dashboard \
  streamlit run analytics_m4/dashboard.py
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

The real analytical source is an ordered, bounded archive prefix whose observed
games cover August 1, 2026 only. Opening labels are provider tags. Source
engine evaluations are sparse and selected, so the clock proxy is exploratory;
no causal or full-month claim follows. The complete 2013 archive establishes
reliable ingestion, not contemporary chess behavior. See [data sources](docs/DATA_SOURCES.md),
[metric contracts](docs/METRICS.md), and the two checked [analysis memos](docs/M4-M5.md).

## Navigation

- [Architecture](docs/ARCHITECTURE.md) and [evidence index](docs/EVIDENCE_INDEX.md)
- [Local runbook](docs/RUNBOOK.md), [decisions](docs/DECISIONS.md), and [project brief](docs/PROJECT_SPEC.md)
- [Dagster and Prefect local adapters](docs/ORCHESTRATION.md); Airflow is a follow-up
- [Repository review](docs/REPOSITORY_REVIEW.md) and [portfolio hardening plan](docs/PORTFOLIO_HANDOFF.md)
- [Jev question-routing learning lab](docs/JEV_ROUTING_RUNBOOK.md), [measured comparison](reports/M8-routing-comparison.html), and [paired final-answer lab](docs/JEV_END_TO_END.md)
- [Separate business communication and data observability examples](auxiliary-examples/README.md)

The default analyst path is offline typed-tool execution or fixture replay. A
personal provider key, explicit model/prices and run cap are required for any
future live run; no live request is part of the demo. M8 Jev routing is an
isolated experiment; the personalized recommender stays on the backlog.
Data source: [Lichess open database](https://database.lichess.org/),
CC0. Copyright (C) 2026 Chess Analytics Lab contributors. Original project code is licensed under
[GPL-3.0-or-later](LICENSE); dependencies retain their own licenses, listed in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
