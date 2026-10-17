# 0080. MCP worked example on the real August prefix

- Status: proposed, accepted on merge
- Date: 2026-10-17

## Motivation

`chesslab mcp` serves the checked tools over stdio (ADR 0077, pull request
#21). Pull request #22 added the local engine tools. Pull request #23 added
an offline evaluation of those tools. The usage guide's runnable snapshot is
still the synthetic demo: 6 seen games, and a draw rate of 0.25 on 4
eligible games.
That demo does not show what the metric tools return on the real August
prefix.

On 2026-10-17 the owner ran a local client against the analytical snapshot
already in `data/`. The client answered five questions from the tools alone.
A second independent run produced the same evidence IDs. Two setup mistakes
account for three attempts before that session: a cloud agent cannot start
the local stdio server or see gitignored data, and a client allowed to run
shell commands can rebuild the synthetic demo and report a draw rate of 0.25.
The session is worth recording. The games stay out of Git.

## Decision

Add [the worked example](../MCP_EXAMPLE.md) and link it from [MCP](../MCP.md).
The note copies the arguments and raw results for the five answers: coverage,
draw rate, grouped opening usage and one opening comparison, the under-10
clock proxy and a bucket comparison, and the clock-proxy definition. It states
the prefix limits beside those results and the local steps that reproduce
the calls. The documentation site does not gain a page. The same boundary is
in ADR 0077: its navigation is the fixed guide set, and this server is a
local process.

No tool, contract, or test changes. A test that needs the real snapshot is
not added. The results file itself is not committed. Paths in the note are
placeholders.

No tool lists valid time controls. In the opening comparison the client chose
White, ratings from 0 to under 4000, and 300+0. Listing time controls remains
a future idea. This decision does not add that tool.

## Impact

A reader can see the tool answers on 99,117 eligible games from dataset
`84a38a404815ed2729917d76` (source snapshot `6cf51473f8da6ae6b12ea5c2`).
Every recorded answer carries that dataset ID and an evidence ID. The clock
definition withholds a causal claim. The note also records the two setup
mistakes above, and the prompt that then returned coverage and the draw rate.

## Implementation steps

1. Write the five steps, the scope box, and the reproduction prompt in `docs/MCP_EXAMPLE.md`. Copy numbers and evidence IDs from the recorded results only.
2. Link that note from `docs/MCP.md` and the documentation index. Add one sentence to the status summary.
3. Add this record and one index row.
4. Do not commit the games, local home-directory paths, usernames, or the results file.
5. Leave the tools and the offline tests unchanged.

## Limits

The prefix is a single UTC day, 2026-08-01, and `partial_archive` is true.
It is a convenience sample of a bounded 100,000-game prefix, not an August
population sample. Evidence IDs show that two runs hashed the same dataset,
tool, arguments, and result. They are not independent proof that the metric
is correct. The filters in the opening comparison were chosen by the client.
The score-rate difference on that cohort is about 0.006 and the tool returns
no confidence interval. This example does not measure model accuracy. The
synthetic demo and the M5–M7 planner scores remain separate evidence.
