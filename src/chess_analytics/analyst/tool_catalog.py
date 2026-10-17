"""One allowlist of checked tools: name, JSON argument schema, and handler.

`CheckedTools.execute` and the MCP server both read this list. `execute` keeps
the historical argument-key gate. The MCP server validates `input_schema`
before it calls the same handler through the killable worker.
"""

from chess_analytics.corpus.metrics import BUCKETS

CONTRACTS = {
    "game_draw_rate": "game_draw_rate.json",
    "opening_adjusted_score": "opening_adjusted_score.json",
    "opening_usage": "opening_usage.json",
    "opening_player_score": "opening_player_score.json",
    "clock_pressure_error_proxy": "clock_pressure_error_proxy.json",
    "evaluation_coverage": "evaluation_coverage.json",
}
ALLOWED_GROUP_BY = {"opening_family", "clock_bucket"}
_METRIC_ID = {"type": "string", "enum": sorted(CONTRACTS)}
_BUCKET = {"type": "string", "enum": sorted(BUCKETS)}
_COHORT = {
    "families": {
        "type": "array",
        "minItems": 2,
        "maxItems": 2,
        "items": {"type": "string", "minLength": 1, "maxLength": 80},
    },
    "color": {"type": "string", "enum": ["black", "white"]},
    "rating_min": {"type": "integer", "minimum": 0, "maximum": 3999},
    "rating_max_exclusive": {"type": "integer", "minimum": 1, "maximum": 4000},
    "base_seconds": {"type": "integer", "minimum": 0},
    "increment_seconds": {"type": "integer", "minimum": 0},
}


def _object(properties: dict, required: list[str] | None = None, *, closed: bool = True) -> dict:
    schema = {"type": "object", "properties": properties}
    if closed:
        schema["additionalProperties"] = False
    if required:
        schema["required"] = required
    return schema


def _object_match(schema: dict, value) -> bool:
    if not isinstance(value, dict):
        return False
    properties = schema.get("properties", {})
    if schema.get("additionalProperties") is False and set(value) - set(properties):
        return False
    if any(name not in value for name in schema.get("required", [])):
        return False
    return all(
        name not in value or arguments_match(properties[name], value[name]) for name in properties
    )


def _string_match(schema: dict, value) -> bool:
    if not isinstance(value, str):
        return False
    if "enum" in schema and value not in schema["enum"]:
        return False
    if "minLength" in schema and len(value) < schema["minLength"]:
        return False
    return "maxLength" not in schema or len(value) <= schema["maxLength"]


def _integer_match(schema: dict, value) -> bool:
    if isinstance(value, bool) or not isinstance(value, int):
        return False
    if "minimum" in schema and value < schema["minimum"]:
        return False
    return "maximum" not in schema or value <= schema["maximum"]


def _array_match(schema: dict, value) -> bool:
    if not isinstance(value, list):
        return False
    if "minItems" in schema and len(value) < schema["minItems"]:
        return False
    if "maxItems" in schema and len(value) > schema["maxItems"]:
        return False
    item_schema = schema.get("items")
    return item_schema is None or all(arguments_match(item_schema, item) for item in value)


def arguments_match(schema: dict, value) -> bool:
    """Return whether `value` matches the small JSON Schema subset these tools publish."""
    kind = schema.get("type")
    if kind == "object":
        return _object_match(schema, value)
    if kind == "string":
        return _string_match(schema, value)
    if kind == "integer":
        return _integer_match(schema, value)
    if kind == "array":
        return _array_match(schema, value)
    return False


class ToolSpec:
    """Name, published argument schema, and the `CheckedTools` method that runs it."""

    def __init__(
        self,
        name: str,
        description: str,
        input_schema: dict,
        keys: frozenset[str],
        exact_keys: bool,
    ):
        self.name = name
        self.description = description
        self.input_schema = input_schema
        self.keys = keys
        self.exact_keys = exact_keys

    def accepts(self, args: dict) -> bool:
        present = set(args)
        if self.exact_keys:
            return present == set(self.keys)
        return present <= set(self.keys)

    def handler(self, tools, args: dict) -> dict:
        method = getattr(tools, self.name)
        if not self.keys:
            return method()
        return method(**args)


def _spec(
    name: str, description: str, schema: dict, keys: frozenset[str], *, exact_keys: bool
) -> ToolSpec:
    return ToolSpec(name, description, schema, keys, exact_keys)


TOOLS = (
    _spec(
        "list_metrics",
        "List governed metric ids for the current analytical snapshot.",
        _object({}),
        frozenset(),
        exact_keys=True,
    ),
    _spec(
        "get_metric_definition",
        "Return one governed metric contract and the sha256 of its file.",
        _object({"metric_id": _METRIC_ID}, ["metric_id"]),
        frozenset({"metric_id"}),
        exact_keys=True,
    ),
    _spec(
        "get_dataset_coverage",
        "Return observed coverage, selection, and source kind for the current snapshot.",
        _object({}),
        frozenset(),
        exact_keys=True,
    ),
    _spec(
        "query_metric",
        "Compute one named metric. Grouped calls take an empty filters object.",
        _object(
            {
                "metric_id": _METRIC_ID,
                "filters": {"type": "object"},
                "group_by": {
                    "type": "array",
                    "maxItems": 1,
                    "items": {"type": "string", "enum": sorted(ALLOWED_GROUP_BY)},
                },
            },
            ["metric_id", "filters"],
        ),
        frozenset({"metric_id", "filters", "group_by"}),
        exact_keys=False,
    ),
    _spec(
        "compare_openings",
        "Compare two opening families in one exact cohort. Association only.",
        _object({"filters": _object(_COHORT, list(_COHORT))}, ["filters"]),
        frozenset({"filters"}),
        exact_keys=True,
    ),
    _spec(
        "analyze_clock_pressure",
        "Return the exploratory clock-pressure proxy for one clock bucket.",
        _object({"bucket": _BUCKET}, ["bucket"]),
        frozenset({"bucket"}),
        exact_keys=True,
    ),
    _spec(
        "compare_clock_buckets",
        "Compare the exploratory clock-pressure proxy for two distinct buckets.",
        _object({"first": _BUCKET, "second": _BUCKET}, ["first", "second"]),
        frozenset({"first", "second"}),
        exact_keys=True,
    ),
)
TOOLS_BY_NAME = {spec.name: spec for spec in TOOLS}
