#!/usr/bin/env python3
"""UCI process that sleeps on go, so the worker kill can reap it."""

import os
import sys
import time
from pathlib import Path

Path("engine-hang.pid").write_text(str(os.getpid()))


def main() -> int:
    while True:
        line = sys.stdin.readline()
        if not line:
            return 0
        text = line.strip()
        if text == "uci":
            print("id name Hang Engine 0", flush=True)
            print("option name Threads type spin default 1 min 1 max 512", flush=True)
            print("option name Hash type spin default 16 min 1 max 1024", flush=True)
            print("option name Clear Hash type button", flush=True)
            print("uciok", flush=True)
        elif text == "isready":
            print("readyok", flush=True)
        elif text == "quit":
            return 0
        elif text.startswith("go"):
            time.sleep(3600)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
