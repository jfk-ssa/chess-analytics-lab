"""In-process MCP session. Skipped when the optional mcp extra is absent."""

import json
import os
import subprocess
from pathlib import Path

import pytest

pytest.importorskip("mcp", reason="MCP protocol tests need the optional mcp extra")

from chess_analytics.analyst.core import execute_plan
from chess_analytics.analyst.mcp_server import INSTRUCTIONS, build_server
from chess_analytics.analyst.tool_catalog import TOOLS
from chess_analytics.dashboard.analysis import current_snapshot
from chess_analytics.portfolio_demo import run

SOURCE = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def analytical_project(tmp_path_factory):
    workspace = tmp_path_factory.mktemp("mcp-analytical")
    run(SOURCE, workspace)
    return workspace / "project"


def _drive(server, check):
    import anyio
    from mcp.client._memory import InMemoryTransport
    from mcp.client.session import ClientSession

    async def _run():
        transport = InMemoryTransport(server)
        async with transport as (read, write), ClientSession(read, write) as client:
            await client.initialize()
            await check(client)

    anyio.run(_run)


def _ok(result: dict) -> str:
    return json.dumps({"ok": True, "dataset_id": "d" * 24, "result": result})


def test_session_lists_read_only_tools_and_states_per_call_limits(analytical_project):
    async def check(client):
        text = client.instructions or ""
        assert "per call" in text
        assert "50/50" not in text
        assert text == INSTRUCTIONS
        listed = await client.list_tools()
        assert [tool.name for tool in listed.tools] == [spec.name for spec in TOOLS]
        assert all(tool.annotations.read_only_hint is True for tool in listed.tools)
        assert all(tool.annotations.open_world_hint is False for tool in listed.tools)

    _drive(build_server(analytical_project), check)


def test_schema_and_unknown_tool_do_not_start_the_worker(analytical_project, monkeypatch):
    def refuse(*_args, **_kwargs):
        raise AssertionError("worker started")

    monkeypatch.setattr("chess_analytics.analyst.core.subprocess.run", refuse)

    async def check(client):
        rejected = await client.call_tool(
            "query_metric",
            {"metric_id": "opening_usage", "filters": {}, "sql": "select 1"},
        )
        unknown = await client.call_tool("run_readonly_query", {"sql": "select 1"})
        maia = await client.call_tool(
            "predict_human_moves",
            {"fen": "x", "rating_self": 5001, "rating_opp": 1500},
        )
        assert rejected.is_error and rejected.content[0].text == "invalid tool arguments"
        assert unknown.is_error and unknown.content[0].text == "unsupported tool"
        assert maia.is_error and maia.content[0].text == "invalid tool arguments"

    _drive(build_server(analytical_project), check)


def test_oversized_worker_output_is_rejected(analytical_project, monkeypatch):
    def huge(*_args, **_kwargs):
        return subprocess.CompletedProcess([], 0, stdout="x" * 1_000_001, stderr="")

    monkeypatch.setattr("chess_analytics.analyst.core.subprocess.run", huge)

    async def check(client):
        result = await client.call_tool("list_metrics", {})
        assert result.is_error
        assert "too much data" in result.content[0].text

    _drive(build_server(analytical_project), check)


def test_worker_environment_is_credential_free(analytical_project, monkeypatch):
    monkeypatch.setenv("CHESSLAB_OPENAI_API_KEY", "secret-value")
    monkeypatch.setenv("OPENAI_API_KEY", "other-secret")
    seen = {}

    def capture(cmd, **kwargs):
        seen["cmd"] = cmd
        seen["env"] = kwargs["env"]
        stdout = _ok({"dataset_id": "d" * 24, "metric_ids": []})
        return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")

    monkeypatch.setattr("chess_analytics.analyst.core.subprocess.run", capture)

    async def check(client):
        result = await client.call_tool("list_metrics", {})
        assert result.is_error is False

    _drive(build_server(analytical_project), check)
    assert seen["env"] == {"PATH": os.defpath, "PYTHONNOUSERSITE": "1"}
    assert "secret-value" not in seen["env"].values()
    assert seen["cmd"][1:3] == ["-m", "chess_analytics.analyst.tool_worker"]


