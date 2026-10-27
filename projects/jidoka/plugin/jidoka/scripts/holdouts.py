#!/usr/bin/env python3
"""Reads and writes an epic's holdouts, which live under one metadata key of the epic bead.

The value is the holdouts as JSON, compressed with zlib and then base64
encoded, so the text means nothing to a model that reads the bead with
bd show. The holdouts are a list, and each holdout is an object with "app",
the name of the app it reaches, and "tasks", the ids of the tasks it
exercises.

`write <epic>` reads the holdouts as one JSON list on stdin, checks their
shape, and stores them on the epic in place of any it held, with
BEADS_ACTOR set to the repo's git user.name.

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

import repo_settings
from commands import COMMAND_TIMEOUT_SECONDS, CommandError, env_as_git_user, run

HOLDOUTS_KEY = "holdouts"


class HoldoutsError(Exception):
    """Holdouts that cannot be read or stored, worded for the person who reads stderr."""


@dataclass(frozen=True)
class Holdout:
    """The app a holdout reaches and the tasks it exercises."""
    app: str
    tasks: tuple[str, ...]


def parsed(holdouts: object) -> list[Holdout]:
    if not isinstance(holdouts, list):
        raise HoldoutsError("the holdouts are not a JSON list")
    found = []
    for index, holdout in enumerate(holdouts):
        if not (isinstance(holdout, dict) and isinstance(holdout.get("app"), str) and holdout["app"].strip()
                and isinstance(holdout.get("tasks"), list)
                and all(isinstance(task, str) and task.strip() for task in holdout["tasks"])):
            raise HoldoutsError(f"holdout {index} is not an object with an app name and a list of task ids")
        found.append(Holdout(holdout["app"], tuple(holdout["tasks"])))
    return found


def encode(holdouts: list[Holdout]) -> str:
    text = json.dumps([{"app": holdout.app, "tasks": list(holdout.tasks)} for holdout in holdouts])
    return base64.b64encode(zlib.compress(text.encode("utf-8"))).decode("ascii")


def decode(value: str) -> list[Holdout]:
    try:
        text = zlib.decompress(base64.b64decode(value, validate=True)).decode("utf-8")
        return parsed(json.loads(text))
    except (binascii.Error, zlib.error, UnicodeDecodeError, ValueError) as error:
        raise HoldoutsError(f"the {HOLDOUTS_KEY} metadata cannot be read: {error}") from error


def of_epic(shown: dict) -> list[Holdout]:
    """The holdouts of the epic as bd show --json prints it, an empty list when it has none."""
    value = (shown.get("metadata") or {}).get(HOLDOUTS_KEY)
    return decode(str(value)) if value else []


def write(epic: str, raw: str, main_tree: Path) -> None:
    try:
        holdouts = parsed(json.loads(raw))
    except ValueError as error:
        raise HoldoutsError(f"the input is not valid JSON: {error}") from error
    run(["bd", "update", epic, "--set-metadata", f"{HOLDOUTS_KEY}={encode(holdouts)}"], main_tree,
        env_as_git_user(main_tree))


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="holdouts.py", description="Store an epic's holdouts.")
    modes = parser.add_subparsers(dest="mode", required=True)
    writing = modes.add_parser("write", help="store the JSON list of holdouts on stdin on the epic")
    writing.add_argument("epic")
    args = parser.parse_args(argv)
    try:
        main_tree = repo_settings.main_worktree(Path.cwd(), COMMAND_TIMEOUT_SECONDS)
        write(args.epic, sys.stdin.read(), main_tree)
    except (HoldoutsError, CommandError, repo_settings.SettingsError, OSError) as error:
        print(f"holdouts: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
