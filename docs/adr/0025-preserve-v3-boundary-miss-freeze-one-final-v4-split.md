# 0025. Preserve v3 boundary miss; freeze one final v4 split

- Status: accepted
- Date: 2026-10-04

The v3 frozen repetitions scored 96/100, 95/100 and 98/100. Answerable
cases passed 238/246 with each run above 90%, but ambiguity/unsupported
was 16/18 in run 1 and 51/54 overall. The two run-1 misses were safe
`unsupported` responses to the same personal-style question whose frozen
reference expected clarification. Keep this failed gate and do not re-score.
All 30 high-severity and 300 evidence-integrity checks passed. Gross v3 cost
was $0.026632805; cumulative M7 accounted gross is $0.067626885.

For one final M7 evaluation, clarify that a fully specified, nonempty but
small opening cohort is answerable descriptively with a sample-size caveat.
Write new missing-filter questions whose clarification reference is less
ambiguous. Use 25 additional opening families absent every inspected split,
four independently tallied tiny cohorts, 50/50 offline oracle/reference
checks, and a fresh freeze before model calls. The v4 conservative quote is
$0.142884 per 100-request repeat; three repeats plus prior accounted gross
are $0.496278885 under the existing approved $0.50 cumulative cap. No v4
model outcome is claimed at this freeze.

Measure data depth without new acquisition: 40 MB compressed prefix,
236,533,866 extracted PGN bytes, 100,000 complete games, 111 seconds
source ingestion and August 1-only observed coverage. Raising the byte cap
alone while retaining the 100,000-game cap adds no observed date. Defer a
new-day acquisition until a bounded date-targeted method is demonstrated;
defer engine enrichment until a fixed, measured value test is defined.
