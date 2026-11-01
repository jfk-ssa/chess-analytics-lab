# Mistake classifier baseline — ADR 0116

This first deliverable builds a frame and trains an offline baseline. It has no
product view or saved model. Labels are the existing `fact_move.error_proxy`
values on moves with non-null `centipawn_deterioration`; the builder does not
run an engine or regenerate labels.

Frame v1 is the `TrainingRow` contract in
`src/chess_analytics/mistake_training.py`, exercised against
`tests/fixtures/mistake_training.json`. The fixture contains six authored
synthetic Standard games, 48 source plies and 36 evaluable rows. Clocks and
labels are fabricated. Pre-move material was hand-tallied, including an
unevaluable recapture and en passant. This is harness evidence only.

The builder joins on provider and game ID and legally replays every ply from
the standard initial board before filtering evaluable moves. Opening family
uses only moves already on the board before the candidate move: the longest
matching UCI prefix in the small static `OPENING_PREFIXES` map. The map covers
`e2e4 d7d5` (Scandinavian Defense) and `d2d4 d7d5 c2c4` (Queen's Gambit);
unknown prefixes are None. Completed-game PGN Opening headers are not features.
It fails on missing or duplicate plies, orphan moves, illegal UCI, nonstandard
variants, missing evaluable labels, and labels inconsistent with deterioration ≥ 200.
It expects the accepted ingestion contract, which excludes custom starting
positions. It reads the warehouse without modifying it and materializes the
frame in memory.

Features are `clock_before_seconds`, `phase_proxy`, `ply`, `color`,
`opening_family`, and `material_balance`; all are strictly pre-move. Material is
**White minus Black before the move**, in pawn units: pawn 1, knight/bishop 3,
rook 5, queen 9, king 0. Missing clocks remain NaN for the estimator; missing opening families
have an explicit category. Identifiers, UCI, labels, deterioration, evaluations
and post-move clocks cannot enter the feature matrix.

The fixed seed is 20261031. Whole game IDs are shuffled after sorting, with
25% (rounded up) held out; one third of the remaining games calibrates the
model. The three groups are disjoint, including across providers sharing a
game ID. No label-dependent retries select a more favorable split. Training
and calibration must each contain both classes or the run fails explicitly.
`DictVectorizer` learns categorical encodings on training games only, and
`HistGradientBoostingClassifier` uses 40 iterations, minimum leaf size 2,
disabled internal early stopping, and one computation thread. A frozen fitted
pipeline receives sigmoid calibration on the separate calibration games.
The untouched holdout supplies Brier score and five equal-width reliability
bins, including empty bins with null means. The final bin includes probability
1.0. Results are printed as JSON; weights and scored samples are never written.

Install dependencies once, then run offline from the repository root:

```sh
uv sync --locked --no-editable --extra ml --reinstall-package chess-analytics-lab
uv run --locked --offline --no-editable --extra ml pytest -q tests/test_mistake_classifier.py
uv run --locked --offline --no-editable --extra ml basedpyright src/chess_analytics/mistake_training.py scripts/train_mistake_classifier.py
uv run --locked --offline --no-editable --extra ml python scripts/train_mistake_classifier.py tests/fixtures/mistake_training.json
```

For an existing analytical warehouse:

```sh
uv run --locked --offline --no-editable python -m chess_analytics.mistake_training /path/to/warehouse.duckdb work/mistake-frame.json
uv run --locked --offline --no-editable --extra ml python scripts/train_mistake_classifier.py work/mistake-frame.json
```

`work/` is already gitignored. There is no model artifact path in this slice.
Core CI exercises schema, replay, feature leakage, splitting and reliability
arithmetic without the optional extra. A separate CI step installs `ml` and runs
the deterministic training, holdout-label isolation and Brier checks for Python
changes and full-suite events.

## Verification and limits

With the `ml` extra installed, the fixture trainer is deterministic at seed
20261031. Holdout games are `syn00005` and `syn00006` (12 rows). Measured
fixture metrics after the prefix-only opening fix: **Brier score ≈ 0.0159**.
Reliability (5 equal-width bins):
bin 0 (n=8) mean predicted ≈ 0.10 / empirical 0.00; bins 1–3 empty; bin 4
(n=4) mean predicted ≈ 0.833 / empirical 1.00. These numbers are harness
evidence on synthetic labels only; they do not measure chess-playing
performance or real-corpus quality.

Core schema/replay/leakage/split tests pass without the extra. Repository
Ruff, format, and basedpyright pass on the typed tree. Rebuild metrics with
the commands above after `uv sync --extra ml`.

Real source annotations vary in quality. The existing sample selects games by
SHA256(game ID) modulo 20 from a bounded archive prefix, independently of
annotation availability; missing/mate evaluations reduce label coverage.
Rare positive labels and selection effects limit interpretation. No population
accuracy, causal clock effect, independent engine quality, replay-model result,
or live result is claimed. Real-corpus evaluation and the risky-positions view
remain follow-ups.
