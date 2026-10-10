# 0021. Always recommend a spend cap with an estimate

- Status: accepted
- Date: 2026-10-04

The user wants a concrete recommendation whenever a live-run spending limit
is needed. Before asking, present the exact frozen request count, current
official model rates, the run's conservative preflight reservation, comparable
actual usage-based costs, uncertainty from cache/output/failures, and a
recommended **gross** cumulative cap. State that account credit is not the
cap. Do not ask for an unexplained number or infer authorization from these
planning figures.

For M7 planning only, scaling the M6 v2 shape gives ~$0.1304 conservative
reservation versus ~$0.0083 actual-cost forecast for 100 calls, and ~$0.3911
versus ~$0.0249 for 300 calls. Recommend **$0.15 for one 50-case/two-condition
pass** or **$0.45 cumulative for three passes**, conditional on a new exact
preflight that fits. These are not M7 quotes or approvals. See `docs/M7.md`.
