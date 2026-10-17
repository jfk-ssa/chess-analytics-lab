"""Offline Maia checked tool. No weights download and no torch import."""

import ast
import importlib.util
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

import chess
import pytest

from chess_analytics.analyst.core import _evidence_id, answer_caveats, execute_plan, run_killable_tool
from chess_analytics.analyst.maia_pins import CODE_COMMIT, CODE_REPO, PINS, RATING_SCALE
from chess_analytics.analyst.mcp_server import _envelope, rejection
from chess_analytics.analyst.plan_recovery import PLAN_SCHEMA
from chess_analytics.analyst.tool_catalog import MAIA_CAVEATS, TOOLS_BY_NAME, arguments_match
from chess_analytics.analyst.tools import CheckedTools
from chess_analytics.common import digest, write_json

ROOT = Path(__file__).resolve().parents[1]
DISTRIBUTION = ROOT / "tests/fixtures/maia/distribution.json"
HANG = ROOT / "tests/fixtures/maia/hang.json"
START = chess.STARTING_FEN
WDL_LABEL = "human-outcome prediction, not engine evaluation"


def bare(project: Path, dataset: str = "a" * 24) -> CheckedTools:
    tools = CheckedTools.__new__(CheckedTools)
    tools.project = project
    tools.dataset_id = dataset
    return tools


def write_maia(project: Path, weights: Path, **overrides) -> None:
    pin = PINS["23M"]
    model = {
        "alias": "23M",
        "family": "maia3",
        "weights_path": str(weights.resolve()),
        "sha256": digest(weights),
        "bytes": weights.stat().st_size,
        "hf_repo": pin["hf_repo"],
        "hf_revision": pin["hf_revision"],
        "code_repo": CODE_REPO,
        "code_commit": CODE_COMMIT,
        "device": "cpu",
        "dtype": "float32",
        "threads": 1,
        "rating_scale": RATING_SCALE,
    }
    model.update(overrides)
    write_json(
        project / "config/maia.json",
        {"version": "1", "default_alias": "23M", "models": {"23M": model}},
    )


def _imports(relative: str) -> list[str]:
    tree = ast.parse((ROOT / relative).read_text())
    names = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def test_example_config_is_obviously_fake_and_pins_are_full_length():
    example = json.loads((ROOT / "config/maia.example.json").read_text())
    assert example["default_alias"] == "23M"
    for alias, pin in PINS.items():
        model = example["models"][alias]
        assert model["weights_path"].startswith("/absolute/path/to/")
        assert model["sha256"] == "0" * 64
        assert model["bytes"] == 0
        assert not Path(model["weights_path"]).exists()
        assert model["hf_repo"] == pin["hf_repo"]
        assert model["hf_revision"] == pin["hf_revision"]
        assert len(pin["sha256"]) == 64
        assert pin["bytes"] > 0
    assert len(CODE_COMMIT) == 40


def test_torch_is_not_imported_by_the_default_modules():
    for relative in (
        "src/chess_analytics/analyst/maia.py",
        "src/chess_analytics/analyst/maia_worker.py",
        "src/chess_analytics/analyst/maia_pins.py",
        "src/chess_analytics/analyst/tools.py",
        "src/chess_analytics/analyst/core.py",
        "src/chess_analytics/analyst/tool_catalog.py",
        "src/chess_analytics/cli.py",
    ):
        assert all(name.split(".")[0] not in {"torch", "maia3"} for name in _imports(relative))
    import chess_analytics.analyst.maia as maia_module

    assert maia_module.predict_human_moves
    assert importlib.util.find_spec("torch") is None
    assert "torch" not in sys.modules


def test_historical_planner_does_not_offer_the_model():
    source = (ROOT / "src/chess_analytics/analyst/provider.py").read_text()
    assert "predict_human_moves" not in source
    enum = PLAN_SCHEMA["properties"]["actions"]["items"]["properties"]["tool"]["enum"]
    assert "predict_human_moves" not in enum
    assert answer_caveats([{"tool": "predict_human_moves", "args": {"rating_self": 1500}}]) == [
        "blitz_trained_rating_scale",
        "model_estimate_not_observation",
        "observed_prefix_only",
    ]
    assert answer_caveats([{"tool": "list_metrics", "args": {}}]) == ["observed_prefix_only"]


