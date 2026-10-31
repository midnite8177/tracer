#!/usr/bin/env python3
"""Prints the folders a lap worker may not write in, which the lap mod holds a worker's Write and Edit calls to.

`lap_protected.py` runs in a lap's worktree and prints a JSON list of the acceptance folders of the repo settings'
apps, as repo-relative paths. The list is empty for the lap of the epic's spec task, the only lap that may change an
acceptance folder. The merge gate holds every other lap to the same folders.

The home is --jidoka-home, else $JIDOKA_HOME, else ~/.jidoka.

Exit codes:
  0  it printed the list.
  1  it could not print the list, with the reason on stderr: bd refuses the task or its epic, or the repo settings do
     not read. The lap mod then denies the worker's Write and Edit.
  2  a usage error.
  3  the folder holds no task's lap, as a pass worktree does not. It has no list: the stage that owns such a worktree
     refuses a change inside an acceptance folder when it settles.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import lap_record
import protected_paths
import settings_reader
from commands import COMMAND_TIMEOUT_SECONDS, CommandError

NO_TASK_LAP_EXIT_CODE = 3
PRINTABLE_ERRORS = (CommandError, settings_reader.SettingsError, OSError)


def barred_folders(worktree: Path, home: Path, main_tree: Path) -> list[str]:
    task = lap_record.task_in_worktree(worktree, main_tree)
    if not task:
        raise CommandError(f"bd shows no task for the lap worktree {worktree}")
    if protected_paths.is_spec_task(task, protected_paths.epic_of_task(task, main_tree)):
        return []
    settings = settings_reader.read_settings(home, main_tree)
    return [str(folder) for folder in protected_paths.protected_folders(settings)]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="lap_protected.py", description="Print the folders a lap worker may not "
                                                                         "write in.")
    parser.add_argument("--jidoka-home", help="the folder that holds jidoka's per-machine state")
    args = parser.parse_args(argv)

    try:
        main_tree = settings_reader.main_worktree(Path.cwd(), COMMAND_TIMEOUT_SECONDS)
        printed = barred_folders(Path.cwd(), settings_reader.jidoka_home(args.jidoka_home), main_tree)
    except lap_record.NotALapWorktree as error:
        print(f"lap_protected: {error}", file=sys.stderr)
        return NO_TASK_LAP_EXIT_CODE
    except PRINTABLE_ERRORS as error:
        print(f"lap_protected: {error}", file=sys.stderr)
        return 1
    print(json.dumps(printed))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
