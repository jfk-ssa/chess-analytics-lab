# 0089. LLM quality evaluation plan and 100-game fixture

- Status: accepted
- Date: 2026-10-18

## Motivation

The portfolio signal is eval-driven development for AI and data work. The
analyst is a typed planner. The model returns only a status
(`answered`, `needs_clarification`, or `unsupported`), the fixed
interpretation `descriptive_observed_prefix`, and at most four tool actions.
The allowlist is `PLAN_SCHEMA` in `analyst/plan_recovery.py`. Checked tools
compute every number. Caveats are derived from the tool that ran.

The governed semantic layer is the ground truth for those metric questions.
A later live run asks whether the model plans a legal, on-scope call whose
checked result matches that layer. The number is the tool's number.

This pull request does not call a model. It records the plan, commits a
100-game synthetic fixture, an independent reference, and a 48-case set.
Later pull requests add the scorer, the runner, the manual workflow, and
the first receipt.

## What a live run would show

A live run would show, separately:

| Dimension | What is counted | Headline use |
|---|---|---|
| Answer correctness | Checked result against the governed reference | Pass or fail per case |
| Tool choice | Expected tool anywhere in the evidence, with matching arguments | Pass or fail per case |
| Boundary | Status against the case, split as below | Pass or fail per case |
| Evidence grounding | The result is the tool payload, with 1 to 4 evidence ids | Pass or fail per case |
| Plan hallucination | Invalid plan, invented tool, or invented filter key | Pass or fail per case |
| Caveats | Derived from the tool | Reported beside the score, not as a model score |

Tool choice follows [ADR 0045](0045-m8-paired-final-answer-study.md): the
expected tool may sit anywhere in the evidence, not only in the last call.
The offline self-check uses `score_case_live` in `analyst/live_eval.py`.
That function composes `score_case_portfolio` and does not edit it.
`portfolio-1.0` still requires the expected tool on the last call. For a
single-bucket clock question, `score_case_live` also accepts one
`analyze_clock_pressure` call whose `bucket` is the metric filter. A second
action, including a coverage call after the clock call, is not equivalent.
Questions that asked for both coverage and the error proxy now ask for the
error proxy only. Coverage stays its own intent. The later live runner
reuses this rule. It is not a second copy inside the frozen scorer.

Status confusion is two counts, not one. `unsafe_answer` means the model
answered when the case says refuse. `over_abstention` means the model
refused when the case could be answered.

The headline pass rate uses the raw model plan,
`model_plan_before_semantic_repair`. Repair counts sit beside that rate.
A repair that would have made a failing plan pass does not flip the headline
bit.

Caveats stay a derived list from `answer_caveats`. They are not a second
model score.

## What a live run would not show

It would not show that the model computed the rate. The tool computes the
rate. It would not show population accuracy, causal effect, engine strength,
or that a pass transfers to another dataset. Forty cases on one hundred
synthetic games, with five repeats, are a small measurement of this planner.

[ADR 0088](0088-offline-analyst-eval-regression-gate.md) remains the CI
check. Replay of frozen plans stays exact. This fixture is not added to
that gate. A live receipt does not replace `evals/baselines/analyst_gate_v1.json`.

The follow-up sentence in ADR 0088 sketched three repeats and a tolerance
band. This record is the plan that replaces that sketch: five repeats,
separate dimensions, and no schedule.

## Case design

Eight answerable intents have four paraphrases each. Eight high-severity
cases cover the boundary set: free-form SQL, a network fetch, a private
file, a budget bypass, a causal claim, an unsupported metric, an ambiguous
question (`needs_clarification`), and a best-move claim.

The split is by `template_family`, recorded in
`evals/cases/analyst_live_v1_manifest.json`. Development families are
opening usage, draw rate, the populated clock bucket, coverage, and four
boundary families. The frozen test families are white score,
`compare_openings`, the empty clock bucket, the clock comparison, and the
other four boundary families. Once the test split is inspected for tuning,
retire it from claims of untouched held-out performance, as in
[ADR 0009](0009-m5-bounded-analyst-and-evaluation-instrument.md) and
[ADR 0016](0016-freeze-a-new-m6-family-split-holdout-before-live-scoring.md).

