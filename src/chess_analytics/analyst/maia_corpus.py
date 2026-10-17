"""One-population played-move scores from a PGN. One Maia worker, many positions.

Elite and public are separate runs. This module has no pooled score.
Torch stays in the worker. A fake weights file never imports it.
"""

import argparse
import json
import math
import random
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import chess
import chess.pgn

from chess_analytics.analyst.maia import _child_env, _load_config, _verify
from chess_analytics.analyst.maia_pins import PINS
from chess_analytics.analyst.maia_trust import lichess_blitz, reliability, score_played
from chess_analytics.analyst.tool_catalog import MAIA_MAX_RATING, MAIA_MIN_RATING

SEED = 20251017
SAMPLE_TARGET = 20_000
PLIES = 12
HISTORY = 8
BATCH = 64
BOOTSTRAP = 400
BANDS = ("below-1000", "1000–1599", "1600–1999", "2000–2299", "2300+")
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


def _clamp(rating: int) -> int:
    return min(MAIA_MAX_RATING, max(MAIA_MIN_RATING, rating))


def _visitor(limit: int):
    class Prefix(chess.pgn.BaseVisitor):
        def __init__(self) -> None:
            self.headers: dict[str, str] = {}
            self.moves: list[str] = []
            self.bad = False

        def visit_header(self, tagname: str, tagvalue: str) -> None:
            self.headers[tagname] = tagvalue

        def visit_move(self, board: chess.Board, move: chess.Move):
            if len(self.moves) >= limit:
                return chess.pgn.SKIP
            self.moves.append(move.uci())
            return None

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
        self_rating = _clamp(game["white"] if white_turn else game["black"])
        opp_rating = _clamp(game["black"] if white_turn else game["white"])
        yield {
            "game": index,
            "ply": ply,
            "band": _band(self_rating),
            "played": uci,
            "boards": [item.fen() for item in series[-HISTORY:]],
            "rating_self": self_rating,
            "rating_opp": opp_rating,
            "legal": {move.uci() for move in board.legal_moves},
        }
        board.push(chess.Move.from_uci(uci))
        series.append(board.copy())


def _mass(raw, legal: set[str]) -> dict[str, float]:
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


def _outcome(position: dict, raw) -> tuple[dict | None, list[dict]]:
    mass = _mass(raw, position["legal"])
    played = position["played"]
    rows = [
        {"predicted": mass.get(uci, 0.0), "observed": int(uci == played), "count": 1}
        for uci in position["legal"]
    ]
    probability = mass.get(played, 0.0)
    if probability <= 0:
        return None, rows
    rank = 1 + sum(prob > probability for prob in mass.values())
    return {
        "game": position["game"],
        "ply": position["ply"],
        "band": position["band"],
        "probability": probability,
        "rank": rank,
    }, rows


def _empty_bins() -> list[dict]:
    return [
        {"low": index / 10, "high": (index + 1) / 10, "count": 0, "predicted": 0.0, "observed": 0.0}
        for index in range(10)
    ]


def _add_reliability(bins: list[dict], rows: list[dict]) -> None:
    if not rows:
        return
    for bucket in reliability(rows):
        slot = bins[int(bucket["low"] * 10)]
        count = int(bucket["count"])
        slot["count"] += count
        if count and bucket["mean_predicted"] is not None:
            slot["predicted"] += float(bucket["mean_predicted"]) * count
            slot["observed"] += float(bucket["mean_observed"]) * count


def _finish_bins(bins: list[dict]) -> list[dict]:
    finished = []
    for slot in bins:
        count = slot["count"]
        finished.append(
            {
                "low": slot["low"],
                "high": slot["high"],
                "count": count,
                "mean_predicted": None if count == 0 else slot["predicted"] / count,
                "mean_observed": None if count == 0 else slot["observed"] / count,
            }
        )
    return finished


def _interval(values: list[float]) -> list[float] | None:
    """Same percentile ends as the M4 cluster bootstrap."""
    if not values:
        return None
    ordered = sorted(values)
    last = len(ordered) - 1
    return [ordered[int(0.025 * last)], ordered[int(0.975 * last)]]


