#!/usr/bin/env python3
"""Writes the heartbeat of each epic the factory runs, and reads it back for the status script.

The scheduler writes <jidoka-home>/heartbeat/<epic>.json on each call of a manager, a JSON object with `epic`,
`time`, the second of the beat since the epoch, `session`, the id of the session the manager runs in (null
when the call did not know it), `fresh_seconds`, how old the beat may be and still count as fresh, and `stopped`,
true when the epic's manager stopped. The call
that records a session claims the epic. `heartbeat.py beat --session <id>` is what the lap
mod runs once a minute from the host's folder, naming its own session. It renews the heartbeat of each epic the
factory runs (an open epic with the `factory` label that is neither parked nor at the gate) whose heartbeat is
fresh and records that session, and writes nothing for any other. A session that claimed no epic, such as an
advisor or a stopped factory, renews nothing, so a heartbeat whose manager is gone goes stale. An epic that was
handed off and has no manager has no heartbeat, so a manager that starts on it a minute later is not taken for a
second manager. The age of the file is how long the host has gone
without beating, so a factory stopped under an epic shows as a heartbeat that stops getting younger. A heartbeat
is fresh while it records no stop and is no older than FRESH_SECONDS, a beat and a half, and a manager that starts
on an epic whose heartbeat is fresh is a second manager. A beat never brings a stale heartbeat back to fresh; only
the next call of a manager claims the epic again, which also clears a stop.

A stopped heartbeat keeps `time`, the second of the last beat, and names no session, so that a host still open and a
waker renew nothing. `scheduler.py stop` writes it for any epic, from any terminal. `factory_state.py --stopping
<epic>`, the closing line of every other stop of a manager, writes it only when the heartbeat records the session in
$JIDOKA_SESSION_ID, so a refused second manager stops nobody's heartbeat and an epic with none gets none.

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
from dataclasses import dataclass
from pathlib import Path

import clock
import epics
import home_files
import settings_reader
from commands import COMMAND_TIMEOUT_SECONDS, CommandError, bd_show
from epic_reader import EpicReadError

HEARTBEAT_FOLDER = "heartbeat"
FRESH_SECONDS = 90
SESSION_VARIABLE = "JIDOKA_SESSION_ID"


def heartbeat_path(home: Path, epic: str) -> Path:
    return home / HEARTBEAT_FOLDER / f"{epic}.json"


@dataclass(frozen=True)
class Heartbeat:
    """What the heartbeat file of an epic holds: `time`, the second of the last beat, `session`, the id of the session
    that claimed the epic or None, and whether the epic's manager `stopped`."""
    time: int
    session: str | None
    stopped: bool

    def age_seconds(self, now: int) -> int:
        return max(0, now - self.time)

    def is_fresh(self, now: int) -> bool:
        """True while the heartbeat records no stop and is no older than FRESH_SECONDS."""
        return not self.stopped and self.age_seconds(now) <= FRESH_SECONDS


def write_heartbeat(home: Path, epic: str, heartbeat: Heartbeat) -> None:
    """Writes the heartbeat whole, so that a reader never finds half of it, even when several writers meet."""
    held = {"epic": epic, "time": heartbeat.time, "session": heartbeat.session, "fresh_seconds": FRESH_SECONDS,
            "stopped": heartbeat.stopped}
    home_files.write_in_home(home / HEARTBEAT_FOLDER, f"{epic}.json", json.dumps(held))


def write_beat(home: Path, epic: str, now: int, session: str | None) -> None:
    write_heartbeat(home, epic, Heartbeat(now, session, False))


def read_heartbeat(home: Path, epic: str) -> Heartbeat | None:
    """The epic's heartbeat as one read of its file, or None when it has no readable heartbeat. A file with no
    `stopped` field records no stop, and a `session` that is not text names none."""
    try:
        held = json.loads(heartbeat_path(home, epic).read_text(encoding="utf-8"))
        last_beat = int(held["time"])
        session = held.get("session")
        stopped = held.get("stopped") is True
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None
    return Heartbeat(last_beat, session if isinstance(session, str) else None, stopped)


def beat_age_seconds(home: Path, epic: str, now: int) -> int | None:
    """Seconds since the epic's last beat, or None when it has no readable heartbeat."""
    held = read_heartbeat(home, epic)
    return None if held is None else held.age_seconds(now)


def beat_session(home: Path, epic: str) -> str | None:
    """The id of the session that claimed the epic, or None when the heartbeat records none or cannot be read."""
    held = read_heartbeat(home, epic)
    return None if held is None else held.session


def fresh_age_seconds(home: Path, epic: str, now: int) -> int | None:
    """Seconds since the epic's last beat when that is no older than FRESH_SECONDS, and None when the heartbeat is
    stale, stopped or unreadable."""
    held = read_heartbeat(home, epic)
    return held.age_seconds(now) if held is not None and held.is_fresh(now) else None


def seconds_until_stale(age_seconds: int) -> int:
    """How many seconds from now a heartbeat of this age is stale: the one past the last second it counts as fresh."""
    return FRESH_SECONDS - age_seconds + 1


def is_fresh(home: Path, epic: str, now: int) -> bool:
    return fresh_age_seconds(home, epic, now) is not None


def fresh_epics(home: Path, now: int) -> list[str]:
    """The ids of the epics, in any repo of the machine, whose heartbeat is fresh; the epics a manager runs now."""
    folder = home / HEARTBEAT_FOLDER
    if not folder.is_dir():
        return []
    return sorted(path.stem for path in folder.glob("*.json") if is_fresh(home, path.stem, now))


def mark_stopped(home: Path, epic: str, now: int) -> None:
    """Records that no manager runs the epic, so its heartbeat counts as stale whatever its age. The session goes, so
    that a host still open and a waker renew nothing, and `time` stays the second of the last beat; an epic with no
    readable beat has no such second, and gets `now`."""
    held = read_heartbeat(home, epic)
    write_heartbeat(home, epic, Heartbeat(now if held is None else min(held.time, now), None, True))


def stop(home: Path, epic: str, now: int, session: str | None) -> None:
    """Marks the epic's heartbeat stopped when the session claimed it, as the closing line of a manager's stop does. A
    session that did not claim the epic, such as a second manager that was refused, leaves the heartbeat of the manager
    that did, and an epic no manager claimed keeps no heartbeat, so a stop writes none for it. A heartbeat already
    stopped names no session, so it stays as it is."""
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
    args = parser.parse_args(argv)
    try:
        home = settings_reader.jidoka_home(args.jidoka_home)
        main_tree = settings_reader.main_worktree(Path.cwd(), COMMAND_TIMEOUT_SECONDS)
        beat(home, main_tree, args.session)
    except (epics.EpicsError, EpicReadError, CommandError, settings_reader.SettingsError, OSError) as error:
        print(f"heartbeat: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
