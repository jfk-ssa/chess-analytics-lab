# Jev end-to-end learning lab

The earlier [routing lab](JEV_ROUTING_RUNBOOK.md) measured whether each
classifier selected the right handler. This lab asks a harder question: does
placing Jev in front of the existing analyst improve **final checked answers**?
The same checked analyst implementation serves both arms. This experiment
uses `gpt-6-luna` in both arms; the accepted M7 checkpoint used
`gpt-6-sol`. Nothing in this study promotes Jev to production automatically.

## Experiment and reference

The [frozen 32-question holdout](../evals/cases/jev_e2e_v1.json) has 24
answerable and eight boundary cases. Eight opening families are absent from
the M7 25-family reference. An [independent raw-PGN tally](../reports/M8-e2e-independent-reference.json)
supplies opening counts and White 1400–1599/60+0 outcomes. The retained M3
independent raw-PGN reference supplies clock values. The case manifest binds
their hashes and the December 2025 first-day-prefix analytical snapshot.
The data are an ordered source prefix, not a representative month or player
population. The eight `clarify`/`unsupported` labels were authored under the
[label audit](M8_LABEL_AUDIT.md) and approved unchanged by the owner after
reading all eight questions before any new model response. One reviewer on
an authored set does not establish general boundary performance.

Both arms see the same question and checked tools. The baseline runs the
existing structured-output analyst for every question. The gated arm first
asks Jev Choice for one of eight routes. Only a `clarify` or `unsupported`
choice with probability at least **0.70** ends the question at the boundary;
all other choices call the unchanged analyst. Thus Jev never supplies a
number or tool argument. The answer scorer checks status, numerical result,
required tool and arguments, caveats, and evidence-ID integrity. Compare
paired final-answer passes, boundary errors, fallback count, elapsed time,
gross provider cost, and cost per correct final answer. A good classifier
score alone is insufficient.

## Reproduce without credentials

From the repository root, install the locked environment and run the offline
contract tests. If the standard uv cache is inaccessible, use the repo-local
cache shown below. A clean checkout can run the mock test, but the 32-case
oracle test needs the ignored, retained December data project.

```sh
UV_CACHE_DIR=.uv-cache uv sync --locked --offline --no-editable \
  --extra dbt --extra dashboard --reinstall-package chess-analytics-lab
UV_CACHE_DIR=.uv-cache uv run --locked --offline --no-editable \
  pytest -q tests/test_jev_e2e.py
```

To rebuild the independent opening reference with the retained raw source,
inspect [its script](../scripts/reference_jev_e2e.py) and run
`python -m scripts.reference_jev_e2e`. The case builder is
`python -m scripts.build_jev_e2e_cases`. These commands rewrite frozen
files, so compare their hashes to the committed manifest before accepting
changes. The checked-tool oracle replay and timeout/cap mock tests make no
provider request. They are harness evidence, not model accuracy.

## Measured paired run and decision

The single paired live run completed 32 questions per arm without a transport
failure. The [original actual report](../reports/M8-e2e-paired-actual.json)
recorded **30/32** in each arm. Inspection found one rubric false negative
in both arms: the analyst fetched the expected clock proxy metric and then
an additional checked coverage metric, so the original M7 scorer rejected
the expected metric merely because it was not the final evidence item. The
saved answers were [rescored offline](../reports/M8-e2e-paired-rescore.json)
under versioned `m8-e2e-1.1`, which checks that the expected metric appears
anywhere in the validated evidence. No model request was repeated. Both arms
then scored **31/32**, with 23/24 answerable and 8/8 boundary cases. The
unanswered case in both arms asked for observed UTC dates and received
`unsupported` rather than the checked coverage result. The original score
and its failure are retained rather than overwritten.

