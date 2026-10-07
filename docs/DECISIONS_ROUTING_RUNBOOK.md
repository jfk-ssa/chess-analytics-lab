# Decisions routing learning lab

This optional experiment adds OpenAI Decisions beside the retained rules, Jev,
and structured-output analyst comparisons. It does not change the production
analyst. The exercise is to learn how a classifier's task labels, probabilities,
measured errors, and billing affect a decision to route or fall back.

## What is being measured

The eight routes are opening usage, opening score, opening comparison, a single
clock bucket, a clock comparison, dataset coverage, clarification, and unsupported
requests. A label chooses a task; it is not SQL, a validated filter, or a chess
answer. Existing checked tools must still validate arguments and compute metrics.

The historical 40 development questions select a probability threshold. All
historical questions have already been inspected, so the separate historical
40-question comparison is development evidence, not an untouched holdout.
The 24 new questions have three examples per route. Their labels were proposed by
the project agent and reviewed by the owner before live scoring; see
[the audit](DECISIONS_LABEL_AUDIT.md). They test new phrasing within familiar tasks,
not another dataset or broad chess ability. Repetitions reuse the same questions
and measure variation; they do not multiply the number of independent examples.

The request uses `gpt-6-luna` with one named Choice question and a fixed route
rubric. The API supplies the selected choice, a probability distribution and a
separate confidence value. We show both measures; neither is assumed calibrated.
The development policy selects the lowest tested **chosen-option probability**
threshold with zero observed accepted routing errors and at least 50% coverage.
If no threshold qualifies, it falls back on every case. The policy is frozen
before fresh scoring. Holdout curves are descriptive; do not pick a new production
threshold from them and still call that same set a holdout.

## Measured checkpoint (2026-10-07)

Six complete live Decisions runs used 184 requests and **$0.0068145 gross**
against the approved $0.05 cumulative cap. There were no transport failures,
unknown reservations, retries or refusals. [Checkpoint](../reports/decisions-checkpoint.json),
[comparison HTML](../reports/decisions-routing-comparison.html).

| Set | Decisions | Comparator | Interpretation |
|---|---|---|---|
| Historical development | 37/40 | Threshold selection only | Frozen threshold 0.70; 25/40 accepted with zero observed errors |
| Historical comparison | 39/40 | Rules 35/40; retained Jev 39/40 and 37/40; retained Luna analyst 33/40 | Same questions and split, different collection times; not fresh paired evidence |
| Fresh owner-reviewed language | 23/24 in each of three runs | Rules 8/24 | Same repeated score and route choices; 24 independent examples |
| Historical retained-answer replay | 31/32 final answers | Retained baseline 31/32 | No new analyst answer; 26 saved-answer fallbacks; simulated cost rises |

The fresh mistake is ds03: “results ... not how often the opening appears”
is labeled opening score but classified opening usage, with chosen-option
probability 0.52. The frozen 0.70 policy rejects it. That policy accepts 17/24
fresh routes (70.8% coverage), with zero observed accepted errors; seven fall back.
Median fresh per-request latency was approximately 0.33 seconds in the first run.
The deliberately varied phrasing challenges the unchanged simple regex baseline;
this small result is not a general assessment of rules versus models.

The historical replay saves six boundary-answer calls but adds a classifier call
to every question. Its simulated cost is $0.003363135 versus $0.0024263 for the
retained baseline, with no correctness gain. Keep Decisions as an optional lab,
not a product dependency. A new paired final-answer experiment is the next gate
if its learning value justifies new spending approvals.

## Setup and offline execution

Run commands from the repository root. Installation may need network access once;
subsequent checks below need no credentials or network.

```bash
UV_CACHE_DIR=.uv-cache uv sync --locked --no-editable --extra dbt --extra dashboard
UV_CACHE_DIR=.uv-cache uv run --locked --offline --no-editable --extra dbt --extra dashboard pytest tests/test_decisions_study.py
UV_CACHE_DIR=.uv-cache uv run --locked --offline --no-editable ruff check .
```

After changing source, reinstall the project wheel with the same extras and
`--reinstall-package chess-analytics-lab`. The adapter uses Python's standard
library and adds no dependency or cloud service.

Produce a no-cost rules comparison and a frozen cost quote:

```bash
.venv/bin/python -m chess_analytics.decisions_study rules \
  --suite fresh --split test --output work/decisions-fresh-rules.json
.venv/bin/python -m chess_analytics.decisions_study prepare \
  --suite fresh --split test --output work/decisions-fresh-preflight.json
```

`prepare` makes no request. The quote hashes the cases, manifest, exact request
bytes, adapter and shared helpers. A drifted quote is rejected before transport.
Tests inject explicit mock transports and verify response validation, owner-review
and spending gates, interruptions, repeat accounting, and safe replay/reporting.
A mock result is harness evidence, never a model benchmark.

## Personal live configuration and spending

