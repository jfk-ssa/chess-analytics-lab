# 0013. First actual M6 development pilot

- Status: accepted
- Date: 2026-10-03

The user chose a $0.10 gross-spend cap; the account's stated $9 credit did not
set the cap. The named personal key in ignored `work/.env` was loaded for the
live run without printing or committing it. Four prompt revisions were frozen
separately. The first three stopped after an unsupported extra tool argument,
invented filter keys, and a title-case color value, respectively. Their actual
responses and failures were retained. The final 24-cell run completed with
zero execution exceptions and 16/24 frozen-scorer passes. Across all 32 API
requests the gross recorded cost was $0.0046302. This is not an untouched
holdout or a repeatability result.

The $0.0046302 figure above is the originally recorded simple-rate estimate,
preserved as historical evidence. A cache-aware recalculation from every
retained provider usage record gives **$0.0028105** gross for the same 32
requests, including $0.0018115 for the final 24 cells. The frozen 16/24 score
does not change. GPT-6 Luna's official Standard rates checked on 2026-10-03
are $0.10/M regular input, $0.125/M cache writes, $0.01/M cached input and
$0.50/M output. If cache detail is absent, charge all input at the highest
applicable input rate for conservative accounting. Future preflights freeze
all four rates, and the runner stops if reported cost exceeds a reservation.

Do not adjust the frozen 16/24 result after inspection. Two proxy answers used
an equivalent checked tool and produced the expected numbers, but failed the
strict tool-choice rubric; discuss this discrepancy alongside, not in place
of, the original score. Multi-step comparison and unsupported-status handling
also failed. The 90% numerical and ambiguity gates are unmet, so M6 remains
in progress and the analyst stays experimental. A later release evaluation
requires development fixes, an unseen family-based split and manual review of
analytical failures. See `reports/M6-live-pilot.json` for response and cost
evidence and `reports/M6-live-preflight.json` for final frozen requests.
