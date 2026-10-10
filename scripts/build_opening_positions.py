"""Derive bounded White opening visits from a checked corpus; never download sources."""

import argparse
import csv
import hashlib
import json
import re
import shutil
import time
from pathlib import Path

import chess
import chess.pgn
import duckdb

from chess_analytics.common import digest, hash_json, now, read_json, write_json, writer_lock

FIELDS = [
    "source_snapshot_id",
    "provider",
    "game_id",
    "cohort",
    "opening_family",
    "source_opening",
    "eco",
    "ply",
    "full_fen",
    "position_key",
    "position_id",
    "route",
    "next_move",
    "route_has_repeat",
]


def position_key(board):
    return " ".join(board.fen(en_passant="legal").split()[:4])


class OpeningVisitor(chess.pgn.BaseVisitor):
    """Replay only the mainline prefix; skip unselected games and later SAN parsing."""

    def __init__(self, selected, plan):
        self.selected = selected
        self.plan = plan
        self.headers = {}
        self.moves = []
        self.visits = []
        self.seen = set()
        self.repeated = False

    def visit_header(self, tagname, tagvalue):
        self.headers[tagname] = tagvalue

    def end_headers(self):
        if self.selected is None:
            return chess.pgn.SKIP
        if self.headers.get("Site", "").rstrip("/").split("/")[-1] != self.selected["game_id"]:
            raise ValueError("PGN identity does not match checked corpus ordinal")
        return None

    def begin_variation(self):
        return chess.pgn.SKIP

    def begin_parse_san(self, board, san):
        return chess.pgn.SKIP if len(self.moves) >= self.plan["max_ply"] + 1 else None

    def visit_move(self, board, move):
        if self.visits and self.visits[-1]["ply"] == len(self.moves):
            self.visits[-1]["next_move"] = move.uci()
        self.moves.append(move.uci())

    def visit_board(self, board):
        ply = len(self.moves)
        if ply > self.plan["max_ply"]:
            return
        key = position_key(board)
        self.repeated |= key in self.seen
        self.seen.add(key)
        if board.turn != chess.WHITE or ply < self.plan["min_ply"]:
            return
        self.visits.append(
            {
                **self.selected,
                "ply": ply,
                "full_fen": board.fen(en_passant="legal"),
                "position_key": key,
                "position_id": hashlib.sha256(key.encode()).hexdigest()[:24],
                "route": " ".join(self.moves),
                "next_move": "",
                "route_has_repeat": self.repeated,
            }
        )

    def result(self):
        return self.visits


def replay_source(source, selected, plan, target):
    games, visits = 0, 0
    started = time.monotonic()
    with source.open(encoding="utf-8") as handle, target.open("w", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=FIELDS)
        writer.writeheader()
        ordinal = 0
        while True:
            ordinal += 1
            choice = selected.get(ordinal)
            rows = chess.pgn.read_game(
                handle, Visitor=lambda choice=choice: OpeningVisitor(choice, plan)
            )
            if rows is None:
                break
            if choice is not None:
                if len(rows) != len(range(plan["min_ply"], plan["max_ply"] + 1, 2)):
                    raise ValueError(f"Incomplete selected opening prefix at ordinal {ordinal}")
                writer.writerows(rows)
                games += 1
                visits += len(rows)
                if games % 10000 == 0:
                    print(
                        json.dumps(
                            {
                                "source": source.name,
                                "games": games,
                                "seconds": round(time.monotonic() - started, 1),
                            }
                        ),
                        flush=True,
                    )
        if games != len(selected):
            raise ValueError("Selected game count does not match replayed PGNs")
    return games, visits


def checked_inputs(corpus_root, corpus):
    sources = {s["source_file"]: s for s in corpus["sources"]}
    with duckdb.connect(
        str(corpus_root / "data/openings/published" / corpus["snapshot_id"] / "warehouse.duckdb"),
        read_only=True,
    ) as db:
        names = db.execute(
            "select distinct source_file from opening_game order by source_file"
        ).fetchall()
    for (name,) in names:
        path = (corpus_root / name).resolve()
        if not path.is_relative_to(corpus_root) or not path.is_file():
            raise ValueError("Missing or outside-corpus source")
        if digest(path) != sources[name]["source_sha256"]:
            raise ValueError("Source PGN hash does not match corpus")
    return sources, [name for (name,) in names]


