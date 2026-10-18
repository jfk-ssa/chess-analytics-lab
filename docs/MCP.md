# Checked tools over MCP

`chesslab mcp` exposes the analyst's checked tools to an MCP client over
stdio. The server is read-only. It does not open a port, and it does not read
API keys, dotenv files, or other process secrets.

Keep the clone outside iCloud- or Dropbox-synced folders such as
`~/Documents` or `~/Desktop` (for example `~/Developer`). Sync tools create
conflict copies inside `.venv` and `.git`. Optionally keep the uv environment
outside the repository: export `UV_PROJECT_ENVIRONMENT` (for example
`$HOME/.venvs/chess-analytics-lab`) before the `uv` commands below.

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
SHA-256 of that canonical JSON. `predict_human_moves` is the exception. Its
probabilities are not bit-stable, so the hash covers the position, ratings,
`top_k`, `min_prob`, and the pinned model identity, and leaves the probability
and win/draw/loss floats out. Tools that already return caveats include
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
| `evaluate_position` | `fen` or `moves`, optional `depth` |
| `position_continuations` | `cohort`, and `fen` or `moves` |
| `compare_candidate_moves` | `cohort`, `candidates` (1–6), and `fen` or `moves`; optional `depth` |
| `predict_human_moves` | `rating_self`, `rating_opp`, and `fen` or `moves`; optional `model`, `top_k`, `min_prob` |

`evaluate_position` and `compare_candidate_moves` need a local engine config.
`position_continuations` needs local opening data. Neither is downloaded.
Depth is at most 16. Engine results include `engine_eval_depth_limited` and
`engine_not_ground_truth`. Those scores are not a model-accuracy claim, and
the frozen M5–M7 results do not transfer to them. The historical live planner
prompt does not offer these three tools. Setup, the opening-data gap in CI,
and what was actually repeated on one machine are in [ENGINE](ENGINE.md).

`predict_human_moves` needs a local Maia-3 config and the optional `maia`
extra. Without the config the result is `maia_not_configured`. Without torch
or the pinned Maia-3 code it is `maia_unavailable`. Probabilities are rounded
to 4 decimal places and carry `model_estimate_not_observation` and
`blitz_trained_rating_scale`. They are a Lichess-blitz model estimate, not a
count of games and not an engine score. The historical live planner prompt
does not offer this tool. Setup and the weights licence are in [MAIA](MAIA.md).

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

Use this command in a project or user MCP file (`.cursor/mcp.json`). `--project` is the repository root:

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
        "/path/to/chess-analytics-lab",
        "chesslab",
        "--project",
        "/path/to/chess-analytics-lab",
        "mcp"
      ]
    }
  }
}
```

Restart the client after saving so it spawns the process. If the extra is not
installed, the protocol tests skip; install it before expecting the server to
start.

## Worked example on the real August prefix

The synthetic demo above is six records, with a draw rate of 0.25 on four
games. Recorded calls against the real August analytical snapshot, the
evidence IDs, and the setup that produced them are in
[the worked example](MCP_EXAMPLE.md).
