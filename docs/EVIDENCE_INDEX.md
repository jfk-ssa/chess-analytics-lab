# Evidence index

A source file and a test are distinct kinds of evidence. The reports here
preserve historical numbers; some can be audited from tracked JSON alone,
while reproducing real corpus metrics requires ignored downloaded bytes.

| Claim | Evidence / reproduction | Limit |
|---|---|---|
| Locked environment, tiny fixture, reference draw rate | [M0–M1 record](../reports/M0-M1.md); `chesslab demo`; [independent expected tally](../tests/fixtures/expected.json) | Synthetic counts only |
| Complete foundation ingest and publisher hash | [M1 acceptance](../reports/M0-M1.md), [dataset pin](../config/datasets.json), `chesslab report --dataset foundation`, [header reference script](../scripts/reference_draw_rate.py) | Requires local January 2013 archive |
| dbt marts, recovery, optional orchestration | [M2](M2.md), [local adapter comparison](../reports/orchestrator-comparison.json), [orchestration commands](ORCHESTRATION.md) | Optional extras; no scheduler/cloud run |
| Ordered-prefix analytical coverage and opening/clock references | [M3](M3.md), [coverage report](../reports/M3-coverage.json), [raw-PGN reference check](../reports/M3-reference-check.json) | August 1 only; selected move annotations |
| Dashboard views and two analytical memos | [M4–M5](M4-M5.md), [dashboard smoke](../reports/M4-dashboard-smoke.json), [fixture UI test](../tests/test_portfolio_demo.py) | Historical smoke needs ignored real snapshot; fixture test runs in clean checkout |
| Checked tools and fixture harness | [M5 report](../reports/M5-both-harness.json), [tool module](../src/chess_analytics/analyst/tools.py), `python -m chess_analytics.analyst eval --split both` | Replay is not a model result |
| Live M6 measured release and failures | [M6 release](M6-RELEASE.md), [run records](../reports/M6-holdout-v2-variability.json) | Frozen 20-case holdout, three repetitions |
| Live M7 accepted gate and earlier failures | [December checkpoint](M7-DECEMBER.md), [reconciliation JSON](../reports/M7-December-Sol-v12-checkpoint.json), [timeline](M7.md), `pytest -q tests/test_m7.py` | Frozen 50 cases on December 1 prefix; optional real-data tests skip without local source |
| New complete offline product demo | `chesslab demo --scope all`, [fixture PGN](../tests/fixtures/portfolio_annotated.pgn), [independent values](../tests/fixtures/portfolio_expected.json), `pytest -q tests/test_portfolio_demo.py` | Authored games, fixture plans, no live model |
| Source/receipt integrity | [read-only local audit](../reports/portfolio-source-audit.json), `python scripts/audit_analytical_sources.py` | Nine available local pairs inspected; historical bulk data ignored |
| Review and hardening | [review findings](REPOSITORY_REVIEW.md), [implementation plan](PORTFOLIO_HANDOFF.md), [regressions](../tests/test_portfolio_integrity.py) | Review probes are distinct from post-fix tests |
| Release candidate inventory | [upload audit](../reports/portfolio-upload-audit.json), `python scripts/audit_upload_candidate.py`; [release check](../reports/portfolio-release-check.json) | Filename-only pattern scan; no public upload or hosted CI claimed |
| M8 routing experiment | [learning runbook](JEV_ROUTING_RUNBOOK.md), [frozen manifest](../evals/cases/jev_routing_v1_manifest.json), [offline preflight](../reports/M8-routing-preflight.json), [actual-run checkpoint](../reports/M8-routing-checkpoint.json), [comparison page](../reports/M8-routing-comparison.html), `pytest -q tests/test_routing_study.py` | Actual route scores: Jev 39/40 and 37/40, analyst 33/40; small authored label set without independent human adjudication; not end-to-end answers |
| M8 paired final-answer experiment | [learning lab](JEV_END_TO_END.md), [case manifest](../evals/cases/jev_e2e_v1_manifest.json), [independent opening reference](../reports/M8-e2e-independent-reference.json), [historical preflight](../reports/M8-e2e-preflight.json), [original actual report](../reports/M8-e2e-paired-actual.json), [offline rescore](../reports/M8-e2e-paired-rescore.json), [checkpoint](../reports/M8-e2e-checkpoint.json), `pytest -q tests/test_jev_e2e.py` | One paired run: both 31/32 after versioned rescore; Jev costs slightly more; eight boundary labels owner-reviewed, numeric results independently referenced; retained raw responses required to reproduce rescore |
| M8 DuckDB exercise | [offline replay](../reports/M8-duckdb-offline.json), `python -m chess_analytics.routing_duckdb --help` | Same question table and Jev SQL preview; no Jev extension/model execution |
| M8 upload candidate | [post-M8 audit](../reports/M8-upload-audit.json), `python scripts/audit_upload_candidate.py --project . --out work/m8-upload-audit.json` | Filename-pattern scan only; final sdist/wheel contained no ignored work, cache, or key file; no upload |
| M8 final-answer candidate audit | [post-study audit](../reports/M8-e2e-upload-audit.json) | Current candidate and 33 reachable commits had no matching sensitive filename/path patterns; bounded scan only, no new clean-export or hosted-CI claim |
| Final publication review and offline fixes | [findings and resolution](FINAL_RELEASE_REVIEW.md), [original review probe](../reports/final-release-review.json), [post-fix candidate scan](../reports/final-upload-audit.json), [package inventory](../reports/final-package-inventory.json), `pytest -q tests/test_jev_e2e.py tests/test_jev_e2e_replay.py` | Local 108/108 tests; clean export 95 passes and 13 expected real-data skips; historical pre-publication candidate; hosted CI later passed and the repository became public; see STATUS |
| Optional Decisions classifier | [runbook](DECISIONS_ROUTING_RUNBOOK.md), [owner label audit](DECISIONS_LABEL_AUDIT.md), [checkpoint](../reports/decisions-checkpoint.json), [comparison](../reports/decisions-routing-comparison.html), `pytest -q tests/test_decisions_study.py` | Six actual classifier runs, 184 requests, $0.0068145 gross; fresh 23/24 per repetition. Retained-answer replay is offline, not fresh live end-to-end evidence. |

The [status](STATUS.md) identifies the current phase and latest verification.
Reports under `reports/` are compact review evidence. Full raw attempts and
bulk data reside in ignored `work/` or `data/`; many cannot be reconstructed
from Git alone. A clean checkout can reproduce the synthetic demo and audit
tracked checkpoint reconciliation, not the original provider requests.
