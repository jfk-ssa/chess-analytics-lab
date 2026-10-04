# M7 Sol development diagnostic — frozen before calls

The January Luna holdout failed its three-run gate in repetition 2 when the
provider emitted conflicting apparent plans: a valid opening-score plan
mixed with a fabricated tool transcript, followed by an evidence-free
`answered` plan. The checked core failed closed. The first January run met
every per-run quality threshold, but historical live scores remain unchanged.

Use six **inspected January cases** as a development diagnostic of
`gpt-6-sol` response reliability: exact opening usage, the problematic
White opening score, an opening comparison, a clock proxy, a private-file
boundary and a missing-rating clarification. These are not a new holdout.
The [preflight](../reports/M7-Sol-development-preflight.json) freezes the
exact requests, source/code hashes, model and prices. The expected checks
are six completed requests with known usage, no malformed plan or transport
failure, at least five scored passes, both boundary cases correct, and
checked evidence on every answered result. Failures and raw responses are
retained. Only a clean diagnostic merits preparing a fresh-data full Sol
gate, which would require a separately recommended spending cap.

Official OpenAI documentation lists Sol with Responses structured-output
support at $2 input, $0.20 cached input, $2.50 cache write and $10 output
per million tokens, checked 2026-10-04. The six-request conservative
reservation is **$0.223097500**. Prior cumulative M7 gross accounted is
**$0.120814360**; their sum **$0.343911860** fits the already approved
**$0.50 cumulative cap**. The runner uses only the named personal key from
the ignored local env file, charges unknown attempts at full reservation,
and stops on the first failed request.

Source: [GPT-6 Sol model page](https://developers.openai.com/api/docs/models/gpt-6-sol).

## Observed diagnostic result

All six actual Sol responses completed and scored passes with known usage.
The two boundary cases passed; no semantic repair, malformed-chunk recovery
or transport retry was needed. Gross was **$0.017980600**, bringing
cumulative M7 accounted gross to **$0.138794960**. This supports preparing
a fresh-data Sol holdout, but six inspected cases do not establish
repeatability or a release quality claim.
