# 0063. Analyst modules by responsibility

- Status: accepted
- Date: 2026-10-10

`provider.py` and `experiment.py` mixed transport, plan-text recovery, pricing,
and frozen preflight. Recovery now lives in `plan_recovery.py`, rates and usage
pricing in `pricing.py`, and `prepare` in `preflight.py`. Callers keep importing
those names from `provider` and `experiment`. Nested helpers in the Jev runner
and the M5 case builder moved to module level so the hottest functions fall
under a McCabe cap of 22: case building 21 (was 39), Jev `run` 20 (was 34),
experiment `run` 19, and `prepare` 21. New preflights also hash the three
extracted modules. Published report JSON is unchanged. On the tiny fixture the
source SHA-256 stayed
`130df65e85d18e78bbafd89daf6696c2596e03abf939adf47f2dcbdc4d33e75b` and the draw
rate stayed 0.2; the snapshot id is `7f6e7510017f1ed5e17b0fef`.
