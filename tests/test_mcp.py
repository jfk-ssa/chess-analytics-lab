"""Registry and import checks that do not need the optional MCP extra."""

import ast
from pathlib import Path

import pytest

from chess_analytics.analyst.mcp_server import SESSION_CALL_LIMIT
from chess_analytics.analyst.tool_catalog import (
    ALLOWED_GROUP_BY,
    CONTRACTS,
    TOOLS,
    TOOLS_BY_NAME,
    arguments_match,
)
from chess_analytics.analyst.tools import CheckedTools
from chess_analytics.cli import main
from chess_analytics.corpus.metrics import BUCKETS

ROOT = Path(__file__).resolve().parents[1]
ALLOWLIST = [
    "list_metrics",
    "get_metric_definition",
    "get_dataset_coverage",
    "query_metric",
    "compare_openings",
    "analyze_clock_pressure",
    "compare_clock_buckets",
    "evaluate_position",
    "position_continuations",
    "compare_candidate_moves",
]


def _module_imports(relative: str) -> list[str]:
    tree = ast.parse((ROOT / relative).read_text())
    names = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def test_mcp_sdk_is_not_imported_at_module_level():
    for relative in (
        "src/chess_analytics/analyst/mcp_server.py",
        "src/chess_analytics/analyst/tool_catalog.py",
        "src/chess_analytics/cli.py",
    ):
        names = _module_imports(relative)
        assert all(name.split(".")[0] not in {"mcp", "mcp_types", "anyio"} for name in names), (
            relative
        )


def test_server_entry_is_stdio_only():
    source = (ROOT / "src/chess_analytics/analyst/mcp_server.py").read_text()
    assert "stdio_server" in source
    assert "streamable_http" not in source
    assert "uvicorn" not in source
    assert SESSION_CALL_LIMIT == 64


def test_mcp_help_is_stdio_only(capsys):
    with pytest.raises(SystemExit) as caught:
        main(["mcp", "--help"])
    assert caught.value.code == 0
    text = capsys.readouterr().out
    assert "stdio" in text
    assert "--host" not in text and "--port" not in text


def test_registry_names_are_the_allowlist():
    assert [spec.name for spec in TOOLS] == ALLOWLIST
    assert set(TOOLS_BY_NAME) == set(ALLOWLIST)


def test_execute_uses_the_registry_and_keeps_the_key_gate():
    tools = CheckedTools.__new__(CheckedTools)
    tools.dataset_id = "abc"
    assert tools.execute("list_metrics", {})["metric_ids"] == sorted(CONTRACTS)
    with pytest.raises(ValueError, match="unsupported tool or arguments"):
        tools.execute("run_readonly_query", {"sql": "select 1"})
    with pytest.raises(ValueError, match="unsupported tool or arguments"):
        tools.execute("query_metric", {"metric_id": "opening_usage", "filters": {}, "sql": "drop"})
    with pytest.raises(ValueError, match="tool arguments must be an object"):
        tools.execute("list_metrics", [])


def test_published_schema_matches_metric_contracts_and_rejects_bad_arguments():
    definition = TOOLS_BY_NAME["get_metric_definition"].input_schema
    query = TOOLS_BY_NAME["query_metric"].input_schema
    clock = TOOLS_BY_NAME["analyze_clock_pressure"].input_schema
    assert set(definition["properties"]["metric_id"]["enum"]) == set(CONTRACTS)
    assert set(query["properties"]["metric_id"]["enum"]) == set(CONTRACTS)
    assert set(query["properties"]["group_by"]["items"]["enum"]) == ALLOWED_GROUP_BY
    assert set(clock["properties"]["bucket"]["enum"]) == BUCKETS
    assert arguments_match(
        query, {"metric_id": "opening_usage", "filters": {"family": "Sicilian Defense"}}
    )
    assert not arguments_match(
        query, {"metric_id": "opening_usage", "filters": {}, "sql": "select 1"}
    )
    assert not arguments_match(clock, {"bucket": True})
    assert not arguments_match(TOOLS_BY_NAME["list_metrics"].input_schema, {"dataset_id": "x"})
