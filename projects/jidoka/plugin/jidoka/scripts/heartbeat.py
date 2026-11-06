#!/usr/bin/env python3
"""Writes the heartbeat of each epic the factory runs, and reads it back for the status script.

The scheduler writes <jidoka-home>/heartbeat/<epic>.json on each call of a manager, a JSON object with `epic`,
`time`, the second of the beat since the epoch, `session`, the id of the session the manager runs in (null
when the call did not know it), and `fresh_seconds`, how old the beat may be and still count as fresh. The call
that records a session claims the epic. `heartbeat.py beat --session <id>` is what the lap
mod runs once a minute from the host's folder, naming its own session. It renews the heartbeat of each epic the
factory runs (an open epic with the `factory` label that is neither parked nor at the gate) whose heartbeat is
fresh and records that session, and writes nothing for any other. A session that claimed no epic, such as an
advisor or a stopped factory, renews nothing, so a heartbeat whose manager is gone goes stale. An epic that was
handed off and has no manager has no heartbeat, so a manager that starts on it a minute later is not taken for a
second manager. The age of the file is how long the host has gone
without beating, so a factory stopped under an epic shows as a heartbeat that stops getting younger. A heartbeat
is fresh while it is no older than FRESH_SECONDS, a beat and a half, and a manager that starts on an epic
whose heartbeat is fresh is a second manager. A beat never brings a stale heartbeat back to fresh; a stop
leaves it stale when it ends the laps, and the next call of a manager claims the epic again.

A manager that stops for any other reason, such as a refused report or a worker that failed, runs
`heartbeat.py stop <epic>` first, so that the heartbeat records the stop and the factory state reads the epic as
stopped while the host stays open. It reads the session from $JIDOKA_SESSION_ID and marks only a heartbeat that
records that session, so a refused second manager stops nobody's heartbeat and an epic with none gets none.

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
from pathlib import Path

import clock
import epics
import settings_reader
from commands import COMMAND_TIMEOUT_SECONDS, CommandError, bd_show
from epic_reader import EpicReadError

HEARTBEAT_FOLDER = "heartbeat"
FRESH_SECONDS = 90
SESSION_VARIABLE = "JIDOKA_SESSION_ID"


def heartbeat_path(home: Path, epic: str) -> Path:
    return home / HEARTBEAT_FOLDER / f"{epic}.json"


def write_beat(home: Path, epic: str, now: int, session: str | None) -> None:
    """Writes the beat through a temporary file, so a reader never finds half of it."""
    path = heartbeat_path(home, epic)
    path.parent.mkdir(parents=True, exist_ok=True)
    scratch = path.with_suffix(".json.tmp")
    beat = {"epic": epic, "time": now, "session": session, "fresh_seconds": FRESH_SECONDS}
    scratch.write_text(json.dumps(beat), encoding="utf-8")
    os.replace(scratch, path)


def beat_age_seconds(home: Path, epic: str, now: int) -> int | None:
    """Seconds since the epic's last beat, or None when it has no readable heartbeat."""
    try:
        held = json.loads(heartbeat_path(home, epic).read_text(encoding="utf-8"))
        return max(0, now - int(held["time"]))
    except (OSError, ValueError, KeyError, TypeError):
        return None


