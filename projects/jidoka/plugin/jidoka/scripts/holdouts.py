#!/usr/bin/env python3
"""Reads and writes an epic's holdouts, which live under one metadata key of the epic bead.

The value is the holdouts as JSON, compressed with zlib and then base64
encoded, so the text means nothing to a model that reads the bead with
bd show. The holdouts are a list, and each holdout is an object with "app",
the name of the app it reaches, "tasks", the ids of the tasks it exercises,
and "scenario", its text.

`write <epic>` reads the holdouts as one JSON list on stdin, checks their
shape, which includes at least one task id in each, and stores them on the
epic in place of any it held, with BEADS_ACTOR set to the repo's git
user.name. `read <epic>` prints the epic's holdouts as one JSON list, `[]`
when it has none. `read <epic> --task <task>` prints only the holdouts that
name the task, each with its `holdout`, its number among all the epic's
holdouts, counted from 1 in the order of the full list, which a report names
it by. `brief <epic>` prints what a subagent that drafts
holdouts may read, as one JSON object: the epic's id, its title, its spec,
which is the epic's description, and each app of the repo settings with its
way in and the folder of its acceptance specs. It prints no task and stores
nothing. The home of the repo settings is --jidoka-home, else $JIDOKA_HOME,
else ~/.jidoka.

The hook `holdouts_guard.py` denies this script to every worker but the app
check and validation, and lets the app check run only `read` with `--task`,
so that no builder reads a holdout and no app check reads one that does not
name its task.

Exit codes:
  0  success.
  1  it refused, or a git or bd command failed, with the reason on stderr.
  2  a usage error.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import json
import sys
import zlib
from dataclasses import dataclass
from pathlib import Path

import settings_reader
from commands import COMMAND_TIMEOUT_SECONDS, CommandError, env_as_git_user, metadata_of, read_bead, run

HOLDOUTS_KEY = "holdouts"


class HoldoutsError(Exception):
    """Holdouts that cannot be read or stored, worded for the person who reads stderr."""


@dataclass(frozen=True)
class Holdout:
    """The app a holdout reaches, the tasks it exercises and its scenario, in prose."""
    app: str
    tasks: tuple[str, ...]
    scenario: str


def parsed(holdouts: object) -> list[Holdout]:
    if not isinstance(holdouts, list):
        raise HoldoutsError("the holdouts are not a JSON list")
    found = []
    for index, holdout in enumerate(holdouts):
        if not (isinstance(holdout, dict) and isinstance(holdout.get("app"), str) and holdout["app"].strip()
                and isinstance(holdout.get("tasks"), list)
                and all(isinstance(task, str) and task.strip() for task in holdout["tasks"])
                and isinstance(holdout.get("scenario"), str) and holdout["scenario"].strip()):
            raise HoldoutsError(f"holdout {index} is not an object with an app name, a list of task ids and a "
                                "scenario")
        if not holdout["tasks"]:
            raise HoldoutsError(f"holdout {index} names no task. Name the tasks it exercises")
        found.append(Holdout(holdout["app"], tuple(holdout["tasks"]), holdout["scenario"]))
    return found


def as_json(holdouts: list[Holdout]) -> list[dict]:
    return [{"app": holdout.app, "tasks": list(holdout.tasks), "scenario": holdout.scenario}
            for holdout in holdouts]


def encode(holdouts: list[Holdout]) -> str:
    text = json.dumps(as_json(holdouts))
    return base64.b64encode(zlib.compress(text.encode("utf-8"))).decode("ascii")


def decode(value: str) -> list[Holdout]:
    try:
        text = zlib.decompress(base64.b64decode(value, validate=True)).decode("utf-8")
        return parsed(json.loads(text))
    except (binascii.Error, zlib.error, UnicodeDecodeError, ValueError) as error:
        raise HoldoutsError(f"the {HOLDOUTS_KEY} metadata cannot be read: {error}") from error


def of_epic(shown: dict) -> list[Holdout]:
    """The holdouts of the epic as bd show --json prints it, an empty list when it has none."""
    value = metadata_of(shown).get(HOLDOUTS_KEY)
    return decode(str(value)) if value else []


def numbered_naming(task: str, holdouts: list[Holdout]) -> list[tuple[int, Holdout]]:
    """The holdouts that name the task, each with its number among all of them, counted from 1."""
    return [(number, holdout) for number, holdout in enumerate(holdouts, start=1) if task in holdout.tasks]


def read(epic: str, main_tree: Path) -> list[Holdout]:
    return of_epic(read_bead(epic, main_tree))


def brief(epic: str, main_tree: Path, home: Path) -> dict:
    shown = read_bead(epic, main_tree)
    settings = settings_reader.read_settings(home, main_tree)
    return {"epic": epic, "title": shown.get("title", ""), "spec": shown.get("description") or "",
            "apps": [{"name": app.name, "way_in": app.way_in, "acceptance": app.acceptance}
                     for app in settings.apps]}


def write(epic: str, raw: str, main_tree: Path) -> None:
    try:
        holdouts = parsed(json.loads(raw))
    except ValueError as error:
        raise HoldoutsError(f"the input is not valid JSON: {error}") from error
    run(["bd", "update", epic, "--set-metadata", f"{HOLDOUTS_KEY}={encode(holdouts)}"], main_tree,
        env_as_git_user(main_tree))


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="holdouts.py", description="Read or store an epic's holdouts.")
    modes = parser.add_subparsers(dest="mode", required=True)
    writing = modes.add_parser("write", help="store the JSON list of holdouts on stdin on the epic")
    writing.add_argument("epic")
    reading = modes.add_parser("read", help="print the epic's holdouts as a JSON list")
    reading.add_argument("epic")
    reading.add_argument("--task", help="print only the holdouts that name this task, each with its number")
    briefing = modes.add_parser("brief", help="print the epic's spec and the repo's apps, and no task")
    briefing.add_argument("epic")
    briefing.add_argument("--jidoka-home", help="the folder that holds jidoka's per-machine state")
    args = parser.parse_args(argv)
    try:
        main_tree = settings_reader.main_worktree(Path.cwd(), COMMAND_TIMEOUT_SECONDS)
        if args.mode == "write":
            write(args.epic, sys.stdin.read(), main_tree)
        elif args.mode == "brief":
            home = settings_reader.jidoka_home(args.jidoka_home)
            print(json.dumps(brief(args.epic, main_tree, home), indent=2, ensure_ascii=False))
        elif args.task is not None:
            named = [{"holdout": number, **as_json([holdout])[0]}
                     for number, holdout in numbered_naming(args.task, read(args.epic, main_tree))]
            print(json.dumps(named, indent=2))
        else:
            print(json.dumps(as_json(read(args.epic, main_tree)), indent=2))
    except (HoldoutsError, CommandError, settings_reader.SettingsError, OSError) as error:
        print(f"holdouts: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
