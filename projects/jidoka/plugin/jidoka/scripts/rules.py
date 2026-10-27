#!/usr/bin/env python3
"""Reads and writes an epic's factory rules, the only script that writes them.

Factory rules are an epic's settings, which the scheduler reads, and its
guidance, which every worker follows. Each setting lives in the epic's
metadata under `rules.<name>`, as JSON text, and the guidance under
`rules.guidance` as a JSON string. Every change posts one line on the epic
as a comment, written under the repo's git user.name, which is also the
BEADS_ACTOR of the writes.

The settings:
  lap_test_scope             targeted or full.
  lap_limit                  a whole number above zero and below the repo
                             settings' lap limit, so an epic only goes lower.
  wall_clocks                an object of stage names to whole minutes.
  passes                     the most passes, a whole number above zero.
  discovered_bugs_into_epic  true to file a bug a lap finds inside the epic.
  extra_commands             a list of commands a worker may run.
  tier_routes                an object of tier names to route names.
  stage_tiers                an object of stage names to tier names.
  budget                     the most the epic may spend, in dollars above zero.
  reserves                   an object of account names to a share above 0 and
                             below 1 of that account's usage window.
  commits_on_main            one or per_task.

`show <epic>` prints the epic, its settings and its guidance as JSON.

`set <epic> <name>=<value> ...` checks every setting before it writes any.
A value is JSON, or else the text itself. A setting already at its value
writes nothing and posts nothing. It prints the epic, the settings it
changed and all the settings.

`guidance <epic>` reads the guidance as text on stdin and stores it in place
of any the epic held.

`preset <epic> <preset>` sets what the preset holds, as `set` does. The
presets are bug-epic and improvement-epic.

`lap-commands` runs in a lap's worktree and prints, as a JSON list, the
commands the built-in list's additions and the lap's epic add to what the repo
settings let a lap worker run. The lap mod reads it.

The home is --jidoka-home, else $JIDOKA_HOME, else ~/.jidoka.

Exit codes:
  0  success.
  1  it refused, or a bd command failed, with the reason on stderr; a
     refusal writes nothing.
  2  a usage error.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import repo_settings
from commands import COMMAND_TIMEOUT_SECONDS, CommandError, bd_show, capture, env_as_git_user, run

KEY_PREFIX = "rules."
GUIDANCE_KEY = f"{KEY_PREFIX}guidance"
COMMENT_HEADING = "Factory rules:"
EPIC_TYPE = "epic"
LAP_LIMIT = "lap_limit"
COMMITS_ON_MAIN = ["one", "per_task"]
EXTRA_COMMANDS = "extra_commands"
LAP_BRANCH_PREFIX = "lap/"


class RulesError(Exception):
    """Rules that cannot be read or written, worded for the person who reads stderr."""


def is_whole(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def is_text(value: object) -> bool:
    return isinstance(value, str) and value.strip() != ""


def is_map_of(value: object, valid: Callable[[object], bool]) -> bool:
    return isinstance(value, dict) and all(is_text(name) and valid(item) for name, item in value.items())


def is_minutes(value: object) -> bool:
    return is_whole(value) and value > 0


def is_dollars(value: object) -> bool:
    return is_number(value) and value > 0


def is_share(value: object) -> bool:
    return is_number(value) and 0 < value < 1


SETTINGS: dict[str, tuple[Callable[[object], bool], str]] = {
    "lap_test_scope": (lambda value: value in repo_settings.TEST_SCOPES,
                       f"one of {', '.join(repo_settings.TEST_SCOPES)}"),
    LAP_LIMIT: (is_minutes, "a whole number above zero"),
    "wall_clocks": (lambda value: is_map_of(value, is_minutes),
                    "an object of stage names to whole minutes above zero"),
    "passes": (is_minutes, "a whole number above zero"),
    "discovered_bugs_into_epic": (lambda value: isinstance(value, bool), "true or false"),
    EXTRA_COMMANDS: (lambda value: isinstance(value, list) and all(map(is_text, value)),
                       "a list of commands"),
    "tier_routes": (lambda value: is_map_of(value, is_text), "an object of tier names to route names"),
    "stage_tiers": (lambda value: is_map_of(value, is_text), "an object of stage names to tier names"),
    "budget": (is_dollars, "a number of dollars above zero"),
    "reserves": (lambda value: is_map_of(value, is_share),
                 "an object of account names to a share above 0 and below 1"),
    "commits_on_main": (lambda value: value in COMMITS_ON_MAIN, f"one of {', '.join(COMMITS_ON_MAIN)}"),
}

PRESETS: dict[str, dict[str, object]] = {
    "bug-epic": {"discovered_bugs_into_epic": True, "commits_on_main": "one"},
    "improvement-epic": {"lap_test_scope": "full", "discovered_bugs_into_epic": False,
                         "commits_on_main": "per_task"},
}


@dataclass(frozen=True)
class Rules:
    """An epic's settings by name, and its guidance, or an empty string when it has none."""
    settings: dict[str, object]
    guidance: str

    def lap_limit_under(self, repo_limit: int) -> int:
        """The most laps of the epic at once: the repo's limit, or the epic's own when that is lower."""
        own = self.settings.get(LAP_LIMIT)
        return min(repo_limit, own) if is_whole(own) else repo_limit


