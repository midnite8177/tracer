"""Tidy, the stage of a pass after test cleanup, which runs no-comments and unslop over the whole epic's diff without
asking anyone.

The scheduler calls `to_run` once every task of an epic is closed and its test cleanup is done. When the epic branch
differs from main in files outside every app's acceptance folder, which is protected, it cuts a detached worktree at
.worktrees/tidy-<epic> from the epic branch's head and hands the scheduler a `tidy` action for a worker on the local
tier. The worker follows the two skills in their unattended mode, asks no question, starts no workers, edits only
those files, commits nothing, and lists the work it found outside them in the scratch folder's discovered-work report,
which `settle` files in the epic. `settle` takes its word that it is done: it refuses, and writes nothing, when the
worktree changed a path outside those files, or when the worktree is gone or at another head than the worker started
from. Otherwise it commits the change as one commit, "No comments and unslop", fast-forwards the epic branch to it
under the merge lock, and with BEADS_ACTOR set to jidoka records on the epic `tidy.state` (done) and posts a comment.
A tidy that changes nothing makes no commit. Validation clears `tidy.state` when it ends red, so the next pass tidies
again.
"""
from __future__ import annotations

from pathlib import Path

import discovered
import pass_support
from commands import SCRATCH_FOLDER, env_as_factory, read_bead, run, set_metadata
from pass_support import Committed, PassError, Stage, StageToRun, accepts_any_change, every_file

STATE_KEY = "tidy.state"
ACTION = "tidy"
AREA = "tidy"


class TidyError(PassError):
    """A reason the tidy writes nothing more, worded for the person who reads stderr."""


STAGE = Stage(name="tidy", action=ACTION, prefix="tidy-", state_key=STATE_KEY,
              commit_message="No comments and unslop", allowed_kind="files the epic added or changed",
              files_key="files", wants=every_file, report=None, error=TidyError)


def worktree_of(epic: str, main_tree: Path) -> Path:
    return STAGE.worktree_of(epic, main_tree)


def to_run(epic: str, shown: dict, branch: str, settings: dict, home: Path, main_tree: Path) -> StageToRun | None:
    """The tidy this pass still owes, or None when it is done or the epic holds no file to tidy. The worktree is cut
    again from the epic branch's head when its folder is gone."""
    return pass_support.to_run(STAGE, epic, shown, branch, settings, home, main_tree)


def discovered_work(epic: str, main_tree: Path) -> list[discovered.Finding]:
    """The work the tidy worker discovered.

    The tidy has no task to block, so a finding placed `blocks` refuses the report, as an unusable report does.
    """
    try:
        findings = discovered.read_findings(worktree_of(epic, main_tree) / SCRATCH_FOLDER)
        if discovered.blockers_in(findings):
            raise discovered.DiscoveryError(f"the tidy has no task to block, so no finding is placed "
                                            f"{discovered.BLOCKS}; place each one {discovered.EPIC} or "
                                            f"{discovered.OUTSIDE}")
    except discovered.DiscoveryError as error:
        raise TidyError(f"the tidy's discovered work cannot be filed, so nothing was written: {error}") from error
    return findings


def settle(epic: str, branch: str, settings: dict, home: Path, main_tree: Path) -> Committed:
    """Commits what the tidy worker left as one commit on the epic branch, records that the tidy is done, and files
    the work the worker discovered. The findings are read first, because settling removes the worktree that holds
    them, and a report that cannot be used refuses the settle."""
    findings = discovered_work(epic, main_tree)
    shown = read_bead(epic, main_tree)
    found = pass_support.owed_in_worktree(STAGE, epic, shown, branch, settings, main_tree)
    settled = pass_support.settle_worktree(found, accepts_any_change, home, main_tree)
    env = env_as_factory()
    run(["bd", "comment", epic, settled.comment(STAGE.commit_message)], main_tree, env)
    run(["bd", "update", epic, *set_metadata((STATE_KEY, pass_support.DONE))], main_tree, env)
    discovered.file_findings(findings, epic, AREA, epic, main_tree)
    return settled
