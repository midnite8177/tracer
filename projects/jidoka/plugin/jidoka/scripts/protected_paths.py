"""Which paths of a repo are protected, and which task may change them.

A protected path is the acceptance folder of an app in the repo settings, or a path inside one. No lap changes a
protected path except the lap of the spec task that its epic records. The merge gate, the lap-protected script, the tidy
and the test cleanup all ask this module, so the rule has one home.
"""
from __future__ import annotations

from pathlib import Path, PurePosixPath

import settings_reader
import specs
from commands import bd_show, parent_of


def folder_of(app: settings_reader.App) -> PurePosixPath | None:
    """The app's acceptance folder, or None when it has none or the setting is no folder inside the repo."""
    if app.acceptance is None or not settings_reader.is_repo_path(app.acceptance):
        return None
    return PurePosixPath(app.acceptance)


def protected_folders(settings: dict) -> list[PurePosixPath]:
    """The acceptance folder of every app in the repo settings that has one."""
    folders = (folder_of(app) for app in settings_reader.apps_of(settings))
    return [folder for folder in folders if folder is not None]


def is_protected(path: str, folders: list[PurePosixPath]) -> bool:
    """True when the path is one of the folders or lies inside one."""
    return any(folder == PurePosixPath(path) or folder in PurePosixPath(path).parents for folder in folders)


def epic_of_task(task: dict, main_tree: Path) -> dict | None:
    """The epic bead the task is a child of, or None for a task with no parent."""
    parent = parent_of(task)
    return bd_show(parent, main_tree) if parent else None


def is_spec_task(task: dict, epic: dict | None) -> bool:
    """True when the task is the spec task that its epic records, the one lap that may change an acceptance folder."""
    return epic is not None and specs.spec_task_of(epic) == str(task.get("id") or "")
