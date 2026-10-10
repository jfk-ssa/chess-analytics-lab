# 0016. Freeze a new M6 family-split holdout before live scoring

- Status: accepted
- Date: 2026-10-04

Retire the inspected M5 test set for untouched model claims. Use eight new
opening-usage families and independently tallied raw-PGN White cohorts for
Zukertort Opening and King's Pawn Game. Freeze 20 cases: 14 answerable and
6 ambiguity/unsupported, including high-severity access and unsupported
claim requests. Keep the development prompt unchanged. Version the holdout
rubric to M6 2.1 so the checked clock wrapper is accepted for equivalent
evaluation-coverage evidence, provided values and filters match. Do not
retroactively rescore earlier development runs. Offline checked-tool/reference
validation passed all 20 cases; it is harness validation, not model accuracy.

Recheck the official GPT-6 Luna Standard rates on 2026-10-04 and freeze a
40-request preflight with conservative quote $0.0503635 and file/request
hashes. No holdout model response exists yet. The prior $0.10 cap covered
the development evaluation; request a separate gross cap before live holdout
execution. This first held-out run will be one-shot and cannot establish
repeatability. The SQL baseline remains deferred because safe free-form SQL
isolation is not implemented; label the comparison accordingly.
