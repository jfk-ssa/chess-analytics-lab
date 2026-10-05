# M8 label audit before the new end-to-end run

The original routing set remains frozen. This audit checks the disputed
reference labels against the written handler taxonomy; it does **not**
retroactively change the labels or count as an independent human review.

| Case | Original label | Why the label remains defensible |
|---|---|---|
| `s09` | `opening_score` | Asks for White's share of possible points in an exact opening and cohort; it is a score, not opening frequency. |
| `b07`, `b10` | `clock_bucket` | Ask for one bucket's pre-turn clock proxy counts. `b10` describes the previous same-side clock in prose rather than naming `under_10`. |
| `c06`, `c07`, `c09`, `c10` | `clock_compare` | Each names two clock buckets and requests a pair or difference. A comparison can include coverage and numerators, not only proxy rates. |
| `v06`–`v09` | `coverage` | Ask about observed dates, source/snapshot identities, missingness, or replay selection. Those are dataset provenance and coverage questions. `v07` should not require clarification just because the IDs are absent from the question; a checked coverage tool supplies them. |

The old Jev passes disagreed on `b10` and `v09`, and both classified `v07`
as clarification. That is model variability/error under the frozen taxonomy,
not evidence that the reference should be rewritten after scoring. The
existing analyst's `unsupported` calls for `v06` and `v07` likely reflect
its synthetic-demo execution context; semantic route labels are independent
of that small fixture's contents. This is an inference, not a verified
explanation of internal model reasoning.

The new [32-case answer holdout](../evals/cases/jev_e2e_v1.json) names eight
opening families absent from the M7 25-family reference. Their counts and
White 1400–1599/60+0 outcomes come from a fresh
[raw-PGN tally](../reports/M8-e2e-independent-reference.json), independent
of the checked metric implementations. The existing independent raw-PGN
clock reference supplies the clock numerators and denominators. All 32
expected plans passed checked-tool replay before any new model response.

The four `clarify` and four `unsupported` labels in the new set were authored
under the published M8 route rubric. Before live end-to-end scoring, the
owner reviewed all eight questions and proposed labels in chat, without
seeing any new model outputs, and approved them all unchanged. This is one
owner's adjudication of a small authored set, not a multi-rater study or an
estimate of general boundary prevalence. The original 80-case routing set
still lacks independent human adjudication.
