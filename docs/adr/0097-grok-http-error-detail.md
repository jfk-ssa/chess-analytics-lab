# 0097. Keep the grok HTTP error body

- Status: accepted
- Date: 2026-10-21

Open pull request #44 still adds `0094-hosted-read-only-dashboard.md`.
This record is 0097.

## Motivation

After [ADR 0095](0095-grok-4-7-live-eval.md) merged, the first grok-4.7
dispatch was low at 5 repeats with cap $10:
[run 39532514934](https://github.com/jfk-ssa/chess-analytics-lab/actions/runs/39532514934)
on `366a261`. The dry run reserved $9.822470 and resolved the effort to
`low`. The live step stopped on the first request. The receipt row says
`transport_failure: RuntimeError: provider HTTP 400: unavailable`,
`gross_cost_usd` null, `resolved_model` null, and
`known_gross_cost_usd` 0. `incomplete_reason` is `transport_failure`.
No case was scored. That receipt is not committed. The artifact name
was `live-eval-receipt-grok-4.7-low-r5-39532514934`.

`unavailable` is not the provider message. `_default_transport` read
`error` as an OpenAI object and called `.get` on it. A string `error`
raises `AttributeError`, and that handler replaced the body with
`unavailable`.

## Decision

HTTP error text is kept. An OpenAI object still formats as
`type: message`, with the message cut at 500 characters. A string
`error` is kept, prefixed with a top-level string or integer `code`
when that code is present. A body with top-level `code` and `message`
and no error object uses those fields. Anything else, including
non-JSON, uses a snippet of the raw body, or `empty body` when the
read is empty. The read stays 8192 bytes. The snippet is 500
characters. Every detail passes through `_redact_known_keys`, and the
transport key is replaced as well. An `Authorization: Bearer` value in
the body is replaced. The request header is not copied into the
exception.

The request body is unchanged. Checked on 2026-10-21, the current docs
do not mark a field this harness sends as unsupported. The pinned
reservations stay low at 5 repeats $9.822470, medium at 1 repeat
$3.734254, and high at 1 repeat $6.093358.

| Item | What the docs say | Change |
|---|---|---|
| Model id `grok-4.7` | [Release notes](https://docs.x.ai/developers/release-notes) and the [Responses reference](https://docs.x.ai/developers/rest-api-reference/inference/responses) use `grok-4.7` | none |
| `reasoning.effort` `low` | [Reasoning](https://docs.x.ai/developers/model-capabilities/text/reasoning): grok-4.7 accepts `low`, `medium`, `high`, and `xhigh`. Reasoning cannot be disabled. `presencePenalty`, `frequencyPenalty`, and `stop` error; this body sends none of those | none |
| `prompt_cache_key` | Responses reference: plumbed to `x-grok-conv-id` for routing. [Best practices](https://docs.x.ai/developers/model-capabilities/text/best-practices) tell callers to set it | none |
| `store: false` | [Generate text](https://docs.x.ai/developers/model-capabilities/text/generate-text) shows `store: false` on `grok-4.7` | none |
| `text.format` `json_schema` with `strict: true` | [Structured outputs](https://docs.x.ai/developers/model-capabilities/text/structured-outputs) shows that object for `grok-4.7`. `PLAN_SCHEMA` uses `type`, `enum`, `required`, `additionalProperties: false`, and `maxItems: 4`. Enums are non-empty. `maxItems` is guaranteed through 256. `additionalProperties` defaults to false. `pattern`, `oneOf`, `anyOf`, and nullable types are not in this schema. Rejected schemas on that page are empty `enum` or `anyOf`, boolean property schemas, `minContains` / `maxContains`, and `items` as an array | none |
| `max_output_tokens` 512 | Responses reference: an integer cap on visible output tokens, not reasoning tokens. Default when unset is 128000 | none |
| `instructions` and string `input` | Both are request fields. `input` is `string` or array. `instructions` cannot be combined with `previous_response_id`. This body does not send `previous_response_id` | none |
| `metadata`, `truncation`, `background` | The reference marks these unsupported or compatibility-only. This body does not send them | none |

[Debugging errors](https://docs.x.ai/developers/debugging) says HTTP 400
means check the request body or URL, and HTTP 422 means a field format
is invalid. It does not publish the error JSON. A missing or invalid
token is HTTP 401, so this 400 is a weak match for a bad key. The
string-`error` parser is for the shape that became `unavailable`, not
because that page prints the JSON.

These points stay uncertain, and they are not a reason to edit the
body: the reference lists `text.format` without spelling the schema
keywords inside it; no example shows `instructions`, a string `input`,
`reasoning.effort`, and `text.format` in one request; `strict: true`
might still reject a schema the supported-keyword list does not name.
The next live receipt is what can show the provider sentence.

## Results

No model was called for this change. The failed run above is the
retained live failure. Local checks are in the pull request. The gate
baseline is unchanged.
