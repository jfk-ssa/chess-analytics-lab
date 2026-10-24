# 0107. Hosted repository source reload

- Status: accepted on merge
- Date: 2026-10-24

## Motivation

On 2026-10-24 the hosted app at
`https://chess-analytics-lab.streamlit.app/` missed two code pushes
until someone used Reboot app. After
[#61](https://github.com/jfk-ssa/chess-analytics-lab/pull/61) and
[#63](https://github.com/jfk-ssa/chess-analytics-lab/pull/63) the page
kept the previous behavior. After
[#62](https://github.com/jfk-ssa/chess-analytics-lab/pull/62)
(`5919d95`) it crashed. `hosted/bi.py` imports names from
`chess_analytics.dashboard_cube`, including `clock_games` and
`month_display`. Those names are in
`src/chess_analytics/dashboard_cube.py` on that commit. Community Cloud
redacted the ImportError text. A reboot cleared both failures.

[Streamlit's app management docs](https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app)
say a push shows up in the running app, and a dependency change is what
triggers a full redeploy. `hosted/requirements.txt` is the only file
Community Cloud installs. It does not install `chess-analytics-lab`.
The entrypoint inserted `src/` for one import and then removed it
([ADR 0094](0094-hosted-read-only-dashboard.md)). Python kept that
module in `sys.modules`. The next rerun executed `hosted/bi.py` from
disk, through `_load_local`, and imported the cached module. New names
in `hosted/bi.py` then failed, and new function bodies in `src/` never
ran. A reboot starts a new interpreter, so the first import reads the
files on disk.

The stale copy is that in-process cache, not a non-editable wheel left
behind by pip. Nothing in the hosted requirements installs this
project. A local `uv sync --no-editable` does install a wheel, and that
wheel would win a later import once `src/` was taken off `sys.path`.

## Decision

`hosted/repo_import.py` imports `chess_analytics.public_extract` and
`chess_analytics.dashboard_cube` from this checkout's `src/` before
`hosted/bi.py` loads. `src/` is first on `sys.path` only while that
import runs. The previous `sys.path` is restored.

The import is skipped when every cached `chess_analytics` module was
loaded from that `src/chess_analytics` tree and a SHA-256 of those
`.py` files still matches the stamp from the last import. When those
modules are already that tree, a later source change reloads them in
place. `importlib.reload` looks the spec up again, so `src/` is first
on `sys.path` for that search; otherwise the finder would bind an
installed copy into the same module object. The module objects stay in
`sys.modules`, so another session's lazy import (`dimension_values`,
`exact_sign_test`) does not see a missing module. Each session has its
own script thread. A cached copy from outside the tree is still
replaced.

`__pycache__` entries are removed only when the resolved directory is
still under `src/chess_analytics`. A symlink that points elsewhere is
left alone. The stamp is updated only when that cleanup could delete
every in-tree `.pyc` it tried to remove. A file that could not be
removed leaves the stamp unset, and the next rerun tries again. An
unchanged rerun keeps the module object.

`RepositoryImportError` is not an `ImportError`. The page prints it.
An `ImportError` from `hosted/bi.py`, and one raised later while the
page renders, is caught and printed with the loaded cube path.
Community Cloud redacts an uncaught import failure. A mismatch that
remains after the reload is a disagreement between the files on disk,
and the page says so.

`hosted/` modules stay on `_load_local`, which executes the file on
every run. This record does not add the project to
`hosted/requirements.txt`. An editable install would still sit in
`sys.modules` until the interpreter restarted.

## Consequences

A push to `main` that changes `src/chess_analytics` or `hosted/` and
leaves `hosted/requirements.txt` unchanged is picked up on the next
rerun. Refresh the page. Reboot app is not required for that case.
Changing `hosted/requirements.txt` still causes Community Cloud to
reinstall dependencies and start a new process.

If Community Cloud does not copy the new files into the running app,
this reload cannot see them. Reboot after the files are present, or
change `hosted/requirements.txt` to force a new environment. That
platform miss is outside this repository.

`tests/test_hosted_dashboard.py` puts a cube module without
`clock_games` in `sys.modules`, including one whose path sits ahead of
`src/` and whose stamp already matches the repository hash, and checks
that the next import is the repository module. The same file checks
that a missing repository tree raises `RepositoryImportError` rather
than `ImportError`. The AppTest renders the committed page with that
stale module already cached. Each test in that file restores the
previous `sys.modules` entries, so the rest of the suite keeps the
installed wheel.
