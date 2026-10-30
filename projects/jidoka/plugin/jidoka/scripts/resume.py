"""What resuming a stopped factory reads from the machine and from git, where beads holds only a record.

The scheduler imports it for the steps of a resume, and the session-start hook imports it to name the epics a
factory stopped on. No command line runs it.

A factory is stopped on an epic when the epic is one the factory runs, it has open tasks that do not wait on the
human, the factory has started on it before, and its heartbeat is not fresh. A parked epic, one at the acceptance
gate and one whose only open tasks are parked wait on the human, not on a restart.

An orphan worker is a process that a dead host left running in a lap's worktree: its parent is the init process, or on
Windows a process that has ended, so no host owns it. A person's shell or editor in the worktree has a parent and is left alone.

A merge lock is dead when the process that took it is gone. The lock file holds that process's id; a file with no
readable id is dead once it is older than LOCK_UNRECORDED_SECONDS, which is longer than a live holder needs to write it.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import heartbeat
import lap_record
import processes
from commands import FACTORY_LABEL, bd_list, bd_show, is_labeled_for_human, metadata_of, run
from epic_branch import branch_head
from epic_reader import EPIC_TYPE, read_epic
from epics import is_running
from land import merge_lock
from merge_gate import contains

FACTORY_COMMAND = "/jidoka:factory"
LOCK_UNRECORDED_SECONDS = 60


@dataclass(frozen=True)
class StoppedEpic:
    """An epic the factory stopped on: its id, its title, and how many tasks it has open."""
    id: str
    title: str
    open_tasks: int

    def line(self) -> str:
        plural = "task" if self.open_tasks == 1 else "tasks"
        return (f"jidoka: {self.title} ({self.id}) stopped with {self.open_tasks} open {plural} left. "
                f"Resume it with {FACTORY_COMMAND} {self.id}")


def recorded_holder(lock: Path) -> int | None:
    try:
        return int(lock.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def clear_dead_merge_lock(home: Path, now: float) -> str | None:
    """Removes the merge lock when its holder is gone, and returns a line saying so; None when nothing was cleared."""
    lock = merge_lock(home)
    if not lock.is_file():
        return None
    holder = recorded_holder(lock)
    if holder is not None:
        dead = not processes.is_alive(holder)
    else:
        try:
            dead = now - lock.stat().st_mtime > LOCK_UNRECORDED_SECONDS
        except OSError:
            return None
    if not dead:
        return None
    lock.unlink(missing_ok=True)
    who = f"process {holder}" if holder is not None else "a process that recorded no id"
    return f"the merge lock at {lock} was held by {who}, which is gone, so it is cleared"


def stop_orphans(worktree: Path) -> list[int]:
    """Stops each orphan worker left in the worktree and returns their ids.

    Each gets SIGTERM, and SIGKILL when it is still there after the wait. On Windows each ends at once, with the
    processes it started.
    """
    orphans = processes.orphans_in(worktree, os.getpid())
    for pid in orphans:
        processes.end_process(pid)
    return orphans


def merged_head(branch: str, title: str, epic_branch: str, main_tree: Path) -> str | None:
    """The head of the lap branch when git shows it merged into the epic branch, and None otherwise.

    A lap that is merged has its head inside the epic branch and its commit named by the task's title, as the
    scheduler commits a build. A lap branch cut from the epic branch and not built yet also sits inside it, but
    its head is another task's commit.
    """
    lap_head = branch_head(branch, main_tree)
    epic_head = branch_head(epic_branch, main_tree)
    if lap_head is None or epic_head is None or not contains(lap_head, epic_head, main_tree):
        return None
    subject = run(["git", "log", "-1", "--format=%s", lap_head], main_tree, None).strip()
    return lap_head if subject == title else None


def prune_worktrees(main_tree: Path) -> None:
    """Drops the records of worktrees whose folders are gone, so a lap whose folder was lost gets a new one."""
    run(["git", "worktree", "prune"], main_tree, None)


def has_started(children: list[dict], home: Path, epic: str) -> bool:
    """True when the factory has run on the epic: a task holds a lap, or the epic has a heartbeat on record."""
    held_a_lap = any(lap_record.stage_of(metadata_of(bead)) for bead in children)
    return held_a_lap or heartbeat.heartbeat_path(home, epic).is_file()


def stopped_on(epic: dict, home: Path, main_tree: Path, now: int) -> StoppedEpic | None:
    epic_id = str(epic["id"])
    if not is_running(epic) or heartbeat.is_fresh(home, epic_id, now):
        return None
    held = read_epic(epic, main_tree)
    open_tasks = held.open_task_beads
    waiting_on_a_restart = [bead for bead in open_tasks if not is_labeled_for_human(bead)]
    if not waiting_on_a_restart or not has_started(list(held.children), home, epic_id):
        return None
    return StoppedEpic(epic_id, str(epic.get("title") or epic_id), len(open_tasks))


def stopped_epics(home: Path, main_tree: Path, now: int) -> list[StoppedEpic]:
    """The epics the factory stopped on, by id."""
    listed = bd_list(["--label", FACTORY_LABEL, "--type", EPIC_TYPE, "--limit", "0"], main_tree)
    ids = sorted(str(item["id"]) for item in listed if item.get("id"))
    shown = [bd_show(epic, main_tree) for epic in ids]
    stopped = (stopped_on(epic, home, main_tree, now) for epic in shown if epic is not None)
    return [found for found in stopped if found is not None]
