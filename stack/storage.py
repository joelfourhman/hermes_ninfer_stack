"""Crash-safe JSON checkpoints and process-scoped exclusive locks."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import tempfile
from pathlib import Path


def atomic_json(path: Path, value: dict, *, checksum: bool = False) -> None:
    value = dict(value)
    value.pop("_sha256", None)
    if checksum:
        value["_sha256"] = hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def checked_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        digest = value.pop("_sha256")
        actual = hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        if actual != digest:
            raise ValueError("checksum mismatch")
        return value
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise ValueError(
            f"Checkpoint is corrupt or unreadable: {path.name}; use job recover with a verified snapshot"
        ) from exc


@contextlib.contextmanager
def exclusive(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    try:
        try:
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise ValueError("Another job controller owns this checkpoint") from exc
        yield
    finally:
        handle.close()  # OS releases the lock on normal exit, crash or reboot.
