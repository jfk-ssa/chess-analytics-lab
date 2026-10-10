# 0035. Accept December Sol v12 after three complete frozen repetitions

- Status: accepted
- Date: 2026-10-04

The user approved the recommended $6.00 cumulative gross cap. The first
sandboxed invocation failed DNS at cell 1 before provider usage was returned.
Keep the failed raw and key-free partial reports and charge the entire
$0.037237500 reservation. A new network-enabled invocation used the same
frozen preflight and a separate ledger. All three 50-case repetitions
completed and scored 50/50, with 41/41 answerable, 9/9 boundary, 5/5 high
severity and 50/50 evidence integrity in each. There were no retries or
repairs. Gross charges for the completed runs were $0.068096900,
$0.055506700 and $0.054292300. Add these to the earlier $0.138794960
accounted M7 gross and the DNS reservation: total **$0.353928360**,
below the approved $6.00 cap. The independent checkpoint gates all pass.

Mark M7 accepted for a fixed-case, new-date, three-repetition quality
checkpoint only. This does not establish general accuracy, monthly trends,
or a model comparison. Retain all earlier stopped Luna gates. The original
retry runner used a generic exported summary filename, which the second
invocation overwrote; the original failed summary survives in its raw
attempt directory and the key-free partial report. Change future exports
to include the ledger stem so separate invocations cannot collide.
