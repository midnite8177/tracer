"""Ending the laps of an epic that the human drops at the acceptance gate.

A lap that is still open on one of the epic's tasks ends interrupted, as a stop ends it: the task is open with no
assignee, and its worktree and branch stay. The epic is closed and no longer held by the factory, so nothing gives
the task another lap.
"""
from __future__ import annotations

from pathlib import Path

import lap_record
from commands import env_as_git_user, run
from epic_reader import child_ids, shown_beads

DROPPED_PREFIX = "Interrupted: the human dropped the epic at the acceptance gate"


def end_laps(epic: str, main_tree: Path) -> list[str]:
    """Ends every open lap of the epic's tasks; returns the ids of their tasks."""
    env = env_as_git_user(main_tree)
    ended = []
    for bead in shown_beads(child_ids(epic, main_tree), main_tree):
        lap = lap_record.open_lap(bead)
        if lap is None:
            continue
        run(["bd", "comment", lap.task, f"{DROPPED_PREFIX}, during the {lap.stage}. The worktree {lap.worktree} and "
                                        f"the branch {lap.branch} keep the work."], main_tree, env)
        run(["bd", "update", lap.task, *lap_record.resting(lap_record.INTERRUPTED)], main_tree, env)
        ended.append(lap.task)
    return ended
