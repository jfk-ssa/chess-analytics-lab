"""Load ``chess_analytics`` from this repository on every hosted rerun.

Community Cloud installs ``hosted/requirements.txt`` and does not install
this project. A push that leaves that file unchanged copies the new files
and reruns ``hosted/dashboard.py`` in the same interpreter. Python keeps
the first ``chess_analytics`` import in ``sys.modules``. ``hosted/bi.py``
is executed from disk on that rerun, so it can import a name the cached
module does not have. Modules already loaded from ``src/`` are reloaded
in place. A copy loaded from anywhere else is replaced.
"""

from __future__ import annotations

import hashlib
import importlib
import sys
import threading
import types
from pathlib import Path
from typing import Any

_STATE = "_hosted_repository_import_state"


class RepositoryImportError(Exception):
    """``src/chess_analytics`` could not be imported for the hosted page."""


def _new_state() -> types.ModuleType:
    created = types.ModuleType(_STATE)
    created.__dict__["payload"] = {"lock": threading.Lock(), "digest": None, "root": None}
    return created


def _payload() -> dict[str, Any]:
    """Process-wide stamp. The hosted entrypoint re-executes this file.

    ``setdefault`` publishes a fully initialized module. Callers use the
    winner, including when two sessions construct a state together.
    """
    created = _new_state()
    winner = sys.modules.setdefault(_STATE, created)
    if isinstance(winner, types.ModuleType):
        raw = winner.__dict__.get("payload")
        if isinstance(raw, dict) and hasattr(raw.get("lock"), "acquire"):
            return raw
    return created.__dict__["payload"]


def _source_root() -> Path:
    return Path(__file__).resolve().parents[1] / "src" / "chess_analytics"


def _failure(src: Path, detail: str) -> str:
    cube = src / "chess_analytics" / "dashboard_cube.py"
    return (
        "The hosted page could not load the cube module from "
        f"{cube}. Community Cloud reruns this app in the same Python process "
        "when hosted/requirements.txt is unchanged, and a cached import would "
        f"hide this file. {detail}"
    )


def _source_digest(root: Path) -> str:
    paths = sorted(path for path in root.rglob("*.py") if "__pycache__" not in path.parts)
    if not paths:
        raise RepositoryImportError(
            _failure(root.parent, "the chess_analytics directory has no Python files.")
        )
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _under_root(path: str, root: Path) -> bool:
    try:
        Path(path).resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _loaded_from(root: Path) -> bool:
    saw = False
    resolved = root.resolve()
    for name, module in list(sys.modules.items()):
        if name != "chess_analytics" and not name.startswith("chess_analytics."):
            continue
        saw = True
        file = getattr(module, "__file__", None)
        if not isinstance(file, str) or not _under_root(file, resolved):
            return False
    return saw


def _purge() -> None:
    for name in list(sys.modules):
        if name == "chess_analytics" or name.startswith("chess_analytics."):
            del sys.modules[name]


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    return True


def _drop_bytecode(root: Path) -> bool:
    """Remove in-tree ``.pyc`` files.

    A ``__pycache__`` symlink whose target leaves ``src/chess_analytics`` is
    skipped. Return False when an in-tree ``.pyc`` could not be removed, so
    the caller does not treat this import as fresh.
    """
    cleared = True
    resolved_root = root.resolve()
    for cache in root.rglob("__pycache__"):
        if not cache.is_dir() or not _inside(cache, resolved_root):
            continue
        for compiled in cache.glob("*.pyc"):
            if not _inside(compiled, resolved_root):
                continue
            try:
                compiled.unlink()
            except OSError:
                cleared = False
    return cleared


def _reloadable(root: Path) -> list[types.ModuleType] | None:
    """Modules already loaded from ``root``, parents before children.

    None when any cached ``chess_analytics`` module is missing a loader or
    was loaded from outside the tree. Those copies are replaced.
    """
    found: list[tuple[str, types.ModuleType]] = []
    for name, module in list(sys.modules.items()):
        if name != "chess_analytics" and not name.startswith("chess_analytics."):
            continue
        if not isinstance(module, types.ModuleType):
            return None
        file = getattr(module, "__file__", None)
        if not isinstance(file, str) or not _under_root(file, root):
            return None
        spec = getattr(module, "__spec__", None)
        loader = getattr(spec, "loader", None) if spec is not None else None
        if loader is None or not hasattr(loader, "exec_module"):
            return None
        found.append((name, module))
    if not any(name == "chess_analytics.dashboard_cube" for name, _module in found):
        return None
    found.sort(key=lambda item: (item[0].count("."), item[0]))
    return [module for _name, module in found]


def _insert_src(src: str) -> None:
    if src in sys.path:
        sys.path.remove(src)
    sys.path.insert(0, src)


def _bind():
    from chess_analytics.dashboard_cube import bounds, connect, cube_path
    from chess_analytics.public_extract import extract_path, load_extract, table_rows

    return extract_path, load_extract, table_rows, bounds, connect, cube_path


def _require_repository_cube(src: Path, root: Path) -> None:
    loaded = sys.modules.get("chess_analytics.dashboard_cube")
    file = getattr(loaded, "__file__", None)
    if not isinstance(file, str) or not _under_root(file, root):
        raise RepositoryImportError(
            _failure(src, f"The import did not come from the repository copy ({file}).")
        )


def _import_from_src(src: Path, root: Path) -> None:
    saved_path = list(sys.path)
    _insert_src(str(src))
    try:
        _bind()
    except ImportError as exc:
        raise RepositoryImportError(_failure(src, f"The repository import failed: {exc}")) from exc
    finally:
        sys.path[:] = saved_path
    _require_repository_cube(src, root)


def _reload(src: Path, root: Path) -> bool:
    """Refresh the package. Return False when an in-tree ``.pyc`` remains.

    Modules already loaded from ``root`` are reloaded in place so another
    session still finds them in ``sys.modules``. ``importlib.reload`` finds
    the spec again, so ``src/`` stays first on ``sys.path`` for that search.
    Without it the finder binds an installed copy into the same module.
    A copy from outside the tree is removed and imported from ``src/``.
    """
    modules = _reloadable(root)
    cleared = _drop_bytecode(root)
    importlib.invalidate_caches()
    if modules is None:
        _purge()
        _import_from_src(src, root)
        return cleared
    saved_path = list(sys.path)
    _insert_src(str(src))
    try:
        try:
            for module in modules:
                importlib.reload(module)
            _require_repository_cube(src, root)
        except (ImportError, OSError, AttributeError, TypeError, RepositoryImportError):
            _purge()
            _import_from_src(src, root)
    finally:
        sys.path[:] = saved_path
    return cleared


def import_repository_package():
    """Import the extract reader and the cube from this checkout's ``src/``.

    Returns ``extract_path``, ``load_extract``, ``table_rows``, ``bounds``,
    ``connect``, and ``cube_path``. Raises ``RepositoryImportError``, which
    is not an ``ImportError``. Community Cloud redacts an uncaught import
    failure, so the page shows this exception's text itself.
    """
    root = _source_root()
    src = root.parent
    payload = _payload()
    with payload["lock"]:
        try:
            digest = _source_digest(root)
        except OSError as exc:
            raise RepositoryImportError(
                _failure(src, f"The repository source could not be read: {exc}")
            ) from exc
        fresh = (
            payload["digest"] == digest
            and payload["root"] == str(root.resolve())
            and _loaded_from(root)
        )
        if not fresh and _reload(src, root):
            payload["digest"] = digest
            payload["root"] = str(root.resolve())
        return _bind()
