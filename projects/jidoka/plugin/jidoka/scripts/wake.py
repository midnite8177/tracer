#!/usr/bin/env python3
"""Says how long to wait before waking a host whose turn ended on an API error, and what to wake it with.

`wake.py --failures <n> --session <id>` is what the lap mod runs from the host's folder after the host's n-th turn
in a row ended on an API error, the StopFailure that a usage limit or an outage causes, naming its own session. The
manager's turn dies there, and an idle host does nothing until a prompt reaches it. Where the session manages an
epic (heartbeat.managed_by), the script prints one JSON object with `epic`, `seconds` (the back-off for the n-th
failure, pause.wait_seconds) and `text`, the prompt that tells the manager to run the scheduler's carry-on. Where
the session manages none, such as an advisor's, it prints nothing, pauses nothing, and the mod wakes nobody.

`--error <kind>` is the kind the StopFailure event carried. A billing_error or authentication_failed also
pauses the running epic on that cause and sends the factory-paused notification once, because only the human
clears either.

The home is --jidoka-home, else $JIDOKA_HOME, else ~/.jidoka.

Exit codes:
  0  the wake was printed, or no epic runs.
  1  it could not run, with the reason on stderr.
  2  a usage error.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import clock
import heartbeat
import launcher
import notify
import pause
import settings_reader
from commands import COMMAND_TIMEOUT_SECONDS, CommandError
from epic_reader import EpicReadError
from epics import EpicsError

HUMAN_CAUSES = {"billing_error": pause.BILLING, "authentication_failed": pause.AUTH}


def pause_and_notify(epic: str, cause: str, home: Path, main_tree: Path) -> None:
    """Pauses the epic on the trouble the host's own turn met, then sends the factory-paused notification.

    A held pause that still waits stays as it is, and one whose wait is over gains a retry and a longer wait, as
    pause.after_trouble says. notify.py sends each pause once. Missing a notification loses
    nothing, so one that cannot be sent never fails the wake.
    """
    pause.meet_trouble(epic, cause, clock.now(), main_tree)
    notify.announce(notify.FACTORY_PAUSED, epic, home, main_tree, "wake")


def wake_text(epic: str, home: Path) -> str:
    return (f"jidoka: the last turn ended on an API error while {epic} runs, and the factory paused. Run "
            f'`{launcher.command_for("scheduler.py")} carry-on {epic} --jidoka-home "{home}"`, start what '
            "its actions name as the factory skill says, and wait again when nothing is left to start.")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="wake.py", description="Say how long to wait before waking the host.")
    parser.add_argument("--failures", type=int, required=True, help="the turns in a row that ended on an API error")
    parser.add_argument("--session", required=True, help="the id of the session whose turn ended on the error")
    parser.add_argument("--error", help="the error kind the StopFailure event carried")
    parser.add_argument("--jidoka-home", help="the folder that holds jidoka's per-machine state")
    args = parser.parse_args(argv)
    if args.failures < 1:
        parser.error("--failures needs a whole number from 1 up")
    try:
        main_tree = settings_reader.main_worktree(Path.cwd(), COMMAND_TIMEOUT_SECONDS)
        home = settings_reader.jidoka_home(args.jidoka_home)
        running = heartbeat.managed_by(home, main_tree, args.session)
    except (EpicsError, EpicReadError, CommandError, settings_reader.SettingsError, OSError) as error:
        print(f"wake: {error}", file=sys.stderr)
        return 1
    if running:
        cause = HUMAN_CAUSES.get(args.error or "")
        if cause is not None:
            try:
                pause_and_notify(running[0], cause, home, main_tree)
            except (EpicsError, EpicReadError, CommandError, OSError) as error:
                print(f"wake: {error}", file=sys.stderr)
        print(json.dumps({"epic": running[0], "seconds": pause.wait_seconds(args.failures - 1),
                          "text": wake_text(running[0], home)}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
