# 0040. Clean-export acceptance and publication boundary

- Status: accepted
- Date: 2026-10-04

A tracked-source export installed the locked dbt/dashboard environment after a
one-time fetch of missing Pygments and Ruff wheels. It passed 81 tests with 12
expected skips for ignored real data, then the full synthetic demo and Ruff. The
local full suite passed 93/93 with no skips; lock, format and whitespace checks
passed. A wheel and source archive omitted ignored work, cache, env and bulk-data
payloads. A filename-only candidate/history pattern audit found no matching
credential or personal path in 33 reachable commits; it is not a proof of absence.
Hosted CI has not run, and no Git remote or upload exists. The owner still needs to
choose a repository distribution license before public publication.
