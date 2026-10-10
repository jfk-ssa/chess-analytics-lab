# 0028. M8 Jev route selection deferred to a narrow measured task

- Status: accepted
- Date: 2026-10-04

The user flagged Jev, `pg_jev`, and DuckDB's Jev support for M8. Record the
comparison in [M8.md](../M8.md). After M7 acceptance and a concrete row-level
decision task, test a direct typed Jev adapter first, then the DuckDB
community extension as the natural SQL route in this local stack. Consider
`pg_jev` only if a PostgreSQL learning slice offers enough benefit to justify
operating a second database and its `plpython3u`/superuser setup. Check
current extension compatibility, API entitlement, prices and credential
behavior before any live M8 experiment. Recommend a specific gross cap with
a conservative quote then; do not infer access from a login or the existing
OpenAI credit. The personalized recommender remains backlog.
