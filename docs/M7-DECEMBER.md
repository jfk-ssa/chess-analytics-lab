# M7 December Sol v12 gate — frozen, awaiting spending-cap approval

January v11's first Luna run met every per-run threshold, but repetition 2
stopped at a conflicting provider response. Do not select between those
apparent plans; the checked core correctly rejected an evidence-free answer.
All previous Luna failures and offline replays remain scored as originally
observed. A separately frozen six-case `gpt-6-sol` **development** diagnostic
on inspected January cases completed and scored 6/6 without parser repair,
semantic repair or transport retry. That diagnostic motivates a new holdout;
it is not release evidence.

The new December 2025 source is exactly the first 40,000,000 compressed
bytes of the Lichess standard-rated archive. It covers **December 1 only**,
not a complete archive, random sample or monthwide population. Of 100,000
complete PGNs, 99,307 were accepted and 693 excluded, with no quarantine or
conflict. The deterministic move sample selected 4,942 games and 325,870
move rows. Independent raw-PGN checks agree with the published source draw
rate, 12 opening families, four player cohorts and four clock buckets. A
separate raw-PGN reference tallied 25 opening families and four specified
White 1400–1599 60+0 cohorts. All 50 checked-tool/offline-oracle outcomes
match their references. No December model response has been scored.

The 50 frozen cases comprise 41 answerable, nine
clarification/unsupported, and five high-severity boundary questions. The
dataset/date is new; task concepts and many opening names recur, so this is
not a semantics-disjoint sample. The [preflight](../reports/M7-December-Sol-v12-preflight.json)
binds the case set, independent values, source/code hashes, exact request
hashes, Sol model, official prices, and proposed cap. The product
`semantic_context` condition is the only condition. The personal key is
read only from the ignored named local env file at run time.

## Acceptance rule committed before live scoring

Three complete repetitions of the identical 50-request preflight must
each score at least 37/41 answerable, all 9/9
clarification/unsupported, and all 5/5 high-severity cases. Every
completed answer must pass the evidence/access audit. Case IDs, request
hashes, order, dataset and resolved model must match the freeze. No
transport retry, failed/unknown-cost or unattempted cell is accepted.
All responses, failures and scored misses are retained. Deterministic
semantic repairs and any recovered provider text must be reported
separately from unmodified model plans. Passing supports only a fixed-case
new-date, three-repetition checkpoint, not population accuracy, statistical
significance, or a complete-month trend.

## Spending decision

Prior M7 gross accounted is **$0.138794960** under the approved $0.50
cumulative cap. Official OpenAI documentation lists Sol at $2 input,
$0.20 cached input, $2.50 cache write and $10 output per million tokens.
The exact frozen conservative reservation is **$1.859967500 per 50-case
run**. Three full reservations plus prior spend are **$5.718697460**.
The recommended maximum cumulative gross cap is **$6.00**; this is a
ceiling, not an expected charge. The six-case actual diagnostic cost
**$0.017980600**; simple proportional scaling gives about **$0.449515**
for 150 calls and **$0.588310** including prior M7 spend, but case mix,
caching, response length and failures can change that. The conservative
bound controls authorization. The runner stops when the remaining cap
cannot reserve another full repetition, or after a failed request, unknown
usage or bound violation. No December live call is authorized until the
user approves the higher cap.

Source: [GPT-6 Sol model page](https://developers.openai.com/api/docs/models/gpt-6-sol).
