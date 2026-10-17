"""Rating-conditioned human-move estimate. Torch stays in the worker subprocess."""

import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path

import chess

from chess_analytics.analyst.maia_pins import (
    ALIASES,
    CODE_COMMIT,
    CODE_REPO,
    PINS,
    RATING_SCALE,
)
from chess_analytics.analyst.positions import parse_position, position_key
from chess_analytics.analyst.tool_catalog import (
    MAIA_CAVEATS,
    MAIA_DEFAULT_TOP_K,
    MAIA_MAX_RATING,
    MAIA_MAX_TOP_K,
    MAIA_MIN_RATING,
    MAIA_PROBABILITY_DECIMALS,
    MAX_MOVE_PREFIX,
)
from chess_analytics.common import digest

HISTORY_BOARDS = 8
_SHA256 = re.compile(r"[0-9a-f]{64}")
_REVISION = re.compile(r"[0-9a-f]{40}")
_MODEL_KEYS = {
    "alias",
    "family",
    "weights_path",
    "sha256",
    "bytes",
    "hf_repo",
    "hf_revision",
    "code_repo",
    "code_commit",
    "device",
    "dtype",
    "threads",
    "rating_scale",
}
_PROVENANCE_KEYS = (
    "alias",
    "weights_sha256",
    "hf_revision",
    "code_commit",
    "torch_version",
    "platform",
    "dtype",
    "threads",
    "rating_scale",
)
_WDL_LABEL = "human-outcome prediction, not engine evaluation"
_PARENT_DEATH = (
    "import ctypes, os, sys\n"
    "ctypes.CDLL('libc.so.6').prctl(1, 9)\n"
    "os.execv(sys.argv[1], sys.argv[1:])\n"
)
_THREAD_ENV = ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS")


def evidence_material(dataset_id: str, args: dict, result: dict) -> list:
    """Identity for this tool. Probability and WDL floats are not part of it.

    Those floats move by about 1e-6 across thread counts, and rounding them
    still flips at decimal boundaries. The displayed probabilities stay in the
    result. `execute_plan` and the MCP server both hash this material.
    """
    provenance = result.get("provenance") or {}
    return [
        dataset_id,
        "predict_human_moves",
        args,
        {
            "fen": result.get("fen"),
            "position_key": result.get("position_key"),
            "history_plies": result.get("history_plies"),
            "rating_self": result.get("rating_self"),
            "rating_opp": result.get("rating_opp"),
            "top_k": result.get("top_k"),
            "min_prob": result.get("min_prob"),
            "reason": result.get("reason"),
            "provenance": {key: provenance.get(key) for key in _PROVENANCE_KEYS},
        },
    ]


def predict_human_moves(
    project: Path,
    dataset_id: str,
    rating_self: int | None = None,
    rating_opp: int | None = None,
    fen: str | None = None,
    moves: list[str] | None = None,
    model: str | None = None,
    top_k: int | None = None,
    min_prob: float | None = None,
) -> dict:
    """Legal-move distribution for one position and two ratings."""
    board, series = _boards(fen, moves)
    if not any(True for _ in board.legal_moves):
        raise ValueError("position has no legal moves")
    self_rating = _rating(rating_self, "rating_self")
    opp_rating = _rating(rating_opp, "rating_opp")
    selected_k = _top_k(top_k)
    floor = _min_prob(min_prob)
    if model is not None and model not in ALIASES:
        raise ValueError("unsupported maia model")
    base = _base(dataset_id, board, series, self_rating, opp_rating, selected_k, floor)
    config = _load_config(project)
    if config is None:
        return {
            **base,
            "reason": "maia_not_configured",
            "moves": [],
            "wdl": None,
            "provenance": None,
        }
    alias = config["default_alias"] if model is None else model
    if alias not in config["models"]:
        raise ValueError("maia model is not configured")
    spec = config["models"][alias]
    _verify(spec)
    message = _run_worker(
        project, _request(spec, alias, series, self_rating, opp_rating), spec["threads"]
    )
    if message.get("reason") == "maia_unavailable":
        return {
            **base,
            "reason": "maia_unavailable",
            "moves": [],
            "wdl": None,
            "provenance": _provenance(spec, message),
        }
    if not message.get("ok"):
        raise ValueError("maia failed")
    return {
        **base,
        "reason": None,
        "moves": _moves(board, message["moves"], selected_k, floor),
        "wdl": _wdl(message["wdl"]),
        "provenance": _provenance(spec, message),
    }