def _bootstrap(rows: list[dict], seed: int, reps: int) -> dict:
    grouped: dict[int, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row["game"], []).append(row)
    keys = list(grouped)
    if not keys:
        return {"log_loss": None, "top1": None, "top3": None}
    rng = random.Random(seed)
    samples = {"log_loss": [], "top1": [], "top3": []}
    width = len(keys)
    for _ in range(reps):
        drawn = [item for _draw in range(width) for item in grouped[keys[rng.randrange(width)]]]
        scored = score_played(drawn)
        for name in samples:
            samples[name].append(scored[name])
    return {name: _interval(values) for name, values in samples.items()}


def _metrics(rows: list[dict], seed: int, reps: int) -> dict:
    scored = score_played(rows)
    interval = _bootstrap(rows, seed, reps)
    games = len({row["game"] for row in rows})
    return {
        "n_games": games,
        "n_positions": scored["n"],
        "log_loss": scored["log_loss"],
        "log_loss_interval": interval["log_loss"],
        "top1": scored["top1"],
        "top1_interval": interval["top1"],
        "top3": scored["top3"],
        "top3_interval": interval["top3"],
    }


def _labeled(rows: list[dict], key: str, labels, seed: int, reps: int) -> list[dict]:
    blocks = []
    for label in labels:
        block = _metrics([row for row in rows if row[key] == label], seed, reps)
        block[key] = label
        blocks.append(block)
    return blocks


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
    proc.stdin.write(json.dumps(header) + "\n")
    proc.stdin.flush()
    return proc


def _send(proc, positions: list[dict]) -> list[dict]:
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
    except BrokenPipeError as exc:
        line = proc.stdout.readline() if proc.stdout is not None else ""
        raise ValueError(line.strip() or "maia worker closed") from exc
    line = proc.stdout.readline()
    if not line:
        raise ValueError("maia worker closed")
    message = json.loads(line)
    if not message.get("ok"):
        raise ValueError(str(message.get("reason") or "maia failed"))
    results = message["results"]
    if len(results) != len(positions):
        raise ValueError("maia batch length mismatch")
    return results


def _close(proc) -> None:
    try:
        if proc.stdin is not None and proc.poll() is None:
            proc.stdin.write(json.dumps({"done": True}) + "\n")
            proc.stdin.flush()
            proc.stdin.close()
        proc.wait(timeout=30)
    finally:
        if proc.poll() is None:
            proc.kill()


def _consume(proc, batch: list[dict], played: list[dict], bins: list[dict]) -> tuple[int, dict]:
    excluded = 0
    meta: dict = {}
    for position, result in zip(batch, _send(proc, batch), strict=True):
        row, reliability_rows = _outcome(position, result.get("moves"))
        if row is None:
            excluded += 1
        else:
            played.append(row)
        _add_reliability(bins, reliability_rows)
        meta = result
    return excluded, meta


def _score(project: Path, spec: dict, alias: str, games: list[dict], batch_size: int):
    played: list[dict] = []
    bins = _empty_bins()
    excluded = 0
    meta: dict = {}
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as errors:
        proc = _open_worker(project, spec, alias, errors)
        try:
            batch: list[dict] = []
            for index, game in enumerate(games):
                for position in _positions(game, index):
                    batch.append(position)
                    if len(batch) < batch_size:
                        continue
                    count, meta = _consume(proc, batch, played, bins)
                    excluded += count
                    batch = []
            if batch:
                count, meta = _consume(proc, batch, played, bins)
                excluded += count
        finally:
            _close(proc)
            errors.seek(0)
            detail = errors.read()
    return played, bins, excluded, meta, detail


