#!/usr/bin/env python3
"""Wakes a manager that T3 released, by sending its T3 thread the carry-on prompt.

T3 ends the session of an idle host after 30 minutes, and a manager that waits on a pause or a parked task goes
quiet for longer. The manager records the T3 thread it runs in, the session_end hook starts a detached waker when
T3 ends that session, and the waker sends the thread the prompt that makes the manager run the scheduler's
carry-on. T3 resumes the same Claude session for that turn.

  t3_wake.py record <epic> --thread <id> --jidoka-home <folder>
      Writes <jidoka-home>/t3-thread/<epic>.json: `epic`, `thread`, and `session`, the id of the session the call
      runs in, from $JIDOKA_SESSION_ID (null when unset).
  t3_wake.py wait <epic> --thread <id> --jidoka-home <folder> [--interval <seconds>]
      Reads the epic's beads every --interval seconds and, at the first unpark, new task or end of a pause, runs
      `t3 thread send <id> <prompt>` and exits 0. A merge is no reason to wake: the watch goes on from what the
      epic holds then. It exits 0 and sends nothing once the factory no longer holds the epic: it landed or was
      dropped. It exits 1 when the beads or the send fail, with the reason on stderr.

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
from pathlib import Path

import epics
import heartbeat
import processes
import repo_settings
import watch
from commands import COMMAND_TIMEOUT_SECONDS, FACTORY_LABEL, CommandError, labels_of
from epic_reader import EpicReadError, shown_epic

THREAD_FOLDER = "t3-thread"
DEFAULT_INTERVAL_SECONDS = watch.DEFAULT_INTERVAL_SECONDS
SEND_TIMEOUT_SECONDS = 120
GIT_TIMEOUT_SECONDS = 5
T3_VARIABLE = "T3CODE_CLI_PATH"
INTERVAL_VARIABLE = "JIDOKA_WAKE_INTERVAL_SECONDS"
WAKE_EVENTS = (watch.UNPARKED, watch.NEW_TASK, watch.PAUSE_OVER)


def record_path(home: Path, epic: str) -> Path:
    return home / THREAD_FOLDER / f"{epic}.json"


def record(home: Path, epic: str, thread: str, session: str | None) -> None:
    path = record_path(home, epic)
    path.parent.mkdir(parents=True, exist_ok=True)
    scratch = path.with_suffix(".json.tmp")
    scratch.write_text(json.dumps({"epic": epic, "thread": thread, "session": session}), encoding="utf-8")
    os.replace(scratch, path)


def threads_of_session(home: Path, session: str) -> list[tuple[str, str]]:
    """The (epic, thread) pairs that a manager of this session recorded."""
    found: list[tuple[str, str]] = []
    folder = home / THREAD_FOLDER
    for path in sorted(folder.glob("*.json")) if folder.is_dir() else []:
        try:
            held = json.loads(path.read_text(encoding="utf-8"))
            epic, thread = held["epic"], held["thread"]
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if held.get("session") == session and isinstance(epic, str) and isinstance(thread, str) and thread:
            found.append((epic, thread))
    return found


def is_held(epic: str, main_tree: Path) -> bool:
    """True while the epic is open and carries the factory label."""
    shown = shown_epic(epic, main_tree)
    return FACTORY_LABEL in labels_of(shown) and not epics.is_closed(shown)


def carry_on_prompt(epic: str, event: str, home: Path) -> str:
    return (f"jidoka: {event} on {epic}. Run `scheduler carry-on {epic} --jidoka-home {home}` and go on from "
            "step 4 of the factory skill.")


def under_t3() -> bool:
    return bool(os.environ.get(T3_VARIABLE, "").strip())


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
    change = watch.watch(epic, read, interval_seconds, None, frozenset(WAKE_EVENTS), lambda: not held(), pacing)
    if change.event == watch.STOPPED:
        return None
    sender(thread, carry_on_prompt(epic, change.event, home))
    return change.event


def start_wakers(home: Path, session: str, folder: Path) -> None:
    """Starts a `wait` process for each epic that a manager of this session recorded a thread for and that the
    factory still holds. The process is detached from the host's session or console, so it outlives the host."""
    threads = threads_of_session(home, session)
    if not threads:
        return
    main_tree = repo_settings.main_worktree(folder, GIT_TIMEOUT_SECONDS)
    for epic, thread in threads:
        if not is_held(epic, main_tree):
            continue
        command = [sys.executable, str(Path(__file__).resolve()), "wait", epic, "--thread", thread,
                   "--jidoka-home", str(home)]
        interval = os.environ.get(INTERVAL_VARIABLE, "").strip()
        if interval:
            command += ["--interval", interval]
        subprocess.Popen(command, cwd=folder, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, **processes.detached_options())


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
    home = repo_settings.jidoka_home(args.jidoka_home)
    thread = args.thread.strip()
    if not thread:
        parser.error("--thread needs a thread id")
    if args.mode == "record":
        try:
            record(home, args.epic, thread, heartbeat.session_of_environment())
        except OSError as error:
            print(f"t3_wake: {error}", file=sys.stderr)
            return 1
        return 0
    if args.interval < 1:
        parser.error("--interval needs a whole number of seconds from 1 up")
    try:
        main_tree = repo_settings.main_worktree(Path.cwd(), COMMAND_TIMEOUT_SECONDS)
        wait_and_send(args.epic, thread, home, args.interval, lambda: watch.snapshot_of(args.epic, main_tree),
                      lambda: is_held(args.epic, main_tree), watch.REAL_PACING, send)
    except (EpicReadError, CommandError, repo_settings.SettingsError, OSError) as error:
        print(f"t3_wake: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
