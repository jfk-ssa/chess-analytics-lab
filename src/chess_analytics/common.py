"""Small local filesystem primitives; no credential discovery."""

import fcntl
import hashlib
import json
import os
import shutil
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path


def now():
    return datetime.now(UTC).isoformat()


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def hash_json(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w") as f:
        json.dump(value, f, indent=2, sort_keys=True)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    temp.replace(path)


def read_json(path):
    return json.loads(Path(path).read_text())


def disk_bytes(root):
    return sum(p.stat().st_size for p in Path(root).rglob("*") if p.is_file())


def guard_disk(root, limit, reserve=0):
    if disk_bytes(root) + reserve > limit:
        raise ValueError("generated-data allowance exceeded; preserve artifacts and free space")
    if shutil.disk_usage(root).free < reserve + 100_000_000:
        raise ValueError("insufficient free disk (100 MB safety margin required)")


@contextmanager
def writer_lock(root):
    root.mkdir(parents=True, exist_ok=True)
    with (root / "writer.lock").open("a") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as e:
            raise ValueError("another local writer owns this data directory") from e
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
