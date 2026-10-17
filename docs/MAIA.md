# Human-move estimates

The lab can already say what an engine thinks is best, and how often a move
showed up in a local corpus. `predict_human_moves` adds a third, different
fact: a probability distribution over legal moves for a player of a given
rating facing an opponent of a given rating. The number is a model estimate.
It is not a count of games, and it is not an engine evaluation.

The model is Maia-3 (arXiv 2605.19091), pinned to commit
`1e13597c42d4858b7cfd7cfdae01e297263364b2` of
https://github.com/CSSLab/maia3. Aliases are `5M`, `23M` (the default), and
`79M`. Maia-2 is not used here. Its released weights were not trained on the
opening plies. There is no PyPI package. The tool calls Maia-3 internals
through a small adapter so an official API can replace them later. Those
internals are not a stable API, which is why the commit is pinned.

The historical live-provider prompt does not offer this tool. Typed plans and
`chesslab mcp` do, because both read the same registry. `maia_v1` compares
four displayed probabilities with tolerance 1e-4. Holdout periods and game
counts are the opening-corpus training index in
[opening-corpus.json](../reports/opening-corpus.json). No played-move log-loss
has been computed from those games. See
[ADR 0082](adr/0082-maia-calibration-and-d4-repertoire.md).

## Tool

| Argument | Meaning |
|---|---|
| `fen` or `moves` | One position. A FEN, or UCI moves from the start. Not both. |
| `rating_self`, `rating_opp` | Integers. The published schema allows 0–5000. The handler clamps to that range, which is what Maia-3 does. |
| `model` | Optional alias. Default is the config's `default_alias`, intended to be `23M`. |
| `top_k` | Optional. Default 10, maximum 20. |
| `min_prob` | Optional number from 0 to 1. Default 0. Compared after rounding. |

`moves` keeps up to seven earlier positions plus the current one. A FEN alone
has no earlier position. The model repeats the current position to fill the
rest, which is how it was trained to handle a short history.

