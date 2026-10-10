# 0045. M8 paired final-answer study

- Status: accepted
- Date: 2026-10-05

Use a narrow Jev boundary gate, not a full semantic route replacement, as the
first integrated test. Jev may end only `clarify` or `unsupported` questions
at probability at least 0.70; every other decision falls through to the
unchanged checked analyst. This protects numerical calculations and keeps
the baseline directly comparable. The owner reviewed and approved all eight
new boundary labels before live scoring; opening and clock values come from
independent raw-PGN references. One paired 32-case run had separate newly
approved cumulative gross caps of $0.03 TypeSafe and $0.20 OpenAI.

The original live report scored both arms 30/32. Its inherited rubric
required the expected checked tool to be the **last** evidence item, wrongly
rejecting an answer that used the expected clock metric followed by an
additional checked coverage metric. Keep that original report, add a focused
regression, and rescore the saved answers offline under `m8-e2e-1.1`, which
accepts the expected tool anywhere in the integrity-checked evidence. Both
arms then score 31/32; no model call was repeated. The shared failure is an
answerable UTC-date coverage question that the analyst marked unsupported.

Both arms used `gpt-6-luna`; the accepted M7 checkpoint used `gpt-6-sol`.
The gated arm saved six analyst calls but made 32 Jev calls. Measured gross
was $0.002503882 gated versus $0.00242630 baseline; summed per-case elapsed
time was 86.11 versus 83.97 seconds. TypeSafe gross $0.000804762 and OpenAI
gross $0.00412542 remained under their caps with no unknown usage. Retain
Jev as a learning lab and do **not** integrate the gate into the product:
this Luna pairing has no measured final-answer quality, cost, or latency
benefit. A Sol pairing was not evaluated.
The result is one small paired run, not a stability or population estimate.
Future Jev work needs a concrete higher-value trigger, fresh independent
cases, and new spending approvals.
