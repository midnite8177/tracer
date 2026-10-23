#!/usr/bin/env python3
"""Writes and shows the settings jidoka keeps for one repo on this machine.

The settings live in <jidoka-home>/repos/<key>.json, where the key comes from
the path of the repo's main worktree, so every worktree of the repo finds the
same file. Moving or renaming the main worktree leaves its settings behind
under the old key. The home is --jidoka-home, else $JIDOKA_HOME, else
~/.jidoka.

`write` reads one JSON object on stdin. Its keys replace the stored ones and
the stored keys it leaves out stay. The script checks the merged settings
before it writes anything, and it derives "build" and "full_suite": the build
of every app that has one, and every app's test, in app order. "moved_lines" names exact
lines of the main worktree's CLAUDE.local.md that the settings now hold; the
script removes one copy of the line for each time it is named and keeps every
other byte of the file.

`show` prints the stored settings, or exits 1 when the repo has none.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

GIT_TIMEOUT_SECONDS = 30
LOCAL_RULES = "CLAUDE.local.md"
GIVEN_KEYS = ["lap_test_scope", "worker_commands", "slot_use", "lap_limit", "apps"]
DERIVED_KEYS = ["build", "full_suite"]
MOVED_LINES = "moved_lines"
APP_KEYS = ["name", "kind", "way_in", "build", "run", "test", "test_target"]
TEST_SCOPES = ["targeted", "full"]
APP_KINDS = ["program", "library"]


class SettingsError(Exception):
    """A reason the script writes nothing, worded for the person who reads stderr."""


def jidoka_home(flag: str | None) -> Path:
    named = flag or os.environ.get("JIDOKA_HOME") or "~/.jidoka"
    return Path(named).expanduser().resolve()


def main_worktree(folder: Path, timeout_seconds: float) -> Path:
    """The common dir is the main worktree's .git, and git may print it relative to the folder."""
    try:
        done = subprocess.run(["git", "rev-parse", "--git-common-dir"], cwd=folder, capture_output=True,
                              text=True, encoding="utf-8", timeout=timeout_seconds)
    except (OSError, subprocess.SubprocessError) as error:
        raise SettingsError(f"git could not run in {folder}: {error}") from error
    common = done.stdout.strip()
    if done.returncode != 0 or not common:
        raise SettingsError(f"{folder} is not inside a git repo")
    return (folder / common).resolve().parent


def settings_path(home: Path, main_tree: Path) -> Path:
    digest = hashlib.sha256(str(main_tree).encode("utf-8")).hexdigest()[:8]
    return home / "repos" / f"{main_tree.name}-{digest}.json"


