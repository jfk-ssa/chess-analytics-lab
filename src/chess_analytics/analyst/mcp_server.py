"""Stdio MCP server for the checked analyst tools. No network listener and no credentials."""

import json
import re
from functools import partial
from pathlib import Path

from chess_analytics.analyst.core import _evidence_id, run_killable_tool
from chess_analytics.analyst.tool_catalog import TOOLS, TOOLS_BY_NAME, arguments_match
from chess_analytics.analyst.tools import CheckedTools

SESSION_CALL_LIMIT = 64
CONTRACT_PREFIX = "chesslab://contracts/"
_CONTRACT_NAME = re.compile(r"[a-z0-9_]+\.json")
INSTRUCTIONS = (
    "Read-only checked chess metric tools for one local analytical snapshot. "
    "Each call returns that snapshot's dataset id and an evidence id. "
    "Checks are per call. This server does not apply the repository planner's "
    "four-step limit, and that planner's evaluation scores do not transfer here."
)


def _call_limit(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("call limit must be a positive integer")
    return value


def _prepare(project: Path, call_limit: int) -> tuple[Path, int]:
    root = project.resolve()
    if not root.is_dir():
        raise ValueError("project path must be a directory")
    CheckedTools(root)
    return root, _call_limit(call_limit)


def _contract_file(project: Path, uri: str) -> Path:
    if not uri.startswith(CONTRACT_PREFIX):
        raise ValueError("unsupported contract resource")
    name = uri.removeprefix(CONTRACT_PREFIX)
    if _CONTRACT_NAME.fullmatch(name) is None:
        raise ValueError("unsupported contract resource")
    path = (project / "contracts" / name).resolve()
    if path.parent != (project / "contracts").resolve() or not path.is_file():
        raise ValueError("unsupported contract resource")
    return path


def _envelope(dataset_id: str, name: str, args: dict, result: dict) -> dict:
    body = {
        "dataset_id": dataset_id,
        "evidence_id": _evidence_id(dataset_id, name, args, result),
        "result": result,
    }
    if "caveats" in result:
        body["caveats"] = result["caveats"]
    return body


def build_server(project: Path, *, call_limit: int = SESSION_CALL_LIMIT):
    """Return an in-process MCP server. The SDK is imported only here."""
    import anyio  # pyright: ignore[reportMissingImports]
    import mcp_types as types  # pyright: ignore[reportMissingImports]
    from mcp.server import Server  # pyright: ignore[reportMissingImports]
    from mcp.shared.exceptions import MCPError  # pyright: ignore[reportMissingImports]
    from mcp_types import INVALID_PARAMS  # pyright: ignore[reportMissingImports]

    root, limit = _prepare(project, call_limit)
    calls = {"count": 0}
    annotations = types.ToolAnnotations(
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    )

    def _fail(message: str):
        return types.CallToolResult(content=[types.TextContent(text=message)], is_error=True)

    async def on_list_tools(_ctx, _params):
        return types.ListToolsResult(
            tools=[
                types.Tool(
                    name=spec.name,
                    description=spec.description,
                    input_schema=spec.input_schema,
                    annotations=annotations,
                )
                for spec in TOOLS
            ]
        )

    async def on_call_tool(_ctx, params):
        calls["count"] += 1
        if calls["count"] > limit:
            return _fail("session tool-call limit reached")
        spec = TOOLS_BY_NAME.get(params.name)
        args = params.arguments if params.arguments is not None else {}
        if spec is None:
            return _fail("unsupported tool")
        if not isinstance(args, dict) or not arguments_match(spec.input_schema, args):
            return _fail("invalid tool arguments")
        try:
            dataset_id, result = await anyio.to_thread.run_sync(
                partial(run_killable_tool, root, params.name, args)
            )
        except (ValueError, TimeoutError, RuntimeError) as exc:
            return _fail(str(exc))
        except OSError:
            return _fail("checked tool failed")
        body = _envelope(dataset_id, params.name, args, result)
        return types.CallToolResult(
            content=[types.TextContent(text=json.dumps(body, sort_keys=True))],
            structured_content=body,
        )

    async def on_list_resources(_ctx, _params):
        folder = root / "contracts"
        resources = []
        if folder.is_dir():
            for path in sorted(folder.glob("*.json")):
                if _CONTRACT_NAME.fullmatch(path.name):
                    resources.append(
                        types.Resource(
                            uri=CONTRACT_PREFIX + path.name,
                            name=path.name,
                            description="Tracked contract JSON. Read-only.",
                            mime_type="application/json",
                        )
                    )
        return types.ListResourcesResult(resources=resources)

    async def on_read_resource(_ctx, params):
        try:
            path = _contract_file(root, params.uri)
            text = path.read_text()
        except (OSError, ValueError) as exc:
            raise MCPError(code=INVALID_PARAMS, message="unsupported contract resource") from exc
        return types.ReadResourceResult(
            contents=[
                types.TextResourceContents(uri=params.uri, mime_type="application/json", text=text)
            ]
        )

    return Server(
        "chesslab",
        version="0.1.0",
        instructions=INSTRUCTIONS,
        on_list_tools=on_list_tools,
        on_call_tool=on_call_tool,
        on_list_resources=on_list_resources,
        on_read_resource=on_read_resource,
    )


def serve(project: Path, *, call_limit: int = SESSION_CALL_LIMIT) -> None:
    """Serve one stdio session. There is no host, port, or HTTP transport."""
    import anyio  # pyright: ignore[reportMissingImports]
    from mcp.server.stdio import stdio_server  # pyright: ignore[reportMissingImports]

    server = build_server(project, call_limit=call_limit)

    async def _run():
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())

    anyio.run(_run)
