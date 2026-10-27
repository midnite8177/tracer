#!/usr/bin/env python3
"""Says how long to wait before waking a host whose turn ended on an API error, and what to wake it with.

`wake.py --failures <n>` is what the lap mod runs from the host's folder after the host's n-th turn in a row
ended on an API error, the StopFailure that a usage limit or an outage causes. The manager's turn dies there,
and an idle host does nothing until a prompt reaches it. Where an epic runs, the script prints one JSON object
with `epic`, `seconds` (the back-off for the n-th failure, pause.wait_seconds) and `text`, the prompt that tells
the manager to run the scheduler's carry-on. Where no epic runs, it prints nothing, and the mod wakes nobody.

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

import notify
import pause
import repo_settings
from commands import COMMAND_TIMEOUT_SECONDS, CommandError
from handoff import HandoffError

SCRIPTS = Path(__file__).resolve().parent


def wake_text(epic: str, home: Path) -> str:
    launcher = SCRIPTS.parent / "bin" / "jidoka-run"
    return (f"jidoka: the last turn ended on an API error while {epic} runs, and the factory paused. Run "
            f'`sh "{launcher}" "{SCRIPTS / "scheduler.py"}" carry-on {epic} --jidoka-home "{home}"`, start what '
            "its actions name as the factory skill says, and wait again when nothing is left to start.")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="wake.py", description="Say how long to wait before waking the host.")
    parser.add_argument("--failures", type=int, required=True, help="the turns in a row that ended on an API error")
    parser.add_argument("--jidoka-home", help="the folder that holds jidoka's per-machine state")
    args = parser.parse_args(argv)
    if args.failures < 1:
        parser.error("--failures needs a whole number from 1 up")
    try:
        main_tree = repo_settings.main_worktree(Path.cwd(), COMMAND_TIMEOUT_SECONDS)
        running = notify.running_epics(main_tree)
        home = repo_settings.jidoka_home(args.jidoka_home)
    except (notify.NotifyError, HandoffError, CommandError, repo_settings.SettingsError, OSError) as error:
        print(f"wake: {error}", file=sys.stderr)
        return 1
    if running:
        print(json.dumps({"epic": running[0], "seconds": pause.wait_seconds(args.failures - 1),
                          "text": wake_text(running[0], home)}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
