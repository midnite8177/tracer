#!/usr/bin/env python3
"""Writes and shows the settings jidoka keeps for one repo on this machine.

The settings live in <jidoka-home>/repos/<key>.json, where the key comes from
the path of the repo's main worktree, so every worktree of the repo finds the
same file. Moving or renaming the main worktree leaves its settings behind
under the old key. The home is --jidoka-home, else $JIDOKA_HOME, else
~/.jidoka. `home` prints that folder, so that the lap mod, which writes into
it, asks this script and holds no copy of the rule. A script that only reads
the settings imports settings_reader.py, not this one.

`write` reads one JSON object on stdin. Its keys replace the stored ones and
the stored keys it leaves out stay. The script checks the merged settings
before it writes anything. The build of the repo, the full suite, the hand-run
groups and the apps with no test command are not stored; settings_reader.py
works them out from the apps each time they are asked for. An app's full-suite command is its test, followed by its test_full
when that is not null, and its targeted command is its test followed by its
test_target. An app with no test command has null for test, test_target and
test_full, and [] for hand_run; the script refuses any other mix, and
refuses settings in which no app has a test command or no app has a build.
An app's "acceptance" is the folder of its acceptance specs, relative to the
repo root, or null when it has none; an app that leaves the key out has none.
An app's "spec_command" is the command that runs all of its acceptance specs and its "spec_target" is the
arguments that follow it to run one, with one <...> placeholder for the spec's name, as "test_target" is for a
test. Each is text or null, and a key left out is null. The script refuses a spec_command in an app with no
acceptance folder, a spec_command with no spec_target, and a spec_target with no spec_command. An app may have an
acceptance folder and no spec_command; run_specs.py refuses to run its specs.
An app's "spec_seconds_limit" is how many seconds a validation's run of its acceptance specs may take before acceptance
shows the slowest specs and a design finding names the protocol driver. It is a number above zero or null, and a key
left out is null.
The script appends nothing to a command, so the person onboarding writes
each hand-run group's exclusion into both commands, and the script refuses
a group whose exclusion either command lacks.
"moved_lines" names exact lines of the main worktree's CLAUDE.local.md that
the settings now hold; the script removes one copy of the line for each time
it is named and keeps every other byte of the file.

"glossary" and "adrs" are the paths of the repo's glossary and ADR folder,
relative to its root, and "glossary_and_adrs" says whether the repo commits
them or keeps them private. A key left out keeps its stored value, else
GLOSSARY.md, docs/adr and committed. Private leaves both at their paths and
adds one anchored line for each to the repo's git exclude file, which hides
only files git does not track, so the script refuses private while git
tracks either path. The ADR folder's line has no trailing slash, so it also
hides the link a bench worktree holds there, and the script takes out the
slashed form. When the choice goes back to committed, or a private path
changes, the script takes out the lines it added for the old paths and
keeps every other byte of the file.

"lizard_limits" holds the limits that lizard_hints.py measures functions against: "ccn" for cyclomatic
complexity, "length" for the lines a function spans and "arguments" for its parameter count, each a whole number
above zero. The object replaces the stored one whole. Left out, it keeps the stored limits, else 15, 80 and 6.

"rule_conflicts" lists the repo's rules that overrule jidoka's session rules.
Each one quotes the repo's rule as "repo_rule", names the file that says it,
relative to the repo root, as "written_in", and quotes the jidoka rule it
overrules as "overrules". Left out, it keeps the stored list, else [].

It refuses while git tracks the main worktree's .beads/, naming the
beads_stealth.py command that switches the workspace to stealth mode.

`show` prints the stored settings, or exits 1 when the repo has none.

The built-in list's additions are the commands a human chose to allow in every
repo on this machine. They live in <jidoka-home>/built_in_commands.json, a JSON
list of commands, and the lap mod allows each as it allows a worker command.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

import git_exclude
import launcher
from commands import CommandError
from settings_reader import (BUILT_IN_COMMANDS_FILE, DEFAULTS, DOC_PATH_KEYS, DOCS_DEFAULTS,
                             GIT_TIMEOUT_SECONDS, GIVEN_KEYS, GLOSSARY_AND_ADRS, PRIVATE,
                             SettingsError, built_in_commands, is_text, jidoka_home, main_worktree,
                             problems_in, read_stored, require_stored, settings_path)

LOCAL_RULES = "CLAUDE.local.md"
MOVED_LINES = "moved_lines"
BEADS_WORKSPACE = ".beads"
SWITCH_COMMAND = launcher.command_for("beads_stealth.py")


def tracks(main_tree: Path, path: str, timeout_seconds: float) -> bool:
    try:
        done = subprocess.run(["git", "--literal-pathspecs", "ls-files", "--", path], cwd=main_tree,
                              capture_output=True, text=True, encoding="utf-8", timeout=timeout_seconds)
    except (OSError, subprocess.SubprocessError) as error:
        raise SettingsError(f"git could not run in {main_tree}: {error}") from error
    if done.returncode != 0:
        raise SettingsError(f"git ls-files failed in {main_tree}: {done.stderr.strip()}")
    return done.stdout.strip() != ""


def refuse_tracked_beads(main_tree: Path, timeout_seconds: float) -> None:
    if tracks(main_tree, BEADS_WORKSPACE, timeout_seconds):
        raise SettingsError(f"nothing was written: git tracks {main_tree / BEADS_WORKSPACE}, and jidoka keeps "
                            f"a repo's beads out of git. Switch them to stealth mode with {SWITCH_COMMAND}, "
                            "which untracks them and stages the removal for you to commit")


def refuse_tracked_private_docs(main_tree: Path, settings: dict, timeout_seconds: float) -> None:
    if settings[GLOSSARY_AND_ADRS] != PRIVATE:
        return
    tracked = [settings[key] for key in DOC_PATH_KEYS if tracks(main_tree, settings[key], timeout_seconds)]
    if tracked:
        raise SettingsError(f"nothing was written: git tracks {' and '.join(tracked)}, and the git exclude file "
                            "hides only files git does not track. Keep glossary_and_adrs committed in this repo")


def private_lines(settings: dict) -> list[str]:
    """The exclude lines of private settings, every one without a trailing slash.

    A slash hides only a real folder, and a worktree holds the ADR folder as a link to the main checkout's.
    """
    if settings.get(GLOSSARY_AND_ADRS) != PRIVATE:
        return []
    return [git_exclude.exclude_line(settings[key], folder=False)
            for key in DOC_PATH_KEYS if is_text(settings.get(key))]


def slashed_adr_line(settings: dict) -> list[str]:
    """The ADR folder's exclude line in its slashed form, which hides the folder but not a worktree's link to it."""
    if settings.get(GLOSSARY_AND_ADRS) != PRIVATE or not is_text(settings.get("adrs")):
        return []
    return [git_exclude.exclude_line(settings["adrs"], folder=True)]


def hide_private_docs(main_tree: Path, previous: dict, settings: dict) -> None:
    """Adds the exclude lines the settings call for and takes out those the previous settings added."""
    wanted = private_lines(settings)
    earlier = {**DOCS_DEFAULTS, **previous}
    candidates = private_lines(earlier) + slashed_adr_line(earlier) + slashed_adr_line(settings)
    stale = [line for line in dict.fromkeys(candidates) if line not in wanted]
    if not (wanted or stale):
        return
    file = git_exclude.exclude_file(main_tree)
    git_exclude.remove(file, stale)
    git_exclude.add(file, wanted)


def rehide_private_docs(home: Path, main_tree: Path) -> None:
    """Brings the exclude lines of the stored settings in line with the form private_lines builds."""
    stored = read_stored(home, main_tree)
    hide_private_docs(main_tree, stored, stored)


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
    refuse_tracked_beads(main_tree, GIT_TIMEOUT_SECONDS)
    path = settings_path(home, main_tree)
    local = main_tree / LOCAL_RULES
    moved = given.pop(MOVED_LINES, [])
    previous = read_stored(home, main_tree)
    stored = {key: value for key, value in previous.items() if key in GIVEN_KEYS or key in DEFAULTS}
    merged = {**DEFAULTS, **stored, **given}
    problems = problems_in(merged) + moved_lines_problems(moved, local)
    if problems:
        raise SettingsError("nothing was written:\n" + "\n".join(f"  {problem}" for problem in problems))
    refuse_tracked_private_docs(main_tree, merged, GIT_TIMEOUT_SECONDS)
    settings = {
        "main_worktree": str(main_tree),
        **{key: merged[key] for key in [*GIVEN_KEYS, *DEFAULTS]},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    hide_private_docs(main_tree, previous, settings)
    if moved:
        write_text(local, without_moved_lines(read_text(local), moved))
    return path


def show(home: Path, cwd: Path) -> str:
    main_tree = main_worktree(cwd, GIT_TIMEOUT_SECONDS)
    return json.dumps(require_stored(home, main_tree), indent=2, ensure_ascii=False) + "\n"


def add_built_in_command(home: Path, command: str) -> bool:
    """Adds the command to the built-in list's additions; False when it is already there."""
    held = built_in_commands(home)
    if command in held:
        return False
    home.mkdir(parents=True, exist_ok=True)
    (home / BUILT_IN_COMMANDS_FILE).write_text(json.dumps([*held, command], indent=2, ensure_ascii=False) + "\n",
                                               encoding="utf-8", newline="\n")
    return True