def repo_lap_limit(settings: dict) -> int:
    """The repo settings' lap limit, or zero when they hold none."""
    limit = settings.get(LAP_LIMIT)
    return limit if is_minutes(limit) else 0


def encode(value: object) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def decode(stored: object) -> object:
    """The value as bd shows it: text that holds JSON is parsed, other text stays text."""
    if not isinstance(stored, str):
        return stored
    try:
        return json.loads(stored)
    except ValueError:
        return stored


def of_epic(shown: dict) -> Rules:
    """The rules of the epic as bd show --json prints it; no settings and no guidance when it has none."""
    metadata = shown.get("metadata") or {}
    settings: dict[str, object] = {}
    problems = []
    guidance = ""
    for key in sorted(key for key in metadata if str(key).startswith(KEY_PREFIX)):
        value = decode(metadata[key])
        name = str(key)[len(KEY_PREFIX):]
        if key == GUIDANCE_KEY:
            if isinstance(value, str):
                guidance = value
            else:
                problems.append("guidance is not text")
        elif name not in SETTINGS:
            problems.append(f"{name} is not a setting jidoka knows")
        elif not SETTINGS[name][0](value):
            problems.append(f"{name} holds {encode(value)}, where it needs {SETTINGS[name][1]}")
        else:
            settings[name] = value
    if problems:
        raise RulesError(f"the factory rules of {shown.get('id')} cannot be read: {'; '.join(problems)}")
    return Rules(settings, guidance)


def problems_in(wanted: dict[str, object], repo_limit: int) -> list[str]:
    problems = []
    for name, value in wanted.items():
        if name not in SETTINGS:
            problems.append(f"{name} is not a setting. The settings are {', '.join(SETTINGS)}")
        elif not SETTINGS[name][0](value):
            problems.append(f"{name} must be {SETTINGS[name][1]}, not {encode(value)}")
        elif name == LAP_LIMIT and not repo_limit:
            problems.append("the repo settings hold no lap limit, so none can be set lower. "
                            "Run /jidoka:onboard to record one")
        elif name == LAP_LIMIT and value >= repo_limit:
            problems.append(f"{LAP_LIMIT} must be below the repo's {repo_limit}, because an epic can only go "
                            f"lower, not {encode(value)}")
    return problems


def epic_to_write(epic: str, main_tree: Path) -> dict:
    shown = bd_show(epic, main_tree)
    if shown is None:
        raise RulesError(f"bd show printed nothing usable for {epic}")
    if shown.get("issue_type") != EPIC_TYPE:
        raise RulesError(f"{epic} is a {shown.get('issue_type') or 'bead'}, not an epic. Factory rules belong to "
                         "an epic")
    return shown


def change_comment(name: str, value: object, before: object | None) -> str:
    was = "" if before is None else f", was {encode(before)}"
    return f"{COMMENT_HEADING} {name} set to {encode(value)}{was}."


def write_settings(epic: str, wanted: dict[str, object], repo_limit: int, main_tree: Path) -> dict[str, object]:
    """Checks every wanted setting, then writes each that differs from the epic's, with a comment for each.

    Returns the settings it changed.
    """
    shown = epic_to_write(epic, main_tree)
    problems = problems_in(wanted, repo_limit)
    if problems:
        raise RulesError(f"the factory rules of {epic} were not changed:\n"
                         + "\n".join(f"  {problem}" for problem in problems))
    held = of_epic(shown).settings
    env = env_as_git_user(main_tree)
    changed: dict[str, object] = {}
    for name, value in wanted.items():
        if held.get(name) == value and type(held.get(name)) is type(value):
            continue
        run(["bd", "update", epic, "--set-metadata", f"{KEY_PREFIX}{name}={encode(value)}"], main_tree, env)
        run(["bd", "comment", epic, change_comment(name, value, held.get(name))], main_tree, env)
        changed[name] = value
    return changed


