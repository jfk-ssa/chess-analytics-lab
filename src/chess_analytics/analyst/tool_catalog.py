"""One allowlist of checked tools: name, JSON argument schema, and handler.

`CheckedTools.execute` and the MCP server both read this list. `execute` keeps
the historical argument-key gate. The MCP server validates `input_schema`
before it calls the same handler through the killable worker.
"""

from chess_analytics.analyst.maia_pins import ALIASES
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
ENGINE_MIN_DEPTH = 1
ENGINE_MAX_DEPTH = 16
ENGINE_DEFAULT_DEPTH = 12
MAX_MOVE_PREFIX = 40
MAX_CANDIDATES = 6
CONTINUATION_RETURN_LIMIT = 8
OPENING_COHORTS = ("elite_reference", "rated_public")
ENGINE_CAVEATS = ("engine_eval_depth_limited", "engine_not_ground_truth")
MAIA_MIN_RATING = 0
MAIA_MAX_RATING = 5000
MAIA_DEFAULT_TOP_K = 10
MAIA_MAX_TOP_K = 20
MAIA_PROBABILITY_DECIMALS = 4
MAIA_CAVEATS = ("model_estimate_not_observation", "blitz_trained_rating_scale")
_DEPTH = {"type": "integer", "minimum": ENGINE_MIN_DEPTH, "maximum": ENGINE_MAX_DEPTH}
_FEN = {"type": "string", "minLength": 1, "maxLength": 128}
_UCI_MOVE = {"type": "string", "minLength": 4, "maxLength": 5}
_MOVE_PREFIX = {
    "type": "array",
    "minItems": 1,
    "maxItems": MAX_MOVE_PREFIX,
    "items": _UCI_MOVE,
}
_CANDIDATES = {
    "type": "array",
    "minItems": 1,
    "maxItems": MAX_CANDIDATES,
    "items": _UCI_MOVE,
}
_COHORT_NAME = {"type": "string", "enum": list(OPENING_COHORTS)}
_RATING = {"type": "integer", "minimum": MAIA_MIN_RATING, "maximum": MAIA_MAX_RATING}
_TOP_K = {"type": "integer", "minimum": 1, "maximum": MAIA_MAX_TOP_K}
_MIN_PROB = {"type": "number", "minimum": 0, "maximum": 1}
_MAIA_MODEL = {"type": "string", "enum": list(ALIASES)}
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


def _number_match(schema: dict, value) -> bool:
    if isinstance(value, bool) or not isinstance(value, int | float):
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
    if kind == "number":
        return _number_match(schema, value)
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
    _spec(
        "evaluate_position",
        "Evaluate one validated position with the configured local engine. "
        "The score is depth-limited evidence, not ground truth.",
        _object({"fen": _FEN, "moves": _MOVE_PREFIX, "depth": _DEPTH}),
        frozenset({"fen", "moves", "depth"}),
        exact_keys=False,
    ),
    _spec(
        "position_continuations",
        "Observed White continuations for one position from local opening data. "
        "Frequency is not move quality. Unavailable when that data is not configured.",
        _object(
            {"fen": _FEN, "moves": _MOVE_PREFIX, "cohort": _COHORT_NAME},
            ["cohort"],
        ),
        frozenset({"fen", "moves", "cohort"}),
        exact_keys=False,
    ),
    _spec(
        "compare_candidate_moves",
        "Pair each candidate's centipawn loss versus the engine best move with "
        "its observed frequency. At most six candidates.",
        _object(
            {
                "fen": _FEN,
                "moves": _MOVE_PREFIX,
                "depth": _DEPTH,
                "cohort": _COHORT_NAME,
                "candidates": _CANDIDATES,
            },
            ["cohort", "candidates"],
        ),
        frozenset({"fen", "moves", "depth", "cohort", "candidates"}),
        exact_keys=False,
    ),
    _spec(
        "predict_human_moves",
        "Estimate a legal-move distribution for a player and opponent rating. "
        "The probabilities are a Maia-3 model estimate on the Lichess blitz scale, "
        "not observed frequencies and not an engine evaluation.",
        _object(
            {
                "fen": _FEN,
                "moves": _MOVE_PREFIX,
                "rating_self": _RATING,
                "rating_opp": _RATING,
                "model": _MAIA_MODEL,
                "top_k": _TOP_K,
                "min_prob": _MIN_PROB,
            },
            ["rating_self", "rating_opp"],
        ),
        frozenset({"fen", "moves", "rating_self", "rating_opp", "model", "top_k", "min_prob"}),
        exact_keys=False,
    ),
)
TOOLS_BY_NAME = {spec.name: spec for spec in TOOLS}
