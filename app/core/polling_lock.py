"""Prevent duplicate polling processes on one computer for a given token."""

import hashlib
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def polling_lock(token: str, directory: Path | None = None) -> Iterator[None]:
    folder = directory or Path(tempfile.gettempdir()) / "submate-polling"
    folder.mkdir(parents=True, exist_ok=True)
    filename = hashlib.sha256(token.encode()).hexdigest() + ".lock"
    with (folder / filename).open("a+b") as handle:
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise RuntimeError("Another local process is polling this bot.") from None
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
