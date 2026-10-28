"""Tidy, the stage of a pass after test cleanup, which runs no-comments and unslop over the whole epic's diff without
asking anyone.

The scheduler calls `to_run` once every task of an epic is closed and its test cleanup is done. When the epic branch
differs from main in files outside every app's acceptance folder, which is protected, it cuts a detached worktree at
.worktrees/tidy-<epic> from the epic branch's head and hands the scheduler a `tidy` action for a worker on the local
tier. The worker follows the two skills in their unattended mode, asks no question, starts no workers, edits only
those files, commits nothing, and lists the work it found outside them in the scratch folder's discovered-work report,
which the scheduler files. `settle` takes its word that it is done: it refuses, and writes nothing, when the worktree
changed a path outside those files, or when the worktree is gone or at another head than the worker started from.
Otherwise it commits the change as one commit, "No comments and unslop", fast-forwards the epic
branch to it under the merge lock, and with BEADS_ACTOR set to jidoka records on the epic `tidy.state` (done) and posts
a comment. A tidy that changes nothing makes no commit. Validation clears `tidy.state` when it ends red, so the next
pass tidies again.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pass_support
from commands import bd_show, env_as_factory, run, set_metadata
from pass_support import PassError, Stage, StageToRun, accepts_any_change, every_file

STATE_KEY = "tidy.state"
ACTION = "tidy"


class TidyError(PassError):
    """A reason the tidy writes nothing more, worded for the person who reads stderr."""


STAGE = Stage(name="tidy", action=ACTION, prefix="tidy-", state_key=STATE_KEY,
              commit_message="No comments and unslop", allowed_kind="files the epic added or changed",
              files_key="files", wants=every_file, report=None, error=TidyError)


@dataclass(frozen=True)
class Tidied:
    """What a settled tidy did: the commit the epic branch now ends with, or its old head when nothing changed, and
    the files the commit changed."""
    head: str
    changed: list[str]

    def fields(self) -> dict:
        return {"head": self.head, "changed": self.changed}


def worktree_of(epic: str, main_tree: Path) -> Path:
    return STAGE.worktree_of(epic, main_tree)


def to_run(epic: str, shown: dict, branch: str, settings: dict, home: Path, main_tree: Path) -> StageToRun | None:
    """The tidy this pass still owes, or None when it is done or the epic holds no file to tidy. The worktree is cut
    again from the epic branch's head when its folder is gone."""
    return pass_support.to_run(STAGE, epic, shown, branch, settings, home, main_tree)


def settle(epic: str, branch: str, settings: dict, home: Path, main_tree: Path) -> Tidied:
    """Commits what the tidy worker left as one commit on the epic branch and records that the tidy is done."""
    shown = bd_show(epic, main_tree)
    if shown is None:
        raise TidyError(f"bd show printed nothing usable for {epic}")
    found = pass_support.owed_in_worktree(STAGE, epic, shown, branch, settings, main_tree)
    settled = pass_support.settle_worktree(found, accepts_any_change, home, main_tree)
    env = env_as_factory()
    run(["bd", "comment", epic, comment_of(settled.changed, settled.head)], main_tree, env)
    run(["bd", "update", epic, *set_metadata((STATE_KEY, pass_support.DONE))], main_tree, env)
    return Tidied(settled.head, settled.changed)


def comment_of(changed: list[str], head: str) -> str:
    if not changed:
        return f"No comments and unslop changed no file, and the epic branch stays at {head}."
    return "\n".join([f"No comments and unslop changed {len(changed)} files, in the commit {head}:",
                      *(f"- {path}" for path in changed)])
