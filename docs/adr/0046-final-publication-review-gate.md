# 0046. Final publication review gate

- Status: accepted
- Date: 2026-10-05

Review the full working-tree upload candidate, including new files, in a
clean export before creating a remote. The export passed 90 tests with 13
expected real-data skips, Ruff and the complete offline demo; package
inventory included the selected license and excluded ignored payloads.
Keep publication pending the four fixes in FINAL_RELEASE_REVIEW.md. The
M8 comparator was Luna, whereas the accepted M7 checkpoint used Sol; the
observed no-benefit conclusion is limited to the Luna experiment. No new
live experiment is required to correct that scope. A mock interruption
proved a missing durable request reservation, and inspection found a
success exit for incomplete runs and a rescore overwrite path. This turn
records review evidence and acceptance criteria only, without code fixes
or publication.
