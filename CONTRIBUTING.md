# Contributing

## Commits

Use [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/)
with an optional scope:

```text
type: subject
type(scope): subject
```

Types used here: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`,
`build`, `ci`, `chore`, and `revert`. A `!` before the colon marks a breaking
change.

Make one logical, revertible commit per change. Lint and tests are green on
that commit before the next change starts.

Keep generated data and reports out of code commits. A generator change and a
measured receipt are separate commits when both need to land.

The local `commit-msg` hook checks the message. Install it with the commands
in the README [development checks](README.md#development-checks).

## Pull requests

Write the pull request title in Conventional Commits form. Squash merge uses
that title as the commit message.

Keep one theme per pull request, with a soft limit of about 400 lines of real
code. Generated files and vendored files sit outside that count.

Fill in the pull request template: why, what changed, how it was tested, and
risk or rollback. Keep fixture, replay, and live results distinct.

A pull request stacked on another open pull request stays a draft. Its
description says `Stacked on #N, merge after`.

This repository accepts squash merges only, and GitHub deletes the head branch
after the merge. Both settings are already enabled.

Name branches `type/short-topic`, for example `docs/commit-conventions`.

## Decisions

New decisions go only into [docs/adr](docs/adr/). Add the next number and a row
in [docs/DECISIONS.md](docs/DECISIONS.md).

[docs/STATUS.md](docs/STATUS.md) stays a short current-state summary: headline,
checkout structure, phase tracker, dataset versions, and limits. Do not append
measurement logs there. Put measured evidence in the relevant receipt under
`reports/` and, when the choice should outlive the chat, in an ADR.
