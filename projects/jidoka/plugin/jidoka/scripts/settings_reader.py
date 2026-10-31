"""Reads the settings jidoka keeps for one repo on this machine, and holds the schema they are stored under.

The settings live in <jidoka-home>/repos/<key>.json, where the key comes from the path of the repo's main
worktree, so every worktree of the repo finds the same file. The home is --jidoka-home, else $JIDOKA_HOME, else
~/.jidoka.

A script that needs a repo's settings asks for them here by the main worktree. `read_settings` gives one `Settings`
value, whose fields are checked once, and refuses with the one wording every caller shares when the repo has none;
`find_settings` gives None instead, for the bench, which works in a repo before it is onboarded. Only the writer,
repo_settings.py, works on the stored object itself (`read_stored`). The module also holds the
whole schema of the stored settings: the keys and their defaults, the apps, their hand-run groups, and the checks
(`problems_in`) that the writer applies before it stores anything and the readers rely on.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

GIT_TIMEOUT_SECONDS = 30
GLOSSARY_AND_ADRS = "glossary_and_adrs"
COMMITTED, PRIVATE = "committed", "private"
DOC_PATH_KEYS = ["glossary", "adrs"]
LIZARD_LIMITS = "lizard_limits"
LIZARD_METRICS = ("ccn", "length", "arguments")
DEFAULT_LIZARD_LIMITS = {"ccn": 15, "length": 80, "arguments": 6}
APP_KEYS = ["name", "kind", "way_in", "build", "run", "test", "test_full", "test_target", "hand_run", "acceptance",
            "spec_command", "spec_target", "spec_seconds_limit"]
HAND_RUN_KEYS = ["name", "exclusion", "command", "reason"]
HAND_RUN_GROUP_KEYS = ["app", "name", "reason", "command"]
NO_TESTS = "an app with no test command has null for test, test_target and test_full, and [] for hand_run"
TEST_SCOPES = ["targeted", "full"]
APP_KINDS = ["program", "library"]
BUILT_IN_COMMANDS_FILE = "built_in_commands.json"
GIVEN_KEYS = ["lap_test_scope", "worker_commands", "slot_use", "lap_limit", "apps"]
DOCS_DEFAULTS = {"glossary": "GLOSSARY.md", "adrs": "docs/adr", GLOSSARY_AND_ADRS: COMMITTED}
RULE_CONFLICTS = "rule_conflicts"
DEFAULTS = {**DOCS_DEFAULTS, RULE_CONFLICTS: [], LIZARD_LIMITS: DEFAULT_LIZARD_LIMITS}
RULE_CONFLICT_KEYS = ["repo_rule", "written_in", "overrules"]
ONBOARD = "/jidoka:onboard"


class SettingsError(Exception):
    """A reason a script stops on the repo settings, worded for the person who reads stderr."""


@dataclass(frozen=True)
class HandRun:
    """One group of an app's tests that the full suite leaves out, as the stored settings hold it."""
    name: str
    exclusion: str
    command: str
    reason: str


@dataclass(frozen=True)
class HandRunGroup:
    """A group of an app's tests that the full suite leaves out, with the app's name and the command the human runs
    it with. The stored "hand_run" list holds one object for each, under the field names."""
    app: str
    name: str
    reason: str
    command: str


@dataclass(frozen=True)
class App:
    """One app of the repo as the stored settings hold it. A field is None when the app has none of it, and
    hand_run is empty when every test of the app runs in the full suite. spec_command runs every acceptance spec of
    the app, and spec_target follows it to run one, with one <...> placeholder for the spec's name. spec_seconds_limit
    is how many seconds a validation's run of the app's specs may take before acceptance shows the slowest specs and
    a design finding names the protocol driver."""
    name: str
    kind: str | None
    build: str | None
    run: str | None
    test: str | None
    test_full: str | None
    test_target: str | None
    way_in: str | None
    acceptance: str | None
    spec_command: str | None
    spec_target: str | None
    spec_seconds_limit: float | None
    hand_run: tuple[HandRun, ...]

    @property
    def full_suite_command(self) -> str | None:
        """The test command followed by test_full when there is one; None for an app with no test command."""
        if self.test is None:
            return None
        return self.test if self.test_full is None else f"{self.test} {self.test_full}"

    @property
    def targeted_command(self) -> str | None:
        """The test command followed by the test_target, its placeholder left in; None when either is missing."""
        if self.test is None or self.test_target is None:
            return None
        return f"{self.test} {self.test_target}"


