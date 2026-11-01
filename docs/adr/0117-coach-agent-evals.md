# 0117. Coach agent and live-eval grading

- Status: accepted
- Date: 2026-10-31

## Motivation

The typed analyst already plans tool calls against governed metrics and
checked tools ([ADR 0085](0085-governed-semantic-layer-metricflow.md),
[ADR 0089](0089-llm-quality-evaluation.md)). A coach-style agent that answers
questions like "why do I lose in the Caro-Kann?" needs the same warehouse
discipline, plus an eval that proves tool use and answer quality under cost
caps. That is the AI half of the job-search showcase, and it **depends on
0115** so metric tools share definitions with Streamlit and Pages.

## Decision

Add a **proposed** coach agent path that only calls typed SQL / metric tools
over the warehouse (no free-form SQL, no network). Grade it in the manual
`live-eval` GitHub environment against a **new** frozen question set.
Compare candidate agents **like for like**: Grok 4.7 (`grok-4.7` in
`model_catalog.py`) and GPT-6.1-Sol (repo id `gpt-6-sol`; STATUS notes the
API id spelling). Scoring: **exact-answer checks carry most of the score**;
an LLM judge scores **only the explanation**. The judge is fixed
**`gpt-6-luna`** for every run. It is not a candidate, so it never grades
itself. Budget caps, receipts, and instructions-hash discipline match the
existing runner.

**First live coach run:** Grok 4.7 only, **$5 USD** cap, through the manual
`live-eval` environment (Doppler-synced secrets per ADR 0114). Sol comparison
comes in a later authorized dispatch under its own cap.

### Hard rule: frozen files and receipts

New eval code **must not** edit:

- Any path in `live_runner.FROZEN_FILES`
  (`src/chess_analytics/analyst/live_runner.py`: `provider.py`,
  `model_catalog.py`, `pricing.py`, `plan_recovery.py`, `preflight.py`,
  `core.py`, `tools.py`, `tool_worker.py`, `evaluation.py`, `experiment.py`,
  `live_eval.py`, `live_score.py`, `live_stats.py`, `live_runner.py`)
- Historical receipts under `reports/live-eval-receipt-*.json`
- Existing case sets / fixture hashes that those receipts bind
  (`case_set_sha256`, `fixture_sha256`, `instructions_sha256`,
  `frozen_file_sha256`)

A new eval gets its **own** module set (or versioned package), frozen-file
list, case JSON, fixture, and receipt filename prefix (proposed:
`reports/live-eval-receipt-coach-*.json`). Like-for-like comparison across
agents requires a shared `instructions_sha256` and identical frozen hashes
within that new set—not reuse of the analyst-v1 frozen blob.

### Agent design (proposed)

- Entry: **proposed** `src/chess_analytics/coach/` (or similar), separate
  from frozen analyst modules.
- Tools: typed wrappers over `query_metric`, `compare_openings`, and
  0115-governed KPI ids (win rate, `mean_centipawn_loss`, time trouble /
  clock pressure). Opening-family filters use the same family expression as
  dbt / ADR 0085.
- Answers must cite tool evidence ids; numbers come from tools only.
- System / developer instructions are hashed into the receipt the same way
  `live_runner._one_instructions_hash` does for the analyst.

### Eval design

| Piece | Rule |
|---|---|
| Question set | Frozen JSON; include opening-loss style items (Caro-Kann etc.) with expected tool + numeric tolerance or exact tool payload fields |
| Exact checks | Tool name, key filters, and numeric fields from the warehouse reference; **majority of the pass weight** |
| LLM judge | Fixed `gpt-6-luna`; scores explanation faithfulness to tool evidence only; judge prompt and model id frozen; never used as a candidate under test |
| Candidates | `grok-4.7` and `gpt-6-sol`, same instructions hash, same case set, same tool binary |
| First live run | `grok-4.7`, max **$5** USD, manual `live-eval` environment |
| Caps | Per-run USD cap required; Doppler / `live-eval` secrets only (`CHESSLAB_OPENAI_API_KEY`, `CHESSLAB_XAI_API_KEY` per ADR 0114). Offline CI stays secret-free. |
| Workflow | Extend or twin `.github/workflows/live-eval.yml` with a coach job that still uses `environment: live-eval`, manual dispatch, main-only—without editing frozen analyst steps' hashed files |

### Data inputs (existing)

- Published mart + semantic path: `games`, `player_games`, MetricFlow metrics
  (`win_rate`, `opening_player_score`, `game_draw_rate`, …), plus 0115
  `move_evals` metrics when merged.
- Checked tools pattern: `src/chess_analytics/analyst/tools.py`
  (`query_metric`, `compare_openings`, `analyze_clock_pressure`).
- Live-eval machinery to **copy patterns from**, not mutate:
  `live_runner.py`, `live_score.py`, `live_stats.py`, ADR 0090–0091, 0093,
  0095, 0099.
- Model catalog: `src/chess_analytics/analyst/model_catalog.py`
  (`GROK_MODEL_ID = "grok-4.7"`, `gpt-6-sol`, `gpt-6-luna`).

Depends on **0115** landing enough governed KPI ids for the frozen
questions. Does not depend on 0116.

### PR slicing (~400 lines each)

1. Coach tool facade + offline unit tests with recorded tool payloads (no
   live calls); docs ADR + case schema.
2. Frozen coach case set + reference builder + offline exact scorer.
3. Live runner twin (new modules), workflow dispatch inputs, receipt schema,
   judge wiring to `gpt-6-luna`.