Only an explicitly supplied ignored `work/.env` (or `work/.env.openai`) containing
`CHESSLAB_OPENAI_API_KEY` is read. There is no ambient credential fallback. Do not
put keys in a tracked file, output, chat, or shell command. The run also requires
an explicit personal-account acknowledgment, frozen quote, campaign directory,
and positive spending cap. Importing the module, preparing a quote, running
rules or reading reports never makes a live request.

The owner approved **$0.05 cumulative gross** for this Decisions campaign. The
one authoritative local ledger is `work/decisions-routing-campaign-v1`. All
attempts and repetitions share it. Provider credits do not increase that cap.
The completed campaign's approval is not permission to start another campaign.
Obtain a new explicit cap before future calls; always present an estimate and a
recommended limit. TypeSafe and Responses analyst calls need separate approvals.

For an authorized run only, the invocation shape is:

```bash
.venv/bin/python -m chess_analytics.decisions_study run \
  --preflight work/decisions-fresh-preflight.json \
  --env-file work/.env --personal-account-acknowledged \
  --campaign work/decisions-routing-campaign-v1 --cap-usd 0.05 \
  --output work/decisions-fresh-live.json
```

The initial price checked on 2026-10-07 is $0.10 per million input tokens;
Decisions does not charge for output or cached tokens at that price. This study
uses the standard global endpoint, not a regional route. Verify current model,
price and availability before another experiment using the
[official guide](https://developers.openai.com/api/docs/guides/decisions) and
[request reference](https://developers.openai.com/api/reference/resources/decisions/methods/create).
Usage multiplied by the recorded rate is gross cost before credits, not proof of
a settled provider invoice. Reservation uses four times request UTF-8 bytes plus
1,024 input tokens per call: conservative, but not a contractual tokenizer bound.

Before any call, the entire run must fit the remaining cumulative cap. A durable
pending reservation is saved before transport; a returned usage count settles
it. Missing usage, transport failure or a killed process retains the reservation.
Invalid answers with valid usage still count as paid. Runs stop at the first
failure, do not retry, and return nonzero when incomplete. A local file lock
prevents simultaneous runs in one campaign. Preserve that directory: creating a
new path or deleting records defeats local accounting and is not a budget reset.
The provider itself is not enforcing this repository's cap.

## Reports and retained-answer replay

Calibration and HTML rendering are offline:

```bash
.venv/bin/python -m chess_analytics.decisions_study calibrate \
  --report reports/decisions-development.json \
  --output work/decisions-development-policy.json
.venv/bin/python -m chess_analytics.decisions_report html \
  --report reports/decisions-fresh-pass-1.json \
  --comparator reports/decisions-fresh-rules.json \
  --output work/decisions-comparison.html
```

The HTML shows confusion matrices, cost per correct route, median measured
request latency, and threshold coverage/error/fallback counts. Compare only the
same case hash **and split**. Historical Jev and analyst results were collected
at different times; analyst timing includes its checked tool execution. Rules
have no inference charge, but missing per-case timings are labeled unmeasured.

The 32 historical paired cases also have independently referenced numerical
answers and retained Luna baseline results. Newly measured Decisions routing
can be combined offline with those saved outcomes: high-confidence clarification
or unsupported routes return a boundary status; every other case uses its saved
baseline answer. The expected label only scores the result; it does not select
which path runs. The replay reports fallback count and simulated cost per correct
answer. It makes **zero new analyst calls** and reports no combined live latency.
It is not a fresh paired experiment, not evidence that Sol benefits, and not a
measurement of newly generated final answers.

```bash
.venv/bin/python -m chess_analytics.decisions_report replay \
  --report reports/decisions-historical-e2e.json \
  --policy reports/decisions-development-policy.json \
  --output work/decisions-retained-answer-replay.json
```

Keep raw responses under ignored `work/`. Compact scored reports, frozen cases,
policy and checkpoint are shareable. Preserve failed attempts alongside successes.
The next decision is whether a fresh paired final-answer experiment offers enough
learning value to justify separate provider caps; routing accuracy alone does not
justify integrating the classifier.

### Report summary

The published comparison opens with “Results at a glance”: the integration
recommendation, fresh accuracy, threshold coverage/fallbacks, cumulative gross
spend, retained-answer outcome and evidence limits. Regenerate that full summary
by adding `--checkpoint reports/decisions-checkpoint.json` to the HTML command
and supplying all six Decisions reports listed in its `files` mapping. The CLI
checks their file hashes before including the checkpoint summary. A partial
comparison can omit `--checkpoint`. This is offline rendering, with no API calls.

The summary compares routing on the same 40 historical questions and final
answers on the same 32 historical questions in separate tables. “Rules baseline”
means regex routing; “analyst baseline” means direct Luna answers. The fresh
24-question comparison contains Decisions and rules only; Jev and analyst
results were not measured there. Decisions final-answer cost remains simulated
from retained answers, while the earlier Jev pairing was executed live.
