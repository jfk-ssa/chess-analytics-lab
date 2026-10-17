"""Maia-3 subprocess. Torch is imported here, and only when the weights are a real checkpoint."""

import contextlib
import json
import os
import platform
import sys
import time
from collections import deque
from pathlib import Path

_FAKE_KIND = "fake_maia_distribution"
_FAKE_LIMIT = 1_000_000


class _UnavailableError(Exception):
    """Torch or the pinned maia3 package is not installed in this interpreter."""


def _platform() -> str:
    return f"{platform.system().lower()}-{platform.machine()}"


def _fake_payload(path: Path) -> dict | None:
    with path.open("rb") as handle:
        if handle.read(1) != b"{":
            return None
        rest = handle.read(_FAKE_LIMIT + 1)
    if len(rest) > _FAKE_LIMIT:
        raise ValueError("maia weights are not a checkpoint")
    payload = json.loads(b"{" + rest)
    if not isinstance(payload, dict) or payload.get("kind") != _FAKE_KIND:
        raise ValueError("maia weights are not a checkpoint")
    return payload


def _echo(payload: dict, request: dict) -> None:
    target = payload.get("echo_request")
    if not isinstance(target, str):
        return
    Path(target).write_text(
        json.dumps(
            {
                "rating_self": request["rating_self"],
                "rating_opp": request["rating_opp"],
                "boards": request["boards"],
                "threads": request["threads"],
            }
        )
    )


def _fake(path: Path, request: dict) -> dict:
    payload = _fake_payload(path)
    if payload is None:
        raise AssertionError("real checkpoint misrouted")
    _echo(payload, request)
    pid_file = payload.get("pid_file")
    if isinstance(pid_file, str):
        Path(pid_file).write_text(str(os.getpid()))
    hang = payload.get("hang_seconds") or 0
    if hang:
        time.sleep(hang)
    return {
        "moves": payload["moves"],
        "wdl": payload["wdl"],
        "torch_version": None,
        "platform": _platform(),
    }


def _installed_commit() -> str:
    from importlib.metadata import PackageNotFoundError, distribution

    try:
        dist = distribution("maia3")
    except PackageNotFoundError as exc:
        raise _UnavailableError from exc
    raw = dist.read_text("direct_url.json")
    if not raw:
        raise RuntimeError("maia install has no pinned commit")
    commit = (json.loads(raw).get("vcs_info") or {}).get("commit_id")
    if not isinstance(commit, str):
        raise RuntimeError("maia install has no pinned commit")
    return commit


def _load(cfg, torch):
    from maia3.models import MAIA3Model  # pyright: ignore[reportMissingImports]

    model = MAIA3Model(cfg).to("cpu").float()
    checkpoint = torch.load(cfg.checkpoint_path, map_location="cpu", weights_only=True)
    state = checkpoint
    if isinstance(checkpoint, dict) and "model_state_dict" in checkpoint:
        state = checkpoint["model_state_dict"]
    renamed = {key.replace("smolgen", "gab"): value for key, value in state.items()}
    missing, unexpected = model.load_state_dict(renamed, strict=False)
    if missing or unexpected:
        raise RuntimeError("maia checkpoint does not match the pinned code")
    model.eval()
    return model


def _infer(model, cfg, request: dict, torch) -> dict:
    import chess
    from maia3.dataset import (  # pyright: ignore[reportMissingImports]
        get_historical_tokens,
        get_legal_moves_mask,
        tokenize_board,
    )
    from maia3.utils import (  # pyright: ignore[reportMissingImports]
        get_all_possible_moves,
        mirror_move,
    )

    boards = [chess.Board(fen) for fen in request["boards"]]
    current = boards[-1]
    moves = get_all_possible_moves()
    index = {move: i for i, move in enumerate(moves)}
    reverse = {i: move for move, i in index.items()}
    history = deque((tokenize_board(board) for board in boards), maxlen=cfg.history)
    tokens = get_historical_tokens(history, cfg, 0.0, 0.0, 0.0, 0.0).unsqueeze(0)
    mask = get_legal_moves_mask(current, index)
    self_elo = torch.tensor([request["rating_self"]], dtype=torch.long)
    oppo_elo = torch.tensor([request["rating_opp"]], dtype=torch.long)
    with torch.no_grad():
        move_logits, value_logits, _rest = model(tokens, self_elo, oppo_elo)
    masked = move_logits.float().masked_fill(~mask, float("-inf"))
    probabilities = torch.softmax(masked, dim=-1)[0]
    distribution = {}
    for raw_index in probabilities.nonzero().flatten().tolist():
        uci = reverse[int(raw_index)]
        if current.turn == chess.BLACK:
            uci = mirror_move(uci)
        distribution[uci] = float(probabilities[int(raw_index)])
    loss, draw, win = torch.softmax(value_logits.float(), dim=-1)[0].tolist()
    return {
        "moves": distribution,
        "wdl": {"win": float(win), "draw": float(draw), "loss": float(loss)},
        "torch_version": torch.__version__,
        "platform": _platform(),
    }


def _real(request: dict, path: Path) -> dict:
    if request.get("device") != "cpu" or request.get("dtype") != "float32":
        raise RuntimeError("maia worker refuses a non-cpu or non-float32 request")
    try:
        import torch  # pyright: ignore[reportMissingImports]
        from maia3.uci import parse_args  # pyright: ignore[reportMissingImports]
    except ImportError as exc:
        raise _UnavailableError from exc
    threads = int(request["threads"])
    torch.set_num_threads(threads)
    with contextlib.suppress(RuntimeError):
        torch.set_num_interop_threads(1)
    if _installed_commit() != request["code_commit"]:
        raise RuntimeError("maia code commit mismatch")
    cfg = parse_args(
        [
            "--model",
            request["model_name"],
            "--checkpoint-path",
            str(path),
            "--device",
            "cpu",
            "--no-use-amp",
            "--local-files-only",
        ]
    )
    cfg.device = "cpu"
    cfg.use_amp = False
    cfg.trust_checkpoint = False
    return _infer(_load(cfg, torch), cfg, request, torch)


def predict(request: dict) -> dict:
    path = Path(request["weights_path"])
    if _fake_payload(path) is not None:
        return _fake(path, request)
    return _real(request, path)


def main() -> int:
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise ValueError("invalid maia worker request")
        print(json.dumps({"ok": True, **predict(request)}))
    except _UnavailableError:
        print(json.dumps({"ok": False, "reason": "maia_unavailable"}))
    except Exception as exc:
        print(json.dumps({"ok": False, "reason": "maia_failed", "error": str(exc)}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
