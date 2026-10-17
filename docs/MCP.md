# Checked tools over MCP

`chesslab mcp` exposes the analyst's checked tools to an MCP client over
stdio. The server is read-only. It does not open a port, and it does not read
API keys, dotenv files, or other process secrets.

Install the optional extra once. The pin is `mcp==2.3.0`.

```sh
uv sync --locked --no-editable --extra mcp
```

The project path must already contain `contracts/` and a current analytical
snapshot (`data/analytical-moves-current.json`). The synthetic demo builds one:

```sh
uv run --locked --offline --no-editable chesslab demo --scope all
```

That snapshot lives under `work/portfolio-demo/project`, not the repository
root. Point `--project` at the directory that holds the snapshot you mean.

```sh
uv run --locked --offline --no-editable --extra mcp \
  --directory /absolute/path/to/chess-analytics-lab \
  chesslab --project /absolute/path/to/work/portfolio-demo/project mcp
```

`--project` is the existing global flag, so it comes before `mcp`, as it does
for `demo` and `ingest`. Use the repository root only when that checkout
already has the analytical snapshot you want. The process exits when the
client closes stdin. `--call-limit` follows `mcp` and defaults to 64 tool
calls for that process.

## What one call guarantees

Each tool result includes the snapshot's dataset ID and an evidence ID. The
evidence ID is the same value `execute_plan` records for the same dataset,
tool, arguments, and result: `ev_` plus the first 20 hex characters of the
SHA-256 of that canonical JSON. Tools that already return caveats include
those caveats on the envelope. The underlying tool result is unchanged.

A call is killed at 30 seconds. Output larger than 1 MB is rejected. The
worker process receives `PATH` and `PYTHONNOUSERSITE` only. DuckDB is opened
read-only. Unknown tools and arguments that miss the published JSON schema
never start the worker.

These checks apply to one call. They do not apply to an answer the client
writes after several calls.

The repository planner accepts at most four tool steps, and the accepted M7
December Sol gate scored 50/50 on each of three frozen repetitions. Both facts
are about that planner and those cases. An outside client drives its own loop.
Those scores do not transfer to it.

## Tools and resources

| Tool | Arguments |
|---|---|
| `list_metrics` | none |
| `get_metric_definition` | `metric_id` |
| `get_dataset_coverage` | none |
| `query_metric` | `metric_id`, `filters`, optional `group_by` of one allowed field |
| `compare_openings` | `filters` with two families and the exact cohort |
| `analyze_clock_pressure` | `bucket` |
| `compare_clock_buckets` | `first`, `second` |

A grouped `query_metric` sends `"filters": {}`. Clock buckets are `under_10`,
`10_to_29`, `30_to_59`, and `60_plus`. Colors are `white` or `black`.

Every `contracts/*.json` file is a resource at
`chesslab://contracts/<filename>`. The six metric contracts are the
definitions the tools interpret. The other files are tracked table and import
contracts, still read-only.

## Claude Desktop

Put this in the Claude Desktop MCP configuration. Replace both absolute paths.
On macOS the file is `~/Library/Application Support/Claude/claude_desktop_config.json`.

```json
{
  "mcpServers": {
    "chesslab": {
      "command": "uv",
      "args": [
        "run",
        "--locked",
        "--offline",
        "--no-editable",
        "--extra",
        "mcp",
        "--directory",
        "/absolute/path/to/chess-analytics-lab",
        "chesslab",
        "--project",
        "/absolute/path/to/work/portfolio-demo/project",
        "mcp"
      ]
    }
  }
}
```

The first sync needs a network. Later runs keep `--offline`. Do not put an API
key in this configuration. The server never reads one.

## Cursor

Use the same command in a project or user MCP file (`.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "chesslab": {
      "command": "uv",
      "args": [
        "run",
        "--locked",
        "--offline",
        "--no-editable",
        "--extra",
        "mcp",
        "--directory",
        "/absolute/path/to/chess-analytics-lab",
        "chesslab",
        "--project",
        "/absolute/path/to/work/portfolio-demo/project",
        "mcp"
      ]
    }
  }
}
```

Restart the client after saving so it spawns the process. If the extra is not
installed, the protocol tests skip; install it before expecting the server to
start.
