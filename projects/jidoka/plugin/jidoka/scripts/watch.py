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
  room-freed a ready task of the epic can open, by the rule slots.py holds and the scheduler applies: another
             running epic freed a slot on the machine or an area of the epic's repo, or let go of the slot that
             its fresh heartbeat reserved. `bead` is the first such task in the order laps open. A task that can
             open when the watch begins ends it at once, because the room freed after the scheduler's last call
             and before the first snapshot. An epic that is paused, parked or held by the brake has no ready task
             to open, so it never ends on this.
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
import dataclasses
import json
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import caps
import clock
import pause
import settings_reader
import rules
import slots
from commands import COMMAND_TIMEOUT_SECONDS, CommandError, is_labeled_for_human, metadata_of
from epic_reader import CLOSED, Epic, EpicReadError, by_priority, read_epic, shown_epic
from lap_record import area_of, open_lap

UNPARKED = "unparked"
NEW_TASK = "new-task"
MERGED = "merged"
PAUSE_OVER = "pause-over"
ROOM_FREED = "room-freed"
STOPPED = "stopped"
CHANGE_EVENTS = frozenset({UNPARKED, NEW_TASK, MERGED, PAUSE_OVER, ROOM_FREED})
DEFAULT_INTERVAL_SECONDS = 30


@dataclass(frozen=True)
class Snapshot:
    """What the watch compares: the beads that carry the human label, the epic's tasks and which of them are open,
    the second the epic's pause ends when it is paused, and the ready tasks that a lap would open for now, in the
    order laps open. A paused, parked or braked epic opens none."""
    parked: frozenset[str]
    tasks: frozenset[str]
    open_tasks: frozenset[str]
    paused_until: int | None
    openable: tuple[str, ...]


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


def openable_tasks(epic: Epic, home: Path, main_tree: Path, now: int) -> tuple[str, ...]:
    """The ids of the ready tasks that the scheduler would open a lap for at `now`, in the order it opens them. The
    machine beside the epic is the one slots.py reads, and the epic's limit is the one the scheduler applies."""
    settings = settings_reader.read_settings(home, main_tree)
    limits = rules.lap_limits(epic.shown, settings, home)
    machine, _ = slots.machine_beside(slots.Standing(home, epic.id, main_tree, limits.machine, now))
    held = [lap for lap in map(open_lap, epic.open_task_beads) if lap is not None]
    candidates = [slots.Candidate(str(task["id"]), area_of(metadata_of(task)))
                  for task in sorted(epic.ready_task_beads, key=by_priority)]
    return tuple(placed.task for placed in machine.place(held, candidates, limits.epic))


def snapshot_of(epic: str, main_tree: Path, home: Path, now: int) -> Snapshot:
    """The epic as the beads show it at `now`, and which of its ready tasks the machine has room for."""
    shown = shown_epic(epic, main_tree)
    read = read_epic(shown, main_tree)
    tasks = read.task_beads
    parked = {str(bead["id"]) for bead in [shown, *tasks] if is_labeled_for_human(bead)}
    held = pause.held_by(shown)
    stands_still = held is not None or is_labeled_for_human(shown) or caps.brake_of(shown).is_on
    openable = () if stands_still else openable_tasks(read, home, main_tree, now)
    return Snapshot(frozenset(parked), frozenset(str(task["id"]) for task in tasks),
                    frozenset(str(task["id"]) for task in tasks if task.get("status") != CLOSED),
                    held.until if held is not None else None, openable)


def change_between(before: Snapshot, after: Snapshot, now: int) -> Change | None:
    """The first change, in the order of the module's docstring, or None."""
    for bead in sorted(before.parked - after.parked):
        return Change(UNPARKED, bead)
    for bead in sorted(after.tasks - before.tasks):
        return Change(NEW_TASK, bead)
    for bead in sorted(before.open_tasks - after.open_tasks):
        return Change(MERGED, bead)
    for bead in after.openable:
        if bead not in before.openable:
            return Change(ROOM_FREED, bead)
    if before.paused_until is not None and now >= before.paused_until:
        return Change(PAUSE_OVER, "")
    return None


def watch(epic: str, read: Callable[[], Snapshot], interval_seconds: int, ends_on: frozenset[str],
          should_stop: Callable[[], bool], pacing: Pacing) -> Change:
    """Blocks until a change whose event is in ends_on, and returns it. A change of another event moves the
    baseline past it, and the watch goes on. Returns the STOPPED event once should_stop() is true.

    The first snapshot is compared with itself as if no task could open, because the caller ran the scheduler
    first and so any task that can open now got its room after that call."""
    if should_stop():
        return Change(STOPPED, "")
    after = read()
    before = dataclasses.replace(after, openable=())
    print(f"watch: watching {epic}, every {interval_seconds} seconds", file=sys.stderr, flush=True)
    while True:
        change = change_between(before, after, pacing.now())
        if change is not None:
            if change.event in ends_on:
                return change
            before = after
        pacing.sleep(interval_seconds)
        if should_stop():
            return Change(STOPPED, "")
        after = read()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="watch.py", description="Wait until the epic changes in a way the "
                                                                   "factory can act on.")
    parser.add_argument("epic")
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL_SECONDS,
                        help="seconds between two reads of the beads")
    parser.add_argument("--jidoka-home", help="the folder that holds jidoka's per-machine state")
    args = parser.parse_args(argv)
    if args.interval < 1:
        parser.error("--interval needs a whole number of seconds from 1 up")
    home = settings_reader.jidoka_home(args.jidoka_home)
    try:
        main_tree = settings_reader.main_worktree(Path.cwd(), COMMAND_TIMEOUT_SECONDS)
        change = watch(args.epic, lambda: snapshot_of(args.epic, main_tree, home, clock.now()), args.interval,
                       CHANGE_EVENTS, lambda: False, REAL_PACING)
    except (EpicReadError, CommandError, settings_reader.SettingsError, rules.RulesError, OSError) as error:
        print(f"watch: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"epic": args.epic, "event": change.event, "bead": change.bead}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