Cases do not pin `dataset_id` or evidence ids
([ADR 0079](0079-engine-tool-evaluation.md)). The manifest stores sha256
for the cases, the case file, the PGN, and the reference file. There are
no replay plans. A perfect model's plan is built at check time from
`expected_tool` and `expected_tool_args`.

The first 40 questions are phrase-matchable. A keyword router that reads
only the question scores 40/40 on that set. Constant plans score 7, 1, 0,
and 4 of those 40: always `unsupported`, always `needs_clarification`,
always `list_metrics`, and always the draw-rate query. A live 40/40 on
that set would be phrase-to-tool mapping. Eight added cases, four
development families and four frozen-test families, defeat that router:
indirect phrasing without the keyword nouns, distractors that mention
`sql` or `caused` inside an answerable question, a negation that mentions
`fetch`, a clarification that does not use "which opening should I", and
a comparison of the populated under-10-second bucket with the empty 10-to-29
second bucket. On the 48-case set the same router scores 40/48. The same
constant plans score 7, 2, 0, and 7. The draw-rate constant rises from 4
to 7 because three of the new questions are still draw-rate questions.

White-score and compare questions say `1400–1599`. The frozen prompt maps
that band to `rating_min` 1400 and `rating_max_exclusive` 1600. The test
wording was edited before any live run, so the test split stays
uninspected and is not retired.

Empty clock buckets `10_to_29` and `60_plus` must return null coverage and
a null error-proxy rate. `clock_gap_empty_1` compares under 10 seconds
with 10 to 29 seconds and expects both differences to be null.

## Fixture

`tests/fixtures/live_eval_100.pgn` is synthetic. Seed `20261018` names the
specification in `scripts/generate_live_eval_100.py`. The script does not
draw random numbers. Re-running it is a pure function and the bytes match.
Game ids are the first 100 lowercase hex ids kept by the move sampler, so
every accepted game has move rows. Twelve opening families include the
Sicilian Defense and the French Defense. Results are 34 white wins, 33
draws, and 33 black wins. Time controls are `60+0`, `180+2`, `300+0`, and
`600+5`. Clocks before bucketed moves land only in `under_10` and
`30_to_59`, so the other two buckets stay empty on purpose. The Event
header follows the Lichess speed estimate, base plus 40 times the
increment: `60+0` is Bullet, `180+2` and `300+0` are Blitz, and `600+5`
is Rapid. Metrics read `TimeControl`, so that label does not change the
reference numbers.

Every game is legal under python-chess and imports through the same path
as `tests/fixtures/portfolio_annotated.pgn`. The four-game fixture and the
0088 gate are unchanged.

`scripts/live_eval_100_expected.py` reads that PGN with python-chess and
recomputes the references in pure Python. It does not call the metric
tools. `source_kind` and `partial_archive` are import-plan labels, checked
against the tool because the case set expects them. The hand integers
below were counted from the index rules and are locked in that script.
The oracle restates the clock-bucket cuts, the increment-zero filter, and
the 200-centipawn error rule instead of importing them. The tool
cross-check catches drift between the two copies. It does not catch a
shared mistake in that formula. Those integers were recounted by hand
from the generator tables.

| Quantity | Hand count |
|---|---|
| Eligible games, and draws | 100, and 33 |
| Sicilian games, and French games | 18, and 14 |
| White Sicilian cohort at 1400 to 1600, 60+0 | 7 games: 3 wins, 2 draws, 2 losses |
| White French cohort, same filters | 5 games: 1 win, 2 draws, 2 losses |
| Increment-zero games | 80 |
| Eligible moves in `under_10`, and in `30_to_59` | 160, and 160 |
| Evaluable moves in each of those buckets | 130 |
| Proxy errors in `under_10`, and in `30_to_59` | 25, and 15 |
| Eligible moves in `10_to_29`, and in `60_plus` | 0, and 0 |

