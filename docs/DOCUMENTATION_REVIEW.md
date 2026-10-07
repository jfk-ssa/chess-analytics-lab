# First-visit repository review — 2026-10-07

This review follows the path of a new reader: understand the purpose, choose a
reading path, clone/run the offline demo, locate the implementation and judge
the evidence. It also checks publication hygiene and the existing offline test
suite. It is a bounded usability review, not a new model benchmark, comprehensive
security audit or an independent statistical validation of the experiments.

## Findings and implemented changes

| Finding | Change | Why it helps |
|---|---|---|
| README assumes the reader is already in the repository | Add clone/cd steps, interpreter/platform notes and explicit development checks | A newcomer can start from GitHub and identify supported execution paths |
| Many guides and milestone files compete for attention | Add [documentation guide](README.md), goal-based reading paths and a repository map | Readers can choose demo, architecture, analytics, evaluation or operations without reading the whole history |
| High scores risk being mistaken for general model ability | Separate fixed historical cases, fresh language cases, replay and live results in the README and [evaluation guide](EVALUATION.md) | Scores stay tied to their actual dataset, task and evidence |
| GitHub shows comparison HTML as source | Add [Markdown comparison](CLASSIFIER_COMPARISON.md) and explain local HTML viewing | Results are readable directly in GitHub, with full plots available after cloning |
| “Baseline” and repeated Jev rows are ambiguous | Define rules versus analyst baselines; name Jev run 1/run 2; separate routing and final-answer tables | Comparisons share a case set and repeated measurements remain visible |
| August and December prefix roles are unclear | Identify dashboard August prefix and separate December analyst prefix in the README | Readers cannot infer full-month coverage or mix data cohorts |
| A Decisions evidence row is separated from its Markdown table | Repair the table and update historical publication wording | Navigation renders correctly and old audit limits are not mistaken for current visibility |
| Old implementation handoff says no upload occurred | Mark it as preserved history and point to STATUS | Current onboarding stays separate from the original work sequence |

## Verification and limits

The local path check covered 43 Markdown files and 358 relative links at the
first review pass, with zero missing targets. It checks path existence, not
external website availability or every heading anchor. A final scan is recorded
in [review checks](../reports/documentation-review.json).

The reviewed demo is credential-free, uses tracked synthetic games, and writes
to ignored `work/portfolio-demo`. Tests prohibit network access. Real-data tests
may skip in a clean clone; live experiment responses and archive bytes remain
ignored. Source changes are installed as a wheel before execution.

One pre-publication test run failed in dbt due to duplicate installed macro files
with numbered cloud-copy names in the local ignored virtual environment. A repeat reproduced it, and a subsequent run exposed the same defect in dbt
core and its overview document. All 133 offending files were unrecorded by the package and byte-identical to their
canonical files; they were moved to ignored `work/dependency-diagnostic`, preserving
rather than deleting them. The owner identified these as cloud-synced copies. They remain excluded by
the existing virtual-environment/work ignore rules. This was a local dependency-directory defect, not a
tracked SQL or model change. The failed test logs remain under ignored `work/`;
the final result is recorded in the review checks and STATUS.

Package and candidate/history scans are bounded inventories/pattern checks, not
proof that every possible secret is absent. The browser blocked local-file
preview, so HTML structure and recorded values were checked but no new visual
layout inspection is claimed. The supplied screenshot informed the Jev row-label
clarification. Hosted CI is reported separately after push.

## Decisions and future work

Keep the existing historical package/report names and frozen results. Do not
rename hash-bound evidence solely to make the tree prettier; current guides
provide functional navigation. The GPL-3.0-or-later owner license is already
resolved. Neither cloud hosting nor provider switching is needed for onboarding.

Optional later improvements: a hosted static report page if public browser
rendering becomes useful, and a fresh paired classifier/analyst study if the
learning value justifies separately approved caps. Neither is required to run
the project or understand its current evidence. No unresolved owner decision
blocks these documentation changes.
