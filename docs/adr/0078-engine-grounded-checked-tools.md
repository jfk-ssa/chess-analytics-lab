# 0078. Engine-grounded checked tools

- Status: proposed, accepted on merge
- Date: 2026-10-17

## Motivation

The analyst can say how often a move was played and how those games scored.
It cannot say whether the move is good. Source evaluations exist for only some
games, and a missing evaluation is not zero error. A local engine can add a
different kind of checked evidence: which common White moves in a position
lose the most evaluation against the engine's own best move, and a later
cross-check of source evaluations at sampled positions. That cross-check is
not this change. This change only makes the checked call possible.

## Decision

Register three tools on the existing allowlist, so typed plans, fixture
replay, and `chesslab mcp` see them. The historical live-provider prompt and
its recovery enum stay the original seven tools. No frozen scorer, reference,
or case file changes. No model accuracy claim is made. A later pull request
has to freeze cases, independent references, and a rubric before anyone
scores these tools. Corpus-wide Stockfish enrichment stays a follow-up.

`evaluate_position` scores one python-chess-validated FEN or UCI prefix.
`compare_candidate_moves` scores at most six legal candidates against the
engine's best move and attaches observed frequency when local opening data
can supply it. `position_continuations` reads that local data and does not
start the engine. The two engine caveats,
`engine_eval_depth_limited` and `engine_not_ground_truth`, are added only
when an answer used an engine tool. A continuations-only answer does not
claim an evaluation, so it does not get those caveats. Every answer still
gets `observed_prefix_only`, as it did before.

The worker stays credential-free: `PATH` and `PYTHONNOUSERSITE` only, a 30
second kill, and a 1 MB cap. The binary path is not an environment variable
and not a tool argument. `<project>/config/engine.json` names an absolute
path and the SHA-256 of that file. The process checks the hash before
launch. No binary is committed, and the repository does not download one.
`config/engine.example.json` is the placeholder.

Search settings that the caller cannot change: one thread, a 16 MB hash, and
a cleared hash before every search. When the engine advertises them, the
tool also sets `UCI_AnalyseMode`, turns `UCI_LimitStrength` off, and turns
`Use NNUE` on. `MultiPV` and `Ponder` are not sent. python-chess manages
those two and rejects an attempt to set them; this binary's defaults are 1
and false. Depth defaults to 12 and is rejected above 16. There is no time
limit inside the search, because a time cutoff would change the node count
from run to run. The 30 second kill remains the hard stop. The engine is
started so that a Linux parent death signal kills it when the worker is
killed. A `.py` file is re-executed with the worker interpreter; an ELF
binary is executed directly. Callers cannot pass UCI text.

Centipawn loss compares the score after the candidate with the score after
the engine's best move, both from the mover's side, at the same depth. It is
not the root search score. It can be negative when the later search prefers
a different move. Mate scores stay separate from centipawns.

Opening continuations are not an opening-explorer API. The tool reads
`<project>/config/opening-visits.json`. `visit_shards` points at a published
visit directory and pins `manifest.json` by SHA-256. The query keeps each
game's earliest visit, which is the rule in
`scripts/summarize_opening_positions.py`. Shard bytes are hashed on the call
only when those files total at most 8 MB. Larger local snapshots check the
manifest hash and that the named files exist; hashing gigabytes can miss
the 30 second kill. `scripts/summarize_opening_positions.py` remains the
full hash check. `ranking_report` reads a local
`observed_white_opening_positions` JSON file and only the cohort's `all`
view, which is the top published positions, not every position in the
window. If the config file is absent, the continuations tool returns
`opening_source_not_configured` and does not download anything. CI pytest
does not have the visit shards or `reports/opening-positions.json`. The
rankings file stays off the branch tip (ADR 0072). Restoring it is a
separate, explicit download and is not part of this tool.

