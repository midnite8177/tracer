"""Symbolic links that work the same on macOS and on Windows.

Windows lets a person without administrator rights make a symbolic link only when Developer Mode is on. Without it
the link call fails with error 1314, and create turns that failure into a LinkError that says how to turn the mode on.
"""
from __future__ import annotations

import os
from pathlib import Path

PRIVILEGE_NOT_HELD = 1314
LONG_PATH_PREFIX = "\\\\?\\"


class LinkError(Exception):
    """A link that could not be made, worded for the person who reads stderr."""


def refusal(link: Path, error: OSError) -> LinkError | None:
    """The LinkError for an error that means Windows lacks the right to make links, and None for any other error."""
    if getattr(error, "winerror", None) != PRIVILEGE_NOT_HELD:
        return None
    return LinkError(f"this account cannot make the symbolic link {link}. Turn on Developer Mode in Windows "
                     "(Settings, System, For developers, Developer Mode) and run the command again")


def create(link: Path, target: Path | str, target_is_directory: bool) -> None:
    """Makes `link` a symbolic link to `target`, raising LinkError when Windows lacks the right to make one."""
    try:
        os.symlink(target, link, target_is_directory=target_is_directory)
    except OSError as error:
        refused = refusal(link, error)
        if refused is None:
            raise
        raise refused from error


def points_to(link: Path, target: Path) -> bool:
    """Whether `link` is a symbolic link to `target`; Windows reports a target with a long-path prefix."""
    if not link.is_symlink():
        return False
    found = os.readlink(link)
    if found.startswith(LONG_PATH_PREFIX):
        found = found[len(LONG_PATH_PREFIX):]
    return Path(found) == target
