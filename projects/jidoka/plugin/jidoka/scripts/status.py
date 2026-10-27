#!/usr/bin/env python3
"""Shows the factory's state from any terminal: each epic it holds and each task's lap, stage, tries and time.

Run it from inside any checkout of the repo. It needs no host: it reads the beads through bd and the
heartbeat files in the jidoka home, and changes nothing. For each open epic with the `factory` label it prints
a heading with the epic's state (running, parked or at the acceptance gate), and for a running epic the age of
its heartbeat, as heartbeat.py writes it, or that there is none. It also says when the epic's brake is on. A
table follows with one row for each task of the epic:
  lap    the lap's number, or - for a task with no lap yet.
  stage  the lap's stage; merged for a closed task, and no lap yet for an open one with no lap.
  tries  the tries the lap has used against the cap of its stage, three for the build, two for the merge.
  time   for a lap at a stage with a wall clock, the minutes the stage has run, the clock, and the minutes
         left, or over when the clock has run out.

The home is --jidoka-home, else $JIDOKA_HOME, else ~/.jidoka.

Exit codes:
  0  success, including when the factory holds no epic.
  1  it could not read the beads, with the reason on stderr.
  2  a usage error.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import caps
import discovered
import heartbeat
import notify
import park
import repo_settings
from bench import FACTORY_LABEL
from commands import COMMAND_TIMEOUT_SECONDS, CommandError
from handoff import CLOSED, EPIC_TYPE, HandoffError, child_ids, shown_beads

SECONDS_PER_MINUTE = 60
SECONDS_PER_HOUR = 3600
MERGE = "merge"
NO_VALUE = "-"
COLUMNS = ("task", "lap", "stage", "tries", "time")


def minutes(seconds: int) -> str:
    return f"{seconds // SECONDS_PER_MINUTE}m"


def age(seconds: int) -> str:
    if seconds < SECONDS_PER_MINUTE:
        return f"{seconds}s"
    if seconds < SECONDS_PER_HOUR:
        return minutes(seconds)
    return f"{seconds // SECONDS_PER_HOUR}h{seconds % SECONDS_PER_HOUR // SECONDS_PER_MINUTE:02d}m"


def metadata_of(bead: dict) -> dict:
    metadata = bead.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def tries_of(metadata: dict, stage: str) -> str:
    if stage == MERGE:
        return f"{caps.count_in(metadata, caps.MERGE_TRIES_KEY)}/{caps.MERGE_TRY_CAP}"
    return f"{caps.count_in(metadata, 'lap.tries')}/{caps.TRY_CAP}"


def time_of(metadata: dict, stage: str, now: int) -> str:
    """The stage's time against its wall clock; nothing for a parked or blocked lap or one that records no start."""
    if stage in (park.PARKED, discovered.BLOCKED):
        return NO_VALUE
    try:
        started = int(str(metadata.get(caps.STARTED_KEY)))
    except ValueError:
        return NO_VALUE
    clock = caps.wall_clock_seconds(stage)
    elapsed = max(0, now - started)
    left = f"({minutes(clock - elapsed)} left)" if elapsed <= clock else "(over)"
    return f"{minutes(elapsed)} of {minutes(clock)} {left}"


def row_of(task: dict, now: int) -> tuple[str, ...]:
    metadata = metadata_of(task)
    stage = str(metadata.get("lap.stage") or "")
    lap = str(metadata.get("lap.number") or NO_VALUE)
    if task.get("status") == CLOSED:
        return str(task["id"]), lap, "merged" if stage else "closed", NO_VALUE, NO_VALUE
    if not stage:
        return str(task["id"]), NO_VALUE, "no lap yet", NO_VALUE, NO_VALUE
    return str(task["id"]), lap, stage, tries_of(metadata, stage), time_of(metadata, stage, now)


def table(tasks: list[dict], now: int) -> list[str]:
    rows = [COLUMNS] + [row_of(task, now) for task in sorted(tasks, key=lambda task: str(task["id"]))]
    widths = [max(len(row[column]) for row in rows) for column in range(len(COLUMNS))]
    titles = ["title"] + [str(task.get("title") or "") for task in sorted(tasks, key=lambda task: str(task["id"]))]
    return ["  " + "  ".join(cell.ljust(width) for cell, width in zip(row, widths)) + "  " + title
            for row, title in zip(rows, titles)]


def state_of(epic: dict) -> str:
    if notify.at_the_gate(epic):
        return "at the acceptance gate"
    return "parked" if park.HUMAN_LABEL in notify.labels_of(epic) else "running"


def epic_lines(epic: dict, home: Path, main_tree: Path, now: int) -> list[str]:
    state = state_of(epic)
    lines = [f"{epic['id']}  {epic.get('title') or ''} [{state}]"]
    if state == "running":
        seconds = heartbeat.beat_age_seconds(home, str(epic["id"]), now)
        lines.append("  " + ("no heartbeat" if seconds is None else f"heartbeat {age(seconds)} ago"))
    brake = caps.brake_of(epic)
    if brake.is_on:
        lines.append(f"  brake on at the {brake.stage}: {brake.laps} laps in a row parked there")
    held = shown_beads(child_ids(str(epic["id"]), main_tree), main_tree)
    return lines + table([bead for bead in held if bead.get("issue_type") != EPIC_TYPE], now)


def status(home: Path, main_tree: Path, now: int) -> str:
    epics = [epic for epic in notify.epics_of(main_tree)
             if FACTORY_LABEL in notify.labels_of(epic) and not notify.is_closed(epic)]
    if not epics:
        return "no epic is in the factory"
    return "\n\n".join("\n".join(epic_lines(epic, home, main_tree, now)) for epic in epics)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="status.py", description="Show each epic the factory holds and each "
                                                                    "task's lap, stage, tries and time.")
    parser.add_argument("--jidoka-home", help="the folder that holds jidoka's per-machine state")
    args = parser.parse_args(argv)
    try:
        main_tree = repo_settings.main_worktree(Path.cwd(), COMMAND_TIMEOUT_SECONDS)
        printed = status(repo_settings.jidoka_home(args.jidoka_home), main_tree, int(time.time()))
    except (notify.NotifyError, HandoffError, CommandError, repo_settings.SettingsError, OSError) as error:
        print(f"status: {error}", file=sys.stderr)
        return 1
    print(printed)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
