# Provider choice for the analyst — 2026-10-04

Keep the direct OpenAI Responses adapter as the M6 reference implementation.
The first family-split holdout and its two stopped repetitions used 72 actual
requests for $0.0060692 gross. At this scale, a percentage inference discount
saves fractions of a cent while a routing change adds compatibility and
measurement questions. Finish the direct-provider reliability gate before
changing the provider in the release experiment.

[OpenRouter's current pricing page](https://openrouter.ai/pricing) lists a
5.5% Standard platform fee on credit purchases and a plan-dependent BYOK
allowance ($25,000/month of list-price inference without fees on Standard,
then 5%). OpenRouter is most useful here as a controlled multi-provider or
multi-model routing experiment; it is not automatically cheaper than direct
OpenAI for this small fixed-model workload. Its routing and spend-control
features may be valuable if the project grows.

[CheaperInference's documentation](https://www.cheaperinference.com/docs)
says it starts with the lowest-cost eligible route, can fall back to another
route, and bills the successful route without a separate routing surcharge,
capped at the model maker's applicable direct list price. Prices and routes
can change; its key-filtered catalog and settled dashboard charge are needed
for a real quote. Its [live catalog](https://platform.cheaperinference.com/)
displayed a GPT-6 Luna discount when checked, but that is not a guaranteed
rate for this workload. CheaperInference is worth a controlled test when
inference spend becomes material.

The user narrowed the decision point: consider alternatives **only when costs
rise materially**. M6's direct-provider accuracy and completion gates are met,
but gross spend on its accepted holdout was only $0.009968525. Do not add a
provider-routing experiment to M7 merely for model choice. If recurring spend
eventually reaches several dollars, run a small paired test
with the same frozen cases, model version, prompts and output schema. Record
actual route, gross settled cost including platform fees, cache behavior,
latency, structured-output and usage-field compatibility, failures and score.
Require a separate personal credential, explicit cap and provider-specific
preflight. Do not reuse the OpenAI key with another gateway or route workplace
data or credentials. Keep provider change out of the current M6 benchmark so
it does not confound the reliability fix.
