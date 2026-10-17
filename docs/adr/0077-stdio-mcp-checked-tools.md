# 0077. Serve checked tools over stdio MCP

- Status: proposed
- Date: 2026-10-17

## Motivation

The checked metric tools only run inside this repository's planner. A client
such as Claude Desktop or Cursor cannot call them. That is a poor fit: each
tool already returns a denominator, and several return caveats, and every
planner step already has an evidence ID bound to the dataset, the tool name,
the arguments, and the result. Those are the properties a read-only tool
surface needs.

Keeping the tool list in one place also gives a later change somewhere to add
a tool without a second allowlist. An engine-grounded tool is not part of this
decision.

## Decision

`chesslab mcp` serves the existing seven tools on standard input and output.
There is no listening socket. The process takes the project path at startup,
reads the current analytical snapshot, and does not read credentials, dotenv
files, or the process environment for secrets. Tool work goes through the same
credential-free worker the live planner uses: a clean environment, a 30-second
kill, and a 1 MB output cap.

The allowlist lives next to `CheckedTools`: name, JSON argument schema, and
handler. `CheckedTools.execute` looks up that registry and still applies the
historical argument-key gate, so typed plans and the provider path accept the
same calls they accepted before. The MCP server validates the JSON schema, then
calls that same handler through the worker. The provider prompt text is
unchanged. Historical scorers and reports are unchanged.

Each MCP tool result adds the dataset ID and an evidence ID from the existing
function. Caveats are copied onto that envelope when the tool result already
has them. The tool result itself is not rewritten, so an evidence ID from
`execute_plan` matches an MCP call with the same arguments and result. One
process accepts 64 tool calls and then refuses. Metric and other tracked
`contracts/*.json` files are MCP resources under `chesslab://contracts/`.

The official `mcp` package, version 2.3.0, is an optional extra with an exact
pin. It is imported only when the server starts or when the protocol tests
run. The default install and test collection do not import it.

The planner's four-step limit, and the M7 December Sol result of 50/50 on each
of three frozen repetitions, describe this repository's planner and those
cases. They do not describe an outside client that chooses its own loop. MCP
checks one call. It does not check the answer a client writes from several
calls. Those evaluation numbers do not transfer.

## Impact

External clients can list metrics, read a contract, query a named metric,
compare openings, and compare clock buckets against one local snapshot. The
default offline environment stays free of the SDK. Protocol tests skip when
the extra is absent. A future foundation snapshot id changes when this lock
and source tree are included in the implementation hash; historical published
reports are not rebuilt. The documentation site does not gain a page: its
navigation is the fixed eight-page set from ADR 0076, and this server is a
local process rather than a website feature. [MCP](../MCP.md) is the usage
guide.

## Implementation steps

1. Put the seven tools in one registry used by `CheckedTools.execute` and the server.
2. Keep the historical key gate on `execute`. Validate the JSON schema only on the MCP path.
3. Start the server from `chesslab --project PATH mcp`, stdio only. `--project` stays the global flag.
4. Run each accepted call through `run_killable_tool`.
5. Return dataset id, evidence id, and existing caveats. Publish `contracts/*.json` as resources.
6. Pin `mcp==2.3.0` in the optional `mcp` extra and refresh `uv.lock`.
7. Cover the protocol with an in-process client, and one real stdio subprocess of the CLI. Skip those tests without the extra.

## Risks

A client can treat a per-call evidence ID as support for an answer it composed.
The session cap resets when the process restarts. The JSON schema is stricter
than the planner's key gate: `query_metric` requires `filters`, and a grouped
call sends `"filters": {}`. The SDK is major version 2; FastMCP is not the API
this server uses. Acceptance here is the offline harness and one stdio
subprocess, not a session inside Claude Desktop or Cursor.