@dataclass(frozen=True)
class Settings:
    """The settings stored for one repo on this machine, checked once as they were read. worker_commands is empty
    and lap_limit is 0 when the repo has none. The listed_ fields hold the lists that the write derives, and are
    None when the stored object lacks one or holds it wrongly; the method that follows each refuses, pointing at
    onboarding, so a script refuses only on the list it needs."""
    path: Path
    apps: tuple[App, ...]
    app_problems: dict[str, tuple[str, ...]]
    worker_commands: tuple[str, ...]
    slot_use: str | None
    lap_limit: int
    lizard_limits: dict[str, int]
    private_docs: tuple[str, ...]
    listed_full_suite: tuple[str, ...] | None
    listed_untested_apps: tuple[str, ...] | None
    listed_hand_run: tuple[HandRunGroup, ...] | None

    def app_named(self, name: str) -> App:
        """The first app that has the name; raises SettingsError when none has it or its entry has a problem the
        write refuses."""
        found = next((app for app in self.apps if app.name == name), None)
        if found is None:
            raise SettingsError(f"the repo settings have no app named {name!r}; "
                                f"the apps are {', '.join(app.name for app in self.apps)}")
        problems = self.app_problems.get(name, ())
        if problems:
            raise SettingsError(f"the repo settings for app {name!r} are incomplete: {'; '.join(problems)}. "
                                f"Run {ONBOARD} to record them")
        return found

    def full_suite(self) -> tuple[str, ...]:
        """The full-suite command of every app that has a test command; raises SettingsError when there is none."""
        if not self.listed_full_suite:
            raise SettingsError(f"{self.path} holds no full_suite list of test commands. Run {ONBOARD} to record it")
        return self.listed_full_suite

    def untested_apps(self) -> tuple[str, ...]:
        """The names of the apps with no test command; raises SettingsError when the list is missing."""
        if self.listed_untested_apps is None:
            raise SettingsError(f"{self.path} holds no untested_apps list of the apps with no test command. "
                                f"Run {ONBOARD} to record it")
        return self.listed_untested_apps

    def hand_run(self) -> tuple[HandRunGroup, ...]:
        """The hand-run groups of every app, in app order; raises SettingsError when the list is missing or a group
        of it lacks a text field."""
        if self.listed_hand_run is None:
            raise SettingsError(f"{self.path} holds no hand_run list of the tests the full suite leaves out. "
                                f"Run {ONBOARD} again to record it")
        return self.listed_hand_run


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


def read_stored(home: Path, main_tree: Path) -> dict:
    """The object stored for the main worktree, as the writer merges into it; empty when the repo has none."""
    return load(settings_path(home, main_tree))


def require_stored(home: Path, main_tree: Path) -> dict:
    """The object stored for the main worktree; raises SettingsError, pointing at onboarding, when the repo has
    none."""
    path = settings_path(home, main_tree)
    stored = load(path)
    if not stored:
        raise SettingsError(f"no settings for {main_tree} in {path.parent}. Run {ONBOARD} to record them")
    return stored


def read_settings(home: Path, main_tree: Path) -> Settings:
    """The settings stored for the main worktree; raises SettingsError, pointing at onboarding, when the repo has
    none."""
    return settings_of(require_stored(home, main_tree), settings_path(home, main_tree))


