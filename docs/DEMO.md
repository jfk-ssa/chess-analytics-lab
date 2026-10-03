# M0/M1 demonstration (offline after dependency installation)

From the repository root:

1. Run `uv run --locked --no-editable chesslab doctor`. It reports runtime/disk and
   confirms live calls are unsupported; it does not discover or read credentials.
2. Run `uv run --locked --no-editable chesslab demo`. Explain that the source is a
   synthetic fixture. Show 26 inputs, 22 accepted games, and the 4/20 metric tally.
3. Repeat the demo. Snapshot ID, unique counts and metric are unchanged.
4. Open `tests/fixtures/README.md` and `contracts/game_draw_rate.json`. Explain the
   denominator and why bot/unknown-result games are visible but excluded.
5. Run `uv run --locked --no-editable pytest -q`. Point to the conflict, interrupted
   publication, tamper, resource-limit, and clean-retry checks.

With the foundation corpus already acquired/built, use `chesslab report --dataset
foundation` and `chesslab validate --dataset foundation`. Show its published manifest,
publisher checksum and independent header tally in `reports/`.

Historical source dates include 2012-12-31 despite the January 2013 archive label.
The example is data-platform evidence, not a current chess population estimate.

The complete dashboard/chat/model-evaluation demonstration in PROJECT_SPEC.md is a
later milestone. Do not describe this CLI demo as analyst replay or a model benchmark.
