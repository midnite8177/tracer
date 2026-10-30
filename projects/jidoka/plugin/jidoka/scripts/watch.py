#!/usr/bin/env python3
"""Waits, in the background, until something changes that the factory can act on.

`watch.py <epic>` is what the manager starts when nothing can run: every task of the epic is parked or blocked,
or the epic is paused or parked, and no worker of the manager is running. Run it from inside any checkout of the
repo. It takes a snapshot of the epic's beads, then reads them again every --interval seconds, and exits at the
first of these, printing one JSON object with `epic`, `event` and `bead`:
  unparked   a bead that carried the `human` label when the watch began, the epic or one of its tasks, no longer
             does.
  new-task   the epic holds a task it did not hold when the watch began.
  merged     a task that was open when the watch began is closed.
  pause-over the epic was paused when the watch began, and the pause's wait is over. The manager has no clock of
             its own to wait on, so the watcher keeps it.
The watcher ends on no other ground, so a factory that waits for a human takes no turn until one of these
happens. The manager then runs `scheduler.py carry-on`. The first line on stderr says the watch began, so a
caller knows the snapshot is taken.

Exit codes:
  0  a change was found.
  1  it could not read the beads, with the reason on stderr.
  2  a usage error.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import clock
import pause
import repo_settings
from commands import COMMAND_TIMEOUT_SECONDS, CommandError, is_labeled_for_human
from epic_reader import CLOSED, EpicReadError, read_epic, shown_epic

UNPARKED = "unparked"
NEW_TASK = "new-task"
MERGED = "merged"
PAUSE_OVER = "pause-over"
STOPPED = "stopped"
CHANGE_EVENTS = frozenset({UNPARKED, NEW_TASK, MERGED, PAUSE_OVER})
DEFAULT_INTERVAL_SECONDS = 30


@dataclass(frozen=True)
class Snapshot:
    """What the watch compares: the beads that carry the human label, the epic's tasks and which of them are open,
    and the second the epic's pause ends, when it is paused."""
    parked: frozenset[str]
    tasks: frozenset[str]
    open_tasks: frozenset[str]
    paused_until: int | None


@dataclass(frozen=True)
class Change:
    event: str
    bead: str


@dataclass(frozen=True)
class Pacing:
    """How a watch waits and tells time: its sleep and the wall-clock second. A test hands in fakes so that a
    watch runs without real waiting."""
    sleep: Callable[[float], None]
    now: Callable[[], int]


REAL_PACING = Pacing(time.sleep, clock.now)


def snapshot_of(epic: str, main_tree: Path) -> Snapshot:
    shown = shown_epic(epic, main_tree)
    tasks = read_epic(shown, main_tree).task_beads
    parked = {str(bead["id"]) for bead in [shown, *tasks] if is_labeled_for_human(bead)}
    held = pause.held_by(shown)
    return Snapshot(frozenset(parked), frozenset(str(task["id"]) for task in tasks),
                    frozenset(str(task["id"]) for task in tasks if task.get("status") != CLOSED),
                    held.until if held is not None else None)


def change_between(before: Snapshot, after: Snapshot, now: int) -> Change | None:
    """The first change, in the order of the module's docstring, or None."""
    for bead in sorted(before.parked - after.parked):
        return Change(UNPARKED, bead)
    for bead in sorted(after.tasks - before.tasks):
        return Change(NEW_TASK, bead)
    for bead in sorted(before.open_tasks - after.open_tasks):
        return Change(MERGED, bead)
    if before.paused_until is not None and now >= before.paused_until:
        return Change(PAUSE_OVER, "")
    return None


def watch(epic: str, read: Callable[[], Snapshot], interval_seconds: int, ends_on: frozenset[str],
          should_stop: Callable[[], bool], pacing: Pacing) -> Change:
    """Blocks until a change whose event is in ends_on, and returns it. A change of another event moves the
    baseline past it, and the watch goes on. Returns the STOPPED event once should_stop() is true."""
    if should_stop():
        return Change(STOPPED, "")
    before = read()
    print(f"watch: watching {epic}, every {interval_seconds} seconds", file=sys.stderr, flush=True)
    while True:
        after = read()
        change = change_between(before, after, pacing.now())
        if change is not None:
            if change.event in ends_on:
                return change
            before = after
        pacing.sleep(interval_seconds)
        if should_stop():
            return Change(STOPPED, "")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="watch.py", description="Wait until the epic changes in a way the "
                                                                   "factory can act on.")
    parser.add_argument("epic")
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL_SECONDS,
                        help="seconds between two reads of the beads")
    args = parser.parse_args(argv)
    if args.interval < 1:
        parser.error("--interval needs a whole number of seconds from 1 up")
    try:
        main_tree = repo_settings.main_worktree(Path.cwd(), COMMAND_TIMEOUT_SECONDS)
        change = watch(args.epic, lambda: snapshot_of(args.epic, main_tree), args.interval,
                       CHANGE_EVENTS, lambda: False, REAL_PACING)
    except (EpicReadError, CommandError, repo_settings.SettingsError, OSError) as error:
        print(f"watch: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"epic": args.epic, "event": change.event, "bead": change.bead}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
