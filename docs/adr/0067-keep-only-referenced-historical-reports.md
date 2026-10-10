# 0067. Keep only referenced historical reports

- Status: accepted
- Date: 2026-10-10

Tracked reports that no test, script, current guide, or kept report names are
removed from the checkout. The full set remains on tag
`archive/reports-before-main-prune-2026-10-10` at commit `2fa1fbb`. Eval case
files stay. A filename built with an f-string or brace expansion counts as a
reference, so the December Sol runs and the M6 v2 run/audit triples stay.
Files named by `repository-review.json` or `reports/M0-M1.md` stay with those
records. The earlier tag `archive/reports-before-prune-2026-10-10` still points
at the previous main tip `523718f`.
