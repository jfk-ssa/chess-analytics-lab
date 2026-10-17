"""How a checked tool starts its one-shot worker.

Linux asks the kernel to kill the child if this process dies
(`PR_SET_PDEATHSIG`, `SIGKILL`). That needs `libc.so.6`, which macOS does
not have. Other platforms run a watcher: it starts the worker in a new
session, closes its own copies of the standard streams so the pipes stay
the worker's, and if its parent pid changes it kills that session. The
watcher then exits with the worker's status. The 30-second Maia timeout,
the 10-second UCI handshake, and the 30-second checked-tool kill are unchanged.
"""

import sys

# Kept exact: Linux CI and the engine parent-death check depend on this text.
_PARENT_DEATH = (
    "import ctypes, os, sys\n"
    "ctypes.CDLL('libc.so.6').prctl(1, 9)\n"
    "os.execv(sys.argv[1], sys.argv[1:])\n"
)
# Parent-death watch for platforms without prctl. Polls inside the 0.1–0.25s band.
_PARENT_WATCH = (
    "import os, signal, subprocess, sys, time\n"
    "parent = os.getppid()\n"
    "child = subprocess.Popen(sys.argv[1:], start_new_session=True)\n"
    "for fd in (0, 1, 2):\n"
    "    try:\n"
    "        os.close(fd)\n"
    "    except OSError:\n"
    "        pass\n"
    "while True:\n"
    "    if os.getppid() != parent:\n"
    "        try:\n"
    "            os.killpg(child.pid, signal.SIGKILL)\n"
    "        except OSError:\n"
    "            pass\n"
    "        child.wait()\n"
    "        os._exit(1)\n"
    "    code = child.poll()\n"
    "    if code is not None:\n"
    "        os._exit(code if code >= 0 else 128 - code)\n"
    "    time.sleep(0.2)\n"
)


def worker_command(argv: list[str]) -> list[str]:
    """Return the argv used to start a worker. `argv[0]` is the program."""
    script = _PARENT_DEATH if sys.platform == "linux" else _PARENT_WATCH
    return [sys.executable, "-c", script, *argv]