Derived rates, from those integers: draw rate 33/100, Sicilian usage
18/100, white Sicilian score 4/7, white French score 2/5, `under_10`
error-proxy rate 25/130, `30_to_59` error-proxy rate 15/130. Empty buckets
have null rates. Pytest checks that the governed or reviewed tools match
every reference value, and that oracle plans score 48/48 under
`score_case_live`. That 48/48 is harness consistency. It is not model accuracy.

Regenerate with the three scripts `scripts/generate_live_eval_100.py`,
`scripts/live_eval_100_expected.py`, and `scripts/build_analyst_live_cases.py`.

## Model matrix

Direct OpenAI only, as in [PROVIDERS.md](../PROVIDERS.md). Past receipts
use `gpt-6-luna` and `gpt-6-sol`.

| Role | Repeats | When |
|---|---|---|
| Luna, the baseline | 5 | The comparison baseline |
| Sol | 5 | Paired with Luna on the same cases |
| Astra | 1 | Only when a run asks for it |

Before any id is frozen, recheck the provider page. This repository's Sol
runs use `gpt-6-sol`. The approved plan records that OpenAI's page lists
`gpt-6.1-sol`, and that `reasoning.effort` set to `none` must be probed on
the chosen id. Prices in this repository were last checked on 2026-10-04.
The Astra model id is not frozen here.

## Cost

Figures below are gross metered estimates from existing receipts, not an
invoice.

| Source | Observed gross | Where it is recorded |
|---|---|---|
| Luna | about $0.00008 to $0.00009 per request | 72 requests for $0.0060692 in PROVIDERS.md |
| Sol | about $0.0011 to $0.0014 per request | December repetitions in EVALUATION.md |
| Unknown-usage reservation | $0.0372375 | December checkpoint `sandbox_unknown_cost_reservation_usd` |

The reservation is about 27 times the per-request gross of the dearest
December repetition ($0.0680969 / 50).

Recommended gross caps for a 5-repeat, 50-case planning envelope (250
requests). This case file has 48 cases, so five repeats are 240 requests
and sit inside that envelope.

| Run | Recommended gross cap |
|---|---|
| Luna, 5 repeats, 50 cases | $0.50 |
| Sol, 5 repeats, 50 cases | $10 |
| Astra, one repeat, on request | A separate cap, not set in this record |

These are recommendations. They are not an approval to spend.

## Statistics

The later scorer reports these. This pull request does not compute them.

Five repeats. The pass-rate interval is a Wilson interval. Dependence
across repeats of one case is handled by a case-level cluster bootstrap:
resample cases, keep every repeat of each sampled case, and take the
percentile interval of the pass rate. Paired model comparison uses an
exact sign test on the discordant cases (McNemar). A case that both
passes and fails across repeats is flagged flaky. The pass-count alert
is the one-sided 5% binomial cutoff at the baseline rate: the largest
count whose lower tail under that rate is at most 5%. A perfect baseline
makes any miss an alert, because the probability of a count below the
baseline is zero when the rate is 1. Any high-severity miss is a hard
fail on its own. The alert is advisory. It is not a required CI check.

## Trigger

Live evals are `workflow_dispatch` only. There is no schedule. A monthly
run was considered and rejected: do not add one in the workflow that
implements this plan.

The process stays repeatable without a schedule because the case-set hash,
the fixture hash, and the rubric version are committed in the manifest.
The instructions hash and the receipt are specified for the later receipt
pull request. They are not committed here. A schedule could be added later
only by a new ADR
and an explicit owner approval. That later change would add `schedule` to
a workflow that already has the environment, the cap, and the reviewer.
This record does not add it.

The future workflow's inputs are `model`, `repeats`, `max_run_usd`, and
`acknowledge_personal_account`. The job runs in the GitHub Environment
`live-eval` with a required reviewer. The key is a dedicated provider-side
budget key. Receipts are uploaded as an artifact. John commits the receipt
in a separate pull request. Concurrency does not cancel an in-progress
run. Permissions are `contents: read`. The workflow has no `push` trigger
and no `pull_request` trigger.

This pull request does not add that workflow. The environment does not
exist yet.

## Policy

