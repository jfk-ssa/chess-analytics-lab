# 0030. Retire stopped March v9; freeze February v10 under the same cap

- Status: accepted
- Date: 2026-10-04

March v9 stopped after 16 attempts: 15 completed, 14 scored passes, with
one HTTP 400 rescued by the single logged retry and a later HTTP 400 stopping
the run. Two unknown-cost subattempts are charged at full reservations.
Cumulative M7 accounted gross is $0.107639170. The overlapping Queen's
Gambit Declined family repair passes offline replay, but the original live
miss remains. Do not claim a three-run gate from partial results.

For the February v10 freeze, retain the same checked-tool boundary behavior
while shortening the planner's inaccessible-data phrase. Allow at most three
logged HTTP 400 transport retries on distinct cells per run, one retry per
cell. This is a measured response to repeated provider rejections on ordinary
opening questions; every rejected subattempt is charged at its full
reservation, and any final failed request stops. The fresh February first-day
40 MB source prefix yielded 99,585 accepted of 100,000 complete PGNs,
5,020 selected games and 335,854 move rows. Independent raw-PGN and 50/50
offline oracle checks passed. Its preflight reserves $0.098598875 per run
including three retries, or $0.403435795 for three plus all prior M7 spend,
under the existing $0.50 cumulative gross cap. Preserve failures and
separate model results from offline replay and deterministic repairs.
