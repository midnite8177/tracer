#!/usr/bin/env python3
"""Writes the heartbeat of each epic the factory runs, and reads it back for the status script.

The scheduler writes <jidoka-home>/heartbeat/<epic>.json on each call of a manager, a JSON object with `epic`
and `time`, the second of the beat since the epoch: that call claims the epic. `heartbeat.py beat` is what the
lap mod runs once a minute from the host's folder. It renews the heartbeat of each epic the factory runs (an
open epic with the `factory` label that is neither parked nor at the gate) whose heartbeat is fresh, and writes
nothing for any other. An epic that was handed off and has no manager has no heartbeat, so a manager that starts
on it a minute later is not taken for a second manager. The age of the file is how long the host has gone
without beating, so a factory stopped under an epic shows as a heartbeat that stops getting younger. A heartbeat
is fresh while it is no older than FRESH_SECONDS, a beat and a half, and a manager that starts on an epic
whose heartbeat is fresh is a second manager. A beat never brings a stale heartbeat back to fresh; a stop
leaves it stale when it ends the laps, and the next call of a manager claims the epic again.

The home is --jidoka-home, else $JIDOKA_HOME, else ~/.jidoka.

Exit codes:
  0  the beats were written, or no epic runs.
  1  it could not run, with the reason on stderr.
  2  a usage error.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import notify
import repo_settings
from commands import COMMAND_TIMEOUT_SECONDS, CommandError
from handoff import HandoffError

HEARTBEAT_FOLDER = "heartbeat"
FRESH_SECONDS = 90


def heartbeat_path(home: Path, epic: str) -> Path:
    return home / HEARTBEAT_FOLDER / f"{epic}.json"


def write_beat(home: Path, epic: str, now: int) -> None:
    """Writes the beat through a temporary file, so a reader never finds half of it."""
    path = heartbeat_path(home, epic)
    path.parent.mkdir(parents=True, exist_ok=True)
    scratch = path.with_suffix(".json.tmp")
    scratch.write_text(json.dumps({"epic": epic, "time": now}), encoding="utf-8")
    os.replace(scratch, path)


def beat_age_seconds(home: Path, epic: str, now: int) -> int | None:
    """Seconds since the epic's last beat, or None when it has no readable heartbeat."""
    try:
        held = json.loads(heartbeat_path(home, epic).read_text(encoding="utf-8"))
        return max(0, now - int(held["time"]))
    except (OSError, ValueError, KeyError, TypeError):
        return None


def is_fresh(home: Path, epic: str, now: int) -> bool:
    """True when the epic's last beat is no older than FRESH_SECONDS."""
    seconds = beat_age_seconds(home, epic, now)
    return seconds is not None and seconds <= FRESH_SECONDS


def mark_stopped(home: Path, epic: str, now: int) -> None:
    """Leaves the epic's heartbeat stale at once, as a stop does, so that a host that is still open does not beat it
    back to fresh."""
    write_beat(home, epic, now - FRESH_SECONDS - 1)


def claim(home: Path, epic: str, now: int) -> None:
    """Writes the epic's heartbeat fresh, as each call of a manager does: it is the one write that starts a
    heartbeat, and it brings a stale one back, so that the host the manager runs in beats the epic from then on."""
    write_beat(home, epic, now)


def beat(home: Path, main_tree: Path) -> list[str]:
    """Renews the heartbeat of each running epic that a manager has claimed and returns their ids.

    A host that handed an epic off has no manager running it yet, and a stale heartbeat means the manager is gone, so
    a beat writes neither: it would show a manager where none runs. Only a manager's call claims an epic.
    """
    running = notify.running_epics(main_tree)
    now = int(time.time())
    beaten = [epic for epic in running if is_fresh(home, epic, now)]
    for epic in beaten:
        write_beat(home, epic, now)
    return beaten


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="heartbeat.py", description="Write the host's heartbeat.")
    modes = parser.add_subparsers(dest="mode", required=True)
    beating = modes.add_parser("beat", help="write a beat for each epic the factory runs")
    beating.add_argument("--jidoka-home", help="the folder that holds jidoka's per-machine state")
    args = parser.parse_args(argv)
    try:
        main_tree = repo_settings.main_worktree(Path.cwd(), COMMAND_TIMEOUT_SECONDS)
        beat(repo_settings.jidoka_home(args.jidoka_home), main_tree)
    except (notify.NotifyError, HandoffError, CommandError, repo_settings.SettingsError, OSError) as error:
        print(f"heartbeat: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
