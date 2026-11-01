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
  lap_limit                  a whole number above zero and below the lower of the
                             machine settings' and the repo settings' lap limit,
                             so an epic only goes lower.
  wall_clocks                an object of stage names to whole minutes.
  passes                     the most passes, a whole number above zero.
  discovered_bugs_into_epic  true to file a bug a lap finds inside the epic.
  extra_commands             a list of commands a worker may run.
  tier_routes                an object of tier names to route names. A route name `codex`,
                             or starting `codex-`, is refused for a tier that has a
                             stage which writes.
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

`choices <epic>` prints, as JSON, each setting that a person picks from a short list, with its choices and the value
the epic holds, null when it holds none: lap_test_scope, lap_limit, discovered_bugs_into_epic and commits_on_main. The
lap limit's choices are the whole numbers below the repo settings' own, none when that is one or zero.

`guidance <epic>` reads the guidance as text on stdin and stores it in place
of any the epic held.

`preset <epic> <preset>` sets what the preset holds, as `set` does. The
presets are bug-epic and improvement-epic.

`lap-commands` runs in a lap's worktree and prints, as a JSON list, the
extra_commands of the epic that holds the lap's task. lap_lists.py reads the
same extra_commands through `extra_commands_of`.

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

import lap_record
import settings_reader
import routes
from commands import COMMAND_TIMEOUT_SECONDS, CommandError, env_as_git_user, metadata_of, parent_of, run
from epic_reader import NotAnEpic, shown_epic
from settings_reader import is_positive_whole

KEY_PREFIX = "rules."
GUIDANCE_KEY = f"{KEY_PREFIX}guidance"
COMMENT_HEADING = "Factory rules:"
LAP_LIMIT = "lap_limit"
DEFAULT_MACHINE_LAP_LIMIT = 4
ONE_COMMIT = "one"
PER_TASK = "per_task"
COMMITS_ON_MAIN = [ONE_COMMIT, PER_TASK]
EXTRA_COMMANDS = "extra_commands"


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


def is_dollars(value: object) -> bool:
    return is_number(value) and value > 0


def is_share(value: object) -> bool:
    return is_number(value) and 0 < value < 1


