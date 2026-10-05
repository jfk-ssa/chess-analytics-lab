# Learning lab: when does Jev help route chess questions?

This is the M8 experiment. The product remains the M0–M7 checked data and
analyst system. A router chooses **which existing handler** might answer a
question; it does not calculate chess metrics, approve arbitrary SQL, or
establish that the final answer is correct. Work through this lab offline
first. The measured [comparison page](../reports/M8-routing-comparison.html)
and [checkpoint](../reports/M8-routing-checkpoint.json) show the actual runs.

## What you are testing

The eight closed labels are `opening_usage`, `opening_score`,
`opening_compare`, `clock_bucket`, `clock_compare`, `coverage`, `clarify`, and
`unsupported`. The last two are boundary decisions: ask for a missing
referent, or decline a request beyond the observed dataset. The same 40 new
test questions are presented to a keyword/rule router, the existing
structured-output analyst, and Jev Choice. The other 40 questions form a
development split. [The case file](../evals/cases/jev_routing_v1.tsv) and
[manifest](../evals/cases/jev_routing_v1_manifest.json) fix identities,
labels, and a SHA-256 hash before model results are scored. Cases are
manually authored and labeled; no independent human adjudication has yet
checked those labels, so this is an exploratory comparison rather than an
unbiased population estimate. The test set is balanced by label, unlike a
real usage distribution.

The rules are intentionally simple and frozen before their first test score.
They get **35/40** test routes right and identify all five unsupported
requests. This establishes a cheap comparator, not a target for test-set
tuning. The five failures and full confusion matrix are in
[the rules report](../reports/M8-routing-rules-test.json). The
[DuckDB offline replay](../reports/M8-duckdb-offline.json) creates a
40-row table, reads its questions, and applies those same Python rules. It
therefore has the same 35/40 score and is explicitly **not** a Jev result.

## Measured M8 checkpoint

The 40-case test was run twice through pinned `jev-1.13.0` and once completely
through the existing `gpt-6-luna` structured analyst. Each model pass used the
same question IDs and frozen reference labels. These are **actual provider
responses**, unlike the offline rules and mock tests.

| Path | Correct routes | Unsupported recall | Gross API cost for complete pass |
|---|---:|---:|---:|
| Rules | 35/40 | 5/5 | $0 |
| Existing structured analyst | 33/40 | 5/5 | $0.00226205 |
| Jev pass 1 | 39/40 | 5/5 | $0.001000188 |
| Jev pass 2 | 37/40 | 5/5 | $0.001000188 |

Two of 40 Jev routes changed between identical requests (`b10`, `v09`).
`v07` was routed to clarification in both passes although its reference is
coverage. At threshold 0.70, Jev auto-routed 34/40 in each pass with zero
errors among those 34; the six fallbacks still need an analyst. The HTML
comparison includes a **post hoc** fallback replay using observed per-case
analyst costs. It was not executed as one combined live path and cannot
establish its latency, cache behavior, or final-answer quality.

An initial OpenAI attempt sent requests, completed 20 cases, then stopped at
`c06` because the checked clock comparison subtracted a null coverage value.
That attempt cost $0.00191639 gross. The null arithmetic was fixed and
regression-tested offline before the complete pass. **Cumulative M8 gross**
was $0.002000376 TypeSafe under the approved $0.05 cap and $0.00417844
OpenAI under its separate $0.10 cap. The [stopped report](../reports/M8-analyst-stopped.json)
and complete [Jev pass 1](../reports/M8-jev-pass-1.json),
[Jev pass 2](../reports/M8-jev-pass-2.json), and
[analyst pass](../reports/M8-analyst-pass-1.json) are tracked summaries;
full raw attempts remain ignored under `work/`. The first analyst retry
also failed closed before transport when a rebuilt demo changed the frozen
dataset ID; it incurred no API charge.

These costs are gross metered cost, not credit purchases or cash paid. Jev
per-case elapsed time measures one classification request; the analyst's
per-case time also includes checked-tool work, so they are not like-for-like
classifier latency measurements. The analyst used the synthetic demo
snapshot; some test questions name opening families absent from that tiny
fixture. This is a semantic-routing comparison, not answer accuracy.

## Reproduce the credential-free path

Run these commands at the repository root after the locked install. If the
default uv cache is inaccessible, prefix commands with `UV_CACHE_DIR=.uv-cache`.

```sh
uv sync --locked --no-editable --extra dbt --extra dashboard
uv run --locked --offline --no-editable python -m chess_analytics.routing_study \
  rules --project . --split test > work/m8-rules-check.json
uv run --locked --offline --no-editable python -m chess_analytics.routing_duckdb \
  --project . --split test --database work/m8-questions.duckdb \
  --output work/m8-duckdb-check.json
uv run --locked --offline --no-editable python -m chess_analytics.routing_report \
  --rules reports/M8-routing-rules-test.json \
  --output work/m8-routing-comparison.html
uv run --locked --offline --no-editable pytest -q tests/test_routing_study.py
```

Use a fresh database path on repeat; the exercise refuses to overwrite an
earlier table. Open `work/m8-routing-comparison.html` in a browser. The
model panels should say *Awaiting actual evaluation* until complete real
attempts are provided. Mock responses in tests prove transport, cap, and
scoring behavior only; they never count as model accuracy.

## Prepare and run a capped live comparison

