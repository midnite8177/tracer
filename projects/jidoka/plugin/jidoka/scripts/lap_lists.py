#!/usr/bin/env python3
"""Prints the commands a lap worker may run, the list the lap mod holds a worker's Bash calls to.

`lap_lists.py <kind>` runs in the worker's worktree and prints the list as a
JSON list. The kind is the lap mod's kind of worker:

  lap    a worker of a task's lap. Its list holds each app's `test` command and
         the repo settings' `worker_commands`, then the merge worker's grants
         when the task is at the merge stage, then the call to run_specs.py
         when the task makes acceptance specs pass (any words but
         --jidoka-home), then the built-in list's
         additions from <jidoka-home>/built_in_commands.json, then the
         `extra_commands` of the epic that holds the task. A pass's test
         cleanup, tidy, review or fix worker runs in a folder under the
         main checkout's .worktrees named for its stage and its epic. There
         the epic is the one the folder names, and there is no merge grant;
         the list holds the looks instead, after the repo settings' commands,
         so the worker can read the epic's change from its base.
         The validation worktree is the exception, as below.
         Any other folder names no epic.
  check  a validation or app check worker. Its list holds each app's `build`,
         `run` and `way_in` and the repo settings' `worker_commands`. The
         worktree can be any folder of the repo.

Each list prints its values whole. The lap mod splits a value into its simple
commands, as it splits every command it decides on, and a value it cannot
split, such as one with a command substitution or an output redirect, adds
nothing.

A text entry allows its words with any words after them. An object entry is
`{"command", "then"}`, which allows its words with nothing after them when
`then` is `nothing`, with only paths after them when it is `paths`, and with
any words but the long options in its `refusing` list, or an abbreviation of
one, when it is `words`. The looks are `git status`, `git diff` and `git log`
without `--output`. The merge worker's grants are `git rebase <epic
branch>`, `git rebase --abort` and `git -c core.editor=true rebase
--continue` whole, `git add` of paths, and the looks. The merge worker of a validation works in the
validation worktree, a folder named for its epic, and only while the epic
records that its validation owes a merge worker (`validation.merge`). Its
grants are `git merge main`, `git merge --abort` and `git -c core.editor=true
merge --continue` whole, with the same `git add` and looks.

Repo settings that are missing add no app or worker commands to the lap list, and the check list refuses.
The lap list is three parts, read one by one: the repo settings' commands, the built-in list,
and the epic's commands, which are the merge grants and the epic's
`extra_commands`. The script leaves out a part it cannot read, names it
on stderr, and still prints the rest.

The home is --jidoka-home, else $JIDOKA_HOME, else ~/.jidoka.

Exit codes:
  0  it printed the list, whole or with the parts that stderr names left out.
  1  it could not print the list, with the reason on stderr.
  2  a usage error.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, TypedDict, TypeVar

import cleanup
import lap_record
import launcher
import settings_reader
import review
import rules
import specs
import tidy
import validation_merge
from commands import COMMAND_TIMEOUT_SECONDS, WORKTREE_FOLDER, CommandError, metadata_of
from epic_reader import recorded_branch
from pass_support import MAIN_BRANCH

LAP = "lap"
CHECK = "check"
LOOKS_REFUSING = ["--output"]
SPECS_REFUSING = ["--jidoka-home"]
PASS_PREFIXES = [cleanup.STAGE.prefix, tidy.STAGE.prefix, tidy.LOCAL_STAGE.prefix, review.REVIEW_PREFIX,
                 review.FIX_PREFIX]
PART_ERRORS = (lap_record.NotALapWorktree, rules.RulesError, CommandError, settings_reader.SettingsError, OSError)
Part = TypeVar("Part")


class Grant(TypedDict):
    """A built-in entry for one stage: its command, and `nothing`, `paths` or `words` for what may follow it."""
    command: str
    then: str


class RefusingGrant(Grant):
    """A `words` entry, which refuses the long options in `refusing` and their abbreviations."""
    refusing: list[str]


def test_commands(settings: settings_reader.Settings) -> list[str]:
    """The test command of every app that has one, in app order."""
    return [app.test for app in settings.apps if app.test is not None]


def check_commands(settings: settings_reader.Settings) -> list[str]:
    """The build, run and way in of every app, in that order for each app and in app order, for those it has."""
    return [command for app in settings.apps for command in (app.build, app.run, app.way_in)
            if command is not None]


def looks() -> list[Grant]:
    """`git status`, `git diff` and `git log` with any words but `--output`, which writes a file."""
    return [RefusingGrant(command=command, then="words", refusing=LOOKS_REFUSING)
            for command in ["git status", "git diff", "git log"]]


def grants(whole: list[str]) -> list[Grant]:
    """The commands a merge worker may run whole, then `git add` of paths, then the looks at the conflicts."""
    return [*(Grant(command=command, then="nothing") for command in whole),
            Grant(command="git add", then="paths"),
            *looks()]


def merge_grant(epic_branch: str) -> list[Grant]:
    return grants([f"git rebase {epic_branch}", "git rebase --abort", "git -c core.editor=true rebase --continue"])


def merge_main_grant() -> list[Grant]:
    """What the merge worker of a validation may run in the validation worktree: merge main, and nothing more."""
    return grants([f"git merge {MAIN_BRANCH}", "git merge --abort", "git -c core.editor=true merge --continue"])


def specs_grant(task: dict) -> list[Grant]:
    """What a build worker may run for a task that makes acceptance specs pass: run_specs.py through the launcher, with
    any words but a jidoka home of its own, so that its red run is recorded against the repo's own settings."""
    try:
        if not specs.specs_of(task):
            return []
    except specs.SpecsError:
        return []
    return [RefusingGrant(command=launcher.run_specs_command(), then="words", refusing=SPECS_REFUSING)]


