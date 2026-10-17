# 0079. Engine tool evaluation

- Status: proposed, accepted on merge
- Date: 2026-10-17

## Motivation

ADR 0078 added `evaluate_position`, `position_continuations`, and
`compare_candidate_moves` without an accuracy claim. The tools can be called.
That does not say whether a recorded plan uses them inside the limits that
were chosen: depth, legal positions, no raw UCI, no causal or best-move-is-truth
claim, a configured engine, local opening data, and at most six candidates.

Saying anything about that use needs a frozen case set, references computed
off the checked-tool path, a scorer that does not touch the historical
rubrics, and boundary cases for those limits. This record adds that
measurement for offline fixture and replay use. It does not score a model.

## Decision

Freeze eighteen `engine_v1` cases, one replay plan each, and one reference
file. Nine cases are answerable and nine are boundary cases. The size is one
case for each tool contract and one for each named limit, plus a second
continuation cohort so the cohort filter is visible, plus one source-evaluation
cross-check. It is not a sample of positions and it has no dev/test split.
The split field is `engine_v1`.

Answerable cases call `evaluate_position` on the start position, after
1. e4 e5, on the kiwipete position at depth 12, and on a mate in one. They
call `position_continuations` for `elite_reference` and `rated_public`. They
call `compare_candidate_moves` for e4 and d4 with and without opening data.
One more `evaluate_position` case sits on a portfolio-fixture position that
has a source evaluation. Boundary cases cover depth 17, a malformed FEN, an
illegal prefix, a raw UCI argument, a causal claim, a best-move-is-truth
claim, a missing engine, missing opening data, and seven candidates.

Stockfish numbers are not stored in the case file. The case file holds the
engine-independent fields a fake UCI engine can satisfy. The reference file
holds the scores. `scripts/check_engine_v1.py` copies those scores into the
expectation only when the configured binary's SHA-256 matches the reference.

The reference script uses python-chess and a direct UCI process. It does not
import the checked tools, the opening tool, or the scorer. It searches every
engine case twice, in two fresh sessions, and writes only when score, mate,
depth, selective depth, best move, and principal variation match. Node counts
are stored. They are not a pass/fail gate. ADR 0078 already saw a two-node
change from hash size, and other CPUs were not measured. On the machine that
wrote this reference the node deltas were zero, including between the direct
process and the checked tools. That match is not claimed for another machine.
A missing config, a missing file, a config hash mismatch, or a different
binary skips the engine comparison and is not scored as a tool failure.
Opening tallies and the source-annotation parse still run.

`engine-1.0` lives in `engine_eval.py`. `evaluation.py` is unchanged, so the
historical preflight hash of that file stays put. The rubric rejects booleans
and non-finite values on numeric keys in the answer, as `portfolio-1.0` does,
and it also rejects those values when they are stored in the reference.
Lists are compared in order, item by item, and extra dict keys are allowed,
because an engine result carries fields the case file does not pin. Evidence
IDs are recomputed. `dataset_id` is not pinned: analytical snapshot ids move
when the implementation hash moves. The answer's dataset id must equal the
result's, and the evidence binding must match. `evaluate_position` and
`compare_candidate_moves` require `engine_eval_depth_limited` and
`engine_not_ground_truth`. Continuation answers forbid those two. Every
answered or refused plan still requires `observed_prefix_only`.

Tool failures are `expected_status: tool_rejected`. `execute_plan` raises on
a bad call, so the replay helper catches that and returns an empty answer
with the error text. Causal and best-move claims are plan-level
`unsupported` with no tool call. Typed plans go through
`CheckedTools.execute`, which checks argument names and then the handler.
Depth 17 raises `depth is outside the checked limit`. Seven candidates raise
`invalid candidate moves`. An extra `uci` key raises
`unsupported tool or arguments` at the key gate. MCP checks the published
JSON Schema first and reports `invalid tool arguments` for the same
out-of-range inputs. That gate already has its own tests and is not a second
copy of this case set.

Published visit shards and `reports/opening-positions.json` are not in this
checkout. The opening cases use five synthetic rows. The cohort denominator
is the training-source count in that fixture: 4 elite games and 7 rated
games. Three elite visits remain after the earliest-visit rule, two of them
`d2d4`, so the elite frequency is 0.75 and the `d4` share is 2/3. The rated
row is one `e2e4` visit, frequency 1/7. These are not corpus frequencies.
Parquet bytes are built when a check runs and are not committed.

