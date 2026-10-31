#!/usr/bin/env python3
"""Wakes a manager that T3 released, by sending its T3 thread the carry-on prompt.

T3 ends the session of an idle host after 30 minutes, and a manager that waits on a pause or a parked task goes
quiet for longer. The manager records the T3 thread it runs in, the session_end hook starts a detached waker when
T3 ends that session, and the waker sends the thread the prompt that makes the manager run the scheduler's
carry-on. T3 resumes the same Claude session for that turn, under a new session id, and the scheduler's next call
in it claims the epic's heartbeat with that id. The record keeps only the thread: the session of the manager is
the one the heartbeat names, so the next release matches the heartbeat again.

T3 ends an idle host with the session end reason `other` (releases_host); /clear, a resume and a logout end a
session for another reason and start no waker. At most one waker runs for an epic: its pid is kept in
<jidoka-home>/t3-thread/<epic>.waker, and a session end while that process runs starts nothing. `forget` deletes
the record and that file, as landing or dropping the epic does.

  t3_wake.py record <epic> --thread <id> --jidoka-home <folder>
      Writes <jidoka-home>/t3-thread/<epic>.json: `epic` and `thread`.
  t3_wake.py wait <epic> --thread <id> --jidoka-home <folder> [--interval <seconds>]
      Reads the epic's beads and the machine's slot record every --interval seconds and, at the first unpark, new
      task, end of a pause or room that opens for a ready task (watch.py describes it, and a task that can open when
      the wait begins counts), runs `t3 thread send <id> <prompt>` and exits 0. A merge is no reason to wake: the
      watch goes on from what the epic holds then. While it waits it renews the epic's heartbeat at each read, with the session the heartbeat
      names, so a waiting factory does not show as stopped and no second manager starts. A heartbeat that names no
      session, such as one a stop left stale, is not renewed. It exits 0 and sends nothing once the factory no
      longer holds the epic: it landed or was dropped. It exits 1 when the beads or the send fail, with the reason
      on stderr.

The `t3` command is $T3CODE_CLI_PATH, else `t3` on the PATH.

Exit codes:
  0  the thread was sent the prompt, or the epic is no longer held.
  1  it could not run, with the reason on stderr.
  2  a usage error.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import clock
import epics
import file_lock
import heartbeat
import processes
import settings_reader
import rules
import watch
from commands import COMMAND_TIMEOUT_SECONDS, FACTORY_LABEL, CommandError, labels_of
from epic_reader import EpicReadError, shown_epic

THREAD_FOLDER = "t3-thread"
RELEASE_REASON = "other"
DEFAULT_INTERVAL_SECONDS = watch.DEFAULT_INTERVAL_SECONDS
SEND_TIMEOUT_SECONDS = 120
GIT_TIMEOUT_SECONDS = 5
T3_VARIABLE = "T3CODE_CLI_PATH"
INTERVAL_VARIABLE = "JIDOKA_WAKE_INTERVAL_SECONDS"
WAKE_EVENTS = (watch.UNPARKED, watch.NEW_TASK, watch.PAUSE_OVER, watch.ROOM_FREED)


def record_path(home: Path, epic: str) -> Path:
    return home / THREAD_FOLDER / f"{epic}.json"


@dataclass(frozen=True)
class ThreadRecord:
    """The T3 thread that the manager of an epic runs in."""
    epic: str
    thread: str


def read_json(path: Path) -> dict | None:
    """The JSON object in the file, or None when the file is missing, unreadable or holds anything else."""
    try:
        held = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return held if isinstance(held, dict) else None


def write_json_atomically(path: Path, value: dict) -> None:
    """Writes the object through a temporary file beside the path, so a reader never finds half of it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    scratch = path.with_name(f"{path.name}.tmp")
    scratch.write_text(json.dumps(value), encoding="utf-8")
    os.replace(scratch, path)


def read_record(home: Path, epic: str) -> ThreadRecord | None:
    """The epic's thread record, or None when it is missing, unreadable or names no thread."""
    held = read_json(record_path(home, epic))
    if held is None:
        return None
    named, thread = held.get("epic"), held.get("thread")
    if isinstance(named, str) and isinstance(thread, str) and thread:
        return ThreadRecord(named, thread)
    return None


def record(home: Path, epic: str, thread: str) -> None:
    write_json_atomically(record_path(home, epic), {"epic": epic, "thread": thread})


def waker_path(home: Path, epic: str) -> Path:
    return home / THREAD_FOLDER / f"{epic}.waker"


def lock_path(home: Path, epic: str) -> Path:
    return home / THREAD_FOLDER / f"{epic}.lock"


def forget(home: Path, epic: str) -> None:
    """Deletes the epic's thread record, the file that names its waker and the lock beside them, whichever exist."""
    for path in (record_path(home, epic), waker_path(home, epic), lock_path(home, epic)):
        path.unlink(missing_ok=True)


def waker_is_running(home: Path, epic: str) -> bool:
    """True while the process that the epic's waker file names runs. A process of that pid that began at another
    moment is not the waker."""
    held = read_json(waker_path(home, epic))
    if held is None:
        return False
    try:
        pid, began = int(held["pid"]), held["started"]
    except (KeyError, ValueError, TypeError):
        return False
    return processes.is_alive(pid) and (began is None or processes.started_at(pid) == began)


def write_waker(home: Path, epic: str, pid: int) -> None:
    write_json_atomically(waker_path(home, epic), {"pid": pid, "started": processes.started_at(pid)})


def releases_host(reason: object) -> bool:
    """True when a session end with this reason is T3 releasing an idle host."""
    return reason == RELEASE_REASON


