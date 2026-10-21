# 0093. grok-4.7 live eval and reasoning-effort sensitivity

- Status: accepted
- Date: 2026-10-21

## Motivation

[ADR 0089](0089-llm-quality-evaluation.md) compares two OpenAI models on
the manual live-eval job. [ADR 0091](0091-manual-live-eval-workflow.md)
is that job: `gpt-6-luna` and `gpt-6-sol`, `reasoning.effort` of `none`,
and one OpenAI environment secret. John asked for `grok-4.7` as a third
comparison, with a $5 per-run cap, and then for three separate 5-repeat
runs at reasoning efforts low, medium, and high.

grok-4.7 cannot disable reasoning. The model page lists `low`, `medium`,
`high`, and `xhigh`, and the default is `high`. `none` is not an allowed
effort. Low is the closest setting to the OpenAI quote, which sends
`none`. This record keeps low as the headline arm and treats medium and
high as a sensitivity analysis.

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
analysis. The headline comparison against the OpenAI models is low.
Medium and high are separate dispatches of the same 48-case set. They
are a sensitivity analysis of reasoning effort, not extra headline arms.

The same model at two efforts has to stay distinguishable after the run.
The receipt field `reasoning_effort` stores the resolved effort. The
Actions run title is `Live eval <model> effort <input> x<repeats> cap
<cap>`, using the raw input because GitHub evaluates `run-name` before
any step. The artifact name is
`live-eval-receipt-<model>-<resolved effort>-<run_id>`. `check-inputs`
writes the resolved effort to `LIVE_EVAL_RESOLVED_EFFORT`. For the
sensitivity analysis, select `low`, `medium`, and `high` explicitly so
the title, the receipt, and the artifact all name that effort. A
`model-default` grok run still records `low` on the receipt and the
artifact. Its title says `model-default`.

The per-run ceiling is $5 for grok-4.7, $0.50 for Luna, and $10 for Sol.
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

The 5-repeat input ceiling is about $6.14 at the uncached $2 rate
before any output or reasoning. Adding the 512 visible tokens does not
bring a 5-repeat run under $5. All three 5-repeat reservations exceed
the $5 cap, and the 1-repeat high reservation exceeds it as well.
1-repeat low and 1-repeat medium fit under $5. `check-inputs` accepts
low, medium, and high at `max_run_usd` of 5. The dry run then exits 1
with a reservation error, before the live step and before the secret
step. That is a clean refusal. A 5-repeat grok-4.7 dispatch at the $5
cap does not send a request. The cap was not raised, and the ceiling
was not replaced with a bytes-divided-by-4 estimate. That estimate can
start a run whose bill exceeds the cap.

The three 5-repeat reservations sum to $58.960530. That is above the
$10 monthly key limit. The monthly limit would also be exceeded by any
one of the medium or high reservations alone.

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

Under those assumptions, a 5-repeat run costs about:

| Effort | Cold prompts | Cached repeats 2–5 | Cold band |
|---|---:|---:|---:|
| low | $2.11 | $1.26 | $1.67–$2.68 |
| medium | $3.69 | $2.84 | $2.25–$5.85 |
| high | $7.29 | $6.44 | $3.69–$13.05 |

The three point estimates together are about $13.08 with cold prompts
and about $10.54 if repeats 2–5 hit the cache. Both are over the $10
monthly limit. High alone is over the $5 per-run cap at the 4,000-token
point. Low and medium point estimates fit under $5, and the runner
still refuses them, because the reservation is the byte ceiling above.
If high reasoning stays near 1,500 tokens and the cache hits, the three
runs can land under $10. That is the optimistic end of the band, not
the planning point.

`provider.py`, `pricing.py`, `live_runner.py`, and the new
`model_catalog.py` are in `frozen_file_sha256`. A later receipt will
not match a receipt written before this change. `preflight.py` is
unchanged. The offline gate compares the scorecard with
`evals/baselines/analyst_gate_v1.json`. That baseline is unchanged.
The implementation hash includes `src/`, so a later snapshot id can
change. The gate does not compare that hash.

The workflow still has no `schedule`, no `push`, and no `pull_request`.
It sets no `timeout-minutes`. A hung grok-4.7 request can sit for 180
seconds. Two hundred and forty such timeouts are longer than the
360-minute GitHub-hosted job limit, so a fully hung run can be stopped
by the platform after spend has started. A shorter workflow timeout was
not added, because it would cancel a paid run that is still inside the
platform limit. OpenAI reservations are unchanged: Luna 5-repeat
$0.443594 and Sol 5-repeat $8.871288.

No live request was sent, so several provider details are unverified.
`cost_in_usd_ticks` is not used. Temperature and `top_p` are left unset.
A usage object whose `total_tokens` exceeds input plus output, and which
omits `reasoning_tokens`, is billed without that gap. The documented
Responses example includes `reasoning_tokens` and is priced from those
fields. Encrypted reasoning items without `content` are skipped. A
`content` value of null becomes a scored miss. The prompt cache key
does not guarantee a hit. Server-side tool fees are not priced because
the request sends no tools.

## Results

Checked on this Linux agent on 2026-10-21. No model was called.
`CHESSLAB_OPENAI_API_KEY` and `CHESSLAB_XAI_API_KEY` were unset. The
suite counts below are filled in after the offline bar on this branch.

The dry-run figures in the decision table are the runner's printed
`reserved_usd` for this fixture. The test pins the three 5-repeat
strings. A 5-repeat dry run at `max_run_usd` 5 raises `ReservationError`
for low, medium, and high, and the transport is not called.