def find_settings(home: Path, main_tree: Path) -> Settings | None:
    """The settings stored for the main worktree, or None when the repo has none, for the one caller that works
    in a repo before it is onboarded."""
    path = settings_path(home, main_tree)
    stored = load(path)
    return settings_of(stored, path) if stored else None


def built_in_commands(home: Path) -> list[str]:
    """The commands the human added to the built-in list on this machine; none when the file is missing."""
    path = home / BUILT_IN_COMMANDS_FILE
    if not path.is_file():
        return []
    try:
        commands = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as error:
        raise SettingsError(f"{path} is not valid JSON: {error}") from error
    if not (isinstance(commands, list) and all(map(is_text, commands))):
        raise SettingsError(f"{path} does not hold a list of commands")
    return commands


def is_text(value: object) -> bool:
    return isinstance(value, str) and value.strip() != ""


def text_or_null(value: object) -> bool:
    return value is None or is_text(value)


def is_repo_path(value: object) -> bool:
    if not is_text(value):
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and ".." not in path.parts and str(path) != "."


def text_of(value: object) -> str | None:
    return value if is_text(value) else None


def is_positive_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


def limit_of(value: object) -> float | None:
    return float(value) if is_positive_number(value) else None


def hand_run_of(app: dict) -> tuple[HandRun, ...]:
    listed = app.get("hand_run")
    return tuple(HandRun(*(str(group.get(key) or "") for key in HAND_RUN_KEYS))
                 for group in (listed if isinstance(listed, list) else []) if isinstance(group, dict))


def app_of(entry: dict) -> App:
    return App(str(entry.get("name") or ""), text_of(entry.get("kind")), text_of(entry.get("build")),
               text_of(entry.get("run")), text_of(entry.get("test")), text_of(entry.get("test_full")),
               text_of(entry.get("test_target")), text_of(entry.get("way_in")), text_of(entry.get("acceptance")),
               text_of(entry.get("spec_command")), text_of(entry.get("spec_target")),
               limit_of(entry.get("spec_seconds_limit")), hand_run_of(entry))


def apps_of(settings: dict) -> list[App]:
    """The apps of stored settings, in the order the settings list them. Settings with no apps give none, and an
    entry that is not a JSON object is left out."""
    listed = settings.get("apps")
    return [app_of(entry) for entry in (listed if isinstance(listed, list) else []) if isinstance(entry, dict)]


def problems_of_app(settings: dict, name: str) -> list[str]:
    """The problems of the first app of the settings that has the name, as the write refuses them; none when no
    app has the name."""
    listed = settings.get("apps")
    for index, entry in enumerate(listed if isinstance(listed, list) else []):
        if isinstance(entry, dict) and entry.get("name") == name:
            return app_problems(index, entry)
    return []


def hand_run_groups_of(stored: dict) -> tuple[HandRunGroup, ...] | None:
    """The hand-run groups that write derived and stored under "hand_run"; None when the list is missing or a group
    of it lacks a text field."""
    listed = stored.get("hand_run")
    if not (isinstance(listed, list) and all(isinstance(group, dict) and all(
            isinstance(group.get(key), str) for key in HAND_RUN_GROUP_KEYS) for group in listed)):
        return None
    return tuple(HandRunGroup(*(group[key] for key in HAND_RUN_GROUP_KEYS)) for group in listed)


def texts_or_none(value: object) -> tuple[str, ...] | None:
    return tuple(value) if isinstance(value, list) and all(map(is_text, value)) else None


