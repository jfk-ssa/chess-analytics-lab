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
- With `dagster~=1.13.26` and `dagster-webserver~=1.13.25`,
  `uv lock --upgrade-package dagster==1.13.26` moved all five packages
  to 1.13.26. The reverse, `dagster~=1.13.25` and
  `dagster-webserver~=1.13.26`, did the same for
  `--upgrade-package dagster-webserver==1.13.26`.

No Dependabot pull request in `jfk-ssa/chess-analytics-lab` bumps dagster
to 1.13.26. Open, closed, and merged dependency PRs were listed with `gh`,
and issue search for that version was empty. The grouped update
[#57](https://github.com/jfk-ssa/chess-analytics-lab/pull/57) (2026-10-24)
bumped seven other packages and left this pair at 1.13.25, nine days
after 1.13.26 was on PyPI. A failed one-package resolution does not open
a pull request. [ADR 0005](0005-parallel-orchestration-learning-path.md)
records the original 1.13.25 pins and stays as written.

## Decision

Dependabot groups every `dagster*` name ahead of the `uv-dependencies`
catch-all. The catch-all also excludes `dagster*`. The first matching
group owns a dependency, so the catch-all would take them without that
order and the exclude.

The dagster extra requires `dagster~=1.13.26` and
`dagster-webserver~=1.13.26`. That is `>=1.13.26,<1.14`. The lock
installs 1.13.26 for all five packages. A later 1.13 patch still
satisfies the other name's range, so one `uv lock --upgrade-package`
can move the set. A 1.14 release is outside this range and needs its
own manifest edit. There is no Dependabot ignore for these packages.
1.13.26 is a matched release.

## Consequences

Weekly uv updates can take a 1.13 Dagster patch without splitting the
pair across an unsatisfiable lock. `uv sync --locked` still installs
the locked 1.13.26 files until a lock update lands. Protobuf stays
6.33.6. This record does not authorize a live model call.