def test_schema_rejects_bad_arguments_before_a_worker(monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("worker started")

    monkeypatch.setattr("chess_analytics.analyst.core.run_killable_tool", boom)
    schema = TOOLS_BY_NAME["predict_human_moves"].input_schema
    good = {"fen": START, "rating_self": 1500, "rating_opp": 1500, "top_k": 10, "model": "23M"}
    assert arguments_match(schema, good)
    assert rejection("predict_human_moves", good) is None
    for args in (
        {"fen": START, "rating_self": 5001, "rating_opp": 1500},
        {"fen": START, "rating_self": -1, "rating_opp": 1500},
        {"fen": START, "rating_self": True, "rating_opp": 1500},
        {"fen": START, "rating_self": 1500, "rating_opp": 1500, "top_k": 21},
        {"fen": START, "rating_self": 1500, "rating_opp": 1500, "min_prob": 1.1},
        {"fen": START, "rating_self": 1500, "rating_opp": 1500, "min_prob": True},
        {"fen": START, "rating_self": 1500, "rating_opp": 1500, "model": "3M"},
        {"fen": START, "rating_self": 1500, "rating_opp": 1500, "sql": "select 1"},
    ):
        assert not arguments_match(schema, args)
        assert rejection("predict_human_moves", args) == "invalid tool arguments"


def test_missing_config_is_structured_and_does_not_start_a_worker(tmp_path, monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("worker started")

    monkeypatch.setattr("chess_analytics.analyst.maia.subprocess.run", boom)
    result = bare(tmp_path).execute(
        "predict_human_moves", {"fen": START, "rating_self": 1500, "rating_opp": 1600}
    )
    assert result["reason"] == "maia_not_configured"
    assert result["moves"] == []
    assert result["wdl"] is None
    assert result["provenance"] is None
    assert result["caveats"] == list(MAIA_CAVEATS)
    assert result["rating_self"] == 1500


def test_config_rejects_a_bad_file_a_relative_path_and_a_hash_mismatch(tmp_path, monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("worker started")

    monkeypatch.setattr("chess_analytics.analyst.maia.subprocess.run", boom)
    tools = bare(tmp_path)
    args = {"fen": START, "rating_self": 1500, "rating_opp": 1500}
    write_maia(tmp_path, DISTRIBUTION, weights_path="relative/maia.pt")
    with pytest.raises(ValueError, match="absolute"):
        tools.execute("predict_human_moves", args)
    write_maia(tmp_path, DISTRIBUTION, weights_path=str(tmp_path / "missing.pt"))
    with pytest.raises(ValueError, match="missing"):
        tools.execute("predict_human_moves", args)
    write_maia(tmp_path, DISTRIBUTION, sha256="0" * 64)
    with pytest.raises(ValueError, match="hash mismatch"):
        tools.execute("predict_human_moves", args)
    write_maia(tmp_path, DISTRIBUTION, bytes=DISTRIBUTION.stat().st_size + 1)
    with pytest.raises(ValueError, match="hash mismatch"):
        tools.execute("predict_human_moves", args)
    write_maia(tmp_path, DISTRIBUTION, dtype="bfloat16")
    with pytest.raises(ValueError, match="invalid"):
        tools.execute("predict_human_moves", args)
    write_maia(tmp_path, DISTRIBUTION, device="cuda")
    with pytest.raises(ValueError, match="invalid"):
        tools.execute("predict_human_moves", args)


def test_fake_distribution_is_legal_labelled_and_stable(tmp_path):
    write_maia(tmp_path, DISTRIBUTION)
    tools = bare(tmp_path)
    args = {"fen": START, "rating_self": 1500, "rating_opp": 1500}
    first = tools.execute("predict_human_moves", args)
    second = tools.execute("predict_human_moves", args)
    assert first == second
    assert [row["uci"] for row in first["moves"]] == ["e2e4", "d2d4"]
    assert [row["san"] for row in first["moves"]] == ["e4", "d4"]
    assert first["moves"][0]["probability"] == pytest.approx(0.625)
    assert first["moves"][1]["probability"] == pytest.approx(0.375)
    assert sum(row["probability"] for row in first["moves"]) == pytest.approx(1)
    assert first["history_plies"] == 0
    assert first["wdl"]["label"] == WDL_LABEL
    assert first["caveats"] == list(MAIA_CAVEATS)
    assert first["provenance"]["alias"] == "23M"
    assert first["provenance"]["dtype"] == "float32"
    assert first["provenance"]["threads"] == 1
    assert first["provenance"]["rating_scale"] == "lichess-blitz"
    assert first["provenance"]["weights_sha256"] == digest(DISTRIBUTION)
    assert first["provenance"]["code_commit"] == CODE_COMMIT
    assert first["provenance"]["torch_version"] is None
    assert first["provenance"]["platform"] == f"{platform.system().lower()}-{platform.machine()}"
    assert "weights_path" not in json.dumps(first)
    evidence = _evidence_id(tools.dataset_id, "predict_human_moves", args, first)
    perturbed = json.loads(json.dumps(first))
    perturbed["moves"][0]["probability"] += 1e-6
    perturbed["wdl"]["win"] += 1e-6
    assert _evidence_id(tools.dataset_id, "predict_human_moves", args, perturbed) == evidence
    low = json.loads(json.dumps(first))
    high = json.loads(json.dumps(first))
    low["moves"][0]["probability"] = 0.10004
    high["moves"][0]["probability"] = 0.10006
    assert round(0.10004, 4) != round(0.10006, 4)
    assert _evidence_id(tools.dataset_id, "predict_human_moves", args, low) == _evidence_id(
        tools.dataset_id, "predict_human_moves", args, high
    )
    changed = json.loads(json.dumps(first))
    changed["provenance"]["threads"] = 2
    assert _evidence_id(tools.dataset_id, "predict_human_moves", args, changed) != evidence


def test_black_reply_history_rating_clamp_and_filters(tmp_path):
    echo = tmp_path / "echo.json"
    payload = json.loads(DISTRIBUTION.read_text())
    payload["echo_request"] = str(echo)
    weights = tmp_path / "echo-weights.json"
    weights.write_text(json.dumps(payload))
    write_maia(tmp_path, weights)
    tools = bare(tmp_path)
    clamped = tools.execute(
        "predict_human_moves",
        {"moves": ["d2d4"], "rating_self": 6000, "rating_opp": -4, "top_k": 10},
    )
    assert clamped["rating_self"] == 5000
    assert clamped["rating_opp"] == 0
    assert clamped["side_to_move"] == "black"
    assert clamped["history_plies"] == 1
    assert clamped["moves"] == [{"uci": "e7e5", "san": "e5", "probability": 1.0}]
    sent = json.loads(echo.read_text())
    assert sent["rating_self"] == 5000 and sent["rating_opp"] == 0
    assert len(sent["boards"]) == 2
    echo.unlink()
    long_game = [
        "e2e4",
        "e7e5",
        "g1f3",
        "b8c6",
        "f1c4",
        "g8f6",
        "d2d3",
        "d7d6",
        "c2c3",
        "c7c6",
    ]
    with pytest.raises(ValueError, match="no legal moves"):
        tools.execute(
            "predict_human_moves",
            {"moves": long_game, "rating_self": 1500, "rating_opp": 1500},
        )
    assert len(json.loads(echo.read_text())["boards"]) == 8
    limited = tools.execute(
        "predict_human_moves",
        {"fen": START, "rating_self": 1500, "rating_opp": 1500, "top_k": 1, "min_prob": 0.5},
    )
    assert [row["uci"] for row in limited["moves"]] == ["e2e4"]
    with pytest.raises(ValueError, match="fen or a move prefix"):
        tools.execute(
            "predict_human_moves",
            {"fen": START, "moves": ["e2e4"], "rating_self": 1500, "rating_opp": 1500},
        )
    with pytest.raises(ValueError, match="top_k"):
        tools.execute(
            "predict_human_moves", {"fen": START, "rating_self": 1500, "rating_opp": 1500, "top_k": 21}
        )


def test_missing_runtime_reports_maia_unavailable(tmp_path):
    if importlib.util.find_spec("torch") is not None and importlib.util.find_spec("maia3") is not None:
        pytest.skip("torch and maia3 are installed")
    weights = tmp_path / "not-a-checkpoint.bin"
    weights.write_bytes(b"not json")
    write_maia(tmp_path, weights)
    result = bare(tmp_path).execute(
        "predict_human_moves", {"fen": START, "rating_self": 1500, "rating_opp": 1500}
    )
    assert result["reason"] == "maia_unavailable"
    assert result["moves"] == []
    assert result["caveats"] == list(MAIA_CAVEATS)
    assert result["provenance"]["weights_sha256"] == digest(weights)
    assert result["provenance"]["torch_version"] is None
    assert "torch" not in sys.modules


def test_worker_environment_stays_offline(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "secret")
    monkeypatch.setenv("HF_TOKEN", "secret")
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["env"] = kwargs["env"]
        body = {
            "ok": True,
            "moves": {"e2e4": 1},
            "wdl": {"win": 0.2, "draw": 0.3, "loss": 0.5},
            "torch_version": None,
            "platform": "linux-x86_64",
        }
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps(body), stderr="")

    monkeypatch.setattr("chess_analytics.analyst.maia.subprocess.run", fake_run)
    write_maia(tmp_path, DISTRIBUTION)
    bare(tmp_path).execute(
        "predict_human_moves", {"fen": START, "rating_self": 1200, "rating_opp": 1200}
    )
    env = captured["env"]
    assert "OPENAI_API_KEY" not in env and "HF_TOKEN" not in env
    assert env["HF_HUB_OFFLINE"] == "1"
    assert env["OMP_NUM_THREADS"] == "1"
    assert "prctl" in captured["command"][2]


@pytest.fixture(scope="module")
def analytical_project(tmp_path_factory):
    from chess_analytics.common import read_json, writer_lock
    from chess_analytics.corpus.publish import build_analytical
    from chess_analytics.corpus.source import extracted_path
    from chess_analytics.ingest.pipeline import ingest
    from chess_analytics.portfolio_demo import _stage_project
    from chess_analytics.warehouse.snapshots import build

    project = tmp_path_factory.mktemp("maia-analytical") / "project"
    _stage_project(ROOT, project)
    root = project / "data"
    plan = read_json(project / "config/datasets.json")["analytical"]
    with writer_lock(root):
        ingest(project, root, "analytical", extracted_path(root, plan), plan)
        build(project, root, "analytical")
        build_analytical(project, root)
    return project


def test_plan_and_mcp_evidence_agree_and_a_hung_worker_is_killed(analytical_project):
    write_maia(analytical_project, DISTRIBUTION)
    args = {"fen": START, "rating_self": 1500, "rating_opp": 1500, "model": "23M"}
    dataset_id, result = run_killable_tool(analytical_project, "predict_human_moves", args)
    answer = execute_plan(
        analytical_project,
        "What would a 1500 play from the start?",
        {
            "status": "answered",
            "interpretation": "descriptive_observed_prefix",
            "actions": [{"tool": "predict_human_moves", "args": args}],
        },
    )
    assert dataset_id == answer["dataset_id"]
    assert result == answer["evidence"][0]["result"]
    assert answer["evidence_ids"][0] == _evidence_id(dataset_id, "predict_human_moves", args, result)
    assert _envelope(dataset_id, "predict_human_moves", args, result)["evidence_id"] == answer["evidence_ids"][0]
    assert "model_estimate_not_observation" in answer["caveats"]
    assert "blitz_trained_rating_scale" in answer["caveats"]
    write_maia(analytical_project, HANG)
    pid_path = analytical_project / "maia-hang.pid"
    pid_path.unlink(missing_ok=True)
    with pytest.raises(TimeoutError, match="killed"):
        run_killable_tool(
            analytical_project,
            "predict_human_moves",
            {"fen": START, "rating_self": 1500, "rating_opp": 1500},
            timeout_seconds=5,
        )
    pid = int(pid_path.read_text())
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.05)
    pytest.fail("maia worker survived the parent kill")


@pytest.mark.skipif(not (ROOT / "config/maia.json").is_file(), reason="config/maia.json is absent")
def test_real_weights_distribution_is_legal_when_configured(tmp_path):
    configured = json.loads((ROOT / "config/maia.json").read_text())
    write_json(tmp_path / "config/maia.json", configured)
    result = bare(tmp_path).execute(
        "predict_human_moves",
        {"moves": ["d2d4"], "rating_self": 1500, "rating_opp": 1500, "top_k": 20},
    )
    assert result["reason"] is None
    assert result["moves"]
    assert sum(row["probability"] for row in result["moves"]) == pytest.approx(1, abs=0.02)
    assert result["caveats"] == list(MAIA_CAVEATS)
    assert result["wdl"]["label"] == WDL_LABEL
