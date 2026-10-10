# 0033. Retire January Luna gate; test Sol on inspected cases

- Status: accepted
- Date: 2026-10-04

January v11 repetition 1 met all per-run gates: 48/50 scored,
39/41 answerable, 9/9 boundary, 5/5 high severity, 50/50 evidence audit,
no retry or semantic repair. Repetition 2 stopped at cell 26 after 25
completed scored passes. The provider mixed a valid opening-score plan with
a fabricated tool transcript, then a separate evidence-free `answered`
plan. The checked core rejected it. Keep the original result stopped rather
than choosing a plan arbitrarily. Cumulative M7 accounted gross through the
January gate is $0.120814360.

Official OpenAI documentation lists `gpt-6-sol` with Responses structured
outputs and per-million-token prices of $2 input, $0.20 cached input,
$2.50 cache writes and $10 output. A six-case inspected January diagnostic
was frozen with a $0.223097500 whole-run reservation under the existing
$0.50 cumulative cap. All six actual calls completed and scored passes,
including the previously troublesome opening-score and boundary requests,
with $0.017980600 gross and no malformed response. This is development
evidence only. Cumulative M7 accounted gross is now $0.138794960. Prepare
a new December dataset, independent references and full Sol preflight
before requesting a higher cumulative cap; make no full-holdout Sol calls
under the current approval.