Evidence records the UCI engine name, the binary SHA-256, the requested
depth, the depth the engine reported, and the node count. It does not record
the binary path, elapsed time, or nodes per second. The evidence ID function
is unchanged, so a repeated result with the same arguments keeps the same ID
when the engine output is the same.

## What was verified on one machine

Verified here on 2026-10-17, and not claimed for any other machine or CPU.
The binary was Ubuntu package `stockfish` `16-1build1` at
`/usr/games/stockfish`, 40,418,008 bytes, SHA-256
`00628bd9c9855c1b7ff93d7f8d51b413586cdc6336fe637f9a14a61531a05aca`.
UCI name `Stockfish 16`. Default `EvalFile` was `nn-5af11540bbfe.nnue`.
The package file list contains no separate net; the binary is the installed
payload. The worker's clean `PATH` is `/bin:/usr/bin`, which does not
include `/usr/games`, so an absolute path is required.

- One thread, 16 MB hash, cleared hash, depth 12, starting position, two fresh processes and two searches in one process: 35,836 nodes, white centipawns 40, principal variation `e2e4 e7e5 g1f3 g8f6 d2d4 f6e4`.
- Same settings, depth 16, position `r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq -`, three fresh processes: 114,636 nodes, white centipawns -130, first moves `e2a6 h3g2 f3g2`.
- Without clearing the hash, a depth-12 start search, then another position, then the start again: nodes 15,979 then 25,102, centipawns 40 then 27, and the variation changed.
- Two threads, depth 14, starting position, three processes: nodes 109,573, 91,039, and 162,841; centipawns 28, 37, and 36.
- Hash 1 MB versus 16 MB at depth 16 on the complex position changed the score and the continuation. Hash 128 MB versus 16 MB kept the score and the first moves but not the node count (114,634 versus 114,636).
- `UCI_AnalyseMode` on versus off at depth 18 on that position matched (494,159 nodes, centipawns -151). The option is set because Stockfish documents it as analysis without time management. This run did not show it changing a result.
- Wall time on this VM: starting position about 0.09 s at depth 12, 0.50 s at depth 16, and 1.28 s at depth 20. The complex position was faster. A slower host, or seven searches inside `compare_candidate_moves`, can still hit the 30 second kill.
- A child started with `prctl(PR_SET_PDEATHSIG, SIGKILL)` exited after its parent received SIGKILL.

Not verified: another machine, another Stockfish build, CPU feature
dispatch, tablebases (`SyzygyPath` left empty; no tablebases were present),
or an engine that loads an external net. The binary hash would not cover
that net. `UCI_AnalyseMode` is not claimed to be what made the repeats match.

## Impact

Typed plans and MCP clients can cite a local engine score and, when a
project config points at local opening data, the observed frequency beside
it. Offline CI uses a fake UCI script. A real binary is skipped when
`config/engine.json` is absent. The documentation site does not gain a page.
[ENGINE](../ENGINE.md) is the usage guide.

## Implementation steps

1. Parse FEN and UCI prefixes with python-chess. Reject raw UCI, extra arguments, and depth outside 1–16.
2. Load the engine only from `config/engine.json`, after the SHA-256 matches.
3. Force one thread, a 16 MB hash, and a cleared hash before each search. Record name, hash, depth, and nodes.
4. Kill the engine with the worker on Linux via the parent-death signal.
5. Read opening continuations from configured visit shards or a ranking report. Do not download either.
6. Add the two engine caveats in `answer_caveats` only for the two engine tools.
7. Leave the provider prompt, plan-recovery enum, scorers, and references unchanged.

## Risks

A client can treat a depth-16 score as ground truth. The caveats say not to.
The same binary on another CPU can disagree; that was not measured. A large
visit snapshot can lose the 30 second race, and above 8 MB its parquet bytes
are not re-hashed on the call. The parent-death signal is Linux-specific.
The historical live planner cannot emit these tools until a new prompt and
freeze exist. Acceptance here is the offline fake engine, plus one local
Stockfish 16 repeat on this machine, not a scored model evaluation.
