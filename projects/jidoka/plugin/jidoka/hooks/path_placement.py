"""Where a path really lands, the Python port of the part of path_placement.ts that the profile guard needs.

Paths are POSIX paths: a path is absolute when it starts with `/`, and `\\` is a character of a name. A path that no
rule here can place is reported as landing nowhere, which the guard reads as outside the worktree, so a path it cannot
read is refused and never allowed.
"""
from __future__ import annotations

import os
from collections.abc import Callable


def is_absolute(path: str) -> bool:
    return path.startswith("/")


def spelled(path: str, base: str) -> str | None:
    """The path with its `.` and `..` segments resolved, a relative one taken from `base`; None when `..` climbs above
    the root or the path is no absolute path once read against `base`."""
    whole = path if is_absolute(path) else f"{base.rstrip('/')}/{path}"
    if not is_absolute(whole):
        return None
    segments: list[str] = []
    for segment in whole.split("/"):
        if segment in ("", "."):
            continue
        if segment != "..":
            segments.append(segment)
        elif segments:
            segments.pop()
        else:
            return None
    return "/" + "/".join(segments)


def contains(root: str, file: str) -> bool:
    return file == root or file.startswith(root if root.endswith("/") else root + "/")


def real_location(path: str, base: str) -> str | None:
    """Where `path` really lands: the nearest part of it that exists is resolved through its links and the rest is
    placed beneath that, so a file not made yet sits where its folder is. None where nothing of the path can be
    resolved, or where a link on it leads nowhere, because a write would then land wherever the link points."""
    lexical = spelled(path, base)
    if lexical is None:
        return None
    parts = lexical.split("/")
    for cut in range(len(parts), 0, -1):
        head = "/".join(parts[:cut]) or "/"
        try:
            real = os.path.realpath(head, strict=True)
        except (FileNotFoundError, NotADirectoryError):
            if os.path.islink(head):
                return None
            continue
        except (OSError, RuntimeError):
            return None
        return spelled("/".join(parts[cut:]), real)
    return None


def as_written(location: str) -> str:
    return location


def is_beneath_by(path: str, folder: str, worktree: str, comparable: Callable[[str], str]) -> bool:
    root = real_location(folder, worktree)
    file = real_location(path, worktree)
    if root is None or file is None:
        return False
    return contains(comparable(root), comparable(file))


def is_really_beneath(path: str, folder: str, worktree: str) -> bool:
    """Whether `path` really lands inside `folder`, whatever links lie on the way. Both are read against `worktree`."""
    return is_beneath_by(path, folder, worktree, as_written)


def is_really_beneath_ignoring_case(path: str, folder: str, worktree: str) -> bool:
    """Whether `path` really lands inside `folder`, compared without case, as a folder that bars writes must, since a
    file system can tell `Specs` from `specs` or not."""
    return is_beneath_by(path, folder, worktree, str.casefold)