def test_session_call_cap_stops_further_worker_calls(analytical_project, monkeypatch):
    calls = {"count": 0}

    def count(cmd, **_kwargs):
        calls["count"] += 1
        return subprocess.CompletedProcess(cmd, 0, stdout=_ok({"ok": True}), stderr="")

    monkeypatch.setattr("chess_analytics.analyst.core.subprocess.run", count)

    async def check(client):
        first = await client.call_tool("list_metrics", {})
        second = await client.call_tool("list_metrics", {})
        assert first.is_error is False
        assert second.is_error
        assert second.content[0].text == "session tool-call limit reached"

    _drive(build_server(analytical_project, call_limit=1), check)
    assert calls["count"] == 1


def test_evidence_id_matches_execute_plan_and_snapshot_bytes_stay(analytical_project):
    database = current_snapshot(analytical_project) / "warehouse.duckdb"
    before = database.read_bytes()
    clock_args = {"first": "30_to_59", "second": "60_plus"}
    clock = execute_plan(
        analytical_project,
        "Compare the two clock buckets.",
        {
            "status": "answered",
            "interpretation": "descriptive_observed_prefix",
            "actions": [{"tool": "compare_clock_buckets", "args": clock_args}],
        },
    )
    listed = execute_plan(
        analytical_project,
        "List metrics.",
        {
            "status": "answered",
            "interpretation": "descriptive_observed_prefix",
            "actions": [{"tool": "list_metrics", "args": {}}],
        },
    )

    async def check(client):
        clock_result = await client.call_tool("compare_clock_buckets", clock_args)
        body = json.loads(clock_result.content[0].text)
        assert clock_result.is_error is False
        assert body["evidence_id"] == clock["evidence_ids"][0]
        assert body["dataset_id"] == clock["dataset_id"]
        assert body["result"] == clock["evidence"][0]["result"]
        assert body["caveats"] == body["result"]["caveats"]
        assert "exploratory_proxy" in body["caveats"]
        metrics = await client.call_tool("list_metrics", {})
        metrics_body = json.loads(metrics.content[0].text)
        assert "caveats" not in metrics_body
        assert metrics_body["evidence_id"] == listed["evidence_ids"][0]
        assert metrics_body["dataset_id"] == listed["dataset_id"]
        assert metrics_body["result"] == listed["result"]

    _drive(build_server(analytical_project), check)
    assert database.read_bytes() == before


def test_cli_stdio_process_lists_tools_and_calls_one(analytical_project):
    """The installed console path over real stdin/stdout, not only the in-memory transport."""
    import sys

    import anyio
    from mcp.client.session import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    parameters = StdioServerParameters(
        command=sys.executable,
        args=[
            "-c",
            "from chess_analytics.cli import main; raise SystemExit(main())",
            "--project",
            str(analytical_project),
            "mcp",
            "--call-limit",
            "4",
        ],
    )

    async def check():
        async with (
            stdio_client(parameters) as (read, write),
            ClientSession(read, write) as client,
        ):
            await client.initialize()
            listed = await client.list_tools()
            assert [tool.name for tool in listed.tools] == [spec.name for spec in TOOLS]
            result = await client.call_tool("list_metrics", {})
            assert result.is_error is False
            body = json.loads(result.content[0].text)
            assert body["dataset_id"]
            assert body["evidence_id"].startswith("ev_")

    anyio.run(check)


def test_contract_resources_are_read_only_files(analytical_project):
    expected = {
        path.name: path.read_text()
        for path in sorted((analytical_project / "contracts").glob("*.json"))
    }

    async def check(client):
        listed = await client.list_resources()
        assert {item.name for item in listed.resources} == set(expected)
        uri = "chesslab://contracts/game_draw_rate.json"
        read = await client.read_resource(uri)
        assert read.contents[0].text == expected["game_draw_rate.json"]
        with pytest.raises(Exception, match="unsupported contract resource"):
            await client.read_resource("chesslab://contracts/../pyproject.toml")

    _drive(build_server(analytical_project), check)