def beat_session(home: Path, epic: str) -> str | None:
    """The id of the session that claimed the epic, or None when the heartbeat records none or cannot be read."""
    try:
        held = json.loads(heartbeat_path(home, epic).read_text(encoding="utf-8"))
        session = held["session"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return session if isinstance(session, str) else None


def fresh_age_seconds(home: Path, epic: str, now: int) -> int | None:
    """Seconds since the epic's last beat when that is no older than FRESH_SECONDS, and None when the heartbeat is
    stale or unreadable."""
    seconds = beat_age_seconds(home, epic, now)
    return seconds if seconds is not None and seconds <= FRESH_SECONDS else None


def is_fresh(home: Path, epic: str, now: int) -> bool:
    return fresh_age_seconds(home, epic, now) is not None


def fresh_epics(home: Path, now: int) -> list[str]:
    """The ids of the epics, in any repo of the machine, whose heartbeat is fresh; the epics a manager runs now."""
    folder = home / HEARTBEAT_FOLDER
    if not folder.is_dir():
        return []
    return sorted(path.stem for path in folder.glob("*.json") if is_fresh(home, path.stem, now))


def mark_stopped(home: Path, epic: str, now: int) -> None:
    """Leaves the epic's heartbeat stale at once, as a stop does, so that a host that is still open does not beat it
    back to fresh."""
    write_beat(home, epic, now - FRESH_SECONDS - 1, None)


def stop(home: Path, epic: str, now: int, session: str | None) -> None:
    """Marks the epic's heartbeat stopped when the session claimed it, as a manager does on each stop that runs no
    `scheduler.py stop`. A session that did not claim the epic, such as a second manager that was refused, leaves the
    heartbeat of the manager that did, and an epic no manager claimed keeps no heartbeat, so a stop writes none for
    it."""
    if session is not None and beat_session(home, epic) == session:
        mark_stopped(home, epic, now)


def session_of_environment() -> str | None:
    """The id of the session the caller runs in, which the session_start hook exports as JIDOKA_SESSION_ID, or None
    when the caller got none."""
    return os.environ.get(SESSION_VARIABLE) or None


def claim(home: Path, epic: str, now: int) -> None:
    """Writes the epic's heartbeat fresh and records the manager's session, as each call of a manager does. It is
    the one write that starts a heartbeat, and it brings a stale one back, so that the session the manager runs in
    beats the epic from then on and no other session does.

    A call that knows no session records none, and no beat ever renews that heartbeat, so it goes stale 90 seconds
    later and a second manager may start; the call says so on stderr.
    """
    session = session_of_environment()
    if session is None:
        print(f"heartbeat: {SESSION_VARIABLE} is not set in this call, so the heartbeat of {epic} records no session "
              f"and no beat will renew it. It goes stale in {FRESH_SECONDS} seconds, and a second manager may then "
              "start. Start the session again so that its hook exports the variable", file=sys.stderr)
    write_beat(home, epic, now, session)


def claimed_by(home: Path, session: str) -> list[str]:
    """The ids of the epics, in any repo of the machine, whose heartbeat records this session, fresh or stale."""
    folder = home / HEARTBEAT_FOLDER
    if not folder.is_dir():
        return []
    return sorted(path.stem for path in folder.glob("*.json") if beat_session(home, path.stem) == session)


def runs_here(epic: str, main_tree: Path) -> bool:
    """True when the factory runs the epic in this repo. An epic of another repo of the machine is one bd cannot
    show here, so it does not run here."""
    try:
        shown = bd_show(epic, main_tree)
    except CommandError:
        return False
    return shown is not None and epics.is_running(shown)


def managed_by(home: Path, main_tree: Path, session: str) -> list[str]:
    """The ids of the epics the factory runs whose heartbeat records this session, fresh or stale; the epics a
    manager of this session claimed, and so the only epics that a failed turn of this session concerns. The
    heartbeat files come first, so a session that claimed nothing reads nothing from bd, and a session that claimed
    an epic reads only that epic, however many epics the repo has held."""
    return [epic for epic in claimed_by(home, session) if runs_here(epic, main_tree)]


def beat(home: Path, main_tree: Path, session: str) -> list[str]:
    """Renews the heartbeat of each running epic that a manager of this session claimed and returns their ids.

    A host that handed an epic off has no manager running it yet, a stale heartbeat means the manager is gone, and
    an epic claimed by another session has a manager in that session, so a beat writes none of them: it would show
    a manager where none runs. Only a manager's call claims an epic.
    """
    now = clock.now()
    beaten = [epic for epic in managed_by(home, main_tree, session) if is_fresh(home, epic, now)]
    for epic in beaten:
        write_beat(home, epic, now, session)
    return beaten


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="heartbeat.py", description="Write the host's heartbeat.")
    modes = parser.add_subparsers(dest="mode", required=True)
    beating = modes.add_parser("beat", help="renew the heartbeat of each epic the factory runs for this session")
    beating.add_argument("--session", required=True, help="the id of the session that beats")
    beating.add_argument("--jidoka-home", help="the folder that holds jidoka's per-machine state")
    stopping = modes.add_parser("stop", help="mark the heartbeat of an epic stopped when this session claimed it, "
                                             "as a manager does when it stops")
    stopping.add_argument("epic", help="the id of the epic whose manager stops")
    stopping.add_argument("--jidoka-home", help="the folder that holds jidoka's per-machine state")
    args = parser.parse_args(argv)
    try:
        home = settings_reader.jidoka_home(args.jidoka_home)
        if args.mode == "stop":
            stop(home, args.epic, clock.now(), session_of_environment())
        else:
            main_tree = settings_reader.main_worktree(Path.cwd(), COMMAND_TIMEOUT_SECONDS)
            beat(home, main_tree, args.session)
    except (epics.EpicsError, EpicReadError, CommandError, settings_reader.SettingsError, OSError) as error:
        print(f"heartbeat: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