def add_worker_command(home: Path, main_tree: Path, command: str) -> bool:
    """Adds the command to the repo's worker_commands; False when it is already there."""
    held = require_stored(home, main_tree).get("worker_commands")
    if not isinstance(held, list):
        raise SettingsError("the stored worker_commands is not a list")
    if command in held:
        return False
    write(home, main_tree, json.dumps({"worker_commands": [*held, command]}))
    return True


def main(argv: list[str]) -> int:
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("--jidoka-home", help="the folder that holds jidoka's per-machine state")
    parser = argparse.ArgumentParser(prog="repo_settings.py",
                                     description="Write or show jidoka's settings for the repo of the cwd.")
    modes = parser.add_subparsers(dest="mode", required=True)
    modes.add_parser("write", parents=[shared], help="merge the JSON object on stdin into the settings")
    modes.add_parser("show", parents=[shared], help="print the settings")
    modes.add_parser("home", parents=[shared], help="print jidoka's home")
    args = parser.parse_args(argv)
    home = jidoka_home(args.jidoka_home)
    if args.mode == "home":
        print(home)
        return 0
    cwd = Path.cwd()
    try:
        if args.mode == "write":
            out = f"{write(home, cwd, sys.stdin.buffer.read().decode('utf-8'))}\n"
        else:
            out = show(home, cwd)
    except UnicodeDecodeError as error:
        print(f"repo_settings: the input is not UTF-8: {error}", file=sys.stderr)
        return 1
    except (SettingsError, CommandError, OSError) as error:
        print(f"repo_settings: {error}", file=sys.stderr)
        return 1
    sys.stdout.buffer.write(out.encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