SETTINGS: dict[str, tuple[Callable[[object], bool], str]] = {
    "lap_test_scope": (lambda value: value in settings_reader.TEST_SCOPES,
                       f"one of {', '.join(settings_reader.TEST_SCOPES)}"),
    LAP_LIMIT: (is_positive_whole, "a whole number above zero"),
    "wall_clocks": (lambda value: is_map_of(value, is_positive_whole),
                    "an object of stage names to whole minutes above zero"),
    "passes": (is_positive_whole, "a whole number above zero"),
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

@dataclass(frozen=True)
class Preset:
    """A set of factory rules a human can start an epic from: its settings, and its guidance, or an empty string
    when it has none."""
    settings: dict[str, object]
    guidance: str

    def fields(self) -> dict:
        return {"settings": self.settings, "guidance": self.guidance}


PRESETS: dict[str, Preset] = {
    "bug-epic": Preset({"discovered_bugs_into_epic": True, "commits_on_main": PER_TASK}, ""),
    "improvement-epic": Preset({}, "changes nothing a user sees"),
}


@dataclass(frozen=True)
class Rules:
    """An epic's settings by name, and its guidance, or an empty string when it has none."""
    settings: dict[str, object]
    guidance: str

    @property
    def commits_on_main(self) -> str:
        """How landing puts the epic on main: ONE_COMMIT, or PER_TASK for a commit of each task."""
        return str(self.settings.get("commits_on_main", ONE_COMMIT))


def machine_lap_limit(home: Path) -> int:
    """The machine settings' lap limit, or DEFAULT_MACHINE_LAP_LIMIT when they hold none that is a whole number
    above zero. Settings that cannot be read give the default, and a line on stderr."""
    held = routes.machine_default(home, LAP_LIMIT, "lap limit",
                                  lambda value: value if is_positive_whole(value) else None)
    return held if held is not None else DEFAULT_MACHINE_LAP_LIMIT


@dataclass(frozen=True)
class LapCeiling:
    """The most laps one epic runs at once before its own rule says less: the lower of the machine settings' lap
    limit and the repo settings', which is zero when they hold none."""
    machine: int
    repo: int

    @property
    def limit(self) -> int:
        return min(self.machine, self.repo)

    @property
    def owner(self) -> str:
        """Whose limit is the lower, worded for a refusal."""
        return "machine's" if self.machine < self.repo else "repo's"


@dataclass(frozen=True)
class LapLimits:
    """The most laps at once: the epic's own, which is the lowest of the machine's, the repo's and the epic's factory
    rule, and the machine's across every running epic."""
    epic: int
    machine: int


def lap_ceiling(settings: settings_reader.Settings, home: Path) -> LapCeiling:
    """The ceiling that the machine settings and the repo settings put on an epic's lap limit."""
    return LapCeiling(machine_lap_limit(home), settings.lap_limit)


def lap_limits(shown: dict, settings: settings_reader.Settings, home: Path) -> LapLimits:
    """The lap limits that apply to the epic as bd shows it: its own factory rule counts only when it is lower than
    the ceiling."""
    ceiling = lap_ceiling(settings, home)
    own = of_epic(shown).settings.get(LAP_LIMIT)
    return LapLimits(min(ceiling.limit, own) if is_whole(own) else ceiling.limit, ceiling.machine)


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
    metadata = metadata_of(shown)
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


def names_codex_route(name: object) -> bool:
    """Whether a route name is `codex` or starts `codex-`."""
    return isinstance(name, str) and (name == routes.CODEX_HARNESS or name.startswith(f"{routes.CODEX_HARNESS}-"))


def codex_route_problems(wanted: dict[str, object], held: dict[str, object]) -> list[str]:
    """The tiers that the routes and stage tiers, as the change would leave them, put on codex while a stage on
    them writes. A setting the change leaves out keeps the value the epic holds."""
    tier_routes = wanted.get("tier_routes", held.get("tier_routes", {}))
    stage_tiers = wanted.get("stage_tiers", held.get("stage_tiers", {}))
    if not (isinstance(tier_routes, dict) and isinstance(stage_tiers, dict)):
        return []
    refusals = (routes.writing_refusal(tier, routes.CODEX_HARNESS, stage_tiers) for tier, route in tier_routes.items()
                if names_codex_route(route))
    return [f"tier_routes: {refusal}" for refusal in refusals if refusal]


def problems_in(wanted: dict[str, object], ceiling: LapCeiling, held: dict[str, object]) -> list[str]:
    problems = []
    for name, value in wanted.items():
        if name not in SETTINGS:
            problems.append(f"{name} is not a setting. The settings are {', '.join(SETTINGS)}")
        elif not SETTINGS[name][0](value):
            problems.append(f"{name} must be {SETTINGS[name][1]}, not {encode(value)}")
        elif name == LAP_LIMIT and not ceiling.repo:
            problems.append("the repo settings hold no lap limit, so none can be set lower. "
                            "Run /jidoka:onboard to record one")
        elif name == LAP_LIMIT and value >= ceiling.limit:
            problems.append(f"{LAP_LIMIT} must be below the {ceiling.owner} {ceiling.limit}, because an epic can "
                            f"only go lower, not {encode(value)}")
    if not problems and ("tier_routes" in wanted or "stage_tiers" in wanted):
        problems.extend(codex_route_problems(wanted, held))
    return problems


def epic_to_write(epic: str, main_tree: Path) -> dict:
    try:
        return shown_epic(epic, main_tree)
    except NotAnEpic as error:
        raise RulesError(f"{error}. Factory rules belong to an epic") from error


def change_comment(name: str, value: object, before: object | None) -> str:
    was = "" if before is None else f", was {encode(before)}"
    return f"{COMMENT_HEADING} {name} set to {encode(value)}{was}."


def write_settings(epic: str, wanted: dict[str, object], ceiling: LapCeiling, main_tree: Path) -> dict[str, object]:
    """Checks every wanted setting, then writes each that differs from the epic's, with a comment for each.

    Returns the settings it changed.
    """
    shown = epic_to_write(epic, main_tree)
    held = of_epic(shown).settings
    problems = problems_in(wanted, ceiling, held)
    if problems:
        raise RulesError(f"the factory rules of {epic} were not changed:\n"
                         + "\n".join(f"  {problem}" for problem in problems))
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


def write_preset(epic: str, preset: str, repo_limit: int, main_tree: Path) -> dict[str, object]:
    """Writes the settings and the guidance that the preset holds; the settings it changed. No preset sets a
    lap_limit, so the repo's limit stands for the whole ceiling."""
    chosen = PRESETS[preset]
    changed = write_settings(epic, chosen.settings, LapCeiling(repo_limit, repo_limit), main_tree)
    if chosen.guidance:
        write_guidance(epic, chosen.guidance, main_tree)
    return changed


def allow_extra_command(epic: str, command: str, home: Path, main_tree: Path) -> bool:
    """Adds the command to the epic's extra_commands; False when the epic already allows it."""
    held = of_epic(epic_to_write(epic, main_tree)).settings.get(EXTRA_COMMANDS, [])
    if not isinstance(held, list) or command in held:
        return False
    write_settings(epic, {EXTRA_COMMANDS: [*held, command]}, ceiling_of(home, main_tree), main_tree)
    return True


def epic_holding(task: dict, main_tree: Path) -> dict:
    """The epic that holds the task as bd shows it; empty for a task with no parent."""
    parent = parent_of(task)
    return epic_to_write(parent, main_tree) if parent else {}


def extra_commands_of(epic: dict) -> list[str]:
    """The extra_commands of the epic as bd show --json prints it; none when it holds none."""
    extra = of_epic(epic).settings.get(EXTRA_COMMANDS, [])
    return extra if isinstance(extra, list) else []


def lap_commands(worktree: Path, main_tree: Path) -> list[str]:
    """The extra_commands of the epic that holds the lap's task."""
    try:
        task = lap_record.task_in_worktree(worktree, main_tree)
    except lap_record.NotALapWorktree as error:
        raise RulesError(str(error)) from error
    return extra_commands_of(epic_holding(task, main_tree))


def shown_rules(epic: str, main_tree: Path) -> dict:
    rules = of_epic(epic_to_write(epic, main_tree))
    return {"epic": epic, "settings": rules.settings, "guidance": rules.guidance}


def pickable_choices(ceiling: LapCeiling) -> dict[str, list]:
    """The settings that take one of a short list, each with the values a person can pick."""
    return {"lap_test_scope": list(settings_reader.TEST_SCOPES),
            LAP_LIMIT: list(range(1, ceiling.limit)),
            "discovered_bugs_into_epic": [True, False],
            "commits_on_main": list(COMMITS_ON_MAIN)}


def shown_choices(epic: str, ceiling: LapCeiling, main_tree: Path) -> dict:
    held = of_epic(epic_to_write(epic, main_tree)).settings
    return {"epic": epic, "settings": [{"name": name, "choices": choices, "value": held.get(name)}
                                       for name, choices in pickable_choices(ceiling).items()]}


def parsed_setting(argument: str) -> tuple[str, object]:
    name, separator, text = argument.partition("=")
    if not (separator and name.strip()):
        raise RulesError(f"{argument!r} is not <name>=<value>")
    try:
        return name.strip(), json.loads(text)
    except ValueError:
        return name.strip(), text


def ceiling_of(home: Path, main_tree: Path) -> LapCeiling:
    return lap_ceiling(settings_reader.read_settings(home, main_tree), home)


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
    modes.add_parser("choices", parents=[shared], help="print the settings a person picks from a list")
    modes.add_parser("guidance", parents=[shared], help="store the guidance on stdin")
    presetting = modes.add_parser("preset", parents=[shared], help="set what a preset holds")
    presetting.add_argument("preset", choices=sorted(PRESETS))
    modes.add_parser("lap-commands", parents=[home_flag], help="print the commands the lap in the cwd may also run")
    args = parser.parse_args(argv)

    try:
        main_tree = settings_reader.main_worktree(Path.cwd(), COMMAND_TIMEOUT_SECONDS)
        home = settings_reader.jidoka_home(args.jidoka_home)
        if args.mode == "lap-commands":
            printed = lap_commands(Path.cwd(), main_tree)
        elif args.mode == "show":
            printed = shown_rules(args.epic, main_tree)
        elif args.mode == "choices":
            printed = shown_choices(args.epic, ceiling_of(home, main_tree), main_tree)
        elif args.mode == "guidance":
            printed = {"epic": args.epic, "changed": write_guidance(args.epic, sys.stdin.read(), main_tree)}
        else:
            ceiling = ceiling_of(home, main_tree)
            if args.mode == "preset":
                changed = write_preset(args.epic, args.preset, ceiling.repo, main_tree)
            else:
                wanted = dict(parsed_setting(argument) for argument in args.settings)
                changed = write_settings(args.epic, wanted, ceiling, main_tree)
            printed = {**shown_rules(args.epic, main_tree), "changed": changed}
    except (RulesError, CommandError, settings_reader.SettingsError, OSError) as error:
        print(f"rules: {error}", file=sys.stderr)
        return 1
    print(json.dumps(printed))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
