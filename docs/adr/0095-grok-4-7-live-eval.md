# 0095. grok-4.7 live eval and reasoning-effort sensitivity

- Status: accepted
- Date: 2026-10-21

Main includes [ADR 0093](0093-first-live-eval-receipts.md) and
[ADR 0096](0096-published-live-eval-report.md). This record is 0095.
Open pull request #44 adds `0094-hosted-read-only-dashboard.md`.

## Motivation

[ADR 0089](0089-llm-quality-evaluation.md) compares two OpenAI models on
the manual live-eval job. [ADR 0091](0091-manual-live-eval-workflow.md)
is that job: `gpt-6-luna` and `gpt-6-sol`, `reasoning.effort` of `none`,
and one OpenAI environment secret. John asked for `grok-4.7` as a third
comparison. The per-run cap is $10. The headline dispatch is low at 5
repeats. Medium and high are a sensitivity check at 1 repeat each.

grok-4.7 cannot disable reasoning. The model page lists `low`, `medium`,
`high`, and `xhigh`, and the default is `high`. `none` is not an allowed
effort. Low is the closest setting to the OpenAI quote, which sends
`none`. This record keeps low at 5 repeats as the headline arm. Medium
and high at 1 repeat are a sensitivity check. Their pass rates are for
one repeat and are not 5-repeat headline rates.

## Decision

The manual job gains the model id `grok-4.7`. The endpoint is the global
Responses URL `https://api.x.ai/v1/responses`. The US regional host is
not used. That host bills 1.1 times the global token rates, and this
harness does not add that premium. The request stays on the OpenAI-shaped
planner body: `instructions`, `input`, `max_output_tokens` 512,
`reasoning.effort`, `store` false, and `text.format` `json_schema` with
`strict` true. grok-4.7 also sends `prompt_cache_key`
`chesslab-analyst-live-v1`. OpenAI bodies do not. OpenAI JSON keeps its
historical insertion order. The grok body is serialized with sorted keys.
The socket timeout is 180 seconds for grok-4.7 and stays 30 seconds for
OpenAI.

`reasoning_effort` is a workflow choice. `model-default` resolves to
`none` for `gpt-6-luna` and `gpt-6-sol`, and to `low` for grok-4.7.
Explicit `none` is rejected for grok-4.7 before any quote. Explicit
`low`, `medium`, `high`, or `xhigh` is rejected for the OpenAI ids.
`xhigh` is a valid grok-4.7 effort and is outside the sensitivity
check. The headline comparison against the OpenAI models is low at 5
repeats. Medium at 1 repeat and high at 1 repeat are separate
dispatches of the same 48 cases. The receipt field `repeats` is 5 or 1.
The job summary names that count on the pass-rate line. A 1-repeat
summary also says the rate is not a 5-repeat headline comparison.
Do not compare those rates with the Luna, Sol, or low 5-repeat rates.

The same model at two efforts has to stay distinguishable after the run.
The receipt field `reasoning_effort` stores the resolved effort. The
Actions run title is `Live eval <model> effort <input> x<repeats> cap
<cap>`, using the raw input because GitHub evaluates `run-name` before
any step. The artifact name is
`live-eval-receipt-<model>-<resolved effort>-r<repeats>-<run_id>`.
Commit that name under `reports/`. [ADR 0096](0096-published-live-eval-report.md)
sorts `reports/live-eval-receipt-*.json` by the trailing run id, so
`r<repeats>` is not read as the run id. The committed Luna and Sol
files stay `live-eval-receipt-<run_id>.json`. `check-inputs`
writes the resolved effort to `LIVE_EVAL_RESOLVED_EFFORT`. For the
sensitivity analysis, select `low`, `medium`, and `high` explicitly so
the title, the receipt, and the artifact all name that effort. A
`model-default` grok run still records `low` on the receipt and the
artifact. Its title says `model-default`.

The per-run ceiling is $10 for grok-4.7, $0.50 for Luna, and $10 for Sol.
The ceiling is not scaled with repeats. The personal-account
acknowledgement applies to the xAI key as well as the OpenAI key. The
new environment secret is `CHESSLAB_XAI_API_KEY` on `live-eval`. John
adds it. The live step passes only the secret for the selected provider.
The OpenAI expression is true only when the model is not grok-4.7. The
xAI expression is true only when the model is grok-4.7. The other
expression is empty. The shell then refuses the run if the other
variable is non-empty, and it exits if the selected key is empty. The
secret step is still after the ref guard, the price check, the input
check, and the dry run. A repository secret of the same name would be
visible when the environment secret is absent, so the name stays off
the repository secrets. John is setting a $10 monthly limit on the xAI
key. That limit is provider-side. This repository does not read it and
does not enforce it.

