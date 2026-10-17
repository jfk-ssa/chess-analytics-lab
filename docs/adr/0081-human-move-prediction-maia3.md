# 0081. Human-move prediction with Maia-3

- Status: proposed, accepted on merge
- Date: 2026-10-17

## Motivation

The analyst can report engine centipawn loss, which says what a search likes,
and observed corpus frequency, which says what people played in the local
files. It cannot estimate what a player of a given rating would play in a
position the corpus barely contains. That estimate is the missing input for
"practically hard" positions and for the White 1.d4 repertoire in
[TRANSPOSITION_LEARNING](../TRANSPOSITION_LEARNING.md), where rare nodes have
too few games for a frequency. This change adds the checked call. It does not
calibrate the model and it does not build the repertoire view.

## Decision

Register `predict_human_moves` on the existing allowlist, so typed plans and
`chesslab mcp` see it. The historical live-provider prompt and its recovery
enum stay the original seven tools. No frozen M5–M7 scorer, reference, or
case file changes. No accuracy claim is made. A later pull request, called
PR 5 in the plan below, has to freeze a tolerance-based `maia_v1` set before
anyone scores this tool. That set uses Lichess months from August 2025
onward, because Maia-3 trained on blitz games from January 2023 through July
2025. The 1.d4 view comes after that, and it uses corpus frequencies where
counts are decent and Maia only for sparse nodes.

The model is Maia-3, commit `1e13597c42d4858b7cfd7cfdae01e297263364b2` of
https://github.com/CSSLab/maia3. Config aliases are `5M`, `23M` (default),
and `79M`, mapped to the published Hugging Face revisions and file hashes in
`maia_pins.py`. There is no PyPI release and no supported Python API. The
worker calls `parse_args`, `tokenize_board`, `get_historical_tokens`,
`get_legal_moves_mask`, `get_all_possible_moves`, and `mirror_move`, then
checks that `load_state_dict` reports no missing or unexpected keys. Those
functions are internals. The commit pin is what makes that acceptable until
an official API exists. The adapter is the only place that knows them.

Inputs are a FEN or a UCI prefix from the start, never both, and integer
ratings for the player and the opponent. The schema rejects ratings outside
0–5000 before a worker starts. The handler also clamps to that range, which
is Maia-3's own rule, so a typed call that skips the schema still stays in
range. With `moves`, the worker sees the current position plus up to seven
earlier ones. A FEN has no history. The model repeats the earliest position
when the history is short. `top_k` defaults to 10 and stops at 20. `min_prob`
defaults to 0. Output probabilities are rounded to 4 decimal places. Illegal
moves are dropped and the legal remainder is renormalized. Win/draw/loss is
labelled `human-outcome prediction, not engine evaluation`. Every result
carries `model_estimate_not_observation` and `blitz_trained_rating_scale`.
The rating scale string is fixed to `lichess-blitz`. Engine centipawn loss is
not merged into this result.

`<project>/config/maia.json` names an absolute weights path, the SHA-256 and
byte size, and the pinned repository, revision, and code commit. The process
checks the file hash before it starts the worker. A missing config file
returns `maia_not_configured` and does not download anything. A hash or size
mismatch raises. `config/maia.example.json` is the placeholder. The weights
are not committed.

`scripts/fetch_maia_weights.py` is the way to obtain a checkpoint. It is not
imported by the tool, and it does not run during tests or CI except through
tests that pass a fake HTTP body. It downloads one pinned Hugging Face
revision, hashes a partial file, and moves that file into `data/models/`
only when the SHA-256 and byte size match the pin. A mismatch deletes the
partial file. The destination must be gitignored (`/data/*` already ignores
`data/models/`). The script prints the config object and the install line
`uv sync --locked --extra maia`. It does not vendor the Maia source. The
code commit is installed by that extra, which is a git URL pinned in
`uv.lock`.

Torch and Maia-3 are that optional extra. The default install, CI, and the
offline suite do not import torch. Linux resolves `torch==2.14.1+cpu` from
the PyTorch CPU index. The PyPI Linux wheel depends on CUDA libraries, and
this tool never uses them. macOS resolves the PyPI arm64 wheel
`torch-2.14.1-cp312-cp312-macosx_14_0_arm64` (127,307,099 bytes), which is
the wheel the lock records for that platform. The import sits inside
`maia_worker.py`, which the parent starts as a subprocess with a clean
environment, `HF_HUB_OFFLINE=1`, float32, CPU, and the configured thread
count (1–8). One position is scored at a time. bf16 and fp16 are rejected
because they were measured to change the top move. If torch or Maia-3 is
missing, the tool returns `maia_unavailable`. The parent dies with the
worker on Linux via the same parent-death signal the engine tools use. The
outer kill remains 30 seconds and 1 MB.