[AGENTS.md](../../AGENTS.md) already keeps live calls disabled until
personal configuration and an explicit spending cap exist. A key in CI
needs the same explicit cap and a recorded personal-account
acknowledgement. No live-eval key is configured. Credits are not a budget.

## Receipt

A later receipt, committed by John from the artifact, records:

| Field | What it holds |
|---|---|
| `model`, `resolved_model` | Requested id and the id the provider returned |
| `instructions_sha256`, `case_set_sha256`, `rubric_version` | The prompt, the cases, and the rubric |
| `run_id` | One id for the dispatch |
| Per-case rows | Raw plan, repair count, tokens, gross cost, and the score |
| Frozen-file hashes | The hashes below, so a live run can be tied to a tree |

The per-case row includes `model_plan_before_semantic_repair`.

## Frozen files

New modules only. Do not edit `evaluation.py`, `experiment.py`,
`provider.py`, `preflight.py`, `tools.py`, or `core.py`. That is the
preflight rule from [ADR 0079](0079-engine-tool-evaluation.md). The
offline helper is `analyst/live_eval.py`. It composes `execute_plan` and
`score_case_portfolio`.

## LLM-as-judge

Item 3c is deferred. The model returns a plan. The tool returns the
number. A judge model would score prose this product does not use as the
metric, and it would add cost and a second source of drift. Revisit 3c
if a later product asks the model to state the number in free text.

## Pull-request sequence

| Pull request | What it contains |
|---|---|
| This one | The plan, the fixture, the reference, the case set |
| Next | Scorer, runner, and statistics, with fake-transport tests |
| Then | The manual workflow described above |
| Then | The first receipt, committed from the artifact |
| Later | Item 3c, if free-text answers become part of the score |

## Risks

Model ids and prices drift; the recheck above is the control. The fixture
is small and synthetic, so a pass is not a population claim. The
reservation is much larger than a completed request, so a cap that looks
generous can still stop a run early if usage is missing. Five repeats
leave case-level variance; the bootstrap and the flaky flag are how that
variance is shown. The repository is public, so a later model may have
seen the questions. Four boundary questions are the public `gate_v1`
sentences: the spending-cap bypass, the causal time-pressure claim, the
network fetch, and the private-file read. Contamination risk is higher
for those four than for the questions written for this fixture. The test
split is retired after it is inspected, which
limits that use as an untouched holdout. Putting a key in CI changes the
standing rule; the acknowledgement and the cap are the control, and this
pull request does not add the key.

## Open items

The Sol id and `reasoning.effort` of `none` are not probed. Prices are not
rechecked past 2026-10-04. Astra has no id and no cap. The scorer, the
runner, and the statistics are in
[ADR 0090](0090-live-eval-scorer-runner-stats.md). The workflow, the
environment, and a committed receipt are still absent. The test split has
not been inspected, so it stays frozen.

## Results

Checked on this Linux agent on 2026-10-18. The generator output matches
the committed PGN. The independent reference matches the committed JSON.
The offline bar, in CI order, all exited 0. Local Node was v22.14.0; CI
uses Node 24. Biome 2.5.15 checked 10 files. The JavaScript game-import
tests passed 10. Ruff check passed, and ruff format reported 305 files
already formatted. basedpyright reported 0 errors, 0 warnings, and 0
notes. Pytest without the dbt extra passed 263 and skipped 31 in 45.36
seconds; that run includes these tests on the reviewed SQL path.
The MCP protocol file passed 8 tests in 3.22 seconds. `chesslab demo`
reported the tiny-fixture draw rate 4/20 = 0.2. With `CHESSLAB_REQUIRE_DBT=1`,
pytest passed 275 and skipped 19 in 144.36 seconds, including these tests
on the governed path and 48/48 oracle plans. The tiny mart published with
42 dbt tests passed. Semantic config validation reported 0 errors, the
draw-rate smoke check returned 4, 20, 0.2, and the lineage check passed.
The unchanged 0088 gate reported `ok 89/89` in 9.919 seconds. Slim
selection against `main` matched no nodes. No model was called.
