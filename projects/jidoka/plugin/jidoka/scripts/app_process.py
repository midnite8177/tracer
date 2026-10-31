#!/usr/bin/env python3
"""Starts and stops the app a validation or app check worker tests, so that the worker leaves none running.

The lap mod denies a worker a shell `kill`, so a worker that starts its app any other way cannot stop it. The app
then holds its port after the worker ends, and the next run meets a port in use or the old build.

`start <app> [--env NAME=VALUE ...]` runs the `run` command that the repo settings give the app, in the folder the
script runs in, in a process group of its own (on Windows, a process with no window), with the variables added to its environment. It prints one line and
returns at once; the worker waits for the app through the app's way in. The app's output goes to
`.scratch/apps/<app>.log` in that folder. It first stops an app that an earlier start left running, so a start
always gives the build of the folder as it is now.

`stop <app>` ends the process group that `start` recorded, with SIGTERM and then SIGKILL, and deletes the record.
On Windows, where there are no process groups to signal, the record names the shell that runs the command, and `stop`
ends that process with the processes it started. It succeeds when the app is not running.

The lap mod allows this script to a check worker, whose arguments it does not read, so the script trusts nothing that
the worker can write. The record of a start, the process group and the moment its leader began, as `processes.started_at` gives
it, is a file under jidoka's home, in a folder keyed by the worktree, which the worker cannot write. `stop` signals the group only when
the group's leader is still the process that `start` recorded, or is gone and the group lives on, which no other
process can have taken the id of. The settings file is the one under jidoka's home, which is $JIDOKA_HOME, else
~/.jidoka, and there is no flag to name another. A variable `--env` adds must be named by a word of the repo
settings' `slot_use`, such as PORT in "PORT 5000 plus the slot", and never one that changes how a program is found
or loaded, such as PATH or LD_PRELOAD.

Exit codes:
  0  success, including a stop of an app that is not running.
  1  it refused or could not start the app, with the reason on stderr.
  2  a usage error.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import processes
import settings_reader
from commands import COMMAND_TIMEOUT_SECONDS, SCRATCH_FOLDER

APPS_FOLDER = "apps"
APP_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
WORD = re.compile(r"[A-Za-z][A-Za-z0-9_]*")
LOADING_NAMES = ("PATH", "SHELL", "HOME", "IFS", "ENV")
LOADING_PREFIXES = ("LD_", "DYLD_", "BASH_", "PYTHON", "NODE_", "RUBY", "PERL", "JAVA", "_JAVA", "JIDOKA_")


class AppProcessError(Exception):
    """A reason the script starts nothing, worded for the person who reads stderr."""


@dataclass(frozen=True)
class Recorded:
    """What a start recorded of the app it started: the process group, and the moment its leader began, as
    `processes.started_at` gives it, or None when it gave none."""
    group: int
    started: str | None


def settings_of(home: Path, folder: Path) -> dict:
    main_tree = settings_reader.main_worktree(folder, COMMAND_TIMEOUT_SECONDS)
    return settings_reader.read_settings(home, main_tree)


def run_command_of(app: str, settings: dict) -> str:
    for held in settings_reader.apps_of(settings):
        if held.name == app:
            if held.run is None:
                raise AppProcessError(f"the app {app} has no run command in the repo settings")
            return held.run
    raise AppProcessError(f"the repo settings name no app {app}")


def is_loading_name(name: str) -> bool:
    return name in LOADING_NAMES or name.startswith(LOADING_PREFIXES)


def slot_variables(settings: dict) -> set[str]:
    """The names a worker may give `--env`: the words of the settings' `slot_use`, in capitals, less the names that
    change how a program is found or loaded."""
    slot_use = settings.get("slot_use")
    words = WORD.findall(slot_use) if isinstance(slot_use, str) else []
    return {word.upper() for word in words if not is_loading_name(word.upper())}


def refuse_unnamed_variables(variables: dict[str, str], settings: dict) -> None:
    allowed = slot_variables(settings)
    for name in variables:
        if name not in allowed:
            raise AppProcessError(f"--env {name} is not a variable that the slot_use of the repo settings names, so "
                                  "nothing started")


def record_path(app: str, home: Path, folder: Path) -> Path:
    key = f"{folder.name}-{hashlib.sha256(str(folder.resolve()).encode('utf-8')).hexdigest()[:12]}"
    return home / APPS_FOLDER / key / f"{app}.json"


def log_path(app: str, folder: Path) -> Path:
    return folder / SCRATCH_FOLDER / APPS_FOLDER / f"{app}.log"


def recorded_group(record: Path) -> Recorded | None:
    """The process group a start recorded, or None when there is no record or it cannot be read."""
    try:
        shown = json.loads(record.read_text(encoding="utf-8"))
        group, started = shown.get("group"), shown.get("started")
    except (OSError, ValueError, AttributeError):
        return None
    if not isinstance(group, int) or group <= 1 or group == processes.own_group():
        return None
    return Recorded(group, started if isinstance(started, str) else None)


def is_what_start_recorded(recorded: Recorded) -> bool:
    """True when the group's leader began when the record says, or is gone. A pid that heads or holds a living group
    is never given to another process, so a group that outlives its leader is still the one that start made."""
    leader = processes.started_at(recorded.group)
    return leader is None or leader == recorded.started


def stop(app: str, home: Path, folder: Path) -> bool:
    """True when it ended a recorded group that was still there; the record is gone either way."""
    record = record_path(app, home, folder)
    recorded = recorded_group(record)
    was_running = False
    if recorded is not None and is_what_start_recorded(recorded):
        was_running = processes.group_is_alive(recorded.group)
        processes.end_group(recorded.group)
    record.unlink(missing_ok=True)
    return was_running


def start(app: str, command: str, variables: dict[str, str], home: Path, folder: Path) -> int:
    stop(app, home, folder)
    log = log_path(app, folder)
    log.parent.mkdir(parents=True, exist_ok=True)
    log.unlink(missing_ok=True)
    with log.open("xb") as output:
        process = subprocess.Popen(command, shell=True, cwd=folder, env={**os.environ, **variables},
                                   stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT,
                                   **processes.detached_options())
    record = record_path(app, home, folder)
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text(json.dumps({"app": app, "group": process.pid, "started": processes.started_at(process.pid),
                                  "command": command}) + "\n", encoding="utf-8")
    return process.pid


def variable(text: str) -> tuple[str, str]:
    name, separator, value = text.partition("=")
    if not name or not separator:
        raise argparse.ArgumentTypeError(f"{text!r} is not NAME=VALUE")
    return name, value


def app_name(text: str) -> str:
    if not APP_NAME.fullmatch(text):
        raise argparse.ArgumentTypeError(f"{text!r} is not an app name")
    return text


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="app_process.py",
                                     description="Start and stop an app's run command for a check worker.")
    modes = parser.add_subparsers(dest="mode", required=True)
    starting = modes.add_parser("start", help="run the app's run command in the background")
    starting.add_argument("app", type=app_name)
    starting.add_argument("--env", action="append", default=[], type=variable, metavar="NAME=VALUE",
                          help="a variable to add to the app's environment, named by the repo settings' slot_use; "
                               "repeat for more")
    stopping = modes.add_parser("stop", help="end the app that start recorded")
    stopping.add_argument("app", type=app_name)
    args = parser.parse_args(argv)
    folder = Path.cwd()
    try:
        home = settings_reader.jidoka_home(None)
        if args.mode == "start":
            settings = settings_of(home, folder)
            command = run_command_of(args.app, settings)
            variables = dict(args.env)
            refuse_unnamed_variables(variables, settings)
            group = start(args.app, command, variables, home, folder)
            print(f"app_process: started {args.app} as process group {group}, output in "
                  f"{log_path(args.app, folder)}")
        elif stop(args.app, home, folder):
            print(f"app_process: stopped {args.app}")
        else:
            print(f"app_process: {args.app} was not running")
    except (AppProcessError, settings_reader.SettingsError, OSError) as error:
        print(f"app_process: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
