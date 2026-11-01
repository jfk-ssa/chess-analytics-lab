# 0116. Mistake classifier and risky-positions view

- Status: accepted
- Date: 2026-10-31

## Motivation

The lab already labels large eval swings on sampled moves
(`error_proxy` when `centipawn_deterioration >= 200`). That is a
deterministic proxy on **source** annotations, not a learned model, and the
Streamlit app has no "risky positions" view. A small supervised classifier
with calibration and a model card shows ML practice on the same warehouse
the metrics layer uses, without live LLM spend.

## Decision

Train a scikit-learn `HistGradientBoostingClassifier` to predict the
existing binary label `error_proxy` (or a contract-versioned successor) from
move- and game-level features. Ship calibration plots / metrics, a model
card under `docs/` or `reports/`, and a Streamlit risky-positions view that
scores positions offline from a locally rebuilt artifact. No change to
`live_runner.FROZEN_FILES`.

**Artifacts:** a small CI fixture only. The model is rebuilt locally. No
trained model weights and no scored sample parquet are committed.

### Per-move engine evals: what exists

**Present today (analytical warehouse / M3 sample), not as a dbt mart until
0115 `move_evals`:**

| Asset | Location | Contents |
|---|---|---|
| `fact_move` schema | `contracts/m3_tables.json` | `eval_before_cp_white`, `eval_after_cp_white`, mate fields, `centipawn_deterioration`, `error_proxy`, `clock_before_seconds` / `clock_after_seconds`, `clock_bucket`, `phase_proxy`, `ply`, `color`, `uci` |
| Builder | `src/chess_analytics/corpus/moves.py` | Source PGN `%eval` / clock annotations; `phase_proxy` ∈ {`early_ply`,`middle_ply`,`late_ply`}; `error_proxy` = deterioration ≥ 200 |
| Publish | `src/chess_analytics/corpus/publish.py` | Writes `fact_move` into analytical `warehouse.duckdb` and `fact_move.parquet` |
| Consumers | `corpus/metrics.py` (`clock_pressure`), `dashboard/analysis.py`, `dashboard_cube.py` | Clock / coverage metrics; cube optional clock cells |

**Not present today:**

- No dbt model builds or stages `fact_move` until 0115 ships `move_evals`.
- No independent Stockfish (or other) re-eval table; values are **source**
  centipawns. Mate transitions are excluded from the deterioration numerator
  in `contracts/clock_pressure_error_proxy.json`.
- No `material` (or material-diff) column on `fact_move` or `fact_game`
  (`contracts/tables.json` has no material fields).

**First PR:** do **not** invent a second eval pipeline. Add a **proposed**
training-frame builder, e.g. `scripts/build_mistake_training_frame.py`, that
joins `fact_move` (label = `error_proxy`; features exclude deterioration and
post-move eval), `fact_game` opening family via the same expression as dbt
`games.opening_family`, and **proposed** `material_balance` from legal UCI
replay. CI keeps only a tiny fixture frame. If 0115's `move_evals` already
exists, the builder may read that mart instead; 0116 does not depend on 0115.

### Model

- Algorithm: `HistGradientBoostingClassifier` (**proposed** dependency:
  add `scikit-learn` to an optional extra, e.g. `ml`, pinned in
  `pyproject.toml` / `uv.lock`—not present in the lock today).
- Label: `error_proxy` boolean on evaluable moves (non-null deterioration).
- Features (v1): `clock_bucket` or `clock_before_seconds`, `phase_proxy`,
  `ply`, `color`, opening family, **proposed** material balance. Do not feed
  `centipawn_deterioration` or post-move eval as features (label leakage).
- Split: game-id grouped holdout (same game never in train and test).
- Calibration: isotonic or sigmoid on a validation fold; report Brier /
  reliability in the model card.
- Local artifact path (proposed, gitignored): rebuilt by the train script.
  CI asserts schema and no-leakage on the fixture only.

### Product view

**Proposed** Streamlit section in `hosted/dashboard.py` (or a sibling module
under `hosted/`): risky cohorts by predicted probability when a local
artifact is present, with support counts and the caveat that labels are
source-eval proxies. Offline only; no API keys; no committed scored sample.

### PR slicing (~400 lines each)

1. Training-frame builder + fixture schema contract; tests that leakage
   columns are absent from the feature matrix.
2. Train / evaluate script, calibration, model card markdown, metrics JSON
   under `reports/` written locally (card prose may be committed; weights
   are not).
3. Streamlit risky-positions view that loads a local artifact path or shows
   an empty state; CI does not require the artifact.

## Consequences

### Evaluation and acceptance

- Holdout metrics and calibration curves recorded in the model card.
- Offline pytest: fixture schema, no leakage columns, deterministic seed on
  the tiny fixture only.
- Hosted view loads without secrets; captions state source-eval limits.
- Does not modify `evals/` frozen analyst cases or live-eval receipts.
- `git` status after a local train must not require adding model binaries.

### Risks

- Source `%eval` quality varies; coverage is a hash-sampled game subset
  (`SAMPLE_MODULUS = 20` in `moves.py`). Model card must say so.
- Class imbalance (`error_proxy` rare) can inflate accuracy; prefer PR-AUC
  / Brier.
- Material feature adds replay CPU; keep it in the offline builder, not the
  Streamlit request path.

### Out of scope

- Committing trained weights or scored samples.
- Live Stockfish annotation of the full corpus.
- Replacing `clock_pressure_error_proxy` with the classifier in the analyst
  allowlist (optional later ADR).
- Depending on MetricFlow / 0115.
- LLM labeling.

## Rejected alternatives

- **Train only after a full engine re-eval table:** delays the showcase;
  source labels already exist and are documented as exploratory.
- **Deep learning on boards:** out of PR-size and hosting budget; Maia
  already covers human-move prediction ([ADR 0081](0081-human-move-prediction-maia3.md)).
- **Use deterioration magnitude as a feature:** trivial leakage.
- **Commit model + scored sample for Cloud demo:** rejected; CI fixture
  only; rebuild locally.

## References

- `contracts/m3_tables.json`, `contracts/clock_pressure_error_proxy.json`,
  `contracts/evaluation_coverage.json`
- `src/chess_analytics/corpus/moves.py`, `publish.py`, `metrics.py`
- [docs/METRICS.md](../METRICS.md), [docs/DATA_DICTIONARY.md](../DATA_DICTIONARY.md),
  [ADR 0007](0007-m3-partial-corpus-and-exploratory-analytics.md)

## Decided 2026-10-31

Classifier artifacts are a small CI fixture only; rebuild the model locally;
do not commit trained weights or scored samples.

### First implementation slice — 2026-10-31

The owner combined the frame builder and baseline trainer in the first PR.
Frame v1 uses White-minus-Black material before each move (pawn 1, knight/bishop
3, rook 5, queen 9). Sorted game IDs receive seeded disjoint training,
sigmoid-calibration and holdout splits; the encoding fits training games only.
The trainer prints metrics without persisting weights. The fixture has six
synthetic games and 36 labeled rows, with replay and leakage tests.

Fixture training at seed 20261031 reports Brier ≈ 0.0159 on 12 holdout rows
(synthetic labels only; not a real-corpus claim). See the
[baseline card and commands](../MISTAKE_CLASSIFIER.md). The product view stays
in slice 3.
