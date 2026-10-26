"""Gives a linked worktree the main checkout's private glossary and ADR folder.

Private docs are untracked, so a new worktree lacks them. Each worktree gets a link at each private path to the
main checkout's copy, so every worktree shares one copy and an edit in any of them changes it. Repo settings that
are missing or keep the docs committed leave the worktree as git made it, and a path the main checkout lacks gets
no link.
"""
from __future__ import annotations

import os
from pathlib import Path

import repo_settings


class ClashError(Exception):
    """A worktree holds its own file or folder at a private path, worded for the person who reads stderr."""


def private_paths(settings: dict) -> list[str]:
    if settings.get(repo_settings.GLOSSARY_AND_ADRS) != repo_settings.PRIVATE:
        return []
    return [settings[key] for key in repo_settings.DOC_PATH_KEYS if repo_settings.is_repo_path(settings.get(key))]


def links_to(link: Path, target: Path) -> bool:
    return link.is_symlink() and Path(os.readlink(link)) == target


def share(main_tree: Path, worktree: Path, home: Path) -> None:
    """Links the worktree to the main checkout's private docs, and refuses before linking any when one clashes."""
    settings = repo_settings.load(repo_settings.settings_path(home, main_tree))
    paths = private_paths(settings)
    if not paths:
        return
    repo_settings.rehide_private_docs(main_tree, settings)
    links = [(worktree / path, main_tree / path) for path in paths if (main_tree / path).exists()]
    clashes = [link for link, target in links if os.path.lexists(link) and not links_to(link, target)]
    if clashes:
        raise ClashError(f"the worktree holds its own {' and '.join(map(str, clashes))}, where start puts a link to "
                         "the main checkout's private copy. Move it aside and start again")
    for link, target in links:
        if not links_to(link, target):
            link.parent.mkdir(parents=True, exist_ok=True)
            link.symlink_to(target, target_is_directory=target.is_dir())
