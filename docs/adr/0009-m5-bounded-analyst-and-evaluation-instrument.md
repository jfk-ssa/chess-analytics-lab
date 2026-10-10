# 0009. M5 bounded analyst and evaluation instrument

- Status: accepted
- Date: 2026-10-03

Keep deterministic typed tools and their SQL separate from interpretation,
provider transport, replay and scoring. Four steps maximum; each answer has
checked snapshot identity and content-derived evidence IDs. There is no
free-form SQL tool: read-only database mode alone is insufficient isolation,
and a separate worker is not justified for the initial offline path. File,
network, extension, multi-statement and unpublished-table attempts are
rejected at the tool boundary. Invalid plans fail rather than being silently
repaired; a semantic repair loop is a measured future extension.

Freeze 50 cases, 30 development and 20 test, with the six requested categories.
Generate reference values from the independent raw-PGN script and store replay
plans separately. The 50/50 replay result validates the harness and checked
tools; it is not a model benchmark. Once test labels are inspected for tuning,
retire this split from claims of untouched held-out model performance.

Add a small [Responses API](https://developers.openai.com/api/docs/guides/structured-outputs)
planner rather than an SDK dependency. It returns a structured tool plan; the
same checked local tools compute all numbers. The adapter reads only an
explicitly named personal key variable after a supplied config enables calls
and names a model, prices and positive run cap. One request is preflighted
against a conservative byte/token cost bound, with no retries; missing usage
fails closed. No model ID, price, account entitlement or benchmark result is
assumed current or established by this offline milestone.