def load(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as error:
        raise SettingsError(f"{path} is not valid JSON: {error}") from error
    if not isinstance(data, dict):
        raise SettingsError(f"{path} does not hold a JSON object")
    return data


def is_text(value: object) -> bool:
    return isinstance(value, str) and value.strip() != ""


def text_or_null(value: object) -> bool:
    return value is None or is_text(value)


def app_problems(index: int, app: object) -> list[str]:
    if not isinstance(app, dict):
        return [f"apps[{index}] is not a JSON object"]
    name = app.get("name")
    label = f"app {name!r}" if is_text(name) else f"apps[{index}]"
    problems = []
    if not is_text(name):
        problems.append(f"{label} has no name")
    unknown = sorted(set(app) - set(APP_KEYS))
    if unknown:
        problems.append(f"{label} has keys jidoka does not know: {', '.join(unknown)}")
    if app.get("kind") not in APP_KINDS:
        problems.append(f"{label} has kind {app.get('kind')!r}; it must be one of {', '.join(APP_KINDS)}")
    for key in ("way_in", "build", "run"):
        if key not in app:
            problems.append(f"{label} has no {key}; use null when it has none")
        elif not text_or_null(app[key]):
            problems.append(f"{label} has a {key} that is neither a command nor null")
    if not is_text(app.get("test")):
        problems.append(f"{label} has no test command")
    if not is_text(app.get("test_target")):
        problems.append(f"{label} does not say how to target a test")
    return problems


def problems_in(settings: dict) -> list[str]:
    problems = [f"{key} is missing" for key in GIVEN_KEYS if key not in settings]
    unknown = sorted(set(settings) - set(GIVEN_KEYS))
    if unknown:
        problems.append(f"the settings have keys jidoka does not know: {', '.join(unknown)}")
    if "lap_test_scope" in settings and settings["lap_test_scope"] not in TEST_SCOPES:
        problems.append(f"lap_test_scope must be one of {', '.join(TEST_SCOPES)}")
    commands = settings.get("worker_commands")
    if "worker_commands" in settings and not (isinstance(commands, list) and all(map(is_text, commands))):
        problems.append("worker_commands must be a list of commands")
    if "slot_use" in settings and not text_or_null(settings["slot_use"]):
        problems.append("slot_use must be text or null")
    limit = settings.get("lap_limit")
    if "lap_limit" in settings and not (isinstance(limit, int) and not isinstance(limit, bool) and limit > 0):
        problems.append("lap_limit must be a whole number above zero")
    if "apps" in settings:
        problems += apps_problems(settings["apps"])
    return problems


def apps_problems(apps: object) -> list[str]:
    if not isinstance(apps, list) or not apps:
        return ["apps must be a list that holds at least one app"]
    problems = []
    for index, app in enumerate(apps):
        problems += app_problems(index, app)
    names = [app.get("name") for app in apps if isinstance(app, dict)]
    repeated = sorted({name for name in names if isinstance(name, str) and names.count(name) > 1})
    if repeated:
        problems.append(f"more than one app is named {', '.join(repeated)}")
    if not any(isinstance(app, dict) and is_text(app.get("build")) for app in apps):
        problems.append("no app has a build command, so the repo has no build")
    return problems


def read_text(path: Path) -> str:
    with open(path, encoding="utf-8", newline="") as fh:
        return fh.read()


def write_text(path: Path, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def without_moved_lines(text: str, moved: list[str]) -> str:
    left = Counter(moved)
    kept = []
    for line in text.splitlines(keepends=True):
        bare = line.rstrip("\r\n")
        if left[bare] > 0:
            left[bare] -= 1
        else:
            kept.append(line)
    return "".join(kept)


def moved_lines_problems(moved: object, local: Path) -> list[str]:
    if not (isinstance(moved, list) and all(isinstance(line, str) for line in moved)):
        return [f"{MOVED_LINES} must be a list of lines"]
    if not moved:
        return []
    blank = [f"{MOVED_LINES} holds a blank line, and blank lines never move" for line in moved if not line.strip()]
    if blank:
        return blank[:1]
    if not local.is_file():
        return [f"{local} does not exist, so it holds none of the moved lines"]
    held = Counter(line.rstrip("\r\n") for line in read_text(local).splitlines(keepends=True))
    return [moved_line_problem(local, line, held[line], count)
            for line, count in Counter(moved).items() if held[line] < count]


def moved_line_problem(local: Path, line: str, held: int, named: int) -> str:
    if held == 0:
        return f"{local} does not hold the line {line!r}"
    return f"{local} holds the line {line!r} {held} times, but {MOVED_LINES} names it {named} times"


def write(home: Path, cwd: Path, raw: str) -> Path:
    try:
        given = json.loads(raw)
    except ValueError as error:
        raise SettingsError(f"the input is not valid JSON: {error}") from error
    if not isinstance(given, dict):
        raise SettingsError("the input is not a JSON object")
    main_tree = main_worktree(cwd, GIT_TIMEOUT_SECONDS)
    path = settings_path(home, main_tree)
    local = main_tree / LOCAL_RULES
    moved = given.pop(MOVED_LINES, [])
    previous = load(path)
    stored = {key: value for key, value in previous.items() if key in GIVEN_KEYS}
    merged = {**stored, **given}
    problems = problems_in(merged) + moved_lines_problems(moved, local)
    if problems:
        raise SettingsError("nothing was written:\n" + "\n".join(f"  {problem}" for problem in problems))
    settings = {
        "main_worktree": str(main_tree),
        **{key: merged[key] for key in GIVEN_KEYS},
        "build": [app["build"] for app in merged["apps"] if app["build"] is not None],
        "full_suite": [app["test"] for app in merged["apps"]],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    if moved:
        write_text(local, without_moved_lines(read_text(local), moved))
    return path


def show(home: Path, cwd: Path) -> str:
    main_tree = main_worktree(cwd, GIT_TIMEOUT_SECONDS)
    path = settings_path(home, main_tree)
    settings = load(path)
    if not settings:
        raise SettingsError(f"no settings for {main_tree} in {path.parent}. Run /jidoka:onboard to record them")
    return json.dumps(settings, indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str]) -> int:
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("--jidoka-home", help="the folder that holds jidoka's per-machine state")
    parser = argparse.ArgumentParser(prog="repo_settings.py",
                                     description="Write or show jidoka's settings for the repo of the cwd.")
    modes = parser.add_subparsers(dest="mode", required=True)
    modes.add_parser("write", parents=[shared], help="merge the JSON object on stdin into the settings")
    modes.add_parser("show", parents=[shared], help="print the settings")
    args = parser.parse_args(argv)
    home = jidoka_home(args.jidoka_home)
    cwd = Path.cwd()
    try:
        if args.mode == "write":
            out = f"{write(home, cwd, sys.stdin.buffer.read().decode('utf-8'))}\n"
        else:
            out = show(home, cwd)
    except UnicodeDecodeError as error:
        print(f"repo_settings: the input is not UTF-8: {error}", file=sys.stderr)
        return 1
    except (SettingsError, OSError) as error:
        print(f"repo_settings: {error}", file=sys.stderr)
        return 1
    sys.stdout.buffer.write(out.encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