4. First authorized live receipt for Grok 4.7 under the $5 cap; later Sol
   comparison under a separate approved cap; Pages / hosted chart optional
   follow-up (do not rewrite analyst charts).

## Consequences

### Evaluation and acceptance

- Offline: every coach case has a deterministic reference from tools on the
  fixture mart; exact scorer passes without network.
- Live: first Grok 4.7 run completes under $5; receipt records
  `instructions_sha256`, frozen hashes for the **coach** file set, gross
  cost, exact pass rate, and judge explanation scores. `hard_fail` policy
  documented before the first dispatch.
- Judge model is always `gpt-6-luna` and never equals the agent under test.
- Analyst live-eval regression and committed analyst receipts remain
  byte-stable.

### Risks

- Touching frozen analyst files by "sharing" helpers would invalidate
  historical receipts; keep a hard import boundary.
- LLM judge variance on explanations; freeze judge temperature / effort and
  keep exact checks as the primary gate.
- Coach questions that need per-move facts need 0115 `move_evals` or
  reviewed clock tools; keep those cases out of v1 if tools are missing.
- Cost: preflight estimate required before every dispatch
  ([ADR 0021](0021-always-recommend-a-spend-cap-with-an-estimate.md)).

### Out of scope

- Editing `FROZEN_FILES` or historical `reports/live-eval-receipt-*.json`.
- Free-form SQL, browsing, or writing the warehouse.
- Promoting the coach to default MCP / production without a later ADR.
- Using a candidate model as judge.
- First-run Sol live spend (later dispatch).

## Rejected alternatives

- **Extend analyst live_eval.py in place:** would change frozen hashes and
  break like-for-like with committed receipts.
- **Judge-only scoring:** loses warehouse grounding; exact checks are primary.
- **Single-candidate eval forever:** Sol comparison remains planned; only
  the first live dispatch is Grok-only.
- **OpenAI judge other than `gpt-6-luna`:** rejected; Luna is fixed.

## References

- [ADR 0085](0085-governed-semantic-layer-metricflow.md),
  [ADR 0089](0089-llm-quality-evaluation.md),
  [ADR 0090](0090-live-eval-scorer-runner-stats.md),
  [ADR 0091](0091-manual-live-eval-workflow.md),
  [ADR 0095](0095-grok-4-7-live-eval.md),
  [ADR 0114](0114-doppler-secrets-source-of-truth.md),
  [ADR 0115](0115-metrics-layer.md),
  [docs/EVALUATION.md](../EVALUATION.md)

## Decided 2026-10-31

1. Judge = `gpt-6-luna` (fixed); exact checks primary; judge scores
   explanation only.
2. First live run = Grok 4.7 under a $5 USD cap in `live-eval`.

### First implementation slice

Slice 1 ships the separate `chess_analytics.coach` payload facade, a strict
Python case validator, and two hand-authored synthetic example cases in
`tests/fixtures/coach_offline.json`. Its local metric allowlist includes
`mean_centipawn_loss` without changing the analyst catalog or frozen files.
Accuracy takes empty filters in this slice; opening-score evidence carries
the literal ADR 0085 family and exact cohort. No SQL is generated.

The intentional small expansion beyond item 1 is an offline explanation
rubric/heuristic, a thin exact-tool check, and configuration constants for
Grok 4.7's first $5 run and the fixed Luna judge. Exact and explanation
weights are 0.8 and 0.2, respectively, reserved for a future combiner; the
offline heuristic does not consume them. The heuristic checks citation ids
and numeric support in cited evidence; it does not establish semantic
entailment or detect every unsupported causal claim.
It is labeled `offline_heuristic`, not a Luna result.

Prose numbers match evidence quantized to the prose token's displayed
decimal precision (integers: 0), explicitly using `ROUND_HALF_EVEN`.
Percent claims quantize evidence multiplied by 100 at the percent's display
precision; both `52%` and `52 %` can support 0.5217. Grouped thousands and
Unicode minus signs are parsed as complete numbers; invalid grouping and
oversized/extreme tokens fail as unsupported numbers.
Numeric support includes cited values and nested args/filters, bucket-label
integers, and integer `rating_max_exclusive - 1` as the inclusive upper
display endpoint (1600 exclusive may display as 1599). Raw filter numbers
remain supported. The explicit governed constant allowlist reads only
`clamp_centipawns` from `contracts/mean_centipawn_loss.json`. It applies
when citing `mean_centipawn_loss` evidence, so unrelated game counts do
not inherit the clamp. Uncited args
and free numbers such as 2024 remain unsupported. Equal duplicate
`evidence_id` payloads dedupe; conflicting payloads raise `ValueError`.

The deterministic `fixture_fake` path uses example tool arguments as an
oracle plan, obtains all explanation numbers from recorded tool results,
and records the hash of the literal UTF-8 coach instructions. It is harness
validation, not a model evaluation or a frozen question set. Future
comparisons require identical instruction and coach frozen-file hashes.
Frozen cases and warehouse references remain slice 2; live runner,
receipts and dispatch wiring remain slice 3; authorized live calls remain
slice 4. The proposed receipt prefix stays
`reports/live-eval-receipt-coach-*.json`. No workflow or receipt is added.
Future live execution still requires the manual `live-eval` environment,
personal-account acknowledgement, an explicit cap, and Doppler runtime
secrets from project `chess-analytics-lab`. These constants enable no calls.

Offline validation: synthetic fixture tests for the facade, exact check,
and hardened offline judge (tokenizer, presentation rounding, cited args,
contract-constant allowlist, duplicate evidence_id) passed; Ruff lint/format
and basedpyright on the CI tree passed. No live calls were made.
