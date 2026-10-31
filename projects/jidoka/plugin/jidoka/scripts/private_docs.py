"""Gives a linked worktree the main checkout's private glossary and ADR folder.

Private docs are untracked, so a new worktree lacks them. Each worktree gets a link at each private path to the
main checkout's copy, so every worktree shares one copy and an edit in any of them changes it. Repo settings that
are missing or keep the docs committed leave the worktree as git made it, and a path the main checkout lacks gets
no link.
"""
from __future__ import annotations

import os
from pathlib import Path

import links
import repo_settings
import settings_reader


class ClashError(Exception):
    """A worktree cannot get its links, because it holds its own file or folder at a private path or because the
    account cannot make links, worded for the person who reads stderr."""


def private_paths(settings: dict) -> list[str]:
    if settings.get(settings_reader.GLOSSARY_AND_ADRS) != settings_reader.PRIVATE:
        return []
    return [settings[key] for key in settings_reader.DOC_PATH_KEYS
            if settings_reader.is_repo_path(settings.get(key))]


def share(main_tree: Path, worktree: Path, home: Path) -> None:
    """Links the worktree to the main checkout's private docs, and refuses before linking any when one clashes."""
    settings = settings_reader.read_settings(home, main_tree)
    paths = private_paths(settings)
    if not paths:
        return
    repo_settings.rehide_private_docs(main_tree, settings)
    wanted = [(worktree / path, main_tree / path) for path in paths if (main_tree / path).exists()]
    clashes = [link for link, target in wanted if os.path.lexists(link) and not links.points_to(link, target)]
    if clashes:
        raise ClashError(f"the worktree holds its own {' and '.join(map(str, clashes))}, where start puts a link to "
                         "the main checkout's private copy. Move it aside and start again")
    for link, target in wanted:
        if not links.points_to(link, target):
            link.parent.mkdir(parents=True, exist_ok=True)
            try:
                links.create(link, target, target.is_dir())
            except links.LinkError as error:
                raise ClashError(str(error)) from error