def is_positive_whole(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def lizard_limits_of(stored: dict) -> dict[str, int]:
    """The limit of every lizard measure: the stored one when it is a whole number above zero, else the default."""
    held = stored.get(LIZARD_LIMITS)
    held = held if isinstance(held, dict) else {}
    return {metric: held[metric] if is_positive_whole(held.get(metric)) else DEFAULT_LIZARD_LIMITS[metric]
            for metric in LIZARD_METRICS}


def private_doc_paths(stored: dict) -> tuple[str, ...]:
    """The glossary and ADR paths the settings keep out of git; none when they are committed."""
    if stored.get(GLOSSARY_AND_ADRS) != PRIVATE:
        return ()
    return tuple(stored[key] for key in DOC_PATH_KEYS if is_repo_path(stored.get(key)))


def settings_of(stored: dict, path: Path) -> Settings:
    """Checks the stored object once and gives its fields. What the settings lack or hold wrongly becomes the
    field's empty value, and the derived lists become None, so a script refuses only on what it needs."""
    commands, limit = stored.get("worker_commands"), stored.get("lap_limit")
    apps = tuple(apps_of(stored))
    return Settings(path, apps, {app.name: tuple(problems_of_app(stored, app.name)) for app in apps},
                    tuple(command for command in commands if isinstance(command, str))
                    if isinstance(commands, list) else (),
                    text_of(stored.get("slot_use")), limit if is_positive_whole(limit) else 0,
                    lizard_limits_of(stored), private_doc_paths(stored), texts_or_none(stored.get("full_suite")),
                    texts_or_none(stored.get("untested_apps")), hand_run_groups_of(stored))


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
    if not (app.get("acceptance") is None or is_repo_path(app["acceptance"])):
        problems.append(f"{label} has an acceptance that is neither a folder inside the repo nor null")
    problems += spec_command_problems(label, app)
    if app.get("spec_seconds_limit") is not None and not is_positive_number(app["spec_seconds_limit"]):
        problems.append(f"{label} has a spec_seconds_limit that is neither a number of seconds above zero nor null")
    command_problems = test_command_problems(label, app)
    problems += command_problems
    if "hand_run" not in app:
        problems.append(f"{label} has no hand_run; use [] when every test runs in the full suite")
    else:
        problems += hand_run_problems(label, app, not command_problems)
    return problems


def spec_command_problems(label: str, app: dict) -> list[str]:
    """The problems of an app's spec_command and spec_target. Both may be left out, which means null; an app may
    have an acceptance folder and no spec_command, and a run of its specs refuses it."""
    problems = [f"{label} has a {key} that is neither {'a command' if key == 'spec_command' else 'text'} nor null"
                for key in ("spec_command", "spec_target") if not text_or_null(app.get(key))]
    if problems:
        return problems
    command, target = app.get("spec_command"), app.get("spec_target")
    if command is not None and app.get("acceptance") is None:
        problems.append(f"{label} has a spec_command but no acceptance folder")
    if command is not None and target is None:
        problems.append(f"{label} has a spec_command but does not say how to target a spec")
    if command is None and target is not None:
        problems.append(f"{label} has a spec_target but no spec_command")
    return problems


def test_command_problems(label: str, app: dict) -> list[str]:
    problems = []
    for key in ("test", "test_target"):
        if key not in app:
            problems.append(f"{label} has no {key}; use null when the app has no test command")
        elif not text_or_null(app[key]):
            problems.append(f"{label} has a {key} that is neither text nor null")
    if "test_full" not in app:
        problems.append(f"{label} has no test_full; use null when the full suite is the test command alone")
    elif not text_or_null(app["test_full"]):
        problems.append(f"{label} has a test_full that is neither arguments nor null")
    if problems:
        return problems
    if app["test"] is not None:
        if app["test_target"] is None:
            problems.append(f"{label} has a test command but does not say how to target a test")
        return problems
    return [f"{label} has a {key} but no test command; {NO_TESTS}"
            for key in ("test_target", "test_full") if app[key] is not None]


def hand_run_problems(label: str, app: dict, commands_valid: bool) -> list[str]:
    groups = app["hand_run"]
    if not isinstance(groups, list):
        return [f"{label} has a hand_run that is not a list of groups"]
    if commands_valid and groups and app["test"] is None:
        return [f"{label} has hand_run groups but no test command; {NO_TESTS}"]
    problems = []
    for index, group in enumerate(groups):
        if not isinstance(group, dict):
            problems.append(f"{label} has a hand_run[{index}] that is not a JSON object")
            continue
        name = group.get("name")
        group_label = f"{label} has a hand_run group " + (repr(name) if is_text(name) else f"hand_run[{index}]")
        unknown = sorted(set(group) - set(HAND_RUN_KEYS))
        if unknown:
            problems.append(f"{group_label} with keys jidoka does not know: {', '.join(unknown)}")
        problems += [f"{group_label} with no {key}" for key in HAND_RUN_KEYS if not is_text(group.get(key))]
        exclusion = group.get("exclusion")
        if commands_valid and is_text(exclusion):
            problems += [f"{group_label} whose exclusion {exclusion!r} is not in the {kind}, {command!r}, "
                         "so that command runs the group"
                         for kind, command in app_commands(app_of(app)) if exclusion not in command]
    return problems


def app_commands(app: App) -> list[tuple[str, str]]:
    """The app's full-suite command and its targeted command, the placeholder left in, each named, for the
    commands it has."""
    named = [("full-suite command", app.full_suite_command), ("targeted command", app.targeted_command)]
    return [(kind, command) for kind, command in named if command is not None]


def problems_in(settings: dict) -> list[str]:
    """The problems of settings the writer is about to store, with the defaults filled in; none when they are whole."""
    problems = [f"{key} is missing" for key in GIVEN_KEYS if key not in settings]
    unknown = sorted(set(settings) - set(GIVEN_KEYS) - set(DEFAULTS))
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
    problems += [f"{key} must be a path inside the repo, relative to its root"
                 for key in DOC_PATH_KEYS if key in settings and not is_repo_path(settings[key])]
    if settings.get(GLOSSARY_AND_ADRS, COMMITTED) not in (COMMITTED, PRIVATE):
        problems.append(f"{GLOSSARY_AND_ADRS} must be one of {COMMITTED}, {PRIVATE}")
    if RULE_CONFLICTS in settings:
        problems += rule_conflicts_problems(settings[RULE_CONFLICTS])
    if LIZARD_LIMITS in settings:
        problems += lizard_limits_problems(settings[LIZARD_LIMITS])
    return problems


def lizard_limits_problems(limits: object) -> list[str]:
    if not isinstance(limits, dict):
        return [f"{LIZARD_LIMITS} must be an object with {', '.join(LIZARD_METRICS)}"]
    unknown = sorted(set(limits) - set(LIZARD_METRICS))
    problems = [f"{LIZARD_LIMITS} has keys jidoka does not know: {', '.join(unknown)}"] if unknown else []
    for metric in LIZARD_METRICS:
        value = limits.get(metric)
        if not (isinstance(value, int) and not isinstance(value, bool) and value > 0):
            problems.append(f"{LIZARD_LIMITS} needs a whole number above zero for {metric}")
    return problems


def rule_conflicts_problems(conflicts: object) -> list[str]:
    if not isinstance(conflicts, list):
        return [f"{RULE_CONFLICTS} must be a list of conflicts"]
    problems = []
    for index, conflict in enumerate(conflicts):
        label = f"{RULE_CONFLICTS}[{index}]"
        if not isinstance(conflict, dict):
            problems.append(f"{label} is not a JSON object")
            continue
        unknown = sorted(set(conflict) - set(RULE_CONFLICT_KEYS))
        if unknown:
            problems.append(f"{label} has keys jidoka does not know: {', '.join(unknown)}")
        problems += [f"{label} has no {key}" for key in RULE_CONFLICT_KEYS if not is_text(conflict.get(key))]
        if is_text(conflict.get("written_in")) and not is_repo_path(conflict["written_in"]):
            problems.append(f"{label} has a written_in that is not a path inside the repo, relative to its root")
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
    if not any(isinstance(app, dict) and is_text(app.get("test")) for app in apps):
        problems.append("no app has a test command, so the repo has no full suite")
    return problems
