"""What resuming a stopped factory reads from the machine and from git, where beads holds only a record.

The scheduler imports it for the steps of a resume, and the session-start hook imports it to name the epics a
factory stopped on. No command line runs it.

A factory is stopped on an epic when the epic is one the factory runs, it has open tasks that do not wait on the
human, the factory has started on it before, and its heartbeat is not fresh. A parked epic, one at the acceptance
gate and one whose only open tasks are parked wait on the human, not on a restart.

An orphan worker is a process that a dead host left running in a lap's worktree: its parent is the init process, so
no host owns it. A person's shell or editor in the worktree has a parent and is left alone.

A merge lock is dead when the process that took it is gone. The lock file holds that process's id; a file with no
readable id is dead once it is older than LOCK_UNRECORDED_SECONDS, which a live holder never needs to write it.
"""
from __future__ import annotations

import json
import os
import signal
import time
from dataclasses import dataclass
from pathlib import Path

import heartbeat
import notify
import park
from commands import CommandError, bd_show, capture, head_of, run
from handoff import EPIC_TYPE, child_ids, shown_beads
from land import merge_lock
from merge_gate import contains

FACTORY_COMMAND = "/jidoka:factory"
INIT_PROCESS = 1
LOCK_UNRECORDED_SECONDS = 60
STOP_WAIT_SECONDS = 3.0
STOP_POLL_SECONDS = 0.05
LAP_STAGE_KEY = "lap.stage"


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


def process_is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


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
        dead = not process_is_alive(holder)
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


def parent_of(pid: int) -> int | None:
    done = capture(["ps", "-o", "ppid=", "-p", str(pid)], Path.cwd(), None)
    try:
        return int(done.stdout.strip())
    except ValueError:
        return None


def pids_with_cwd_in(worktree: Path) -> list[int]:
    """The processes whose working folder is the worktree or a folder under it, as lsof lists them."""
    root = worktree.resolve()
    try:
        done = capture(["lsof", "-a", "-d", "cwd", "-Fpn"], Path.cwd(), None)
    except CommandError:
        return []
    found: list[int] = []
    pid: int | None = None
    for line in done.stdout.splitlines():
        if line.startswith("p") and line[1:].isdigit():
            pid = int(line[1:])
        elif line.startswith("n") and pid is not None:
            folder = Path(line[1:])
            if folder == root or root in folder.parents:
                found.append(pid)
    return found


def stop_orphans(worktree: Path) -> list[int]:
    """Stops each orphan worker left in the worktree and returns their ids.

    Each gets SIGTERM, and SIGKILL when it is still there after STOP_WAIT_SECONDS.
    """
    orphans = [pid for pid in pids_with_cwd_in(worktree) if pid != os.getpid() and parent_of(pid) == INIT_PROCESS]
    for pid in orphans:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            continue
        deadline = time.monotonic() + STOP_WAIT_SECONDS
        while process_is_alive(pid) and time.monotonic() < deadline:
            time.sleep(STOP_POLL_SECONDS)
        if process_is_alive(pid):
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    return orphans


def merged_head(branch: str, title: str, epic_branch: str, main_tree: Path) -> str | None:
    """The head of the lap branch when git shows it merged into the epic branch, and None otherwise.

    A lap that is merged has its head inside the epic branch and its commit named by the task's title, as the
    scheduler commits a build. A lap branch cut from the epic branch and not built yet also sits inside it, but
    its head is another task's commit.
    """
    lap_head = head_of(f"refs/heads/{branch}", main_tree)
    epic_head = head_of(f"refs/heads/{epic_branch}", main_tree)
    if lap_head is None or epic_head is None or not contains(lap_head, epic_head, main_tree):
        return None
    subject = run(["git", "log", "-1", "--format=%s", lap_head], main_tree, None).strip()
    return lap_head if subject == title else None


def prune_worktrees(main_tree: Path) -> None:
    """Drops the records of worktrees whose folders are gone, so a lap whose folder was lost gets a new one."""
    run(["git", "worktree", "prune"], main_tree, None)


def labels_of(bead: dict) -> list[str]:
    return [str(label) for label in bead.get("labels") or []]


def has_started(children: list[dict], home: Path, epic: str) -> bool:
    """True when the factory has run on the epic: a task holds a lap, or the epic has a heartbeat on record."""
    held_a_lap = any((bead.get("metadata") or {}).get(LAP_STAGE_KEY) for bead in children)
    return held_a_lap or heartbeat.heartbeat_path(home, epic).is_file()


def stopped_on(epic: dict, home: Path, main_tree: Path, now: int) -> StoppedEpic | None:
    epic_id = str(epic["id"])
    if not notify.is_running(epic) or heartbeat.is_fresh(home, epic_id, now):
        return None
    children = shown_beads(child_ids(epic_id, main_tree), main_tree)
    open_tasks = [bead for bead in children
                  if bead.get("issue_type") != EPIC_TYPE and not notify.is_closed(bead)]
    waiting_on_a_restart = [bead for bead in open_tasks if park.HUMAN_LABEL not in labels_of(bead)]
    if not waiting_on_a_restart or not has_started(children, home, epic_id):
        return None
    return StoppedEpic(epic_id, str(epic.get("title") or epic_id), len(open_tasks))


def stopped_epics(home: Path, main_tree: Path, now: int) -> list[StoppedEpic]:
    """The epics the factory stopped on, by id."""
    listing = run(["bd", "list", "--label", "factory", "--type", EPIC_TYPE, "--limit", "0", "--json"], main_tree, None)
    listed = json.loads(listing or "[]")
    ids = sorted(str(item["id"]) for item in listed if isinstance(item, dict) and item.get("id"))
    shown = [bd_show(epic, main_tree) for epic in ids]
    stopped = (stopped_on(epic, home, main_tree, now) for epic in shown if epic is not None)
    return [found for found in stopped if found is not None]