def threads_of_session(home: Path, session: str) -> list[tuple[str, str]]:
    """The (epic, thread) pairs of the epics whose heartbeat names this session as its manager's."""
    found: list[tuple[str, str]] = []
    folder = home / THREAD_FOLDER
    for path in sorted(folder.glob("*.json")) if folder.is_dir() else []:
        held = read_record(home, path.stem)
        if held is not None and heartbeat.beat_session(home, held.epic) == session:
            found.append((held.epic, held.thread))
    return found


def is_held(epic: str, main_tree: Path) -> bool:
    """True while the epic is open and carries the factory label."""
    shown = shown_epic(epic, main_tree)
    return FACTORY_LABEL in labels_of(shown) and not epics.is_closed(shown)


def carry_on_prompt(epic: str, event: str, home: Path) -> str:
    return (f"jidoka: {event} on {epic}. Run `scheduler carry-on {epic} --jidoka-home {home}` and go on from "
            "step 4 of the factory skill.")


def beating(home: Path, epic: str, read: Callable[[], watch.Snapshot], now: Callable[[], int]
            ) -> Callable[[], watch.Snapshot]:
    """A read that first renews the epic's heartbeat with the session it names, the one T3 resumes when the waker
    sends the thread its prompt. The lap mod of a released host writes no beat, so without this one jidoka-ui shows a
    waiting factory as stopped and the scheduler lets a second manager start."""
    def read_and_beat() -> watch.Snapshot:
        session = heartbeat.beat_session(home, epic)
        if session is not None:
            heartbeat.write_beat(home, epic, now(), session)
        return read()
    return read_and_beat


def t3_command() -> str:
    return os.environ.get(T3_VARIABLE, "").strip() or "t3"


def send(thread: str, prompt: str) -> None:
    try:
        done = subprocess.run([t3_command(), "thread", "send", thread, prompt], capture_output=True, text=True,
                              encoding="utf-8", timeout=SEND_TIMEOUT_SECONDS)
    except (OSError, subprocess.SubprocessError) as error:
        raise CommandError(f"t3 thread send failed: {error}") from error
    if done.returncode != 0:
        raise CommandError(f"t3 thread send exited {done.returncode}: {done.stderr.strip()}")


def wait_and_send(epic: str, thread: str, home: Path, interval_seconds: int, read: Callable[[], watch.Snapshot],
                  held: Callable[[], bool], pacing: watch.Pacing, sender: Callable[[str, str], None]) -> str | None:
    """Blocks until the epic can move again and sends the prompt, returning the event; returns None when the
    factory no longer holds the epic."""
    change = watch.watch(epic, read, interval_seconds, frozenset(WAKE_EVENTS), lambda: not held(), pacing)
    if change.event == watch.STOPPED:
        return None
    sender(thread, carry_on_prompt(epic, change.event, home))
    return change.event


def start_wakers(home: Path, session: str, folder: Path) -> None:
    """Starts a `wait` process for each epic that a manager of this session recorded a thread for, that the
    factory still holds and that has no waker running. The process is detached from the host's session or console,
    so it outlives the host."""
    threads = threads_of_session(home, session)
    if not threads:
        return
    main_tree = settings_reader.main_worktree(folder, GIT_TIMEOUT_SECONDS)
    for epic, thread in threads:
        if not is_held(epic, main_tree):
            continue
        command = [sys.executable, str(Path(__file__).resolve()), "wait", epic, "--thread", thread,
                   "--jidoka-home", str(home)]
        interval = os.environ.get(INTERVAL_VARIABLE, "").strip()
        if interval:
            command += ["--interval", interval]
        with file_lock.exclusive(lock_path(home, epic)):
            if waker_is_running(home, epic):
                continue
            waker = subprocess.Popen(command, cwd=folder, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL, **processes.detached_options())
            write_waker(home, epic, waker.pid)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="t3_wake.py", description="Wake a released T3 host.")
    modes = parser.add_subparsers(dest="mode", required=True)
    recording = modes.add_parser("record", help="record the T3 thread the manager runs in")
    waiting = modes.add_parser("wait", help="send the carry-on prompt when the epic can move again")
    waiting.add_argument("--interval", type=int, default=DEFAULT_INTERVAL_SECONDS,
                         help="seconds between two reads of the beads")
    for sub in (recording, waiting):
        sub.add_argument("epic")
        sub.add_argument("--thread", required=True, help="the T3 thread id")
        sub.add_argument("--jidoka-home", help="the folder that holds jidoka's per-machine state")
    args = parser.parse_args(argv)
    home = settings_reader.jidoka_home(args.jidoka_home)
    thread = args.thread.strip()
    if not thread:
        parser.error("--thread needs a thread id")
    if args.mode == "record":
        try:
            record(home, args.epic, thread)
        except OSError as error:
            print(f"t3_wake: {error}", file=sys.stderr)
            return 1
        return 0
    if args.interval < 1:
        parser.error("--interval needs a whole number of seconds from 1 up")
    try:
        main_tree = settings_reader.main_worktree(Path.cwd(), COMMAND_TIMEOUT_SECONDS)
        wait_and_send(args.epic, thread, home, args.interval,
                      beating(home, args.epic, lambda: watch.snapshot_of(args.epic, main_tree, home, clock.now()),
                              clock.now),
                      lambda: is_held(args.epic, main_tree), watch.REAL_PACING, send)
    except (EpicReadError, CommandError, settings_reader.SettingsError, rules.RulesError, OSError) as error:
        print(f"t3_wake: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
