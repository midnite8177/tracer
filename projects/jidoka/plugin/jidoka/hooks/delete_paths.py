"""The paths a delete, a new folder or a move changes, read from its words, the Python port of delete_paths.ts.

A command is read only when its options are the few a lap worker may use and each path is named one by one; any
other command, and any path the shell might expand, is left to the lists.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

RM_OPTIONS = "fr"
GIT_RM_OPTIONS = "rq"
GIT_RM_LONG_OPTIONS = ["--cached"]
MKDIR_OPTIONS = "p"
MV_OPTIONS = "f"

EXPANDS = re.compile(r"[*?\[\]{}~$!]")
SHORT_OPTIONS = re.compile(r"-[^-]+")


@dataclass(frozen=True)
class Placed:
    """The paths a placing command takes content from and puts content at: `leaving` are the paths a move takes from,
    `arriving` the paths a folder is made at or a move puts content at. A move into an existing folder puts its
    sources beneath that folder, at a place its words do not name."""
    leaving: list[str]
    arriving: list[str]


def is_short_options(word: str, allowed: str) -> bool:
    return SHORT_OPTIONS.fullmatch(word) is not None and all(letter in allowed for letter in word[1:])


def paths_after(rest: list[str], is_option: Callable[[str], bool]) -> list[str] | None:
    """The paths among the words that follow a command; None when an option is not one `is_option` names, when a path
    could expand to more than one, or when no path is named. A word that starts with a dash is an option, so no path
    can start with one."""
    paths = [word for word in rest if not (word.startswith("-") and is_option(word))]
    stray = any(word.startswith("-") or EXPANDS.search(word) for word in paths)
    return None if stray or not paths else paths


def is_delete(words: list[str]) -> bool:
    """Whether the words are `rm` or `git rm`, whether or not their options and paths are ones a lap worker may use."""
    return words[:1] == ["rm"] or words[:2] == ["git", "rm"]


def deleted_paths(words: list[str]) -> list[str] | None:
    """The paths a delete names when it is `rm` with no option but -f and -r, or `git rm` with no option but -r, -q and
    --cached; None for any other command, and for a delete whose paths cannot be told: a glob, a variable, `~`, a
    `--`, or no path at all."""
    if words[:1] == ["rm"]:
        return paths_after(words[1:], lambda word: is_short_options(word, RM_OPTIONS))
    if words[:2] == ["git", "rm"]:
        return paths_after(words[2:], lambda word: is_short_options(word, GIT_RM_OPTIONS)
                           or word in GIT_RM_LONG_OPTIONS)
    return None


def placed_paths(words: list[str]) -> Placed | None:
    """The paths a command makes folders at or moves files between when it is `mkdir` with no option but -p, `mv` with
    no option but -f, or `git mv` with no option but -f; None for any other command, and for one whose paths cannot be
    told by the delete's rule. A move names its sources and then its destination, so it takes at least two paths."""
    if words[:1] == ["mkdir"]:
        made = paths_after(words[1:], lambda word: is_short_options(word, MKDIR_OPTIONS))
        return None if made is None else Placed(leaving=[], arriving=made)
    if words[:1] == ["mv"]:
        moved = paths_after(words[1:], lambda word: is_short_options(word, MV_OPTIONS))
    elif words[:2] == ["git", "mv"]:
        moved = paths_after(words[2:], lambda word: is_short_options(word, MV_OPTIONS))
    else:
        return None
    if moved is None or len(moved) < 2:
        return None
    return Placed(leaving=moved[:-1], arriving=[moved[-1]])


def changes_folder(words: list[str]) -> bool:
    """Whether the command changes the folder later commands run in, so their relative paths no longer read against
    the worktree."""
    return words[:1] in (["cd"], ["pushd"], ["popd"])
