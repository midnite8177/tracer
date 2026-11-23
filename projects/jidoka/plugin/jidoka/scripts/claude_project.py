"""The folder in which Claude Code keeps what it records of a project, as retro.py and the context skill both find it.

Claude Code names that folder after the project's path with every character other than a letter or digit turned into
`-`, under `<config folder>/projects/`. The match here ignores case, since macOS and Windows paths do, and the `-` at
either end of a name, so that both scripts find the same folder.
"""
from __future__ import annotations

import re
from pathlib import Path


def folder_name_of(path: str) -> str:
    """The name Claude Code gives the folder of the project at path."""
    return re.sub(r"[^A-Za-z0-9]", "-", path)


def folder_of(projects: Path, path: str) -> Path | None:
    """The folder under projects that Claude Code keeps for the project at path, or None when projects holds none."""
    wanted = folder_name_of(path).strip("-").lower()
    if not projects.is_dir():
        return None
    for folder in sorted(projects.iterdir()):
        if folder.is_dir() and folder.name.strip("-").lower() == wanted:
            return folder
    return None