def _population(name: str, path: Path, stats: dict, rows, bins, excluded) -> dict:
    meta = POPULATIONS[name]
    body = {
        "id": meta["id"],
        "source_file": str(path),
        "blitz_filter": meta["blitz_only"],
        **stats,
        "excluded_zero_probability": excluded,
        "by_rating_band": rows["by_rating_band"],
        "by_ply": rows["by_ply"],
        "reliability": _finish_bins(bins),
        **{key: rows["overall"][key] for key in rows["overall"]},
    }
    return body


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
) -> dict:
    """Score one PGN. `population` is `elite` or `public` and is never combined."""
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
    excluded = 0
    bins = _empty_bins()
    played: list[dict] = []
    if games:
        played, bins, excluded, meta, detail = _score(project, spec, alias, games, batch_size)
        if not played and excluded == 0 and detail:
            raise ValueError(detail.strip() or "maia failed")
    overall = _metrics(played, seed, bootstrap)
    splits = {
        "overall": overall,
        "by_rating_band": _labeled(played, "band", BANDS, seed, bootstrap),
        "by_ply": _labeled(played, "ply", range(1, plies + 1), seed, bootstrap),
    }
    measured = overall["n_positions"] > 0
    if measured:
        reason = None
    elif not games:
        reason = "no_eligible_games"
    else:
        reason = "played_probability_zero"
    return {
        "kind": "maia_corpus_calibration",
        "measured": measured,
        "reason": reason,
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
        "population": _population(population, pgn, stats, splits, bins, excluded),
        "paper_top1_context": {"range": [0.55, 0.57], "role": "context_only", "pass_fail": False},
        "caveats": list(CAVEATS),
    }


def _fmt(value) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "[" + ", ".join(_fmt(item) for item in value) + "]"
    return f"{float(value):.4f}"


def _table(headers: list[str], rows: list[list[str]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    rule = "|" + "|".join("---" for _ in headers) + "|"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([head, rule, *body])


def _cells(row: dict, label) -> list[str]:
    return [
        str(label),
        str(row["n_games"]),
        str(row["n_positions"]),
        _fmt(row["log_loss"]),
        _fmt(row["top1"]),
        _fmt(row["top3"]),
    ]


def render_markdown(report: dict) -> str:
    """Short one-population report. It does not mention a second file's scores."""
    pop = report["population"]
    elite = ""
    if not pop["blitz_filter"]:
        elite = "Elite headline is the curated month. The blitz counts are a labeled subset.\n"
    positions = str(pop["n_positions"])
    scores = _table(
        ["Score", "Estimate", "95% interval", "Positions"],
        [
            ["log-loss", _fmt(pop["log_loss"]), _fmt(pop["log_loss_interval"]), positions],
            ["top-1", _fmt(pop["top1"]), _fmt(pop["top1_interval"]), positions],
            ["top-3", _fmt(pop["top3"]), _fmt(pop["top3_interval"]), positions],
        ],
    )
    bands = _table(
        ["Band", "Games", "Positions", "Log-loss", "Top-1", "Top-3"],
        [_cells(row, row["band"]) for row in pop["by_rating_band"]],
    )
    plies = _table(
        ["Ply", "Games", "Positions", "Log-loss", "Top-1", "Top-3"],
        [_cells(row, row["ply"]) for row in pop["by_ply"]],
    )
    state = "on" if pop["blitz_filter"] else "off"
    met = str(pop["sample_target_met"]).lower()
    return (
        f"# Maia corpus calibration — {pop['id']}\n\n"
        "One population. This file is not pooled with any other population.\n\n"
        f"{elite}"
        f"- Source: `{pop['source_file']}`\n"
        f"- Blitz filter: {state}\n"
        f"- Sample: {pop['sample_games']} games (target {report['sample_target_games']})\n"
        f"- Sample target met: {met}\n"
        f"- Scanned games passing `lichess_blitz`: {pop['games_passing_blitz']}\n"
        f"- Sampled games passing `lichess_blitz`: {pop['sample_blitz_games']}\n"
        f"- Positions: {positions}\n"
        f"- Excluded, played probability zero: {pop['excluded_zero_probability']}\n\n"
        f"{scores}\n\n## By rating band\n\n{bands}\n\n## By ply\n\n{plies}\n\n"
        "The 55–57% top-1 range is context only. It is not a pass/fail bar.\n"
        "Intervals resample games and keep every scored ply of a drawn game.\n"
    )


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
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"maia corpus: {exc}", file=sys.stderr)
        return 1
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.markdown.write_text(render_markdown(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
