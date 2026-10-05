import json
import shutil
from pathlib import Path

import duckdb

from analyst_m5.evaluation import _subset
from analyst_m5.provider import validate_personal_config
from analytics_m3.moves import selected, write_sampled_moves
from analytics_m3.publish import build_analytical
from analytics_m3.source import extracted_path
from chess_analytics.cli import fixture_plan
from chess_analytics.common import digest, read_json, write_json
from chess_analytics.ingest.pipeline import ingest
from chess_analytics.warehouse.snapshots import build

project = Path.cwd()
work = project / "work/repository-review/probe-data"
work.mkdir(exist_ok=True)
out = {}
config = read_json(project / "config/personal_provider.example.json")
config.update(
    enabled=True,
    personal_account_acknowledged=True,
    model="review-model",
    max_run_usd=0.1,
    input_usd_per_million=1.0,
    output_usd_per_million=1.0,
)
out["nonfinite_accepted"] = {}
for key in ("max_run_usd", "input_usd_per_million", "output_usd_per_million"):
    for label, value in [("nan", float("nan")), ("infinity", float("inf"))]:
        try:
            validate_personal_config({**config, key: value})
            out["nonfinite_accepted"][key + ":" + label] = True
        except ValueError:
            out["nonfinite_accepted"][key + ":" + label] = False
out["scorer_boolean_accepted_as_number"] = {
    "integer": _subset(1, True),
    "float": _subset(1.0, True),
}
game_id = next(f"{i:08d}" for i in range(1000) if selected(f"{i:08d}"))
raw = f"""[Event "Rated Blitz synthetic review"]
[Site "https://lichess.org/{game_id}"]
[White "ReviewWhite"]
[Black "ReviewBlack"]
[Result "1-0"]
[TimeControl "60+0"]
[Opening "Review Opening"]

1. e4 {{[%clk 0:00:59] [%eval 0.10]}} e5 {{[%clk 0:00:59] [%eval 0.10]}} \
2. Nf3 {{[%clk 0:00:58] [%eval 0.10]}} Nc6 1-0

"""
plan = fixture_plan(project)
source = work / "duplicates.pgn"
source.write_text(raw * 2)
root = work / "duplicates"
stage = ingest(project, root, "analytical", source, plan)
snapshot = build(project, root, "analytical")
counts = write_sampled_moves(source, snapshot, work / "moves.jsonl", plan, root)
out["duplicate"] = {
    "ingest_counts": read_json(stage / "manifest.json")["counts"],
    "move_counts": counts,
}
# A real isolated publication with two different valid sources sharing game ID/ply count.
p = work / "project"
p.mkdir(exist_ok=True)
for name in ("src", "contracts", "analytics_m3"):
    shutil.copytree(project / name, p / name, dirs_exist_ok=True)
shutil.copy2(project / "uv.lock", p / "uv.lock")
write_json(p / "config/datasets.json", {"analytical": plan})
r = p / "data"
a = work / "source-a.pgn"
a.write_text(raw)
ingest(p, r, "analytical", a, plan)
build(p, r, "analytical")
b = extracted_path(r, plan)
b.parent.mkdir(parents=True, exist_ok=True)
b.write_text(raw.replace("[%eval 0.10]", "[%eval 9.90]"))
write_json(
    b.with_suffix(".receipt.json"),
    {
        "source_sha256": digest(b),
        "partial_archive": True,
        "compressed_prefix_sha256": "review-synthetic",
    },
)
try:
    result = build_analytical(p, r)
    with duckdb.connect(str(result / "warehouse.duckdb"), read_only=True) as con:
        values = con.execute(
            "select distinct eval_after_cp_white from fact_move "
            "where eval_after_cp_white is not null"
        ).fetchall()
    out["mismatched_source_publication"] = {
        "published": True,
        "source_a_sha256": digest(a),
        "source_b_sha256": digest(b),
        "manifest_source_sha256": read_json(result / "manifest.json")["source_sha256"],
        "stored_evaluations_cp": [v[0] for v in values],
    }
except Exception as exc:
    out["mismatched_source_publication"] = {"published": False, "exception": str(exc)}
write_json(work.parent / "probes.json", out)
print(json.dumps(out, indent=2))
