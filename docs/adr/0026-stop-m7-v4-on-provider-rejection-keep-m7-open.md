# 0026. Stop M7 v4 on provider rejection; keep M7 open

- Status: accepted
- Date: 2026-10-04

The final v4 split passed 50/50 offline oracle checks and was frozen before
live calls. Its first repetition stopped at attempt 59 when the provider
returned HTTP 400 `invalid_request_error` saying the prompt was flagged.
The failed request has no usage; charge its full $0.001043 reservation and
make no further calls on this split. Preserve 58 completed responses, 41
scored passes and 41 unattempted cells. In the first 29 completed pairs,
schema-only passed 12/29 and governed metric context 29/29. This is censored
evidence and does not establish a full-run or broad quality comparison.

Across M7, known actual gross is $0.072358895; the two unknown-cost
attempts carry $0.00200325 in full reservations. Total accounted gross is
$0.074362145 below the user-approved $0.50 cumulative cap. This includes
the separate v1 diagnostic call. The v2 and v3 frozen quality gates failed,
and v4 did not complete. Keep M7 **in progress** with a measured negative
checkpoint, rather than treating the improved development scores as an
accepted release. No more calls on inspected cases. The next credible
quality gate needs independently referenced new data, a new untouched
holdout, and a bounded acquisition method. M8 Jev remains follow-up and
the recommender remains backlog.
