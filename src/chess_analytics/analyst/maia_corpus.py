"""One-population played-move scores from a PGN. One Maia worker, many positions.

Elite and public are separate runs. This module has no pooled score.
Torch stays in the worker. A fake weights file never imports it.
"""

import argparse
import contextlib
import json
import math
import os
import random
import re
import select
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import NoReturn

import chess
import chess.pgn

from chess_analytics.analyst.maia import (
    HISTORY_BOARDS,
    _child_env,
    _load_config,
    _verify,
    clamp_rating,
)
from chess_analytics.analyst.maia_pins import PINS
from chess_analytics.analyst.maia_report import (
    BANDS,
    ZERO_SHARE_WARN,
    add_reliability,
    empty_bins,
    finish_bins,
    labeled,
    metrics,
    render_markdown,
)
from chess_analytics.analyst.maia_trust import lichess_blitz

SEED = 20251017
SAMPLE_TARGET = 20_000
PLIES = 12
BATCH = 64
BOOTSTRAP = 400
READ_TIMEOUT = 600
CLOSE_TIMEOUT = 30
PROGRESS_EVERY = 10
POPULATIONS = {
    "elite": {"id": "elite_2025_11", "blitz_only": False},
    "public": {"id": "public_2026_08_blitz", "blitz_only": True},
}
CAVEATS = (
    "elite_high_rated_curated_month",
    "months_are_after_the_training_window_not_a_designed_sample",
    "platform_unmeasured_outside_linux_x86_64",
    "same_machine_only",
    "populations_not_pooled",
    "public_sample_is_the_2026-08-01_prefix",
)
_CLOCK = re.compile(r"(\d+)\+(\d+)")


def _band(rating: int) -> str:
    if rating < 1000:
        return BANDS[0]
    if rating < 1600:
        return BANDS[1]
    if rating < 2000:
        return BANDS[2]
    if rating < 2300:
        return BANDS[3]
    return BANDS[4]


def _visitor(limit: int):
    class Prefix(chess.pgn.BaseVisitor):
        def __init__(self) -> None:
            self.headers: dict[str, str] = {}
            self.moves: list[str] = []
            self.bad = False

        def visit_header(self, tagname: str, tagvalue: str) -> None:
            self.headers[tagname] = tagvalue

        def visit_move(self, board: chess.Board, move: chess.Move) -> None:
            # visit_move's return value is ignored. Record the prefix and keep parsing.
            if len(self.moves) < limit:
                self.moves.append(move.uci())

        def handle_error(self, error: Exception) -> None:
            self.bad = True

        def result(self):
            return self

    return Prefix


def _clock(headers: dict) -> tuple[int | None, int | None]:
    match = _CLOCK.fullmatch(headers.get("TimeControl") or "")
    if match is None:
        return None, None
    return int(match[1]), int(match[2])


def _elo(headers: dict, color: str) -> int | None:
    value = headers.get(f"{color}Elo", "")
    return int(value) if value.isdigit() else None


def _accept(parsed, limit: int) -> dict | None:
    headers = parsed.headers
    if parsed.bad or not parsed.moves:
        return None
    if headers.get("Variant", "Standard") != "Standard":
        return None
    if headers.get("SetUp", "0") != "0" or "FEN" in headers:
        return None
    if headers.get("WhiteTitle") == "BOT" or headers.get("BlackTitle") == "BOT":
        return None
    white, black = _elo(headers, "White"), _elo(headers, "Black")
    if white is None or black is None:
        return None
    base, increment = _clock(headers)
    return {
        "moves": parsed.moves[:limit],
        "white": white,
        "black": black,
        "blitz": lichess_blitz(base, increment),
    }


def select_games(path: Path, *, blitz_only: bool, sample_size: int, seed: int, plies: int) -> tuple:
    """Reservoir-sample up to `sample_size` accepted games. Seeded, without replacement."""
    rng = random.Random(seed)
    chosen: list[dict] = []
    seen = eligible = passing = 0
    visitor = _visitor(plies)
    with path.open(encoding="utf-8", errors="replace") as handle:
        while (parsed := chess.pgn.read_game(handle, Visitor=visitor)) is not None:
            seen += 1
            game = _accept(parsed, plies)
            if game is None:
                continue
            passing += int(game["blitz"])
            if blitz_only and not game["blitz"]:
                continue
            eligible += 1
            game["ordinal"] = seen
            if len(chosen) < sample_size:
                chosen.append(game)
            else:
                slot = rng.randrange(eligible)
                if slot < sample_size:
                    chosen[slot] = game
    stats = {
        "games_seen": seen,
        "games_eligible": eligible,
        "games_passing_blitz": passing,
        "sample_games": len(chosen),
        "sample_blitz_games": sum(game["blitz"] for game in chosen),
        "sample_target_met": eligible >= sample_size,
    }
    return chosen, stats


