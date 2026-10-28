#!/usr/bin/env python3
"""Prints the commands a lap worker may run, the list the lap mod holds a worker's Bash calls to.

`lap_lists.py <kind>` runs in the worker's worktree and prints the list as a
JSON list. The kind is the lap mod's kind of worker:

  lap    a worker of a task's lap. Its list holds each app's `test` command and
         the repo settings' `worker_commands`, then the merge worker's grants
         when the task is at the merge stage, then the built-in list's
         additions from <jidoka-home>/built_in_commands.json, then the
         `extra_commands` of the epic that holds the task. The worktree must
         be a lap worktree.
  check  a validation or app check worker. Its list holds each app's `build`,
         `run` and `way_in` and the repo settings' `worker_commands`, each
         value whole. The lap mod splits a value into its simple commands, as
         it splits every command it decides on. The worktree can be any folder
         of the repo.

A text entry allows its words with any words after them. An object entry is
`{"command", "then"}`, which allows its words with nothing after them when
`then` is `nothing`, with only paths after them when it is `paths`, and with
any words but the long options in its `refusing` list, or an abbreviation of
one, when it is `words`. The merge worker's grants are `git rebase <epic
branch>`, `git rebase --abort` and `git -c core.editor=true rebase
--continue` whole, `git add` of paths, and `git status`, `git diff` and
`git log` without `--output`.

Repo settings that are missing add no app or worker commands.

The home is --jidoka-home, else $JIDOKA_HOME, else ~/.jidoka.

Exit codes:
  0  success.
  1  it could not print the list, with the reason on stderr.
  2  a usage error.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import TypedDict

import lap_record
import repo_settings
import rules
from commands import COMMAND_TIMEOUT_SECONDS, CommandError, metadata_of
from epic_reader import recorded_branch

LAP = "lap"
CHECK = "check"
LOOKS_REFUSING = ["--output"]


class Grant(TypedDict):
    """A built-in entry for one stage: its command, and `nothing`, `paths` or `words` for what may follow it."""
    command: str
    then: str


class RefusingGrant(Grant):
    """A `words` entry, which refuses the long options in `refusing` and their abbreviations."""
    refusing: list[str]


def texts(value: object) -> list[str]:
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def app_values(settings: dict, fields: list[str]) -> list[str]:
    """The text the settings' apps hold under the fields, app by app."""
    apps = settings.get("apps")
    values: list[object] = []
    for app in apps if isinstance(apps, list) else []:
        if isinstance(app, dict):
            values += [app.get(field) for field in fields]
    return texts(values)


def merge_grant(epic_branch: str) -> list[Grant]:
    whole = [f"git rebase {epic_branch}", "git rebase --abort", "git -c core.editor=true rebase --continue"]
    looks = ["git status", "git diff", "git log"]
    return [*(Grant(command=command, then="nothing") for command in whole),
            Grant(command="git add", then="paths"),
            *(RefusingGrant(command=command, then="words", refusing=LOOKS_REFUSING) for command in looks)]


def lap_list(worktree: Path, home: Path, main_tree: Path, settings: dict) -> list[str | Grant]:
    task = lap_record.task_in_worktree(worktree, main_tree)
    epic = rules.epic_holding(task, main_tree)
    epic_branch = recorded_branch(epic)
    is_merging = lap_record.stage_of(metadata_of(task)) == lap_record.MERGE
    granted = merge_grant(epic_branch) if is_merging and epic_branch else []
    return [*app_values(settings, ["test"]), *texts(settings.get("worker_commands")), *granted,
            *repo_settings.built_in_commands(home), *rules.extra_commands_of(epic)]


def check_list(settings: dict) -> list[str]:
    return [*app_values(settings, ["build", "run", "way_in"]), *texts(settings.get("worker_commands"))]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="lap_lists.py", description="Print the commands a lap worker may run.")
    parser.add_argument("kind", choices=[LAP, CHECK])
    parser.add_argument("--jidoka-home", help="the folder that holds jidoka's per-machine state")
    args = parser.parse_args(argv)

    try:
        main_tree = repo_settings.main_worktree(Path.cwd(), COMMAND_TIMEOUT_SECONDS)
        home = repo_settings.jidoka_home(args.jidoka_home)
        settings = repo_settings.load(repo_settings.settings_path(home, main_tree))
        printed = lap_list(Path.cwd(), home, main_tree, settings) if args.kind == LAP else check_list(settings)
    except (lap_record.NotALapWorktree, rules.RulesError, CommandError, repo_settings.SettingsError, OSError) as error:
        print(f"lap_lists: {error}", file=sys.stderr)
        return 1
    print(json.dumps(printed))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