Prices were read from the grok-4.7 model page and the xAI pricing page
on 2026-10-21. Below 200,000 prompt tokens the rates are $2.00 input,
$0.50 cached input, and $6.00 output per million tokens. At or above
200,000 prompt tokens the whole request bills $4.00, $1.00, and $12.00,
including cached input and reasoning. Reasoning tokens bill as output.
xAI publishes no cache-write premium. The recorded price-check date
stays `2026-10-20` in `preflight.py`. That OpenAI recheck is inside the
14-day window on 2026-10-21, so a dispatch that day does not need
`allow_stale_price_check`. `pricing.py` still does not store a date.
`prices_rechecked` stays false. The long-context rates are code, and
the quote uses them when the prompt ceiling reaches 200,000 tokens.
This fixture does not reach that tier.

The reservation is a ceiling, not a forecast. Input tokens are the
ASCII length of the JSON body plus the same 1,000-token envelope the
OpenAI quote uses. A token is at least one byte, so the length is an
upper bound. Cached input is cheaper, and the reservation assumes a
cache miss. Visible output is reserved at `max_output_tokens` (512).
The grok-4.7 best-practices guide says that field caps the visible
answer and that reasoning tokens sit outside it. The REST reference
still says `max_output_tokens` includes reasoning and that
`reasoning.effort` is only supported by grok-4.3. This harness follows
the grok-4.7 model page and best-practices guide. xAI publishes no
per-effort maximum. The extra reasoning tokens reserved on top of 512
are a harness ceiling: low 2,048, medium 8,192, high 16,384, and xhigh
32,768. They are not a measured usage and not an API-enforced cap. One
response can therefore cost more than its quote before the runner stops
the next request.

On 2026-10-21 the offline dry run of the 48-case fixture, with no
network, printed these short-tier reservations. Every prompt ceiling
was about 12,800 tokens. The long-context tier was not used.

| Effort | 1 repeat, 48 requests | 5 repeats, 240 requests |
|---|---:|---:|
| low | $1.964494 | $9.822470 |
| medium | $3.734254 | $18.671270 |
| high | $6.093358 | $30.466790 |

John's run plan uses the $10 cap as follows. Low at 5 repeats reserves
$9.822470 and the dry run proceeds. Medium at 1 repeat reserves
$3.734254 and proceeds. High at 1 repeat reserves $6.093358 and
proceeds. Medium at 5 repeats reserves $18.671270 and high at 5 repeats
reserves $30.466790. Both exceed $10, so those dry runs exit 1 with a
reservation error before the live step and before the secret step.
The dry-run command is piped to `tee`. That step sets `pipefail`, so
the reservation failure is the step's status. Without it, `tee` would
succeed and the secret step would still run.
The ceiling was not replaced with a bytes-divided-by-4 estimate.

The three planned reservations sum to $19.650082. That is above the
$10 monthly key limit. The expected spend of the same three runs is
not. The provider stops the key at the monthly limit if actual usage
reaches it. This repository still does not enforce that limit. Dispatch
low at 5 repeats first. Compare that receipt's `known_gross_cost_usd`
and `token_usage` with this quote before dispatching the 1-repeat
checks. `token_usage` sums `input_tokens`, `output_tokens`,
`reasoning_tokens`, and `billed_output_tokens`, so the check does not
add the rows by hand.

A realistic expected cost is a different number, and it is not what the
runner enforces. The assumptions are stated here so the two figures
stay separate.

- Prompt tokens are estimated as body bytes divided by 4. The 48 bodies
  at effort low sum to 565,607 bytes, about 141,402 tokens per pass.
  The effort name changes that length by a few bytes.
- One pass of cold input at $2 per million is about $0.283. Five cold
  passes are about $1.414. If `prompt_cache_key` hits for repeats 2
  through 5, those four passes use the $0.50 cached rate and the input
  total is about $0.566. A hit is not guaranteed.
- Visible JSON is estimated at 80 tokens. The oracle plans for these
  cases are 89 to 312 bytes.
- Reasoning tokens are not published per effort. The planning point is
  400 for low, 1,500 for medium, and 4,000 for high. The bands used
  below are 100–800, 500–3,000, and 1,500–8,000. Output is $6 per
  million.
- No tool fees. The request sends no tools. The short-context rates
  apply. The global endpoint applies.

Under those assumptions, the planned runs cost about:

| Run | Cold | Cached later repeats | Cold band |
|---|---:|---:|---:|
| low, 5 repeats | $2.11 | $1.26 | $1.67–$2.68 |
| medium, 1 repeat | $0.74 | cold only | $0.45–$1.17 |
| high, 1 repeat | $1.46 | cold only | $0.74–$2.61 |

The three planning points together are about $4.31 if every prompt is
cold, and about $3.46 if repeats 2–5 of the low run hit the cache.
That is the expected total near $4–5. The top of the three bands
together is about $6.46, still under the $10 monthly limit. A 5-repeat
medium or high run is not part of the plan. Those reservations are
above the $10 per-run cap and the dry run stops them.

`provider.py`, `pricing.py`, `live_runner.py`, and the new
`model_catalog.py` are in `frozen_file_sha256`. A later receipt will
not match a receipt written before this change. `preflight.py` is
unchanged. The offline gate compares the scorecard with
`evals/baselines/analyst_gate_v1.json`. That baseline is unchanged.
The implementation hash includes `src/`, so a later snapshot id can
change. The gate does not compare that hash.