def _positions(game: dict, index: int):
    board = chess.Board()
    series = [board.copy()]
    for ply, uci in enumerate(game["moves"], start=1):
        white_turn = board.turn == chess.WHITE
        self_rating = clamp_rating(game["white"] if white_turn else game["black"])
        opp_rating = clamp_rating(game["black"] if white_turn else game["white"])
        yield {
            "game": index,
            "ply": ply,
            "band": _band(self_rating),
            "played": uci,
            "boards": [item.fen() for item in series[-HISTORY_BOARDS:]],
            "rating_self": self_rating,
            "rating_opp": opp_rating,
            "legal": sorted(move.uci() for move in board.legal_moves),
        }
        board.push(chess.Move.from_uci(uci))
        series.append(board.copy())


def _mass(raw, legal: list[str]) -> dict[str, float]:
    if not isinstance(raw, dict):
        return {}
    kept = []
    for uci, prob in raw.items():
        if uci not in legal or isinstance(prob, bool) or not isinstance(prob, int | float):
            continue
        if not math.isfinite(float(prob)) or float(prob) <= 0:
            continue
        kept.append((uci, float(prob)))
    total = sum(prob for _, prob in kept)
    if total <= 0:
        return {}
    return {uci: prob / total for uci, prob in kept}


def _outcome(position: dict, raw) -> tuple[dict, list[dict]]:
    """Zero played probability is a ranking miss. Log-loss drops it later."""
    mass = _mass(raw, position["legal"])
    played = position["played"]
    rows = [
        {"predicted": mass.get(uci, 0.0), "observed": int(uci == played), "count": 1}
        for uci in position["legal"]
    ]
    probability = mass.get(played, 0.0)
    rank = 0 if probability <= 0 else 1 + sum(prob > probability for prob in mass.values())
    return {
        "game": position["game"],
        "ply": position["ply"],
        "band": position["band"],
        "probability": probability,
        "rank": rank,
    }, rows