| Executed arm | Final answers, rescored | Analyst calls | Jev calls | Gross API cost | Gross/correct | Sum of per-case elapsed time |
|---|---:|---:|---:|---:|---:|---:|
| Luna analyst | 31/32 | 32 | 0 | $0.00242630 | $0.00007827 | 83.97 s |
| Jev gate + Luna fallback | 31/32 | 26 | 32 | $0.002503882 | $0.00008077 | 86.11 s |

The Jev gate safely ended six boundary requests and sent all 24 answerable
questions to the analyst. At this size and price, its extra 32 requests
cost more than the six avoided analyst calls, and total elapsed time was
slightly higher. It did not improve the shared coverage failure. The
[checkpoint](../reports/M8-e2e-checkpoint.json) therefore keeps Jev as an
isolated learning lab. This run shows no benefit for the tested Luna pairing;
it does not measure Jev with the accepted Sol configuration. One paired run
cannot establish latency or quality stability. A future integration would
need a higher-volume or differently priced use case and fresh, independently
reviewed holdout evidence.

Reproduce the versioned scoring correction from retained ignored raw
answers:

```sh
python -m scripts.replay_jev_e2e --repo . \
  --attempt work/m8-e2e-attempt-1 \
  --output work/m8-e2e-rescore-check.json
```

## Capped provider run

The compact [historical preflight](../reports/M8-e2e-preflight.json) states the model,
rates, source hashes and conservative whole-run reservations. The full
request hashes live in ignored `work/m8-e2e-preflight.json`. Regenerate it
after a source, holdout, model, or data change:

```sh
UV_CACHE_DIR=.uv-cache uv run --locked --offline --no-editable \
  python -m chess_analytics.jev_e2e prepare --repo . \
  --data-project work/m7-december-project \
  --preflight work/m8-e2e-preflight.json
```

The executed 32-case reservation was about **$0.008664432 TypeSafe** and
**$0.1186775 OpenAI**. OpenAI reserves 64 calls: 32 baseline plus all 32
possible gated fallbacks. Actual spend can be lower. The quote is deliberately
conservative but is not a contractual tokenizer or billing bound. Credits
do not set a cap. The approved caps for this one study are $0.03 TypeSafe
and $0.20 OpenAI cumulative gross for this completed attempt. Only named ignored files
`work/.env.typesafe` and `work/.env` supply personal keys; no ambient key is
read. The live command is:

```sh
UV_CACHE_DIR=.uv-cache uv run --locked --no-editable \
  python -m chess_analytics.jev_e2e run --repo . \
  --data-project work/m7-december-project \
  --preflight work/m8-e2e-preflight.json \
  --jev-env work/.env.typesafe --openai-env work/.env \
  --jev-cap 0.03 --openai-cap 0.20 \
  --output work/m8-e2e-attempt-1
```

The scorer changed after the run, so its historical full preflight will
correctly fail the source-hash check for a future run. A fresh run requires
a regenerated preflight and newly approved caps. Each request's raw response
or failure and the attempt report stay in ignored `work/`. Before transport,
the runner writes a durable pending record reserving the full quoted call.
A stopped attempt is never scored as complete. On retry under the same
approved caps, use a fresh output directory and pass each earlier attempt
with `--prior-attempt work/ATTEMPT_DIR`. The runner reconciles settled
usage and unresolved reservations. Manual prior totals remain available
for verified external charges; do not combine them with `--prior-attempt`.
Never overwrite or silently retry a failed attempt. Tracked reports
summarize evidence without keys or raw API payloads. Offline replay and
mock transport passes are harness evidence, not live model performance.

## Interpreting the gate

Promotion would require a final-answer benefit at comparable boundary
safety, rather than just a cheaper route label. A high-confidence false
`clarify` or `unsupported` is a lost answer and matters more than a harmless
fallback. In 32 fixed cases, even a clean paired result is exploratory;
future use would need fresh cases, independent review beyond one owner, and
variability checks. The DuckDB Jev extension remains an isolated learning
exercise because the pinned production DuckDB build did not provide a
compatible community extension binary.
