# Local engine checks

The analyst can report how often a move was played and how those games
scored. A local engine adds a different checked fact: the engine's score for
one position, and the centipawn gap between a candidate and the engine's
best move. That score is depth-limited evidence. It is not ground truth, and
it is not a model-accuracy result.

`engine_v1` is the frozen measurement for these tools
([ADR 0079](adr/0079-engine-tool-evaluation.md)). It scores harness and tool
behavior on 18 fixed cases. It is not a model-accuracy result, and this
repository does not claim a live provider run for it. A future live run needs
its own freeze and a finite cap. The historical live-provider prompt does not
offer the tools. Typed plans and `chesslab mcp` do, because both read the same
registry.

`scripts/build_engine_v1_cases.py` writes the questions, the structural
expectations, and the replay plans. `scripts/reference_engine_v1.py --write`
records scores from a direct UCI process when `config/engine.json` names a
binary. It does not call the checked tools. `scripts/check_engine_v1.py`
compares tool output with that reference. Score, mate, depth, selective depth,
best move, and principal variation must match exactly when the binary SHA-256
matches. Node counts are reported and do not fail the check. A missing engine,
a missing file, a config hash mismatch, or a different binary skips the engine
comparison and is not a tool failure. Opening tallies and the source-annotation
parse still run. CI does not download Stockfish. The manifest records the
binary hash and the settings used for the frozen reference.

## Tools

| Tool | What it returns |
|---|---|
| `evaluate_position` | Score for one FEN or one UCI prefix, plus engine name, binary SHA-256, depth, and nodes |
| `position_continuations` | Observed White next moves from local opening data |
| `compare_candidate_moves` | At most six candidates, each with centipawn loss versus the engine's best move and, when the local data has the position, observed games |

Pass a FEN or a move list, not both. A FEN is six fields, or the first four
(piece placement, side to move, castling, en passant). A move list is UCI
from the starting position, at most 40 plies. Depth is an integer from 1 to
16 and defaults to 12. Cohorts are `elite_reference` and `rated_public`.
Candidates are legal UCI moves.

Centipawn loss uses the score after the move, from the mover's side, minus
the same score after the engine's best move. It is not the root search
score. A negative loss means the later search liked the candidate more than
the move the root search called best. Mate stays out of the centipawn field.

`evaluate_position` and `compare_candidate_moves` put
`engine_eval_depth_limited` and `engine_not_ground_truth` on the tool
result. `execute_plan` adds those two caveats to the answer only when one of
those tools ran. `position_continuations` does not add them. Answers still
carry `observed_prefix_only`. The planner still stops at four steps.

## Engine config

The worker's environment is only `PATH` (`/bin:/usr/bin`) and
`PYTHONNOUSERSITE`. It will not see a shell export, and `/usr/games` is not
on that `PATH`. Copy the example and replace both placeholders. The path
must be absolute. The hash is SHA-256 of the file.

```sh
cp config/engine.example.json <project>/config/engine.json
sha256sum /absolute/path/to/stockfish
```

```json
{
  "version": "1",
  "binary_path": "/absolute/path/to/stockfish",
  "binary_sha256": "paste-64-hex-characters"
}
```

`<project>` is the directory you pass to `chesslab --project` or
`execute_plan`. A hash mismatch, a missing file, or a relative path fails
the call before the engine starts. The repository does not contain a binary
and does not download one. `config/engine.json` is gitignored.

The tool never accepts a UCI string. It speaks to the engine through
python-chess. Fixed settings are one thread, a 16 MB hash, and a cleared
hash before every search. If the engine advertises them, the tool also sets
`UCI_AnalyseMode`, turns strength limiting off, and turns NNUE on. `MultiPV`
and `Ponder` stay at the engine default because python-chess manages them.
There is no movetime limit. The worker is killed at 30 seconds, and on Linux
the engine process is killed with it.

A configured file whose name ends in `.py` is run with the worker's Python.
That is how the offline tests use a fake UCI script. An ELF binary is
executed directly.

## Opening continuations

`position_continuations` replaces a network opening explorer. It only reads
files named by `<project>/config/opening-visits.json`. CI does not have
those files. Pytest does not download them. `reports/opening-positions.json`
stays off the branch tip; restoring it with
`scripts/materialize_opening_positions.py` is a separate download and this
tool will not do it.

Visit shards are the full White-decision window (by default ply 6, 8, …, 20)
produced by `scripts/build_opening_positions.py`. Point `snapshot_dir` at the
published directory that contains `manifest.json` and `visits-*.parquet`.

```json
{
  "version": "1",
  "kind": "visit_shards",
  "snapshot_dir": "/absolute/path/to/published-snapshot",
  "manifest_sha256": "paste-64-hex-characters-of-manifest.json"
}
```

Each game counts once, at its earliest visit. The cohort denominator is the
manifest's training-source game count, not a personal encounter rate.
Frequency is not move quality. When the shard files total at most 8 MB, the
call also checks each artifact hash in the manifest. Above that, it checks
the manifest hash and that the files exist. The summarizer remains the full
hash check. A large snapshot can still hit the 30 second kill.

The ranking report is the compact JSON from
`scripts/summarize_opening_positions.py`. It only contains the published top
positions in each cohort's `all` view (up to twenty recurring and twenty
transposing). Other positions return
`position_not_in_published_rankings`.

```json
{
  "version": "1",
  "kind": "ranking_report",
  "report_path": "/absolute/path/to/opening-positions.json",
  "report_sha256": "paste-64-hex-characters"
}
```

Paths inside this file may be absolute or relative to the project. If the
config file is missing, the tool returns `available: false` and
`reason: opening_source_not_configured`. A bad hash is an error. Black to
move returns `not_white_to_move`, because the visit data is White's decision.

`compare_candidate_moves` still returns engine scores when the opening
config is missing. Observed games are null in that case.

## Reproducibility

Same binary, one thread, a fixed hash, and a cleared hash matched on this
machine for the positions and depths in
[ADR 0078](adr/0078-engine-grounded-checked-tools.md). The `engine_v1`
reference used that same binary and the same pinned settings at depth 12.
On this machine the direct process and the checked tools agreed, including
node counts. That agreement is not claimed for another machine, and the check
does not fail on a node-count difference. Two threads did not
match. Skipping the hash clear did not match. Hash size changed the result
between 1 MB and 16 MB. `UCI_AnalyseMode` did not change the one pair of
searches where it was toggled. No second machine was tried. An external NNUE
file would not be covered by the binary hash; the binary used for that check
had no separate net in its package.

Evidence omits the path, the clock, and nodes per second, because those are
not stable. It includes the UCI name, the binary SHA-256, requested depth,
reported depth, selective depth when the engine sends it, and nodes.

## Offline tests

`tests/fixtures/engines/fake_uci.py` is a deterministic UCI script.
`hang_uci.py` sleeps on `go` so the worker kill is observable. Tests that
need Stockfish skip when `config/engine.json` is absent. Do not point CI at
a download of the binary.
