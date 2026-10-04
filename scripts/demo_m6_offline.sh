#!/usr/bin/env bash
# From the repository root, after the locked dependencies are cached/installed.
# Uses synthetic data and retained key-free reports; makes no provider request.
set -euo pipefail

uv run --locked --offline --no-editable chesslab demo
uv run --locked --offline --no-editable python scripts/check_m6_release.py \
  --preflight reports/M6-holdout-v2-preflight.json \
  --reports reports/M6-holdout-v2-run-{1,2,3}.json \
  --audits reports/M6-holdout-v2-audit-{1,2,3}.json \
  --out work/M6-release-checkpoint-demo.json
