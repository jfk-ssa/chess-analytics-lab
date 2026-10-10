# 0031. Retire February v10 and prepare new January source

- Status: accepted
- Date: 2026-10-04

February v10 repetition 1 met all per-run gates (47/50 total, 38/41
answerable, 9/9 boundary, 5/5 high severity, 50/50 evidence integrity),
with one logged HTTP 400 retry and one deterministic semantic repair.
Repetition 2 stopped at cell 26 after 25 completed scored passes: the
provider returned a complete plan plus 870 repeated non-ASCII punctuation
characters and marked the response incomplete at the output cap. Preserve
the original stopped result. The new parser accepts a complete plan followed
only by a bounded single non-ASCII punctuation/symbol repetition when the
provider declares the response incomplete; all other suffixes fail closed.
The retained response passes offline replay, not a live rescore. Cumulative
M7 accounted gross through February is $0.115247510. The new January first-day
40 MB source prefix will receive independent references and a new frozen
holdout before any further live evaluation. The aggregate local work-data
allowance for January acquisition was raised to 8 GB to retain historical
failed workspaces; the network range remains exactly 40 MB and free disk was
about 68 GiB.
