"""An exclusive lock on a file that the system lets go of when the holder exits, on macOS, Linux and Windows.

macOS and Linux lock the whole file with `flock`. Windows has no `fcntl`, so it locks the first byte with
`msvcrt.locking`, which gives up after ten tries a second apart; the wait goes on until the lock is taken.
"""
from __future__ import annotations

import errno
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

try:
    import fcntl
except ImportError:
    fcntl = None


def acquire(handle) -> None:
    if fcntl is not None:
        fcntl.flock(handle, fcntl.LOCK_EX)
        return
    import msvcrt
    handle.seek(0)
    while True:
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            return
        except OSError as error:
            if error.errno != errno.EDEADLOCK:
                raise


def release(handle) -> None:
    if fcntl is not None:
        fcntl.flock(handle, fcntl.LOCK_UN)
        return
    import msvcrt
    handle.seek(0)
    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


@contextmanager
def exclusive(path: Path) -> Iterator[None]:
    """Holds the lock on the file at path, which is made when it is missing, while the block runs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        acquire(handle)
        try:
            yield
        finally:
            release(handle)