@dataclass(frozen=True)
class EpicPart:
    """What the worktree's epic adds to a lap list: the merge worker's grants, and the epic's extra commands."""
    granted: list[Grant]
    extra: list[str]


NO_EPIC_PART = EpicPart(granted=[], extra=[])


def part_or(missing: str, fallback: Part, read: Callable[[], Part]) -> Part:
    """The part as read; when it cannot be read, the fallback, with the part named on stderr."""
    try:
        return read()
    except PART_ERRORS as error:
        print(f"lap_lists: the list lacks {missing}: {error}", file=sys.stderr)
        return fallback


def epic_named_by(worktree: Path, main_tree: Path, prefixes: list[str]) -> str:
    """The epic the worktree's folder names after one of the prefixes, or an empty string for any other folder."""
    folder = worktree.resolve()
    if folder.parent != (main_tree / WORKTREE_FOLDER).resolve():
        return ""
    for prefix in prefixes:
        if folder.name.startswith(prefix) and len(folder.name) > len(prefix):
            return folder.name[len(prefix):]
    return ""


def pass_epic(worktree: Path, main_tree: Path) -> str:
    """The epic a pass worktree's folder names, or an empty string for a folder that is no pass worktree."""
    return epic_named_by(worktree, main_tree, PASS_PREFIXES)


def lap_epic_part(worktree: Path, main_tree: Path) -> EpicPart:
    task = lap_record.task_in_worktree(worktree, main_tree)
    if not task:
        raise CommandError(f"bd shows no task for the lap worktree {worktree}")
    epic = rules.epic_holding(task, main_tree)
    epic_branch = recorded_branch(epic)
    is_merging = lap_record.stage_of(metadata_of(task)) == lap_record.MERGE
    granted = merge_grant(epic_branch) if is_merging and epic_branch else []
    return EpicPart(granted=[*granted, *specs_grant(task)], extra=rules.extra_commands_of(epic))


def epic_part(worktree: Path, main_tree: Path) -> EpicPart:
    merging = epic_named_by(worktree, main_tree, [validation_merge.WORKTREE_PREFIX])
    epic = merging or pass_epic(worktree, main_tree)
    if not epic:
        return lap_epic_part(worktree, main_tree)
    shown = rules.epic_to_write(epic, main_tree)
    granted = merge_main_grant() if merging and validation_merge.owes_merge(shown) else []
    return EpicPart(granted=granted, extra=rules.extra_commands_of(shown))


def repo_part(home: Path, main_tree: Path) -> list[str]:
    settings = settings_reader.read_settings(home, main_tree)
    return [*test_commands(settings), *settings.worker_commands]


def pass_looks(worktree: Path, main_tree: Path) -> list[Grant]:
    """The looks for a worker of a pass, which reads the epic's change from its base; none in any other folder."""
    return looks() if pass_epic(worktree, main_tree) else []


def lap_list(worktree: Path, home: Path, main_tree: Path) -> list[str | Grant]:
    repo = part_or("the repo settings' commands", [], lambda: repo_part(home, main_tree))
    built_in = part_or("the built-in list", [], lambda: settings_reader.built_in_commands(home))
    epic = part_or("the epic's commands", NO_EPIC_PART, lambda: epic_part(worktree, main_tree))
    return [*repo, *pass_looks(worktree, main_tree), *epic.granted, *built_in, *epic.extra]


def check_list(settings: settings_reader.Settings) -> list[str]:
    return [*check_commands(settings), *settings.worker_commands]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="lap_lists.py", description="Print the commands a lap worker may run.")
    parser.add_argument("kind", choices=[LAP, CHECK])
    parser.add_argument("--jidoka-home", help="the folder that holds jidoka's per-machine state")
    args = parser.parse_args(argv)

    try:
        main_tree = settings_reader.main_worktree(Path.cwd(), COMMAND_TIMEOUT_SECONDS)
        home = settings_reader.jidoka_home(args.jidoka_home)
        if args.kind == LAP:
            printed = lap_list(Path.cwd(), home, main_tree)
        else:
            printed = check_list(settings_reader.read_settings(home, main_tree))
    except PART_ERRORS as error:
        print(f"lap_lists: {error}", file=sys.stderr)
        return 1
    print(json.dumps(printed))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