The workflow still has no `schedule`, no `push`, and no `pull_request`.
The job sets `timeout-minutes: 150`. The runner also stops before the
next request once 140 minutes have passed in the live loop, writes the
receipt with `incomplete_reason` `wall_clock`, and leaves the upload
time inside the job timeout. ADR 0091 left the job at the platform's
360-minute limit so a paid run would not be cancelled early. A grok
socket timeout of 180 seconds times 240 requests is 12 hours. The
platform would stop that hang only after about 120 requests. The new
bound stops it after about 46.

The bound comes from the two completed OpenAI jobs, not from a grok
call. The Luna 5-repeat live step was 413 seconds (run 39494372489)
and the Sol 5-repeat live step was 379 seconds (run 39519293762). The
slower request average is about 1.7 seconds. One hundred and fifty
minutes allows about 37 seconds average across 240 requests, about 22
times that measurement, plus the under-one-minute setup those jobs
used. A 1-repeat run of 48 requests fits even at two minutes each. It
does not fit if every call sits on the 180-second socket timeout. That
is the hang this bound is for. OpenAI reservations are unchanged: Luna
5-repeat $0.443594 and Sol 5-repeat $8.871288.

No live request was sent, so several provider details are unverified.
Temperature and `top_p` are left unset. Encrypted reasoning items
without `content` are skipped. A `content` value of null becomes a
scored miss. The prompt cache key does not guarantee a hit. The
request sends no tools. Whether `max_output_tokens` includes reasoning
is still the disagreement recorded above.

Usage pricing does not drop tokens the response already reported.
Billed output is the max of `output_tokens` plus reasoning, and
`total_tokens` minus `input_tokens`, except when reasoning is already
inside the output. That contained case is only when `reasoning_tokens`
is less than or equal to `output_tokens` and `total_tokens` equals
input plus output. The documented Responses example is 32 input, 9
output, 110 reasoning, and 151 total, so reasoning is added. A subset
with reasoning inside a matching total is not added. An omitted
`reasoning_tokens` whose total is larger than input plus output is
billed at `total_tokens - input_tokens`. Reasoning smaller than that
gap is not the whole bill; the gap is. A total that equals input plus
output while reasoning is greater than output is not treated as
contained, so the reasoning tokens are added. A missing total with
reasoning present adds those reasoning tokens. Pricing raises when
reasoning and the total are both missing, when `total_tokens` is below
`input_tokens`, or when a present count is not a non-negative integer.
The runner then charges that request's quote and does not send another.

`cost_in_usd_ticks` divided by 10^10 is the provider charge for that
request, including cache discounts and server-side tool fees. When the
field is a non-negative integer, the price is the max of the token
reconstruction and the tick charge. A lower tick figure does not reduce
the reconstruction. `num_server_side_tools_used` above zero requires
the tick field. Without it, pricing raises and the run stops.

## Results

Checked on this Linux agent on 2026-10-21. No model was called.
`CHESSLAB_OPENAI_API_KEY` and `CHESSLAB_XAI_API_KEY` were unset.

The dry-run figures in the decision table are the runner's printed
`reserved_usd` for this fixture. The test pins them. At `max_run_usd`
10, low at 5 repeats and medium and high at 1 repeat pass the dry run.
Medium and high at 5 repeats raise `ReservationError`. The transport
is not called. A live loop whose wall clock is already past the limit
writes `incomplete_reason` `wall_clock` and sends no further request.

- `ruff check .` passed. After the rebase onto the published report,
  `ruff format --check .` reported 326 files already formatted.
- basedpyright reported 0 errors, 0 warnings, and 0 notes.
- After that rebase and the trailing-run-id sort, `pytest -q` reported
  370 passed, 31 skipped, 118.65s. The grok tests still cover the quote,
  reservation, workflow checks, the wall-clock stop, and the usage rows
  that must not price below the reported bill. Those rows are the
  omitted total gap, reasoning smaller than that gap, reasoning larger
  than output when the total matches input plus output, tick charges
  above and below the reconstruction, and server-side tools without
  ticks. `discover_receipts` sorts both `live-eval-receipt-<run id>.json`
  and `live-eval-receipt-<model>-<effort>-r<repeats>-<run id>.json` by
  the trailing run id.
- The dbt extra and the gate were not re-run for this pricing change.
  Before it, on this date, `CHESSLAB_REQUIRE_DBT=1 pytest -q` reported
  361 passed and 19 skipped, and the gate printed `ok 89/89`.
  `evals/baselines/analyst_gate_v1.json` is unchanged.
- actionlint was not re-run. The earlier 1.7.12 check of
  `live-eval.yml` had no findings, and this change adds the repeat
  count to the artifact name. `tests/test_live_eval_workflow.py`
  passed, including the mutated-workflow failures and removal of
  `pipefail` from the dry-run step. The workflow was not dispatched
  from this agent. There is no key on this agent.

After this record merged, John dispatched low at 5 repeats. That run
stopped on HTTP 400 and the receipt detail was `unavailable`.
[ADR 0097](0097-grok-http-error-detail.md) keeps the error body and
leaves this request unchanged.
