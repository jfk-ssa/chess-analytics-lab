# 0108. Dagster packages update together

- Status: accepted on merge
- Date: 2026-10-25

## Motivation

Dagster publishes `dagster`, `dagster-webserver`, `dagster-graphql`,
`dagster-pipes`, and `dagster-shared` as one version. On PyPI, 2026-10-25,
both direct packages are at 1.13.26, uploaded 2026-10-09.
`dagster-webserver` 1.13.25 requires `dagster==1.13.25`.
`dagster-webserver` 1.13.26 requires `dagster==1.13.26`.
`dagster` 1.13.26 requires `dagster-pipes==1.13.26` and
`dagster-shared==1.13.26`. `dagster` 1.13.26 still requires `protobuf<7`
on Python 3.12, so the protobuf major ignore in
[ADR 0104](0104-hosted-altair-6-and-pandas-3-pins.md) stays.

The dagster extra pinned both direct packages at `==1.13.25`. Dependabot's
uv updater rewrites one requirement, then runs
`uv lock --upgrade-package` for that name. A group walks those updates one
dependency at a time; it does not edit both exact pins before the lock.
`dependabot-core` `Uv::FileUpdater::LockFileUpdater` still takes
`dependencies.first` and comments that it updates a single dependency.

Checked on 2026-10-25 against this checkout:

- `uv lock --upgrade-package dagster==1.13.26` with `dagster-webserver`
  left at `==1.13.25` failed. uv reported that the dagster extra depends
  on `dagster==1.13.26` and on `dagster-webserver==1.13.25`, and that
  `dagster-webserver==1.13.25` depends on `dagster==1.13.25`.
- The reverse, only `dagster-webserver==1.13.26`, failed the same way
  against `dagster==1.13.25`.
- Both names at 1.13.26 resolved. The lock moved `dagster`,
  `dagster-graphql`, `dagster-pipes`, `dagster-shared`, and
  `dagster-webserver` from 1.13.25 to 1.13.26. No other package moved.
- From that 1.13.25 lock, with both specs at `>=1.13.25,<2`,
  `uv lock --upgrade-package dagster==1.13.26` moved all five packages
  to 1.13.26. The same start with
  `--upgrade-package dagster-webserver==1.13.26` did the same.

No Dependabot pull request in `jfk-ssa/chess-analytics-lab` bumps dagster
to 1.13.26. Open, closed, and merged dependency PRs were listed with `gh`,
and issue search for that version was empty. The grouped update
[#57](https://github.com/jfk-ssa/chess-analytics-lab/pull/57) (2026-10-24)
bumped seven other packages and left this pair at 1.13.25, about two weeks
after 1.13.26 was on PyPI. A failed one-package resolution does not open
a pull request. [ADR 0005](0005-parallel-orchestration-learning-path.md)
records the original 1.13.25 pins and stays as written.

## Decision

Dependabot groups every `dagster*` name ahead of the `uv-dependencies`
catch-all. The catch-all also excludes `dagster*`. The first matching
group owns a dependency, so the catch-all would take them without that
order and the exclude.

The dagster extra requires `dagster>=1.13.26,<2` and
`dagster-webserver>=1.13.26,<2`. The lock installs 1.13.26 for all five
packages. `uv sync --locked` installs that lock, not the newest release
inside the range.

`~=1.13.26` is `>=1.13.26,<1.14`. Dependabot's increase strategy rewrites
a compatible pin to the new version at the same precision, so one name
becomes `~=1.14.0` (`>=1.14.0,<1.15`) while the other stays below 1.14.
That pair does not resolve. Increase on `>=1.13.26,<2` rewrites only the
floor: the updated name becomes `>=1.14.0,<2`, and the other stays
`>=1.13.26,<2`. 1.14 is still inside the untouched range. The same
one-package upgrade that moved 1.13.25 to 1.13.26 can then move the set
to 1.14, because the sibling release will require the matching `==1.14`
and that version satisfies the spec that was not rewritten. 1.14 is not
on PyPI, so this minor step is that constraint, not a second lock run.
A 2.0 release is outside `<2`. There is no Dependabot ignore for these
packages. 1.13.26 is a matched release.

## Consequences

Weekly uv updates can take a later 1.x Dagster release without splitting
the pair across an unsatisfiable lock. `uv sync --locked` still installs
the locked 1.13.26 files until a lock update lands. Protobuf stays
6.33.6. This record does not authorize a live model call.
