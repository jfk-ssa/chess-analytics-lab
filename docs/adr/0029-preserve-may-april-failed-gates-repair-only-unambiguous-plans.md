# 0029. Preserve May/April failed gates; repair only unambiguous plans

- Status: accepted
- Date: 2026-10-04

The May v7 complete run scored 36/41 answerable, below the 37/41 gate; its
second run stopped on provider HTTP 400. Five exact source-family usage misses
pass a narrowly specified checked-tool routing **offline replay**. June's two
malformed `args_json` responses pass bounded leading-object recovery offline.
The April v8 new-date run scored 50/50 and 49/50 in its first two repetitions,
then stopped at cell 13 of the third when a provider response repeated the
same valid plan ten times and truncated another copy. Keep all original live
scores and failures. The April parser fix accepts only identical complete
objects, optionally followed by a duplicate prefix when the provider marks
an incomplete response. Reject conflicting objects, unrelated suffixes,
oversized text or excess repetitions; log recovery. The retained April
response passes offline replay. This is not live release evidence.

Use the March v9 bounded first-day source prefix and independently referenced
50-case freeze to test the parser in a new live run. The exact March range is
40,000,000 bytes of the 29,351,713,061-byte publisher listing; `counts.txt`
lists 90,074,196 games for the full archive. The original 5 GB *aggregate
local work* allowance rejected a new download before writing bytes because
retained historical workspaces used about 4.8 GB. Keep that zero-byte failed
attempt, raise only this acquisition allowance to 6 GB, and retain the 40 MB
fetch and 100,000-complete-PGN caps. The machine had about 69 GiB free.

Prior M7 accounted gross through April is $0.102386695. The March preflight
reserves $0.094273125 per 50-cell repetition, including one logged and fully
charged transport retry; three plus prior reserve $0.385206070 under the
existing $0.50 cumulative gross approval. The gate remains three complete
runs, answerable >=37/41 each, boundaries 9/9, high severity 5/5, all
integrity checks, no final failure or unknown cost. Report any deterministic
semantic repairs and text recoveries separately from unmodified model plans.
