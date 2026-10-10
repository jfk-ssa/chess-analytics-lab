# Analyst evaluation and evidence boundaries

The analyst turns a typed or model-proposed plan into at most four allowlisted,
read-only metric actions. Each result is computed by checked tools against one
analytical snapshot; evidence IDs bind dataset, action arguments and result.
The evaluator is separate from the planner. It compares answers to frozen
references and checks tool/filter and access boundaries. `src/chess_analytics/analyst/core.py`,
`tools.py`, `provider.py`, `evaluation.py`, and `experiment.py` are the current
implementation files. Restricted free-form SQL is disabled.

| Evidence kind | Meaning | Current measured result |
|---|---|---|
| Synthetic fixture test | Pipeline and UI correctness on authored games | Four unique accepted games; opening and clock references pass; no model responses |
| Fixture replay / M5 harness | Recorded tool plans and scorer machinery | 50/50 M5 cases; this tests the harness, not model accuracy |
| Offline checked-tool oracle | Reference computation before a live run | M7 December 50/50 cases matched independent references; no model responses |
| Live M6 release | Actual Luna responses on a frozen holdout | 40/40, 38/40, 40/40 across three runs; 118/120 total; two safe incorrect abstentions retained |
| Live M7 accepted gate | Actual Sol responses on a new-date December 1 prefix, fixed 50-case set | 50/50 in each of three repetitions; 150/150 evidence/access audits; no repairs or retries in the complete runs |
| Failed/stopped live attempts | Real provider or sandbox errors and scored misses | Preserved separately in [M6 release](M6-RELEASE.md), [M7 timeline](M7.md), and [December checkpoint](M7-DECEMBER.md) |

The M7 checkpoint covers 41 answerable and nine boundary cases per run, with
five high-severity boundary cases included. All gates in the frozen
[checkpoint](../reports/M7-December-Sol-v12-checkpoint.json) passed. The three
complete repetitions cost $0.0680969, $0.0555067 and $0.0542923 gross, totaling
$0.1778959. Prior M7 accounted gross was $0.13879496. One sandbox failure
returned unknown usage and retained a $0.0372375 reservation, making cumulative
accounted M7 gross $0.35392836 under the approved $6 cap. These are gross
metered estimates, not a verified credit or cash statement. No new live request
was made for portfolio hardening.

The December data cover only December 1, the 50 cases are fixed and some task
concepts recur from development, and the same cases were repeated three times.
The result supports this checkpoint's measured repeatability and boundary
behavior. It is not a population accuracy estimate, complete-month insight, or
a general statement about other models/providers. Earlier Luna gates failed or
stopped; the negative and censored outcomes remain visible in the linked reports.

The original M5/M6/M7 scorer functions and their historical rubrics remain
unchanged. New synthetic portfolio cases use `score_case_portfolio` with rubric
`portfolio-1.0`, which rejects booleans and non-finite numbers in numerical
references. Re-running historical answers through it would be a new analysis,
not a rewrite of frozen results.

For offline replay, first run `chesslab demo --scope all`, then use the command
in [DEMO.md](DEMO.md). Historical fixture harness checks are available with
`python -m chess_analytics.analyst eval --split both` **only when its matching analytical
snapshot is available**; that command writes a local report. The immutable
tracked M5 report remains readable without it. No live evaluation command is
part of the quickstart. A new experiment requires a new freeze, reference
set, finite cap and personal provider configuration before any request.

## Optional classifier comparisons

[The comparison summary](CLASSIFIER_COMPARISON.md) separates task routing from
final-answer correctness. Jev routing has two retained repetitions; its 32-case
pairing used Luna rather than the accepted M7 Sol analyst. Decisions has new live
classifications, a fresh 24-case owner-reviewed language set, and a separately
labeled replay using saved Luna answers. Neither gate is promoted. Follow the
[Jev](JEV_ROUTING_RUNBOOK.md) and [Decisions](DECISIONS_ROUTING_RUNBOOK.md) runbooks
for offline harness/replay paths; a new live experiment requires its own cap.