def write_guidance(epic: str, text: str, main_tree: Path) -> bool:
    """Stores the guidance in place of the epic's own; False when it is already what the epic holds."""
    shown = epic_to_write(epic, main_tree)
    guidance = text.strip()
    if not guidance:
        raise RulesError(f"the guidance for {epic} is empty, and nothing was changed")
    if of_epic(shown).guidance == guidance:
        return False
    env = env_as_git_user(main_tree)
    run(["bd", "update", epic, "--set-metadata", f"{GUIDANCE_KEY}={encode(guidance)}"], main_tree, env)
    lines = len(guidance.splitlines())
    run(["bd", "comment", epic, f"{COMMENT_HEADING} guidance set, {lines} {'line' if lines == 1 else 'lines'}."],
        main_tree, env)
    return True


def allow_extra_command(epic: str, command: str, home: Path, main_tree: Path) -> bool:
    """Adds the command to the epic's extra_commands; False when the epic already allows it."""
    held = of_epic(epic_to_write(epic, main_tree)).settings.get(EXTRA_COMMANDS, [])
    if not isinstance(held, list) or command in held:
        return False
    write_settings(epic, {EXTRA_COMMANDS: [*held, command]}, repo_limit_of(home, main_tree), main_tree)
    return True


def lap_commands(worktree: Path, home: Path, main_tree: Path) -> list[str]:
    """The built-in list's additions, then the extra_commands of the epic that holds the lap's task."""
    done = capture(["git", "rev-parse", "--abbrev-ref", "HEAD"], worktree, None)
    branch = done.stdout.strip()
    if done.returncode != 0 or not branch.startswith(LAP_BRANCH_PREFIX):
        raise RulesError(f"{worktree} is not a lap worktree: its branch is {branch or 'unknown'}, not "
                         f"{LAP_BRANCH_PREFIX}<task>")
    task = bd_show(branch[len(LAP_BRANCH_PREFIX):], main_tree)
    epic = str(task.get("parent") or "") if task is not None else ""
    extra = of_epic(epic_to_write(epic, main_tree)).settings.get(EXTRA_COMMANDS, []) if epic else []
    return [*repo_settings.built_in_commands(home), *(extra if isinstance(extra, list) else [])]


def shown_rules(epic: str, main_tree: Path) -> dict:
    rules = of_epic(epic_to_write(epic, main_tree))
    return {"epic": epic, "settings": rules.settings, "guidance": rules.guidance}


def parsed_setting(argument: str) -> tuple[str, object]:
    name, separator, text = argument.partition("=")
    if not (separator and name.strip()):
        raise RulesError(f"{argument!r} is not <name>=<value>")
    try:
        return name.strip(), json.loads(text)
    except ValueError:
        return name.strip(), text


def repo_limit_of(home: Path, main_tree: Path) -> int:
    return repo_lap_limit(repo_settings.load(repo_settings.settings_path(home, main_tree)))


def main(argv: list[str]) -> int:
    home_flag = argparse.ArgumentParser(add_help=False)
    home_flag.add_argument("--jidoka-home", help="the folder that holds jidoka's per-machine state")
    shared = argparse.ArgumentParser(add_help=False, parents=[home_flag])
    shared.add_argument("epic")
    parser = argparse.ArgumentParser(prog="rules.py", description="Show or change an epic's factory rules.")
    modes = parser.add_subparsers(dest="mode", required=True)
    modes.add_parser("show", parents=[shared], help="print the epic's settings and guidance")
    setting = modes.add_parser("set", parents=[shared], help="change settings, one comment on the epic for each")
    setting.add_argument("settings", nargs="+", metavar="NAME=VALUE")
    modes.add_parser("guidance", parents=[shared], help="store the guidance on stdin")
    presetting = modes.add_parser("preset", parents=[shared], help="set what a preset holds")
    presetting.add_argument("preset", choices=sorted(PRESETS))
    modes.add_parser("lap-commands", parents=[home_flag], help="print the commands the lap in the cwd may also run")
    args = parser.parse_args(argv)

    try:
        main_tree = repo_settings.main_worktree(Path.cwd(), COMMAND_TIMEOUT_SECONDS)
        home = repo_settings.jidoka_home(args.jidoka_home)
        if args.mode == "lap-commands":
            printed = lap_commands(Path.cwd(), home, main_tree)
        elif args.mode == "show":
            printed = shown_rules(args.epic, main_tree)
        elif args.mode == "guidance":
            printed = {"epic": args.epic, "changed": write_guidance(args.epic, sys.stdin.read(), main_tree)}
        else:
            wanted = (PRESETS[args.preset] if args.mode == "preset"
                      else dict(parsed_setting(argument) for argument in args.settings))
            changed = write_settings(args.epic, wanted, repo_limit_of(home, main_tree), main_tree)
            printed = {**shown_rules(args.epic, main_tree), "changed": changed}
    except (RulesError, CommandError, repo_settings.SettingsError, OSError) as error:
        print(f"rules: {error}", file=sys.stderr)
        return 1
    print(json.dumps(printed))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
