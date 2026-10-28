#!/usr/bin/env python3
"""Shows the factory's state from any terminal: each epic it holds and each task's lap, stage, tries and time.

Run it from inside any checkout of the repo. It needs no host: it reads the beads through bd and the
heartbeat files in the jidoka home, and changes nothing. For each open epic with the `factory` label it prints
a heading with the epic's state (running, parked or at the acceptance gate), and for a running epic the age of
its heartbeat, as heartbeat.py writes it, or that there is none. It also says when the epic's brake is on, and while the epic's pause waits, its cause, the wait left and the
retries so far (JIDOKA_NOW stands in for the clock, as clock.py says). A
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
from pathlib import Path

import caps
import clock
import heartbeat
import lap_record
import pause
import repo_settings
from commands import COMMAND_TIMEOUT_SECONDS, FACTORY_LABEL, CommandError, NotAWholeNumber, labels_of, metadata_of
from epic_reader import CLOSED, EpicReadError, read_epic
from epics import EpicsError, epics_of, is_closed, state_of
from lap_outcomes import SchedulerError

SECONDS_PER_MINUTE = 60
SECONDS_PER_HOUR = 3600
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


def tries_of(metadata: dict, stage: str) -> str:
    return f"{lap_record.tries_used(metadata, stage)}/{lap_record.try_cap(stage)}"


def time_of(metadata: dict, stage: str, now: int) -> str:
    """The stage's time against its wall clock; nothing for a lap at rest or one that records no start."""
    if stage in lap_record.RESTING_STAGES:
        return NO_VALUE
    started = lap_record.started_of(metadata)
    if started is None:
        return NO_VALUE
    clock = lap_record.wall_clock_seconds(stage)
    elapsed = max(0, now - started)
    left = f"({minutes(clock - elapsed)} left)" if elapsed <= clock else "(over)"
    return f"{minutes(elapsed)} of {minutes(clock)} {left}"


def row_of(task: dict, now: int) -> tuple[str, ...]:
    metadata = metadata_of(task)
    stage = lap_record.stage_of(metadata)
    lap = lap_record.number_of(metadata) or NO_VALUE
    if task.get("status") == CLOSED:
        return str(task["id"]), lap, lap_record.MERGED if stage else "closed", NO_VALUE, NO_VALUE
    if not stage:
        return str(task["id"]), NO_VALUE, "no lap yet", NO_VALUE, NO_VALUE
    return str(task["id"]), lap, stage, tries_of(metadata, stage), time_of(metadata, stage, now)


def table(tasks: list[dict], now: int) -> list[str]:
    rows = [COLUMNS] + [row_of(task, now) for task in sorted(tasks, key=lambda task: str(task["id"]))]
    widths = [max(len(row[column]) for row in rows) for column in range(len(COLUMNS))]
    titles = ["title"] + [str(task.get("title") or "") for task in sorted(tasks, key=lambda task: str(task["id"]))]
    return ["  " + "  ".join(cell.ljust(width) for cell, width in zip(row, widths)) + "  " + title
            for row, title in zip(rows, titles)]


def epic_lines(epic: dict, home: Path, main_tree: Path, now: int) -> list[str]:
    state = state_of(epic)
    lines = [f"{epic['id']}  {epic.get('title') or ''} [{state.name}]"]
    if state.is_running:
        seconds = heartbeat.beat_age_seconds(home, str(epic["id"]), now)
        lines.append("  " + ("no heartbeat" if seconds is None else f"heartbeat {age(seconds)} ago"))
    held_pause = pause.held_by(epic)
    if held_pause is not None and held_pause.is_waiting(now):
        retries = f"{held_pause.retries} retry" if held_pause.retries == 1 else f"{held_pause.retries} retries"
        lines.append(f"  paused on {pause.WORDS[held_pause.cause]}, {minutes(held_pause.until - now)} left, {retries}")
    brake = caps.brake_of(epic)
    if brake.is_on:
        lines.append(f"  brake on at the {brake.stage}: {brake.laps} laps in a row parked there")
    return lines + table(read_epic(epic, main_tree).task_beads, now)


def status(home: Path, main_tree: Path, now: int) -> str:
    epics = [epic for epic in epics_of(main_tree) if FACTORY_LABEL in labels_of(epic) and not is_closed(epic)]
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
        printed = status(repo_settings.jidoka_home(args.jidoka_home), main_tree, clock.now())
    except (EpicsError, EpicReadError, SchedulerError, NotAWholeNumber, CommandError,
            repo_settings.SettingsError, OSError) as error:
        print(f"status: {error}", file=sys.stderr)
        return 1
    print(printed)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
