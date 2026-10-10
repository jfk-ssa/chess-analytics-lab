# 0051. Optional OpenAI Decisions classifier

- Status: accepted
- Date: 2026-10-07

Add a separate Decisions API learning experiment; keep rules, Jev and the existing
checked analyst intact. Use the standard global Decisions endpoint, gpt-6-luna,
one fixed eight-choice route question, and standard-library HTTP. Official pricing
checked today is $0.10 per million input tokens. No new dependency or infrastructure.

All historical cases are inspected development evidence. Select and freeze the
0.70 chosen-option probability threshold from 40 development responses before
fresh scoring. The owner approved 24 new labels and a simplified private-history
question before any holdout call. Label review is independent of the authoring
agent, but is owner review rather than external expert adjudication. Three identical
repetitions scored 23/24 each; do not count them as 72 independent examples or tune
the rubric against the repeated error without retiring this holdout.

All six runs used one durable locked campaign ledger and the approved $0.05
cumulative Decisions cap. Actual recorded usage totals $0.0068145 for 184 requests,
with no unknown reservations, transport failures, retries or refusals. Retain raw
attempts under ignored work; compact scored reports and the checkpoint are public
artifacts. Usage-based gross is not a provider invoice settlement. Future paid
runs need a new explicit estimate, recommended cap and approval; remaining credits
and unused cap are not an authorization for another campaign.

Compare retained Jev/analyst runs only on the same historical split; no fresh
TypeSafe or Responses call was authorized or made. The 32-case historical
retained-answer replay scores 31/32 with 26 fallbacks, unchanged from baseline,
and raises simulated cost from $0.0024263 to $0.003363135. It has no combined live
latency and proves no benefit for the accepted M7 Sol analyst. Keep Decisions
optional; a fresh paired final-answer test needs separate provider estimates and
caps before considering integration. See [runbook](../DECISIONS_ROUTING_RUNBOOK.md)
and [checkpoint](../../reports/decisions-checkpoint.json).
