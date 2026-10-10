# 0038. Review first; defer implementation and Jev

- Status: accepted
- Date: 2026-10-04

The owner requested an end-to-end portfolio review, then explicitly asked for a
fix plan to pass to a lower model. Preserve production code at reviewed commit
`26f675b`; save and reverse the interrupted five-file implementation diff under
ignored `work/repository-review/proposed-fixes.patch`. It is untested and incomplete.
Only review artifacts and status/decision documentation change in this pass.

[Review](../REPOSITORY_REVIEW.md) records confirmed offline defects, 56 local passing
tests, 44 passing/12 skipped exported-source tests, and a missing-cache-wheel
limitation on fresh installation. [Handoff](../PORTFOLIO_HANDOFF.md) prioritizes finite
budget validation and source binding before a complete synthetic product demo.
Use functional public interfaces while retaining immutable milestone/version
evidence; broad package/path renames need explicit hash/compatibility handling.
License selection remains an owner decision. No live spend, new model task,
Jev implementation, cloud service or repository upload is authorized by this plan.