Evidence IDs for every other tool hash the result, floats included. Maia
probabilities are not bit-stable: thread count and batch size moved them by
about 1e-6 on the machine that measured them, and rounding to 6 decimals
still changed hashes at boundaries. This tool therefore hashes the dataset,
the arguments, the position, the ratings actually sent, `top_k`, `min_prob`,
and the pinned identity (weights SHA-256, Hugging Face revision, code
commit, torch version, platform, dtype, thread count, rating scale). The
probability and win/draw/loss floats are not in the hash. `execute_plan` and
the MCP server both call `_evidence_id`, which branches on the tool name, so
they agree. A 1e-6 change in a stored probability does not change the ID.
A thread-count change does.

## Licence

Maia-3 code is AGPL-3.0. The weight files have no licence file. The model
card says "AGPLv3" in prose only, and the Hugging Face licence metadata is
empty. Issues 8, 11, and 12 on the Maia-3 repository, asking about
redistribution, were open and unanswered on 2026-10-17. John approved local
personal use that does not distribute or serve the weights. The repository
pins identifiers and hashes only. The tool must not be put behind a public
service, and the weights must not be redistributed, until that grant is
settled. Revisit this record if either of those changes.

## Alternatives rejected

Maia-2 has a pip package, but the released weights were not trained on the
early plies, so it is the wrong model for opening work. Maia-1 via lc0 takes
one rating band and does not give a full distribution from the call this lab
needs. Maia-3's own UCI engine prints a ranking and a value-head WDL, not
move probabilities, and its default temperature samples. Allie 2.0 is
clock-aware and MIT, but it is unreviewed, about 11 GB, and requires
`trust_remote_code`. None of those is the checked tool.

The weights could have been committed or vendored. They were not, because
the weights licence is unresolved. A download that is not pinned would not
be reproducible. The pinned manual script is the middle of those options.

## Impact

Typed plans and MCP clients can place a labelled move distribution next to
an engine score and a corpus frequency. Offline CI uses a fake distribution
file. A real checkpoint is skipped when `config/maia.json` is absent. The
documentation site does not gain a page. [MAIA](../MAIA.md) is the usage
guide. ADR 0080 records the worked MCP example and stays in the index
ahead of this record.

## Implementation steps

1. Parse a FEN or a UCI prefix with the existing position helper. Clamp ratings to 0–5000. Reject depth-style surprises: extra keys, `top_k` above 20, and a non-float32 config.
2. Load `config/maia.json`. Return `maia_not_configured` when the file is absent. Refuse a hash or size mismatch before the worker starts.
3. Run the model in a credential-free subprocess. Import torch only there. Force CPU, float32, one position, and the configured thread count.
4. Mask to legal moves, round probabilities to 4 decimals, and attach the two caveats and the provenance block.
5. Hash inputs and the pinned identity, not the probability floats. Use that hash from both `execute_plan` and MCP.
6. Register the tool. Leave the provider prompt and the historical enum unchanged.
7. Add the pinned download script and an ignored destination. Do not commit weights or Maia source.

## Risks

A client can read a model probability as a fact about people. The caveats say
not to. The weights licence is unresolved; serving the tool publicly would
reopen it. The Maia-3 functions this worker calls can change without a
release tag. The pin is the mitigation, and it will go stale. Floats differ
across machines. Evidence IDs will not match across machines, and this
record does not claim they will. Apple Silicon speed and numerics were not
measured. Opening accuracy is not in the Maia-3 paper. A large 79M load can
still lose the 30-second race on a slow host. The parent-death signal is
Linux-specific. The historical live planner cannot emit this tool until a
new prompt and freeze exist.

## Follow-up

PR 5, separately: calibrate 23M (and, if useful, 5M and 79M) against the
Lichess corpus on months from August 2025 onward, by ply and rating, with
log-loss and top-k agreement. Freeze a tolerance-based `maia_v1` set from
that measurement. Only then add the 1.d4 repertoire view that prefers corpus
frequencies and uses Maia where the counts are sparse. Do not treat this
pull request as that measurement.
