#!/usr/bin/env python3
"""Records which task is an epic's spec task and which acceptance specs each task makes pass, and prints them back.

The spec task is the epic's `acceptance.spec_task` metadata, the id of one of its tasks. The specs a task makes pass
are its `acceptance.specs` metadata, a JSON list of spec names as text. A spec name is the words of the spec as the
human approved it; the script does not check a name against the app's acceptance folder. Handoff reads both
through `spec_task_of` and `specs_of`.

The specs planning marked as already true are the spec task's `acceptance.already_true` metadata, a JSON list of
spec names too. They pass before the epic's work, so the merge gate asks the spec task's lap to leave them passing,
where it asks it to leave every spec that another task makes pass failing. `already_true_of` reads them.

`show <epic>` prints the epic, its spec task, an empty string when it has none, and each task that makes specs pass
with its specs, as JSON.

`spec-task <epic> <task>` records the task as the epic's spec task, in place of any other. The task must be one of
the epic's tasks.

`makes-pass <epic> <task> <spec> ...` records the specs the task makes pass, in place of any it held. The task must be
one of the epic's tasks, and each spec name must have a letter or a digit. A spec named twice is recorded once.

`already-true <epic> <task> <spec> ...` records the specs planning marked as already true on the task, in place of any
it held, under the same rules as `makes-pass`. It prints what `show` prints, which leaves them out.

All writes run under the repo's git user.name. A write that changes nothing writes nothing. Every write prints what
`show` prints.

Exit codes:
  0  success.
  1  it refused, or a bd command failed, with the reason on stderr; a refusal writes nothing.
  2  a usage error.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import settings_reader
from commands import COMMAND_TIMEOUT_SECONDS, CommandError, env_as_git_user, metadata_of, run, set_metadata
from epic_reader import Epic, EpicReadError, Rerun, epic_of

SPEC_TASK_KEY = "acceptance.spec_task"
SPECS_KEY = "acceptance.specs"
ALREADY_TRUE_KEY = "acceptance.already_true"
RERUN = Rerun(on_the_holding_epic="Name the specs on the epic that holds it", after_onboarding="name the specs")


class SpecsError(Exception):
    """Specs that cannot be read or written, worded for the person who reads stderr."""


def spec_task_of(shown: dict) -> str:
    """The id of the epic's spec task as the epic bead records it, or an empty string when it records none."""
    return str(metadata_of(shown).get(SPEC_TASK_KEY) or "")


def specs_of(shown: dict) -> list[str]:
    """The specs the task bead records as made to pass, none when it records none; raises SpecsError when the
    metadata is not a list of names."""
    return names_under(shown, SPECS_KEY)


def already_true_of(shown: dict) -> list[str]:
    """The specs the task bead records as already true, none when it records none; raises SpecsError when the
    metadata is not a list of names."""
    return names_under(shown, ALREADY_TRUE_KEY)


def names_under(shown: dict, key: str) -> list[str]:
    stored = metadata_of(shown).get(key)
    if stored is None:
        return []
    try:
        names = json.loads(stored) if isinstance(stored, str) else stored
    except ValueError:
        names = None
    if not (isinstance(names, list) and all(isinstance(name, str) and name.strip() for name in names)):
        raise SpecsError(f"{key} of {shown.get('id')} is not a list of spec names. "
                         f"Record the specs again with {'makes-pass' if key == SPECS_KEY else 'already-true'}")
    return names


def encode(names: list[str]) -> str:
    return json.dumps(names, separators=(",", ":"), ensure_ascii=False)


def shown_specs(epic: Epic) -> dict:
    return {"epic": epic.id, "spec_task": spec_task_of(epic.shown),
            "tasks": [{"id": str(task["id"]), "specs": specs}
                      for task in epic.task_beads if (specs := specs_of(task))]}


def task_in(epic: Epic, task: str) -> dict:
    """The bead of the task as the epic holds it; raises SpecsError for a bead the epic does not hold as a task."""
    found = next((bead for bead in epic.task_beads if str(bead["id"]) == task), None)
    if found is None:
        raise SpecsError(f"{task} is not a task of {epic.id}. Name one of the epic's tasks")
    return found


def named_specs(given: list[str]) -> list[str]:
    cleaned = list(dict.fromkeys(" ".join(name.split()) for name in given))
    empty = [name for name in cleaned if not any(character.isalnum() for character in name)]
    if empty:
        raise SpecsError(f"a spec name needs a letter or a digit, not {empty[0]!r}. Name the spec in the words "
                         "the human approved")
    return cleaned


def record_spec_task(epic: Epic, task: str, main_tree: Path) -> None:
    task_in(epic, task)
    if spec_task_of(epic.shown) != task:
        run(["bd", "update", epic.id, *set_metadata((SPEC_TASK_KEY, task))], main_tree, env_as_git_user(main_tree))


def record_specs(epic: Epic, task: str, key: str, given: list[str], main_tree: Path) -> None:
    bead = task_in(epic, task)
    names = named_specs(given)
    if names_under(bead, key) != names:
        run(["bd", "update", task, *set_metadata((key, encode(names)))], main_tree,
            env_as_git_user(main_tree))


def main(argv: list[str]) -> int:
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("epic")
    parser = argparse.ArgumentParser(prog="specs.py", description="Record an epic's spec task and the acceptance "
                                                                  "specs each task makes pass.")
    modes = parser.add_subparsers(dest="mode", required=True)
    modes.add_parser("show", parents=[shared], help="print the epic's spec task and the specs its tasks make pass")
    naming = modes.add_parser("spec-task", parents=[shared], help="record the epic's spec task")
    naming.add_argument("task")
    passing = modes.add_parser("makes-pass", parents=[shared], help="record the specs a task makes pass")
    passing.add_argument("task")
    passing.add_argument("specs", nargs="+", metavar="SPEC")
    true = modes.add_parser("already-true", parents=[shared], help="record the specs planning marked as already true")
    true.add_argument("task")
    true.add_argument("specs", nargs="+", metavar="SPEC")
    args = parser.parse_args(argv)

    try:
        main_tree = settings_reader.main_worktree(Path.cwd(), COMMAND_TIMEOUT_SECONDS)
        if args.mode == "spec-task":
            record_spec_task(epic_of(args.epic, main_tree, RERUN), args.task, main_tree)
        elif args.mode == "makes-pass":
            record_specs(epic_of(args.epic, main_tree, RERUN), args.task, SPECS_KEY, args.specs, main_tree)
        elif args.mode == "already-true":
            record_specs(epic_of(args.epic, main_tree, RERUN), args.task, ALREADY_TRUE_KEY, args.specs, main_tree)
        printed = shown_specs(epic_of(args.epic, main_tree, RERUN))
    except (SpecsError, EpicReadError, CommandError, settings_reader.SettingsError, OSError) as error:
        print(f"specs: {error}", file=sys.stderr)
        return 1
    print(json.dumps(printed))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
