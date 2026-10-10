## Why

<!-- The problem or decision this change addresses. -->

## What changed

<!-- The behavior or files that changed. -->

## How it was tested

<!-- Keep fixture, replay, and live results distinct. -->

- [ ] `uv run --locked --offline --no-editable ruff check .`
- [ ] `uv run --locked --offline --no-editable ruff format --check .`
- [ ] `uv run --locked --offline --no-editable basedpyright`
- [ ] `uv run --locked --offline --no-editable pytest -q`
- [ ] No live provider calls, credential reads, or new downloads

## Risk or rollback

<!-- What could break, and how to revert this squash commit. -->

## Stacked pull requests

<!-- If this depends on another open pull request, keep this draft and write: Stacked on #N, merge after -->