def _open_worker(project: Path, spec: dict, alias: str, errors):
    header = {
        "weights_path": str(spec["weights_path"]),
        "model_name": PINS[alias]["model_name"],
        "threads": spec["threads"],
        "device": "cpu",
        "dtype": "float32",
        "code_commit": spec["code_commit"],
    }
    proc = subprocess.Popen(
        [sys.executable, "-m", "chess_analytics.analyst.maia_worker", "--batch"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=errors,
        cwd=project,
        env=_child_env(spec["threads"]),
        text=True,
    )
    if proc.stdin is None or proc.stdout is None:
        raise ValueError("maia worker pipes are missing")
    # One reader. Detach the text wrapper so its buffer cannot hide bytes.
    stdout = proc.stdout
    proc.stdout = stdout.detach()  # pyright: ignore[reportAttributeAccessIssue]
    try:
        proc.stdin.write(json.dumps(header) + "\n")
        proc.stdin.flush()
    except BrokenPipeError:
        _fail(proc, errors, "maia worker closed")
    return proc


def _stderr(errors) -> str:
    errors.seek(0)
    return errors.read().strip()


def _kill(proc) -> None:
    if proc.poll() is None:
        proc.kill()
        with contextlib.suppress(subprocess.TimeoutExpired):
            proc.wait(timeout=5)


def _fail(proc, errors, primary: str) -> NoReturn:
    _kill(proc)
    detail = _stderr(errors)
    if detail and detail not in primary:
        primary = f"{primary}\n{detail}"
    raise ValueError(primary)


def _read_line(stream, timeout: float) -> str:
    """One stdout line. Bytes after the newline stay on the stream for the next read."""
    deadline = time.monotonic() + timeout
    fd = stream.fileno()
    pending = getattr(stream, "maia_rest", b"")
    blocking = os.get_blocking(fd)
    os.set_blocking(fd, False)
    try:
        while b"\n" not in pending:
            remaining = deadline - time.monotonic()
            ready = remaining > 0 and select.select([fd], [], [], remaining)[0]
            if not ready:
                stream.maia_rest = pending
                raise TimeoutError
            try:
                piece = os.read(fd, 65536)
            except BlockingIOError:
                continue
            if not piece:
                stream.maia_rest = b""
                return ""
            pending += piece
    finally:
        os.set_blocking(fd, blocking)
    line, _, pending = pending.partition(b"\n")
    stream.maia_rest = pending
    return line.decode()


def _send(proc, positions: list[dict], errors, timeout: float) -> list[dict]:
    payload = [
        {
            "boards": position["boards"],
            "rating_self": position["rating_self"],
            "rating_opp": position["rating_opp"],
        }
        for position in positions
    ]
    try:
        proc.stdin.write(json.dumps({"positions": payload}) + "\n")
        proc.stdin.flush()
    except BrokenPipeError:
        _fail(proc, errors, "maia worker closed")
    try:
        line = _read_line(proc.stdout, timeout)
    except TimeoutError:
        _fail(proc, errors, f"maia worker timed out after {timeout:g}s")
    if not line:
        _fail(proc, errors, "maia worker closed")
    message = json.loads(line)
    if not message.get("ok"):
        primary = str(message.get("error") or message.get("reason") or "maia failed")
        _fail(proc, errors, primary)
    results = message["results"]
    if len(results) != len(positions):
        _fail(proc, errors, "maia batch length mismatch")
    return results


def _close(proc, errors, timeout: float = 30) -> None:
    try:
        if proc.stdin is not None and proc.poll() is None:
            try:
                proc.stdin.write(json.dumps({"done": True}) + "\n")
                proc.stdin.flush()
                proc.stdin.close()
            except BrokenPipeError:
                _fail(proc, errors, "maia worker closed")
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        _fail(proc, errors, f"maia worker timed out after {timeout:g}s")
    finally:
        _kill(proc)


def _progress(done: int, total: int, started: float, batches: int, every: int, final: bool) -> None:
    if not final and batches != 1 and batches % every and done != total:
        return
    elapsed = time.monotonic() - started
    if final:
        print(f"maia corpus: finished {done}/{total} positions in {elapsed:.1f}s", file=sys.stderr)
        return
    eta = ""
    if batches > 1 and done < total and done > 0:
        eta = f", ETA {elapsed / done * (total - done):.0f}s"
    print(f"maia corpus: {done}/{total} positions, elapsed {elapsed:.1f}s{eta}", file=sys.stderr)


def _consume(proc, batch, played: list[dict], bins: list[dict], errors, timeout: float) -> dict:
    meta: dict = {}
    for position, result in zip(batch, _send(proc, batch, errors, timeout), strict=True):
        row, reliability_rows = _outcome(position, result.get("moves"))
        played.append(row)
        add_reliability(bins, reliability_rows)
        meta = result
    return meta


def _score(project, spec, alias, games, batch_size, progress_every, read_timeout):
    played: list[dict] = []
    bins = empty_bins()
    meta: dict = {}
    total = sum(len(game["moves"]) for game in games)
    started = time.monotonic()
    done = batches = 0
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as errors:
        proc = _open_worker(project, spec, alias, errors)
        try:
            batch: list[dict] = []
            for index, game in enumerate(games):
                for position in _positions(game, index):
                    batch.append(position)
                    if len(batch) < batch_size:
                        continue
                    meta = _consume(proc, batch, played, bins, errors, read_timeout)
                    done += len(batch)
                    batches += 1
                    _progress(done, total, started, batches, progress_every, False)
                    batch = []
            if batch:
                meta = _consume(proc, batch, played, bins, errors, read_timeout)
                done += len(batch)
                batches += 1
                _progress(done, total, started, batches, progress_every, False)
                batch = []
            _close(proc, errors, CLOSE_TIMEOUT)
        except Exception:
            _kill(proc)
            raise
        finally:
            _kill(proc)
    _progress(done, total, started, batches, progress_every, True)
    return played, bins, meta


def _population(name: str, path: Path, stats: dict, rows, bins) -> dict:
    meta = POPULATIONS[name]
    return {
        "id": meta["id"],
        "source_file": str(path),
        "blitz_filter": meta["blitz_only"],
        **stats,
        "by_rating_band": rows["by_rating_band"],
        "by_ply": rows["by_ply"],
        "reliability": finish_bins(bins),
        **rows["overall"],
    }


def calibrate(
    project: Path,
    pgn: Path,
    population: str,
    *,
    sample_size: int = SAMPLE_TARGET,
    seed: int = SEED,
    plies: int = PLIES,
    batch_size: int = BATCH,
    bootstrap: int = BOOTSTRAP,
    progress_every: int = PROGRESS_EVERY,
    read_timeout: float = READ_TIMEOUT,
) -> dict:
    """Score one PGN. `population` is `elite` or `public` and is never combined."""
    if progress_every < 1:
        raise ValueError("--progress-every must be at least 1")
    if population not in POPULATIONS:
        raise ValueError("unknown maia population")
    config = _load_config(project)
    if config is None:
        raise ValueError("maia_not_configured")
    alias = config["default_alias"]
    spec = config["models"][alias]
    _verify(spec)
    blitz_only = POPULATIONS[population]["blitz_only"]
    games, stats = select_games(
        pgn, blitz_only=blitz_only, sample_size=sample_size, seed=seed, plies=plies
    )
    meta: dict = {}
    bins = empty_bins()
    played: list[dict] = []
    if games:
        played, bins, meta = _score(
            project, spec, alias, games, batch_size, progress_every, read_timeout
        )
    overall = metrics(played, seed, bootstrap)
    share = overall["zero_probability_share"] or 0
    if share > ZERO_SHARE_WARN:
        print(
            f"maia corpus: zero played-move probability on {share:.1%} of positions",
            file=sys.stderr,
        )
    splits = {
        "overall": overall,
        "by_rating_band": labeled(played, "band", BANDS, seed, bootstrap),
        "by_ply": labeled(played, "ply", range(1, plies + 1), seed, bootstrap),
    }
    caveats = list(CAVEATS)
    if population != "public":
        caveats = [item for item in caveats if item != "public_sample_is_the_2026-08-01_prefix"]
    return {
        "kind": "maia_corpus_calibration",
        "measured": overall["n_positions"] > 0,
        "reason": None if overall["n_positions"] else "no_eligible_games",
        "seed": seed,
        "plies": plies,
        "sample_target_games": sample_size,
        "bootstrap": {"repetitions": bootstrap, "unit": "game", "interval": "percentile_95"},
        "model": {
            "alias": alias,
            "weights_sha256": spec["sha256"],
            "weights_bytes": spec["bytes"],
            "code_commit": spec["code_commit"],
            "device": "cpu",
            "dtype": "float32",
            "threads": spec["threads"],
            "platform": meta.get("platform"),
            "torch_version": meta.get("torch_version"),
        },
        "population": _population(population, pgn, stats, splits, bins),
        "paper_top1_context": {"range": [0.55, 0.57], "role": "context_only", "pass_fail": False},
        "caveats": caveats,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score one Maia population from a local PGN")
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--pgn", type=Path, required=True)
    parser.add_argument("--population", choices=tuple(POPULATIONS), required=True)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, required=True)
    parser.add_argument("--sample-size", type=int, default=SAMPLE_TARGET)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--plies", type=int, default=PLIES)
    parser.add_argument("--batch-size", type=int, default=BATCH)
    parser.add_argument("--bootstrap", type=int, default=BOOTSTRAP)
    parser.add_argument("--progress-every", type=int, default=PROGRESS_EVERY)
    parser.add_argument("--read-timeout", type=float, default=READ_TIMEOUT)
    args = parser.parse_args(argv)
    try:
        report = calibrate(
            args.project.resolve(),
            args.pgn,
            args.population,
            sample_size=args.sample_size,
            seed=args.seed,
            plies=args.plies,
            batch_size=args.batch_size,
            bootstrap=args.bootstrap,
            progress_every=args.progress_every,
            read_timeout=args.read_timeout,
        )
    except (
        OSError,
        ValueError,
        json.JSONDecodeError,
        subprocess.TimeoutExpired,
        TimeoutError,
    ) as exc:
        print(f"maia corpus: {exc}", file=sys.stderr)
        return 1
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.markdown.write_text(render_markdown(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
