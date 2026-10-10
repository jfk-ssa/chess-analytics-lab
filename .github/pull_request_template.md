## Summary

<!-- What changed, and why. Keep fixture, replay, and live results distinct. -->

## Test plan

- [ ] `uv run --locked --offline --no-editable ruff check .`
- [ ] `uv run --locked --offline --no-editable ruff format --check .`
- [ ] `uv run --locked --offline --no-editable basedpyright`
- [ ] `uv run --locked --offline --no-editable pytest -q`
- [ ] No live provider calls, credential reads, or new downloads

## Notes

<!-- Optional: skipped real-data tests, docs, or follow-ups. -->
