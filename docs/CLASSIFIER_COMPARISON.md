# Rules, Jev and Decisions: measured comparison

**HTML version:** [Read this guide on the documentation site](https://jfk-ssa.github.io/chess-analytics-lab/comparison.html).

**Keep both classifiers optional.** Decisions matched the better Jev routing run
on the shared historical questions. Neither classifier has demonstrated better
final-answer quality than the direct analyst; adding a gate cost more on the
small final-answer comparison. This is a learning experiment, not a general
model ranking or a production recommendation.

## Routing: same 40 historical questions

A correct route selects one of eight task/boundary labels; it does not establish
a correct chess metric. The two Jev rows are repetitions of the same configuration
on the same questions, retained to show variation.

| Method | Correct routes | Gross API cost per run |
|---|---|---|
| Rules baseline | 35/40 (87.5%) | $0 |
| Jev — run 1 | 39/40 (97.5%) | $0.001000188 |
| Jev — run 2 | 37/40 (92.5%) | $0.001000188 |
| Existing Luna analyst | 33/40 (82.5%) | $0.00226205 |
| OpenAI Decisions API | 39/40 (97.5%) | $0.001469 |

All rows use the same 40 questions and split, but were collected at different
times. These questions have been inspected during development; they are not an
untouched holdout. Rules are the simple regex routing baseline; “existing
analyst” here means its task selection, not a final-answer score.
[Retained routing checkpoint](../reports/M8-routing-checkpoint.json),
[Decisions historical run](../reports/decisions-historical-test.json).

## Final answers: same 32 historical questions

Here, baseline means the Luna analyst answering directly. Jev's boundary gate
was executed alongside it. Decisions was evaluated later using new classifications
and the saved baseline answers: its row is **offline replay**, not a new live
paired run or a measurement of newly generated final answers.

| Path | Correct final answers | Gross total | Evidence |
|---|---|---|---|
| Direct analyst baseline | 31/32 | $0.0024263 | Retained live paired experiment, versioned offline rescore |
| Jev + analyst | 31/32 | $0.002503882 | Same live pairing and rescore; 26 analyst calls |
| Decisions + saved analyst answers | 31/32 | $0.003363135 (simulated) | Offline retained-answer replay; 26 saved-answer fallbacks |

The baseline is cheapest and correctness is unchanged. The Decisions row has
no combined live latency. All three refer to Luna; they do not establish a
benefit for the accepted M7 Sol analyst.
[Paired checkpoint](../reports/M8-e2e-checkpoint.json),
[Decisions replay](../reports/decisions-retained-answer-replay.json).

## Fresh language: Decisions versus rules only

On 24 new owner-reviewed questions, Decisions scored **23/24 in each of three
repetitions**, while rules scored **8/24**. Jev and the existing analyst were
not run on this set. Do not compare these scores with the 40-question table.
Repeating the questions yields 24 independent examples, not 72.

The 0.70 chosen-option probability threshold was selected on historical development
cases before fresh scoring. It accepts 17/24 fresh routes, with zero observed
accepted errors and seven fallbacks. The repeated miss confuses an opening's
score results with its frequency; the frozen gate sends that case to fallback.
This small set does not prove calibrated confidence or general boundary safety.
[Label review](DECISIONS_LABEL_AUDIT.md),
[frozen policy](../reports/decisions-development-policy.json).

All six Decisions runs used 184 requests and $0.0068145 cumulative gross against
an approved $0.05 cap. This is metered usage at the recorded price, before
credits—not a settled invoice. Historical costs are not current pricing quotes.
No new Jev or analyst call was made for the Decisions comparison.
[Full checkpoint](../reports/decisions-checkpoint.json).

## Explore or reproduce

For confusion matrices, latency and coverage/error plots, open the
[published report](https://jfk-ssa.github.io/chess-analytics-lab/reports/decisions-routing-comparison.html).
The [interactive guide](https://jfk-ssa.github.io/chess-analytics-lab/comparison.html)
lets you inspect saved question-level routes and change a descriptive threshold.
Alternatively clone and open [the tracked HTML report](../reports/decisions-routing-comparison.html)
locally; GitHub shows its source rather than running it. The [Decisions runbook](DECISIONS_ROUTING_RUNBOOK.md)
explains offline preparation, personal credentials, durable spending accounting,
report rendering and replay. The [Jev runbook](JEV_ROUTING_RUNBOOK.md) and
[paired-answer lab](JEV_END_TO_END.md) explain the earlier experiments.

A fresh paired final-answer experiment is the next optional gate. It needs
independent references and new provider-specific estimates, recommended caps
and approvals before any paid request. Routing scores alone do not justify integration.
