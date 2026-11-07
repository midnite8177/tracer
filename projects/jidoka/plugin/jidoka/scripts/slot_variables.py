#!/usr/bin/env python3
"""Prints the variables a lap worker may set in front of a listed command, for the lap mod.

`slot_variables.py` runs in the worker's worktree and prints, as a JSON list in sorted order, the names
`settings_reader.slot_variables` gives for the repo settings: the words of `slot_use` in capitals, less the names that
change how a program is found or loaded. They are the names `app_process.py start --env` takes. A repo whose `slot_use`
is null prints an empty list. The lap mod takes no names from a run that exits non-zero, so that worker sets no
variable in front of a command.

The home is --jidoka-home, else $JIDOKA_HOME, else ~/.jidoka.

Exit codes:
  0  it printed the list.
  1  it could not read the repo settings, with the reason on stderr.
  2  a usage error.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import settings_reader
from commands import COMMAND_TIMEOUT_SECONDS


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="slot_variables.py",
                                     description="Print the variables a lap worker may set in front of a command.")
    parser.add_argument("--jidoka-home", help="the folder that holds jidoka's per-machine state")
    args = parser.parse_args(argv)

    try:
        main_tree = settings_reader.main_worktree(Path.cwd(), COMMAND_TIMEOUT_SECONDS)
        settings = settings_reader.read_settings(settings_reader.jidoka_home(args.jidoka_home), main_tree)
    except (settings_reader.SettingsError, OSError) as error:
        print(f"slot_variables: {error}", file=sys.stderr)
        return 1
    print(json.dumps(sorted(settings_reader.slot_variables(settings))))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
