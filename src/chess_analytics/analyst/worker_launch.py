"""How a checked tool starts its one-shot worker.

Linux asks the kernel to kill the child if this process dies
(`PR_SET_PDEATHSIG`, `SIGKILL`). macOS and other platforms have no `prctl`,
and `libc.so.6` is not there, so the same wrapper raises `OSError` before
`exec` and the tool never starts. Those platforms launch the worker
directly.

A child of the process that set the timeout is still killed on the way
out: 30 seconds for the Maia worker, 10 seconds for an engine that never
finishes the UCI handshake. The 30-second checked-tool kill is a different
process. On Linux the parent-death signal kills the engine or Maia worker
with that tool process. On macOS the signal stops at the tool process, so
the grandchild can outlive it. There is no equivalent one-line guard.
"""

import sys

# Kept exact: Linux CI and the engine parent-death check depend on this text.
_PARENT_DEATH = (
    "import ctypes, os, sys\n"
    "ctypes.CDLL('libc.so.6').prctl(1, 9)\n"
    "os.execv(sys.argv[1], sys.argv[1:])\n"
)


def worker_command(argv: list[str]) -> list[str]:
    """Return the argv used to start a worker. `argv[0]` is the program."""
    if sys.platform == "linux":
        return [sys.executable, "-c", _PARENT_DEATH, *argv]
    return list(argv)
