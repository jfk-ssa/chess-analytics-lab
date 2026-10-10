# 0061. Transposition learning in the existing lab

- Status: accepted
- Date: 2026-10-09

The owner approved documenting the learning rationale, repairing relocated path
assumptions, and adding a matching HTML guide. The full lab repository was found
separately from the initially moved 174-game example and moved into the linked
project with its history and retained data. Keep the smaller example as a
companion, with corrected pointers to the main lab.

Use the existing static documentation builder and shared Inter Medium design.
Illustrate two legal move orders converging through the already pinned chess
library; label this a walkthrough rather than a measured learning result.
Research on chess chunks, templates, and specialization motivates the method
indirectly. Record a comparison experiment instead of asserting training gains.

Default to White, rank by declared cohort or personal-history frequency, and
extend to Black later. An explicit most-frequent policy can compare both colors.
Reuse retained PGNs, source/game identity, legal replay, immutable Parquet and
DuckDB publication, and existing cohort filters. New opening relations require
their own extraction plan, metric contracts, derived snapshot, and validated
pointer. Preserve route and draw history alongside canonical position keys.
Begin with retained games; broader sampling or player exports can follow when
the selected learning question needs them. No new acquisition or paid model
run is included in this documentation milestone.
