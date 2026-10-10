# 0020. Start M7 with error-driven depth; defer provider alternatives

- Status: accepted
- Date: 2026-10-04

The user clarified that OpenRouter or CheaperInference should be considered
**only when costs rise**. This supersedes earlier wording that allowed a
model-choice reason by itself. The M6 accepted holdout cost less than one cent;
do not build a router comparison now. No new live run is authorized by M6's
closed $0.10 cap.

Start M7 from the two inspected clock-coverage abstentions. Add an explicit
planner instruction that a specified bucket's evaluation coverage is answerable
from checked eligible/evaluable counts despite sparse evaluation availability.
Keep missing-bucket clarification, causal claims, private data and full-month
projection unsupported or clarified as before. This instruction is a development
change only; it is not evidence of improved model accuracy. Next build new
independent development and held-out cases before seeking a new live cap.

The depth order is evaluation quality first, then bounded data-extension
feasibility, then optional controlled engine enrichment. The current 40 MB
prefix covers August 1 only and Stockfish is not installed locally. Do not
start an unbounded download or engine run; adopt either only after measuring
coverage benefit and resource cost. See `docs/M7.md`.

The initial 12-case clock development set uses the independent M3 raw-PGN
tally for four buckets and includes missing-bucket, private-data, causal and
full-month negative controls. Its checked-tool/oracle replay passed 12/12.
Those are harness results, not model responses; they do not justify a new
quality claim or reuse of the inspected M6 v2 holdout.
