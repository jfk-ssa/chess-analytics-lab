# 0017. Holdout accuracy passed once; release held on repeatability

- Status: accepted
- Date: 2026-10-04

With explicit user authorization, execute the frozen 40-cell family-split
holdout and two identical repetitions under one $0.10 cumulative gross cap.
The first run completed 40/40 and scored 39/40, including 27/28 answerable,
12/12 ambiguity/unsupported, and 6/6 high-severity cases. Independent
post-run evidence audit found 40/40 completed responses internally traceable.
The one scored miss returned a real second-family metric instead of the
requested opening comparison.

Preserve both stopped repetitions. The second made 10 requests and stopped
on a two-chunk provider-format response; the third made 22 and stopped when
`compare_openings` lacked a `filters` wrapper. The third also made one
incorrect clarification refusal. No attempt was retried. Across 120 planned
request slots, 72 were attempted and 48 never attempted. All attempt costs
are known; total gross cost was $0.0060692, under the cap. Report missing
cells explicitly and do not use attempted-only scores as repeatability
estimates. The first run's accuracy gates passed, but a measured release
requires reliable completion; keep M6 in progress and the analyst labeled
experimental. This holdout is now inspected and retired for future untouched
model claims. Remediate on development cases and freeze a new holdout before
trying another live release evaluation. The typed-planner contrast remains
separate from the unimplemented restricted-SQL baseline.