def extract(corpus_root, output, plan):
    corpus_root, output = corpus_root.resolve(), output.resolve()
    if output.is_relative_to(corpus_root):
        raise ValueError("Derived output must be separate from the read-only corpus root")
    if (
        plan["learner_color"] != "white"
        or plan["min_ply"] < 2
        or plan["min_ply"] % 2
        or plan["max_ply"] % 2
        or not plan["min_ply"] <= plan["max_ply"] <= 40
    ):
        raise ValueError("Opening plan requires an even bounded White decision window")
    pointer = read_json(corpus_root / "data/opening-current.json")
    if not re.fullmatch(r"[0-9a-f]{24}", pointer["snapshot_id"]):
        raise ValueError("Invalid corpus snapshot identity")
    snapshot = corpus_root / "data/openings/published" / pointer["snapshot_id"]
    corpus = read_json(snapshot / "manifest.json")
    for name, expected in corpus["artifacts"].items():
        if digest(snapshot / name) != expected:
            raise ValueError("Opening corpus artifact hash changed")
    sources, names = checked_inputs(corpus_root, corpus)
    identity = hash_json(
        {
            "corpus": digest(snapshot / "manifest.json"),
            "plan": plan,
            "builder": digest(Path(__file__)),
        }
    )[:24]
    output.mkdir(parents=True, exist_ok=True)
    final = output / "published" / identity
    with writer_lock(output):
        if final.exists():
            for name, expected in read_json(final / "manifest.json")["artifacts"].items():
                if digest(final / name) != expected:
                    raise ValueError("Derived opening artifact hash changed")
            return final
        candidate = output / "staging" / identity
        candidate.mkdir(parents=True, exist_ok=True)
        if shutil.disk_usage(output).free < plan["minimum_free_bytes"]:
            raise ValueError("Insufficient free disk for bounded opening extraction")
        try:
            with duckdb.connect(str(snapshot / "warehouse.duckdb"), read_only=True) as index:
                for number, name in enumerate(names):
                    parquet = candidate / f"visits-{number:02}.parquet"
                    receipt = candidate / f"source-{number:02}.json"
                    if parquet.exists() and receipt.exists():
                        if digest(parquet) != read_json(receipt)["parquet_sha256"]:
                            raise ValueError("Resumed visit shard hash changed")
                        continue
                    rows = index.execute(
                        """select source_ordinal,source_snapshot_id,
                      provider,game_id,
                      source_cohort,source_opening,source_eco from opening_game where source_file=?
                      order by source_ordinal""",
                        [name],
                    ).fetchall()
                    selected = {}
                    for ordinal, source_id, provider, game_id, cohort, opening, eco in rows:
                        if ordinal in selected:
                            raise ValueError("Duplicate source ordinal in selected corpus")
                        selected[ordinal] = dict(
                            zip(
                                FIELDS[:7],
                                [
                                    source_id,
                                    provider,
                                    game_id,
                                    cohort,
                                    (opening or "Unknown").split(":", 1)[0],
                                    opening or "Unknown",
                                    eco or "Unknown",
                                ],
                                strict=True,
                            )
                        )
                    csv_path = candidate / "visits.csv"
                    games, visits = replay_source(corpus_root / name, selected, plan, csv_path)
                    with duckdb.connect() as db:
                        db.execute("set memory_limit='1GB'")
                        db.execute("set threads=2")
                        db.read_csv(
                            str(csv_path),
                            header=True,
                            columns={
                                key: "INTEGER"
                                if key == "ply"
                                else "BOOLEAN"
                                if key == "route_has_repeat"
                                else "VARCHAR"
                                for key in FIELDS
                            },
                        ).write_parquet(str(parquet), compression="zstd")
                    write_json(
                        receipt,
                        {
                            "source_file": name,
                            "source_sha256": sources[name]["source_sha256"],
                            "games": games,
                            "visits": visits,
                            "parquet_sha256": digest(parquet),
                        },
                    )
                    csv_path.unlink()
                    if (
                        sum(p.stat().st_size for p in candidate.iterdir() if p.is_file())
                        > plan["max_output_bytes"]
                    ):
                        raise ValueError("Derived output byte cap exceeded")
            manifest = {
                "kind": "checked_white_opening_visits",
                "version": "1.0.0",
                "snapshot_id": identity,
                "created_at": now(),
                "plan": plan,
                "corpus_snapshot_id": corpus["snapshot_id"],
                "corpus_manifest_sha256": digest(snapshot / "manifest.json"),
                "corpus_artifacts": corpus["artifacts"],
                "training_sources": corpus["training_sources"],
                "builder_sha256": digest(Path(__file__)),
                "games": sum(read_json(p)["games"] for p in candidate.glob("source-*.json")),
                "visits": sum(read_json(p)["visits"] for p in candidate.glob("source-*.json")),
                "artifacts": {
                    p.name: digest(p)
                    for p in candidate.iterdir()
                    if p.is_file() and p.name != "failure.json"
                },
            }
            if manifest["games"] != corpus["counts"]["training_games"]:
                raise ValueError("Extracted total differs from corpus training denominator")
            write_json(candidate / "manifest.json", manifest)
            final.parent.mkdir(parents=True, exist_ok=True)
            candidate.rename(final)
        except BaseException as error:
            write_json(
                candidate / "failure.json",
                {"at": now(), "error": f"{type(error).__name__}: {error}"},
            )
            raise
        write_json(output / "current.json", {"snapshot_id": identity})
    return final


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("work/opening-positions"))
    parser.add_argument("--plan", type=Path, default=Path("config/opening-positions.json"))
    args = parser.parse_args()
    print(extract(args.corpus_root, args.output, read_json(args.plan)), flush=True)


if __name__ == "__main__":
    main()