def _boards(fen: str | None, moves: list[str] | None) -> tuple[chess.Board, list[chess.Board]]:
    board = parse_position(fen, moves, max_moves=MAX_MOVE_PREFIX)
    if moves is None:
        return board, [board]
    cursor = chess.Board()
    series = [cursor.copy()]
    for uci in moves:
        cursor.push(chess.Move.from_uci(uci))
        series.append(cursor.copy())
    return board, series[-HISTORY_BOARDS:]


def clamp_rating(value: int) -> int:
    return min(MAIA_MAX_RATING, max(MAIA_MIN_RATING, value))


def _rating(value, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return clamp_rating(value)


def _top_k(value) -> int:
    if value is None:
        return MAIA_DEFAULT_TOP_K
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("top_k is outside the checked limit")
    if not 1 <= value <= MAIA_MAX_TOP_K:
        raise ValueError("top_k is outside the checked limit")
    return value


def _min_prob(value) -> float:
    if value is None:
        return 0.0
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError("min_prob is outside the checked limit")
    number = float(value)
    if not 0.0 <= number <= 1.0:
        raise ValueError("min_prob is outside the checked limit")
    return number


def _base(dataset_id, board, series, self_rating, opp_rating, top_k, floor) -> dict:
    white = board.turn == chess.WHITE
    return {
        "dataset_id": dataset_id,
        "fen": board.fen(),
        "position_key": position_key(board),
        "side_to_move": "white" if white else "black",
        "history_plies": len(series) - 1,
        "rating_self": self_rating,
        "rating_opp": opp_rating,
        "top_k": top_k,
        "min_prob": floor,
        "caveats": list(MAIA_CAVEATS),
    }


def _request(
    spec: dict, alias: str, series: list[chess.Board], self_rating: int, opp_rating: int
) -> dict:
    return {
        "weights_path": str(spec["weights_path"]),
        "model_name": PINS[alias]["model_name"],
        "threads": spec["threads"],
        "device": "cpu",
        "dtype": "float32",
        "code_commit": spec["code_commit"],
        "boards": [board.fen() for board in series],
        "rating_self": self_rating,
        "rating_opp": opp_rating,
    }


def _moves(board: chess.Board, raw, top_k: int, floor: float) -> list[dict]:
    if not isinstance(raw, dict):
        raise ValueError("maia worker returned invalid probabilities")
    legal = {move.uci(): move for move in board.legal_moves}
    kept = []
    for uci, prob in raw.items():
        if uci not in legal or isinstance(prob, bool) or not isinstance(prob, int | float):
            continue
        if not math.isfinite(prob) or prob <= 0:
            continue
        kept.append((uci, float(prob)))
    total = sum(prob for _, prob in kept)
    if total <= 0:
        raise ValueError("maia returned no legal moves")
    rows = []
    for uci, prob in kept:
        rounded = round(prob / total, MAIA_PROBABILITY_DECIMALS)
        if rounded <= 0 or rounded < floor:
            continue
        rows.append({"uci": uci, "san": board.san(legal[uci]), "probability": rounded})
    rows.sort(key=lambda row: (-row["probability"], row["uci"]))
    return rows[:top_k]


def _wdl(raw) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("maia worker returned no outcome")
    try:
        values = {
            key: round(float(raw[key]), MAIA_PROBABILITY_DECIMALS)
            for key in ("win", "draw", "loss")
        }
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("maia worker returned no outcome") from exc
    return {"label": _WDL_LABEL, **values}


def _provenance(spec: dict, message: dict) -> dict:
    return {
        "alias": spec["alias"],
        "family": "maia3",
        "weights_sha256": spec["sha256"],
        "bytes": spec["bytes"],
        "hf_repo": spec["hf_repo"],
        "hf_revision": spec["hf_revision"],
        "code_repo": spec["code_repo"],
        "code_commit": spec["code_commit"],
        "torch_version": message.get("torch_version"),
        "platform": message.get("platform"),
        "device": "cpu",
        "dtype": "float32",
        "threads": spec["threads"],
        "rating_scale": spec["rating_scale"],
    }


def _load_config(project: Path) -> dict | None:
    path = project / "config" / "maia.json"
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError("maia config is invalid") from exc
    if not isinstance(payload, dict) or set(payload) != {"version", "default_alias", "models"}:
        raise ValueError("maia config is invalid")
    models = payload["models"]
    if (
        payload["version"] != "1"
        or payload["default_alias"] not in ALIASES
        or not isinstance(models, dict)
        or not models
        or set(models) - set(ALIASES)
        or payload["default_alias"] not in models
    ):
        raise ValueError("maia config is invalid")
    return {
        "default_alias": payload["default_alias"],
        "models": {alias: _model(alias, body) for alias, body in models.items()},
    }


def _model(alias: str, body) -> dict:
    if not isinstance(body, dict) or set(body) != _MODEL_KEYS or body["alias"] != alias:
        raise ValueError("maia config is invalid")
    if not _identity(alias, body) or not _limits(body):
        raise ValueError("maia config is invalid")
    weights = Path(body["weights_path"])
    if not weights.is_absolute():
        raise ValueError("maia weights path must be absolute")
    return {**body, "weights_path": weights}


def _identity(alias: str, body: dict) -> bool:
    pin = PINS[alias]
    return (
        body["family"] == "maia3"
        and body["device"] == "cpu"
        and body["dtype"] == "float32"
        and body["rating_scale"] == RATING_SCALE
        and body["hf_repo"] == pin["hf_repo"]
        and body["hf_revision"] == pin["hf_revision"]
        and body["code_repo"] == CODE_REPO
        and body["code_commit"] == CODE_COMMIT
        and _SHA256.fullmatch(body["sha256"]) is not None
        and _REVISION.fullmatch(body["code_commit"]) is not None
        and isinstance(body["weights_path"], str)
    )


def _limits(body: dict) -> bool:
    threads = body["threads"]
    size = body["bytes"]
    if isinstance(threads, bool) or not isinstance(threads, int):
        return False
    if isinstance(size, bool) or not isinstance(size, int):
        return False
    return 1 <= threads <= 8 and size >= 1


def _verify(spec: dict) -> None:
    path = spec["weights_path"]
    if not path.is_file():
        raise ValueError("maia weights are missing")
    if path.stat().st_size != spec["bytes"] or digest(path) != spec["sha256"]:
        raise ValueError("maia weights hash mismatch")


def _child_env(threads: int) -> dict:
    value = str(threads)
    env = {
        "PATH": os.defpath,
        "PYTHONNOUSERSITE": "1",
        "HF_HUB_OFFLINE": "1",
        "HF_HUB_DISABLE_TELEMETRY": "1",
        "TRANSFORMERS_OFFLINE": "1",
    }
    env.update({name: value for name in _THREAD_ENV})
    return env


def _run_worker(project: Path, payload: dict, threads: int) -> dict:
    command = [
        sys.executable,
        "-c",
        _PARENT_DEATH,
        sys.executable,
        "-m",
        "chess_analytics.analyst.maia_worker",
    ]
    try:
        completed = subprocess.run(
            command,
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            cwd=project,
            env=_child_env(threads),
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError("maia worker killed after 30-second deadline") from exc
    try:
        message = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("maia failed") from exc
    if not isinstance(message, dict):
        raise ValueError("maia failed")
    return message
