# 0104. Hosted Altair 6 and pandas 3 pins

- Status: accepted on merge
- Date: 2026-10-24

## Motivation

[ADR 0103](0103-security-pins-for-pillow-and-certifi.md) left pandas
2.3.3, protobuf 6.33.6, and Altair 5.5.0 in place when Streamlit moved
to 1.66.1. A later lock update proposes Altair 6.3.0, narwhals 2.27.1,
pandas 3.0.6, and protobuf 7.36.2 in `hosted/requirements.txt`. That
file has to match `uv.lock`. The lock is one resolution for every
extra, including Dagster and dbt.

The Streamlit 1.66.1 wheel recorded in `uv.lock` declares
`altair!=5.4.0,!=5.4.1,<7,>=5.0.0`, `pandas<4,>=1.5.3`, and
`protobuf<8,>=5.26.1`. The lock lists those dependencies by name. The
ranges live in that wheel's metadata. Altair 6.3.0, pandas 3.0.6, and
protobuf 7.36.2 each sit inside the corresponding range. Narwhals
2.27.1 satisfies Altair 6.3.0's `narwhals>=2.4.0`. Altair 6.3.0 still
depends on `jsonschema>=3.0`, so the jsonschema 4.26.0 pin stays.

Pandas 3 and Altair 6 are the versions the hosted page and the local
dashboard will import. Prefect 3.9.0, already a direct extra pin, drops
Python 3.10, removes `Runner.execute_flow_run`,
`Runner.execute_bundle`, and `Runner.reschedule_current_flow_runs`, and
warns on Pendulum-only datetime methods on Python 3.11 and 3.12.

## Decision

`uv.lock` and `hosted/requirements.txt` pin Altair 6.3.0, narwhals
2.27.1, and pandas 3.0.6. Pluggy 1.7.0 matches the build-system pin.
Protobuf stays 6.33.6.

Dagster 1.13.25 requires `protobuf<7` on Python 3.12. dbt-common 1.39.0
and dbt-adapters 1.24.5 require `protobuf<7.0,>=6.0`. Those extras share
this lock, so protobuf 7.36.2 does not resolve. The hosted pin follows
the lock. Dependabot ignores protobuf major updates until those three
packages accept protobuf 7.

The repository has no pandas import. Hosted charts pass row dicts to
`alt.Chart` and `alt.Data`. They register `alt.theme`, the theme API
Altair 5.5 introduced and Altair 6 kept. They do not call the removed
`alt.themes` registry. The Prefect demo calls `@flow`, `@task`, and
`Flow.serve`. It does not call the removed Runner methods or
Pendulum-only datetime methods. This project requires Python 3.12, so
the Python 3.10 removal does not apply. [ADR 0103](0103-security-pins-for-pillow-and-certifi.md)
keeps the pin choice it recorded.

## Consequences

Community Cloud pip and `uv sync --extra dashboard` install the same
Altair, narwhals, pandas, and protobuf versions. A later protobuf 7 pin
has to wait until the locked Dagster and dbt ranges allow it, and then
the Dependabot ignore comes off. This record does not authorize a live
model call.