The direct adapter sends only the bounded question and a compact catalog to
TypeSafe. It pins `jev-1.13.0`, validates the Choice distribution and usage,
logs raw responses and failures, and refuses a changed preflight. It reads
only `work/.env.typesafe`, containing exactly `TYPESAFE_API_KEY=...`; never
commit or paste the key. The OpenAI comparator reads only the explicitly
named `work/.env` or `work/.env.openai` with
`CHESSLAB_OPENAI_API_KEY=...`; it uses the existing checked analyst and a
separate cap. No ambient workplace credential is discovered. Use the
synthetic demo snapshot to make the analyst input reproducible:

```sh
uv run --locked --offline --no-editable --extra dashboard chesslab demo --scope all
uv run --locked --offline --no-editable python -m chess_analytics.routing_study \
  prepare --project . --split test --preflight work/m8-jev-test-preflight.json \
  > work/m8-jev-preflight-stdout.json
uv run --locked --offline --no-editable python -m chess_analytics.routing_analyst \
  prepare --repo . --data-project work/portfolio-demo/project --split test \
  --preflight work/m8-analyst-test-preflight.json \
  > work/m8-analyst-preflight-stdout.json
```

Read `total_reserved_cost_usd`, model, rates, and request hashes before
running. The TypeSafe estimate uses four times the UTF-8 request bytes plus
1,024 tokens per request at the [published Jev rate](https://docs.typesafe.ai/models);
it is deliberately conservative but **not a contractual token bound**. The
OpenAI estimate uses the existing provider's quote and the
[published model rate](https://developers.openai.com/api/docs/models/gpt-6-luna).
Actual gross usage and unknown-cost reservations remain in the attempt log.
An API balance or promotional credit is never itself a run cap.
The current [compact offline preflight](../reports/M8-routing-preflight.json)
reserves $0.010722096 for one Jev pass and $0.07403775 for one existing-analyst
pass. Recompute the ignored full preflights after changing source, cases, or
data snapshots.

After an explicit **separate M8 cap** is approved for each provider, use
fresh ignored output directories. Replace the example cap with the approved
value; these commands are not standing spending authorization:

```sh
uv run --locked --no-editable python -m chess_analytics.routing_study \
  run --project . --preflight work/m8-jev-test-preflight.json \
  --env-file work/.env.typesafe --max-run-usd APPROVED_TYPESAFE_CAP \
  --output work/m8-jev-test-attempt-1
uv run --locked --no-editable python -m chess_analytics.routing_analyst \
  run --repo . --data-project work/portfolio-demo/project \
  --preflight work/m8-analyst-test-preflight.json --env-file work/.env \
  --max-run-usd APPROVED_OPENAI_CAP --output work/m8-analyst-test-attempt-1
uv run --locked --offline --no-editable python -m chess_analytics.routing_report \
  --rules reports/M8-routing-rules-test.json \
  --jev reports/M8-jev-pass-1.json --jev-repeat reports/M8-jev-pass-2.json \
  --analyst reports/M8-analyst-pass-1.json \
  --output work/m8-routing-comparison-actual.html
```

An attempt that stops early keeps its individual raw response/failure files
and `report.json`; the display will not convert it into a full-run score.
Gross cost per correct **route** divides all recorded call costs by correctly
routed questions. It is not cost per correct **end-to-end answer**. That
requires a separate answered-case experiment with independently checked
numeric answers and the same downstream tools for both paths. Do not infer
it from this routing table.

## Reading the result

In the confusion matrix, rows are reference labels and columns are predicted
routes; the diagonal is correct. Pay special attention to `unsupported`
recall and false `unsupported`/`clarify` decisions on answerable questions.
Overall accuracy alone can conceal both failures. Jev probabilities permit a
*selective* policy: accept a route only above a chosen probability threshold,
otherwise fall back to the existing analyst. The curve reports the fraction
automatically routed versus errors among those accepted. A high threshold
often reduces coverage; whether it reduces errors is an empirical question.
The Jev `confidence` field is not a measured probability of being right on
this chess corpus. Small bins and five test cases per class limit claims about
calibration, reproducibility, or future performance. Compare latency and
gross cost with fallback costs included before adopting the router.

## DuckDB Jev learning slice

The offline command above proves that the exact 40 questions can be loaded
and queried as a DuckDB table. Its report embeds a `jev_eval` SQL preview with
the same eight labels and row/character/retry limits. The public
[DuckDB extension page](https://duckdb.org/community_extensions/extensions/jev)
lists `INSTALL jev FROM community`, but the extension maintainer's
[build instructions](https://github.com/judoaseeta/duckdb-jev) say to build
against DuckDB 1.5.5. A real attempted install on this repository's pinned
DuckDB 1.4.1/macOS arm64 returned HTTP 404. The core lock remains untouched.
To execute the preview later, build or obtain a binary for a matching
*isolated* DuckDB version, verify the extension and TypeSafe account, and
approve a separate bounded statement cost. The extension's row and character
settings limit exposure, but its `jev_stats()` is an after-the-fact estimate,
not a hard dollar cap. Do not pass the raw game database to the extension.
The direct adapter is the measured Jev path until those conditions hold.

## Decision gate

Keep the rule and structured analyst baselines available. Only make Jev a
production route if new adjudicated cases show a useful quality or
coverage gain without regressing boundary decisions, and a separate
end-to-end experiment shows value after fallback cost. The same table can
later support a PostgreSQL `pg_jev` exercise, but running a local server and
superuser extension install solely for this 40-row experiment is not yet
justified.
