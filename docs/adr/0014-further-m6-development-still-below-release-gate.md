# 0014. Further M6 development, still below release gate

- Status: accepted
- Date: 2026-10-03

The user approved a separate $0.10 gross cap for the next M6 evaluation.
Use the M6 2.0 scorer on subsequent runs to accept the equivalent checked
clock-pressure wrapper when numerical evidence matches; keep the original
M5-frozen 16/24 result. Clarify supported filters and refusal categories in
the planner instructions, without expanding the tool allowlist. A complete
24-cell revision scored 20/24, but answerable cases were only 9/12, below the
90% release target. The next revision stopped at 16 cells after a provider
response contained two output-text chunks, one malformed. Retain that full
response as a failed attempt and do not select a favorable chunk. These
40 requests cost $0.00361867 gross using cache-aware usage accounting, well
under the new $0.10 cap. The results are inspected development data, not a
held-out benchmark. M6 remains in progress; a new family-split holdout is
still needed after development quality reaches the gate.