Source evaluations are re-read from `tests/fixtures/portfolio_annotated.pgn`
with python-chess, not from the corpus move extractor. The ply-3 annotation
in game 0 is white centipawns -250. The engine score on that position in this
reference is 34, so the recorded gap is 284. Equality is not required and the
gap is not a quality score. A missing annotation stays null, and a mate
annotation stays a mate with null centipawns.

Replay plans are kind `fixture_plan_no_model_response` and live under
`evals/replay_plans/engine_v1/` so they do not mix with M5 ids. The harness
can run them with no model and no key. No live provider run is made or
claimed. A future live run needs its own freeze and a finite cap.

## What was verified on one machine

Verified here on 2026-10-17 with the same Ubuntu `stockfish` `16-1build1`
binary recorded in ADR 0078: `/usr/games/stockfish`, 40,418,008 bytes,
SHA-256 `00628bd9c9855c1b7ff93d7f8d51b413586cdc6336fe637f9a14a61531a05aca`,
UCI name `Stockfish 16`. Settings: one thread, 16 MB hash, hash cleared
before each search, depth 12, `UCI_AnalyseMode` on, `UCI_LimitStrength` off,
`Use NNUE` on, `MultiPV` and `Ponder` not sent, no movetime. The reference
process is python-chess `SimpleEngine` started directly. It does not use the
tool's parent-death wrapper. The checked-tool comparison on this machine
still matched.

- Start, depth 12: white centipawns 40, 35,836 nodes, selective depth 16, best `e2e4`, first six plies `e2e4 e7e5 g1f3 g8f6 d2d4 f6e4`. That agrees with the depth-12 line in ADR 0078.
- After 1. e4 e5, Black to move: white centipawns 43, 27,410 nodes, best `g1f3`.
- Kiwipete, depth 12, not the depth-16 experiment in ADR 0078: white centipawns -122, 28,166 nodes, best `e2a6`. The depth-16 result (centipawns -130, 114,636 nodes) was not rerun here.
- Mate in one (`7k/8/5KQ1/8/8/8/8/8 w - - 0 1`): mate 1, centipawns null, 281 nodes, best `g6g7`.
- Portfolio fixture after 1. e4 c5 2. Nf3: engine white centipawns 34, 28,016 nodes, best `d7d6`. Source annotation -250. Gap 284. Not a claim that either number is the truth.
- Compare e4 and d4 from the start: root white centipawns 40. After e4, 34 and loss 0. After d4, 32 and loss 2. The loss is the gap between the two after-move scores, not 40 minus 32.

Two independent reference sessions agreed on every exact field, and every
node delta in that pair was 0. `scripts/check_engine_v1.py` then agreed with
the reference on every exact field, and every tool-versus-reference node
delta was 0. Content hashes are in `evals/cases/engine_v1_manifest.json`.
Another machine, another build, or another CPU was not tried.

The fake UCI script was checked separately. It agrees with a direct
`SimpleEngine` on the same script, and the replay harness passes the
structural cases and the boundary rejections without Stockfish. CI uses that
path. It does not download an engine or an opening shard.

## Impact

Offline tests can tell a broken engine-tool plan from a passing one without a
model key and without Stockfish. A developer with the pinned binary can
regenerate or check the numeric reference. Historical case files, references,
scorers, reports, and the live-provider prompt stay as they were.
`portfolio-1.0` stays the rubric for portfolio fixtures. The documentation
site does not gain a page.

## Implementation steps

1. Write the eighteen questions, structural expectations, synthetic visit rows, and replay plans.
2. Compute references with a direct UCI process and an independent opening SQL read.
3. Score with `engine-1.0` in a new module. Leave `evaluation.py` byte-for-byte.
4. Compare tool output with the reference only when the binary hash matches. Report node deltas without gating them.
5. Test the scorer, the manifest, the replay schema, and boundary rejections with the fake engine. Skip real-engine comparison when no engine is configured.

## Risks

A reader can treat the eighteen cases as a model score or as corpus opening
rates. The manifest, the rubric name, and the status summary say they are
not. The same binary on another CPU can disagree on nodes and, unmeasured
here, on the score. The check does not fail a node difference, and a
different binary is a skip. The source gap of 284 centipawns can be misread
as an accuracy number. It is the difference of two non-equivalent annotations
on one fixture position. The reference process does not use the parent-death
wrapper, so a wrapper-only bug would not show up in the reference itself; the
tool comparison on this machine is what covers that path for this binary.
The replay locks the typed-plan errors. MCP's earlier schema rejection uses
a different message and is not re-scored here.
