# 0010. M6 offline release preparation

- Status: accepted
- Date: 2026-10-03

Implement a disposable subprocess for live model-selected checked tool calls,
with a 30-second wall-clock timeout and a credential-free environment. The
allowlist remains the tool API; this process boundary enforces time limits and
keeps the provider key out of tool execution, but is not an OS-level sandbox.
Free-form SQL remains disabled.

Use the 30 development cases only for the first measured pilot; select 12 across
numerical, ambiguity, missing-data and access categories. Compare two typed
planner prompts using the same model/tools/settings and add metric definitions
only in the semantic-context condition. Do not call this the specification's
SQL baseline or an untouched holdout. The existing test references were
inspected during harness validation. A later held-out result requires a new
unseen family split.

Propose GPT-6 Luna at the official listed Standard text prices on 2026-10-03
($0.10/M input, $0.50/M output), 512 maximum output tokens, and a hypothetical
$1 total cap solely for the offline quote. This does not enable the tracked
provider config or authorize spend. Before a live run, reverify personal
entitlement, exact model/prices, and the user's cap, then freeze request and
code hashes. Reserve each entire request bound against the total cap. Retain
all responses/failures; stop after a failure with uncertain usage. Do not infer
zero cost from a transport error. No model request or result has occurred.