Each returned move has UCI, SAN, and a probability rounded to 4 decimal
places (Python's round-half-even). Illegal moves are dropped and the legal
remainder is renormalized. The win/draw/loss block is the model's value head
for the side to move, labelled `human-outcome prediction, not engine evaluation`.
It is not a centipawn score. Engine centipawn loss stays on the engine tools.

Every result includes `model_estimate_not_observation` and
`blitz_trained_rating_scale`. The checkpoints were trained on Lichess blitz
from January 2023 through July 2025. Ratings from another site or time
control are out of distribution. There is no clock input. A missing config
returns `reason: maia_not_configured`. A missing torch or Maia-3 install
returns `reason: maia_unavailable`. A hash mismatch is an error and does not
return a distribution.

## Config

Copy the example and replace the placeholder path, byte size, and SHA-256.
The path must be absolute. `config/maia.json` is gitignored.

```sh
cp config/maia.example.json <project>/config/maia.json
```

The fetch script prints a document with the real hash and size:

```sh
uv run --locked --no-editable python scripts/fetch_maia_weights.py \
  --alias 23M --dest data/models
```

`--alias` wins. Without it, the script reads `default_alias` from
`config/maia.json`. It downloads only the pinned Hugging Face repository and
revision for that alias, hashes the partial file, and moves it into place
only when the SHA-256 and byte size match. A mismatch deletes the partial
file and leaves any previous good file alone. The script does not run on
import, during tests, or in CI.

`data/models/` is gitignored by `/data/*`. The script refuses a destination
that Git does not ignore. It also prints:

```text
uv sync --locked --extra maia --extra dbt
```

That extra installs torch and Maia-3 at the pinned commit. The default
`uv sync --locked` does not install torch. On Linux the pin is
`torch==2.14.1+cpu` from the PyTorch CPU index, because the PyPI Linux wheel
depends on CUDA libraries and this tool refuses every device except CPU. On
macOS the pin is the PyPI wheel
`torch-2.14.1-cp312-cp312-macosx_14_0_arm64` (127,307,099 bytes). The running
tool sets `HF_HUB_OFFLINE=1` and reads the local path only.

Checked fields: alias, family `maia3`, absolute `weights_path`, sha256, byte
size, the pinned `hf_repo` and `hf_revision`, `code_repo`, `code_commit`,
`device` `cpu`, `dtype` `float32`, `threads` from 1 to 8, and `rating_scale`
`lichess-blitz`. Anything else is rejected. bf16 and fp16 are rejected. The
worker uses one position at a time, float32, and the configured thread count.

## Evidence

Other tools hash the result, including every float. Maia probabilities move
by about 1e-6 when the thread count or batch size changes, and rounding them
can still flip an evidence ID at a decimal boundary. `predict_human_moves`
therefore hashes the dataset, the arguments, the position, the ratings,
`top_k`, `min_prob`, and the pinned identity: weights SHA-256, Hugging Face
revision, code commit, torch version, platform, dtype, thread count, and
rating scale. The probability and win/draw/loss floats are not in the hash.
`execute_plan` and the MCP server use the same function, so the same call
gets the same ID. Two results whose floats differ by 1e-6 still match.
Changing the thread count does not.

Same-machine repeatability is the only claim. Another machine, another torch
build, or Apple Silicon was not measured here. Do not treat two machines as
bit-identical.

## Licence

Maia-3's code is AGPL-3.0. The weight files have no licence file. The model
card says "AGPLv3" in prose. Hugging Face has no licence metadata for them.
GitHub issues 8, 11, and 12, which ask about redistribution, were unanswered
as of 2026-10-17. This lab uses the weights as a personal local tool. They
are not committed and they are not served. Do not put this tool behind a
public service, and do not redistribute the weights, without a clear grant
from the maintainers (maiachess@cs.toronto.edu). Revisit this if the tool
starts being distributed or served.

## Offline tests

`tests/fixtures/maia/distribution.json` is a deterministic stand-in. It is
not a Maia checkpoint. `hang.json` sleeps so the 30-second kill is observable.
Tests that need the real weights skip when `config/maia.json` is absent. CI
does not download the weights and does not install the `maia` extra.

## What this does not do

It does not merge centipawn loss into the distribution. It does not sample
moves. It does not accept a time-control argument other than the fixed
Lichess blitz scale. Opening accuracy for Maia-3 is not in the paper.

## Corpus calibration

`python -m chess_analytics.analyst.maia_corpus` reads one local PGN and writes
one population. Elite and public stay in separate files. The public run keeps
Lichess blitz only (`lichess_blitz`). The elite run scores the curated month
and records how many of those games would pass the same window. The sample is
a fixed-seed draw of up to 20,000 games, seed `20251017`, first 12 plies.
One worker process loads the checkpoint and scores batches. It does not start
a process per position.

Install, then fetch the pinned 23M weights (91,799,307 bytes).
`--write-config` writes `config/maia.json`. It refuses when that path is
not gitignored, and it refuses to overwrite the file without `--force`. The JSON document is on stdout. The install hint and the
do-not-commit line are on stderr. Do not commit the config. The August
prefix download was approved with ADR 0083. On a Mac, sync both extras so a
later `uv sync` does not drop torch or dbt. Prefix a long scorer with
`caffeinate -i`. Elite and public can run in two terminals. Stderr prints
progress every 10 batches, with an ETA after the first batch, and a finished
line.

```sh
uv sync --locked --extra maia --extra dbt
uv run --locked --no-editable python scripts/fetch_maia_weights.py \
  --alias 23M --dest data/models --write-config
uv run --locked --no-editable python -m chess_analytics.corpus acquire
uv run --locked --no-editable python -m chess_analytics.corpus extract
caffeinate -i uv run --locked --no-editable python -m chess_analytics.analyst.maia_corpus \
  --pgn data/opening-sources/elite/lichess_elite_2025-11.pgn \
  --population elite \
  --json reports/maia-corpus-calibration-elite.json \
  --markdown reports/maia-corpus-calibration-elite.md
caffeinate -i uv run --locked --no-editable python -m chess_analytics.analyst.maia_corpus \
  --pgn data/analytical/complete-2026-08-first-100000.pgn \
  --population public \
  --json reports/maia-corpus-calibration-public.json \
  --markdown reports/maia-corpus-calibration-public.md
```

Smoke the public scorer first. Multiply its elapsed time by about 200 for
the 20,000-game run. The batch read timeout defaults to 600s because
Apple Silicon per-position speed is unmeasured; set `--read-timeout` from
this smoke run. Shutdown uses a separate 30s timeout.

```sh
uv run --locked --no-editable python -m chess_analytics.analyst.maia_corpus \
  --pgn data/analytical/complete-2026-08-first-100000.pgn \
  --population public \
  --sample-size 100 --bootstrap 20 \
  --json /tmp/maia-corpus-smoke.json \
  --markdown /tmp/maia-corpus-smoke.md
```

`acquire` reuses a cached prefix when the pinned SHA-256 matches. The public
sample is the ordered 2026-08-01 prefix, not a full month. Report paths
matching `reports/maia-corpus-calibration-*` are gitignored. A played
probability of zero is a top-1 and top-3 miss and stays out of log-loss; a
share above 1% is a stderr warning. The paper's 55–57% top-1 range is
printed as context and is not a pass/fail bar. A run on Apple Silicon is
same-machine only. `maia_v1` still skips there.

## Replies to 1.d4

`scripts/maia_d4_repertoire.py` calls `predict_human_moves` after `d2d4` at
1200, 1500, and 1800, with both players at that rating. `--eval` prints
`score_maia_v1` instead. The two caveats stay
on the view. On one `linux-x86_64` run with torch `2.14.1+cpu`, float32, and
one thread, the top replies were:

| Rating | d5 | Nf6 | e6 | e5 |
|---:|---:|---:|---:|---:|
| 1200 | 0.5485 | 0.1001 | 0.0844 | 0.1031 |
| 1500 | 0.4910 | 0.1404 | 0.0943 | 0.0881 |
| 1800 | 0.4239 | 0.2078 | 0.0974 | 0.0632 |

At 1200, e5 is ahead of Nf6. At 1500 and 1800, Nf6 is the second reply.
These are model estimates from that run. They are not counts of games.
`maia_v1` stores the same displayed values and allows an absolute difference
of 0.0001. Another platform skips that check.
