#!/usr/bin/env python3
"""Installs jidoka's plugin on this machine, and updates it when run again.

Jeff runs it in a terminal and names the Claude config dirs to install into.
It checks for git, bd, claude and Python 3.10 or later and installs none of
them. On Windows it also checks for Git for Windows, whose Git Bash runs every hook and the launcher, and for
Developer Mode, which symbolic links need, and refuses naming what is missing. It refuses while the plugin folder next to this file has uncommitted
changes, so what gets installed is a commit. It writes that commit's plugin
to <jidoka-home>/plugins/<version>/, a snapshot, because Claude Code runs a
plugin from a folder marketplace in place and an edit to the checkout would
otherwise change the scripts under a running session. It records the Python
it runs under, the config dirs, a native route for each tier, except for a
tier whose route is already recorded, which /jidoka:setup may have set, and
jidoka's source repo in <jidoka-home>, then adds the snapshot as a local marketplace
and installs the plugin at user scope into each named config dir, and into
Codex when codex is on the PATH. Codex gets its own copy of the snapshot in <jidoka-home>/codex/<version>/,
whose hooks/hooks.json names no modules, because Codex refuses a hooks file that has the field and loads none
of the hooks. It also writes a converted copy of the plugin into each T3 Antigravity profile, the folders under
<t3-userdata>/providers/antigravity that hold a config folder, and enables jidoka in the profile's config.json. It
makes the copy itself, because `antigravity plugin install` writes only to ~/.gemini. The copy has a root plugin.json
and a root hooks.json with one named hook, Bash matched as run_command, and the profile guard, matched to every tool,
which holds a lap worker's calls to the lap's rules. It has no lap mod and no SessionEnd. Its commands
name the launcher and the scripts by absolute path in the snapshot, set JIDOKA_HOME to the home this run records, and
end in `--host antigravity`. The copy holds no bin or scripts folder, and each `<skill folder>/../../bin`, `scripts`
or `hooks` path in a skill's text names the snapshot instead, so that a running factory keeps its version's scripts.
Every skill and agent is named jidoka-<name> in its folder, its name field and its text. A copy of the version being
installed is left as it is, and a copy of any other version is replaced. With no profile, the host is
skipped. A snapshot is never rewritten. A version
whose snapshot came from different plugin content is refused until
release.py gives the change a new version. The source repo is the main
worktree of the repo this file is in, found with git, so an install from a
linked worktree records the main checkout. Retro files a fix to jidoka
there, from whatever repo it runs in.

It also publishes jidoka-ui, which lives beside jidoka in projects/jidoka-ui of the same checkout, so that
/jidoka:factory can start it. It runs `dotnet publish` on what HEAD holds of that folder, never on the files on disk,
into <jidoka-home>/ui/<tree>/, named for the folder's git tree, built beside its target and renamed into place. A
folder that already exists for the tree is reused. It records the dotnet, the published app and the port under `ui`
in the machine settings. The port is the one the Pushover link defaults to, and the factory's start passes it to
the app, so the two cannot disagree. dotnet is not one of the tools the installer needs. Without it, the install
goes on, says that jidoka-ui was not published, and keeps what an earlier run recorded.

At a terminal it also asks for the Pushover user key, application token and jidoka-ui address that
notify.py uses, and writes them to <jidoka-home>/pushover.json, readable by its owner only. It asks nowhere
else. The keys are typed into this script and never pass through a model. An empty user key leaves the
file as it was, and a run with no terminal asks nothing.
"""
from __future__ import annotations

import argparse
import getpass
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

PLUGIN_FOLDER = Path(__file__).resolve().parent / "plugin"
sys.path.append(str(PLUGIN_FOLDER / "jidoka" / "scripts"))
DONT_WRITE_BYTECODE_BEFORE_IMPORTS = sys.dont_write_bytecode
# A bytecode file written into the plugin folder would make the installer refuse that folder as uncommitted.
sys.dont_write_bytecode = True
import commands  # noqa: E402
import lap_guard_record  # noqa: E402
import links  # noqa: E402
import machine_settings  # noqa: E402
import routes as machine_routes  # noqa: E402

sys.dont_write_bytecode = DONT_WRITE_BYTECODE_BEFORE_IMPORTS

MIN_PYTHON = (3, 10)
REQUIRED_TOOLS = ["git", "bd", "claude"]
MARKETPLACE = "jidoka"
PLUGIN_ID = "jidoka@jidoka"
PLUGIN_MANIFEST = Path("jidoka") / ".claude-plugin" / "plugin.json"
PLUGIN_HOOKS = Path("jidoka") / "hooks" / "hooks.json"
TREE_FILE = "plugin-tree-id"
OWNED_SETTINGS = ["python", "config_dirs", "routes", "source_repo", "ui"]
PUSHOVER_FILE = "pushover.json"
UI_FOLDER = Path("projects") / "jidoka-ui"
UI_WEB_PROJECT = Path("src") / "JidokaUi.Web" / "JidokaUi.Web.csproj"
UI_APP = "JidokaUi.Web.dll"
UI_PORT = 5099
DEFAULT_UI_URL = f"http://localhost:{UI_PORT}"
RENAME_ATTEMPTS = 10
RENAME_PAUSE_SECONDS = 0.5
PLUGIN_DIR = Path("jidoka")
PLUGIN_NAME = "jidoka"
CLAUDE_PLUGIN_ROOT = "${CLAUDE_PLUGIN_ROOT}"
T3_ANTIGRAVITY_PROFILES = Path("providers") / "antigravity"
ANTIGRAVITY_CONFIG_DIR = Path("config")
ANTIGRAVITY_CONFIG = ANTIGRAVITY_CONFIG_DIR / "config.json"
ANTIGRAVITY_PLUGINS = ANTIGRAVITY_CONFIG_DIR / "plugins"
ANTIGRAVITY_HOOK_TIMEOUT_SECONDS = 60
ANTIGRAVITY_TOOLS = {"Bash": "run_command"}
ANTIGRAVITY_GROUPED_EVENTS = {"PreToolUse"}
ANTIGRAVITY_FLAT_EVENTS = {"SessionStart"}
CLAUDE_ONLY_EVENTS = {"SessionEnd"}
ANTIGRAVITY_PREFIX = "jidoka-"
ANTIGRAVITY_HOST = "antigravity"
JIDOKA_HOME_VARIABLE = "JIDOKA_HOME"
SKILL_SCRIPT_FOLDERS = re.compile(r"<skill folder>/\.\./\.\./(bin|scripts|hooks)/")
JIDOKA_TOKEN = re.compile(r"(?<![\w-])jidoka:(?=[a-z])")
NAME_FIELD = re.compile(r"^name:[ \t]*(['\"]?)([^'\"\r\n]+?)\1[ \t]*$", re.MULTILINE)


class InstallerError(Exception):
    pass


@dataclass(frozen=True)
class Terminal:
    """The person at the keyboard. `ask` shows what they type, `ask_secret` hides it."""
    ask: Callable[[str], str]
    ask_secret: Callable[[str], str]


@dataclass(frozen=True)
class Tools:
    git: str
    claude: str
    codex: str | None
    dotnet: str | None


@dataclass(frozen=True)
class Folders:
    """The folders a run is told about: the Claude config dirs to install into, jidoka's home, and the T3 userdata
    folder that holds the Antigravity profiles."""
    config_dirs: list[Path]
    jidoka_home: Path
    t3_userdata: Path


@dataclass(frozen=True)
class OwnedSettings:
    """The machine settings that the installer owns and writes on every run; ui is None when there is no record to
    keep."""
    python: str
    config_dirs: list[Path]
    routes: dict[str, machine_routes.Route]
    source_repo: Path
    ui: dict | None


@dataclass(frozen=True)
class PublishedUi:
    """What this run did about jidoka-ui: the `ui` record to keep in the machine settings, None when there is none
    to keep, and the line that says what happened."""
    record: dict | None
    line: str


def find_missing(python_version: tuple[int, int], which: Callable[[str], str | None]) -> list[str]:
    missing = []
    if python_version < MIN_PYTHON:
        wanted = ".".join(str(part) for part in MIN_PYTHON)
        current = ".".join(str(part) for part in python_version)
        missing.append(f"Python {wanted} or later (this is Python {current})")
    for name in REQUIRED_TOOLS:
        if which(name) is None:
            missing.append(f"`{name}`")
    return missing


def git_bash_exists(git: str, environ: Mapping[str, str]) -> bool:
    """Whether Git Bash, which runs every hook, the launcher and the test commands, is where Claude Code looks for
    it."""
    return commands.git_bash_path(git, environ) is not None


def developer_mode_is_on(make_link: Callable[[Path, Path | str, bool], None]) -> bool:
    """Whether this account can make a symbolic link, which Windows allows without administrator rights only in
    Developer Mode. Any other failure to make the link is raised."""
    with tempfile.TemporaryDirectory() as folder:
        link = Path(folder) / "link"
        try:
            make_link(link, Path(folder) / "target", False)
        except links.LinkError:
            return False
    return True


def find_missing_on_windows(git: str, environ: Mapping[str, str],
                            make_link: Callable[[Path, Path | str, bool], None]) -> list[str]:
    missing = []
    if not git_bash_exists(git, environ):
        missing.append("Git for Windows, whose Git Bash runs every hook and the launcher "
                       "(https://gitforwindows.org)")
    if not developer_mode_is_on(make_link):
        missing.append("Developer Mode, which Windows requires to make the symbolic links jidoka uses "
                       "(Settings, System, For developers, Developer Mode)")
    return missing


def no_missing_on_this_host(git: str) -> list[str]:
    return []


def missing_on_windows(git: str) -> list[str]:
    return find_missing_on_windows(git, os.environ, links.create)


def find_every_gap(python_version: tuple[int, int], which: Callable[[str], str | None],
                   missing_on_host: Callable[[str], list[str]]) -> list[str]:
    """Every prerequisite the machine lacks, so one refusal names them all. The host's own checks run on the git
    that `which` finds, and only when it finds one."""
    missing = find_missing(python_version, which)
    git = which("git")
    if git is not None:
        missing += missing_on_host(git)
    return missing


def locate_tools(which: Callable[[str], str | None]) -> Tools:
    git, claude = which("git"), which("claude")
    if git is None or claude is None:
        raise InstallerError("git and claude must be on the PATH")
    return Tools(git, claude, which("codex"), which("dotnet"))


def refuse_incomplete_routes(previous: dict) -> None:
    """Refuses the routes that an earlier run or setup recorded, which this run keeps, when one lacks a field that its
    harness requires."""
    earlier = previous.get("routes")
    try:
        for tier, route in (earlier.items() if isinstance(earlier, dict) else []):
            machine_routes.Route.parse(tier, route)
    except machine_routes.RouteError as err:
        raise InstallerError(f"the recorded routes cannot be kept: {err}") from err


def git_run(git: str, folder: Path, args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run([git, "-C", str(folder), *args], capture_output=True, text=True, encoding="utf-8")


def dirty_files(git: str, folder: Path) -> list[str]:
    """The paths under folder that differ from the last commit, untracked files included."""
    inside = git_run(git, folder, ["rev-parse", "--is-inside-work-tree"])
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        raise InstallerError(f"{folder} is not inside a git repository, so there is no commit to install")
    status = git_run(git, folder, ["status", "--porcelain", "--untracked-files=all", "--", "."])
    if status.returncode != 0:
        raise InstallerError(f"git status failed in {folder}: {status.stderr.strip()}")
    return [line[3:] for line in status.stdout.splitlines() if line]


def main_worktree(git: str, folder: Path) -> Path:
    """The common dir is the main worktree's .git, and git may print it relative to the folder."""
    found = git_run(git, folder, ["rev-parse", "--git-common-dir"])
    common = found.stdout.strip()
    if found.returncode != 0 or not common:
        raise InstallerError(f"git could not find the repository that holds {folder}: {found.stderr.strip()}")
    return (folder / common).resolve().parent


def refuse_if_dirty(git: str, folder: Path) -> None:
    dirty = dirty_files(git, folder)
    if dirty:
        raise InstallerError("the plugin folder has uncommitted changes. Commit or discard them first:\n"
                             + "\n".join(f"  {path}" for path in dirty))


def read_version(plugin_folder: Path) -> str:
    manifest = plugin_folder / PLUGIN_MANIFEST
    try:
        version = json.loads(manifest.read_text(encoding="utf-8"))["version"]
    except (OSError, ValueError, KeyError, TypeError) as err:
        raise InstallerError(f"{manifest} does not hold a version: {err}") from err
    if not isinstance(version, str) or not version or not version.isprintable() or version in (".", "..") \
            or Path(version).name != version or PureWindowsPath(version).name != version:
        raise InstallerError(f"{manifest} holds the version {version!r}, which cannot name a snapshot folder")
    return version


def load_settings(home: Path) -> dict:
    try:
        return machine_settings.settings_in(home)
    except machine_settings.MachineSettingsError as err:
        raise InstallerError(str(err)) from err


def record(home: Path, owned: OwnedSettings, previous: dict) -> None:
    home.mkdir(parents=True, exist_ok=True)
    (home / "python").write_text(owned.python + "\n", encoding="utf-8", newline="\n")
    kept = {key: value for key, value in previous.items() if key not in OWNED_SETTINGS}
    earlier_routes = previous.get("routes")
    settings = {
        "python": owned.python,
        "config_dirs": [str(path) for path in owned.config_dirs],
        "routes": {**{tier: route.as_dict() for tier, route in owned.routes.items()},
                   **(earlier_routes if isinstance(earlier_routes, dict) else {})},
        "source_repo": str(owned.source_repo),
        **({"ui": owned.ui} if owned.ui is not None else {}),
        **kept,
    }
    machine_settings.write_settings(home, settings)


def run_tool(executable: str, args: list[str], env: dict[str, str]) -> str:
    """Runs the tool and returns what it printed to stdout. A nonzero exit raises an error that names the command."""
    done = subprocess.run([executable, *args], capture_output=True, text=True, encoding="utf-8", env=env)
    if done.returncode != 0:
        shown = " ".join([Path(executable).stem, *args])
        detail = (done.stderr.strip() or done.stdout.strip() or "no output")
        raise InstallerError(f"`{shown}` failed with exit {done.returncode}: {detail}")
    return done.stdout


def tree_at_head(git: str, folder: Path) -> str:
    found = git_run(git, folder, ["rev-parse", "HEAD:./"])
    if found.returncode != 0:
        raise InstallerError(f"git could not read {folder} at HEAD: {found.stderr.strip()}")
    return found.stdout.strip()


def checkout_root(git: str, folder: Path) -> Path:
    found = git_run(git, folder, ["rev-parse", "--show-toplevel"])
    if found.returncode != 0 or not found.stdout.strip():
        raise InstallerError(f"git could not find the checkout that holds {folder}: {found.stderr.strip()}")
    return Path(found.stdout.strip())


def extract_head(git: str, folder: Path, destination: Path) -> None:
    """Unpacks what HEAD holds of folder into destination. Where Python has tar filters, a member or link that leaves
    destination is refused."""
    archived = subprocess.run([git, "-C", str(folder), "archive", "--format=tar", "HEAD", "--", "."],
                              capture_output=True)
    if archived.returncode != 0:
        raise InstallerError(f"git archive failed in {folder}: {archived.stderr.decode('utf-8', 'replace').strip()}")
    try:
        with tarfile.open(fileobj=io.BytesIO(archived.stdout)) as tar:
            if hasattr(tarfile, "data_filter"):
                tar.extractall(destination, filter="data")
            else:
                tar.extractall(destination)
    except tarfile.TarError as err:
        raise InstallerError(f"the archive of {folder} could not be unpacked: {err}") from err


def building_beside(target: Path) -> Path:
    """A new empty folder beside target to build it in, after clearing the ones a killed run left there."""
    target.parent.mkdir(parents=True, exist_ok=True)
    for stale in target.parent.glob(f".{target.name}-*"):
        shutil.rmtree(stale, ignore_errors=True)
    return Path(tempfile.mkdtemp(prefix=f".{target.name}-", dir=target.parent))


def renamed_into_place(built: Path, target: Path, rename: Callable[[Path, Path], object],
                       pause: Callable[[float], object]) -> None:
    """Renames built to target, and tries a refused rename again.

    Windows refuses to rename a folder while another process, such as a virus scanner or the search indexer, holds
    a file in it open. Such a process lets go of a new file after a short time.
    """
    for attempt in range(1, RENAME_ATTEMPTS + 1):
        try:
            rename(built, target)
            return
        except PermissionError as err:
            if attempt == RENAME_ATTEMPTS:
                raise InstallerError(f"{built} could not be renamed to {target} after {RENAME_ATTEMPTS} tries: {err}. "
                                     "Another process holds a file in it open. Run install.py again") from err
            pause(RENAME_PAUSE_SECONDS)


@dataclass(frozen=True)
class Refusing:
    """The policy for a target that exists by the time its build ends: the install stops with `appeared`."""
    appeared: str


@dataclass(frozen=True)
class Replacing:
    """The policy for a target that exists by the time its build ends: it is renamed aside, the build is renamed to
    its place, and the old one is removed. The old one comes back when the build cannot take its place."""


def discarded(path: Path) -> None:
    """Removes a file, link or folder, and does nothing when it is not there."""
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
    else:
        shutil.rmtree(path, ignore_errors=True)


def replaced_in_place(built: Path, target: Path) -> None:
    """Renames built to target, with whatever is at target renamed aside first and removed once built is in place."""
    aside = target.with_name(f".{target.name}-replaced")
    discarded(aside)
    if not os.path.lexists(target):
        renamed_into_place(built, target, Path.rename, time.sleep)
        return
    renamed_into_place(target, aside, Path.rename, time.sleep)
    try:
        renamed_into_place(built, target, Path.rename, time.sleep)
    except InstallerError:
        renamed_into_place(aside, target, Path.rename, time.sleep)
        raise
    discarded(aside)


def built_in_place(target: Path, fill: Callable[[Path], Path], existing: Refusing | Replacing) -> None:
    """Builds target beside itself and renames it into place, so target is never half written.

    Fill gets a new empty folder and returns the folder inside it to move to target. The folder fill got is removed
    whether the build succeeded or not. `existing` says what happens when target is there by the time the build ends.
    """
    building = building_beside(target)
    try:
        built = fill(building)
        built.chmod(0o755)
        if isinstance(existing, Replacing):
            replaced_in_place(built, target)
        elif target.exists():
            raise InstallerError(existing.appeared)
        else:
            renamed_into_place(built, target, Path.rename, time.sleep)
    finally:
        shutil.rmtree(building, ignore_errors=True)


def write_snapshot(git: str, plugin_folder: Path, tree: str, target: Path) -> None:
    """Builds the snapshot beside target and renames it into place, so target is never half written."""
    def fill(building: Path) -> Path:
        extract_head(git, plugin_folder, building)
        (building / TREE_FILE).write_text(tree + "\n", encoding="utf-8", newline="\n")
        return building

    built_in_place(target, fill,
                   Refusing(f"{target} appeared while the snapshot was being built, and a snapshot is never rewritten"))


def ensure_snapshot(git: str, plugin_folder: Path, jidoka_home: Path, version: str) -> Path:
    """The folder <jidoka-home>/plugins/<version>/, written from HEAD unless it already holds this plugin content."""
    tree = tree_at_head(git, plugin_folder)
    target = jidoka_home / "plugins" / version
    if not target.exists():
        write_snapshot(git, plugin_folder, tree, target)
        return target
    try:
        recorded = (target / TREE_FILE).read_text(encoding="utf-8").strip()
    except OSError as err:
        raise InstallerError(f"the snapshot {target} has no readable {TREE_FILE}, so it cannot be trusted. "
                             "Move it aside and run install.py again") from err
    if recorded != tree:
        raise InstallerError(f"the snapshot {target} came from plugin tree {recorded}, but HEAD holds tree {tree}. "
                             "A snapshot is never rewritten. Run release.py to give the change a new version, "
                             "then run install.py again")
    return target


def read_json_object(file: Path) -> dict:
    try:
        held = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as err:
        raise InstallerError(f"{file} cannot be read as JSON: {err}") from err
    if not isinstance(held, dict):
        raise InstallerError(f"{file} does not hold a JSON object")
    return held


def without_modules(hooks_file: Path) -> None:
    """Rewrites a hooks.json without its modules list, the field that only Claude Code reads."""
    hooks = read_json_object(hooks_file)
    hooks.pop("modules", None)
    hooks_file.write_text(json.dumps(hooks, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def ensure_codex_snapshot(snapshot: Path, jidoka_home: Path, version: str) -> Path:
    """The folder <jidoka-home>/codex/<version>/, a copy of the snapshot whose hooks/hooks.json names no modules.

    Codex refuses a hooks.json that has a field other than description and hooks, and so loads none of the hooks.
    The snapshot Claude Code reads keeps its modules, which name the lap mod. An existing copy is reused, because
    the snapshot it came from is never rewritten.
    """
    target = jidoka_home / "codex" / version
    if target.exists():
        return target
    def fill(building: Path) -> Path:
        shutil.copytree(snapshot, building, symlinks=True, dirs_exist_ok=True)
        without_modules(building / PLUGIN_HOOKS)
        return building

    built_in_place(target, fill, Refusing(f"{target} appeared while the copy for Codex was being built"))
    return target


def write_published_ui(git: str, dotnet: str, ui_folder: Path, target: Path) -> None:
    """Publishes what HEAD holds of jidoka-ui beside target and renames the result into place, so target is never
    half written and an uncommitted edit never reaches the app the factory starts."""
    def fill(building: Path) -> Path:
        source = building / "source"
        output = building / "app"
        extract_head(git, ui_folder, source)
        run_tool(dotnet, ["publish", str(source / UI_WEB_PROJECT), "--configuration", "Release",
                          "--output", str(output)], dict(os.environ))
        if not (output / UI_APP).is_file():
            raise InstallerError(f"dotnet publish wrote no {UI_APP} in {output}")
        return output

    built_in_place(target, fill, Refusing(f"{target} appeared while jidoka-ui was being published"))


def publish_ui(git: str, dotnet: str | None, checkout: Path, jidoka_home: Path, previous: dict) -> PublishedUi:
    """Publishes jidoka-ui to <jidoka-home>/ui/<tree>/ unless that folder exists, and gives the record that starts
    it. Without dotnet, or without jidoka-ui in the checkout, it keeps the record of an earlier run."""
    earlier = previous.get("ui")
    kept = earlier if isinstance(earlier, dict) else None
    ui_folder = checkout / UI_FOLDER
    if not ui_folder.is_dir():
        return PublishedUi(kept, f"jidoka-ui was not published, because this checkout holds no {UI_FOLDER}.")
    if dotnet is None:
        return PublishedUi(kept, "jidoka-ui was not published, because dotnet is not on the PATH. Install the "
                                 ".NET 10 SDK and run install.py again to let /jidoka:factory start it.")
    target = jidoka_home / "ui" / tree_at_head(git, ui_folder)
    if target.exists():
        line = f"jidoka-ui is already published in {target}"
    else:
        write_published_ui(git, dotnet, ui_folder, target)
        line = f"Published jidoka-ui to {target}"
    return PublishedUi({"dotnet": dotnet, "app": str(target / UI_APP), "port": UI_PORT}, line)


def unnamed_config_dirs(previous: dict, config_dirs: list[Path]) -> list[str]:
    """The config dirs an earlier run recorded that this run does not name."""
    recorded = previous.get("config_dirs")
    if not isinstance(recorded, list):
        return []
    named = {str(path) for path in config_dirs}
    return [path for path in recorded if isinstance(path, str) and path not in named]


def install_into_claude(claude: str, config_dir: Path, snapshot: Path) -> None:
    env = {**os.environ, "CLAUDE_CONFIG_DIR": str(config_dir)}
    run_tool(claude, ["plugin", "marketplace", "add", str(snapshot)], env)
    run_tool(claude, ["plugin", "marketplace", "update", MARKETPLACE], env)
    run_tool(claude, ["plugin", "install", PLUGIN_ID, "--scope", "user"], env)
    run_tool(claude, ["plugin", "update", PLUGIN_ID, "--scope", "user"], env)


def codex_marketplace_source(codex: str, env: dict[str, str]) -> str | None:
    """The folder Codex has for the jidoka marketplace, its `root`, or None when Codex has no marketplace by that
    name."""
    listed = run_tool(codex, ["plugin", "marketplace", "list", "--json"], env)
    try:
        marketplaces = json.loads(listed)["marketplaces"]
        for marketplace in marketplaces:
            if marketplace["name"] == MARKETPLACE:
                return marketplace["root"]
    except (ValueError, KeyError, TypeError) as err:
        raise InstallerError("`codex plugin marketplace list --json` printed a list the installer cannot read: "
                             + listed.strip()) from err
    return None


def install_into_codex(codex: str, snapshot: Path) -> None:
    """Codex refuses to add a marketplace whose name it already has from another source,
    so this first removes a jidoka marketplace that points at an older copy of the snapshot."""
    env = dict(os.environ)
    source = codex_marketplace_source(codex, env)
    if source is not None and source != str(snapshot):
        run_tool(codex, ["plugin", "marketplace", "remove", MARKETPLACE], env)
    run_tool(codex, ["plugin", "marketplace", "add", str(snapshot)], env)
    run_tool(codex, ["plugin", "add", PLUGIN_ID], env)


def antigravity_matcher(matcher: str, hooks_file: Path) -> str:
    """Antigravity's tool names for the Claude Code tool names in a matcher. A tool Antigravity has no name for is
    refused, because a matcher that names no tool never fires."""
    if not matcher:
        return "*"
    names = []
    for tool in matcher.split("|"):
        if tool not in ANTIGRAVITY_TOOLS:
            raise InstallerError(f"{hooks_file} has a matcher for {tool}, which has no Antigravity tool name in "
                                 "ANTIGRAVITY_TOOLS")
        names.append(ANTIGRAVITY_TOOLS[tool])
    return "|".join(names)


def antigravity_command(command: str, plugin: Path, jidoka_home: Path) -> str:
    """The hook command for Antigravity: the scripts by their path in the snapshot, the launcher looking for its
    Python in the home this install recorded, and the host named for the script, which cannot tell it from the
    payload."""
    return (f'{JIDOKA_HOME_VARIABLE}="{jidoka_home}" {command.replace(CLAUDE_PLUGIN_ROOT, str(plugin))} '
            f"--host {ANTIGRAVITY_HOST}")


def antigravity_handlers(group: dict, plugin: Path, jidoka_home: Path, hooks_file: Path) -> list[dict]:
    try:
        return [{"type": handler.get("type", "command"),
                 "command": antigravity_command(handler["command"], plugin, jidoka_home),
                 "timeout": ANTIGRAVITY_HOOK_TIMEOUT_SECONDS} for handler in group["hooks"]]
    except (KeyError, TypeError, AttributeError) as err:
        raise InstallerError(f"{hooks_file} has a hook group whose handlers cannot be read: {err!r}") from err


def antigravity_hooks(hooks_file: Path, plugin: Path, jidoka_home: Path) -> dict:
    """The hooks of hooks_file as the one named hook Antigravity reads from a plugin's root hooks.json.

    A tool event keeps its groups, each with a matcher in Antigravity's tool names. A session event is a flat list of
    handlers, which Antigravity gives no matcher. Every command names its script by its absolute path under plugin,
    the snapshot's copy, so a profile copy never runs scripts that the next install rewrites under it.
    """
    events = read_json_object(hooks_file).get("hooks")
    if not isinstance(events, dict):
        raise InstallerError(f"{hooks_file} has no hooks object")
    named: dict[str, list] = {}
    for event, groups in events.items():
        if event in CLAUDE_ONLY_EVENTS:
            continue
        if not isinstance(groups, list) or not all(isinstance(group, dict) for group in groups):
            raise InstallerError(f"{hooks_file} holds {event} hooks that are not a list of groups")
        if event in ANTIGRAVITY_GROUPED_EVENTS:
            named[event] = [{"matcher": antigravity_matcher(group.get("matcher", ""), hooks_file),
                             "hooks": antigravity_handlers(group, plugin, jidoka_home, hooks_file)} for group in groups]
        elif event in ANTIGRAVITY_FLAT_EVENTS:
            named[event] = [handler for group in groups
                            for handler in antigravity_handlers(group, plugin, jidoka_home, hooks_file)]
        else:
            raise InstallerError(f"{hooks_file} has {event} hooks, which the Antigravity copy has no form for")
    named.setdefault(lap_guard_record.HOOK_EVENT, []).append(profile_guard_group(plugin, jidoka_home))
    return {PLUGIN_NAME: named}


def profile_guard_group(plugin: Path, jidoka_home: Path) -> dict:
    """The hook group that holds a lap worker's calls to the lap's rules. It matches every tool, because the guard
    denies a tool it does not know. hooks.json does not name it, because Claude Code has the lap mod for that and
    would only pay for a second process on every call."""
    command = f'"{CLAUDE_PLUGIN_ROOT}/bin/jidoka-run" "{CLAUDE_PLUGIN_ROOT}/hooks/{lap_guard_record.HOOK_SCRIPT}"'
    return lap_guard_record.hook_group_of(antigravity_command(command, plugin, jidoka_home),
                                          ANTIGRAVITY_HOOK_TIMEOUT_SECONDS)


def antigravity_manifest(plugin: Path) -> dict:
    """The plugin.json of the profile copy: the manifest's own fields, without the Claude Code ones."""
    manifest = read_json_object(plugin / ".claude-plugin" / "plugin.json")
    return {key: manifest[key] for key in ["name", "version", "description", "author"] if key in manifest}


def sibling_skill_folders(names: list[str]) -> re.Pattern[str]:
    """Matches `../<name>` for a skill name, where the text points at a sibling skill's folder; matches nothing when
    there are no skills."""
    if not names:
        return re.compile(r"(?!)")
    return re.compile(r"(?<![\w.])\.\./(" + "|".join(re.escape(name) for name in names) + r")(?=/)")


def antigravity_text(text: str, siblings: re.Pattern[str], plugin: Path) -> str:
    """The text with each `jidoka:<name>` token as `jidoka-<name>`, each `../<skill>/` as `../jidoka-<skill>/`, and
    each `<skill folder>/../../bin/`, `scripts/` or `hooks/` as the same folder under plugin, the snapshot's copy,
    which the profile copy does not hold."""
    in_snapshot = SKILL_SCRIPT_FOLDERS.sub(lambda found: f"{plugin.as_posix()}/{found.group(1)}/", text)
    return siblings.sub(lambda found: f"../{ANTIGRAVITY_PREFIX}{found.group(1)}",
                        JIDOKA_TOKEN.sub(ANTIGRAVITY_PREFIX, in_snapshot))


def with_prefixed_name(text: str) -> str:
    """The text with the `name:` field of its front matter prefixed, and the text as it was when it has none."""
    if not text.startswith("---"):
        return text
    end = text.find("\n---", 3)
    if end == -1:
        return text
    return NAME_FIELD.sub(lambda found: f"name: {ANTIGRAVITY_PREFIX}{found.group(2)}", text[:end], count=1) + text[end:]


def copy_converting(source: str, destination: str, siblings: re.Pattern[str], plugin: Path) -> str:
    """Copies a file with its text converted by antigravity_text, and a file that is not UTF-8 text as it is."""
    data = Path(source).read_bytes()
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return shutil.copy2(source, destination)
    Path(destination).write_bytes(antigravity_text(text, siblings, plugin).encode("utf-8"))
    shutil.copymode(source, destination)
    return destination


def rewrite_name_field(file: Path) -> None:
    file.write_bytes(with_prefixed_name(file.read_text(encoding="utf-8")).encode("utf-8"))


def write_antigravity_skills_and_agents(plugin: Path, copy: Path) -> None:
    """Writes the plugin's skills and agents into copy under names that start with `jidoka-`, since Antigravity has
    no plugin namespace to put in front of a skill's name. Their text names plugin's own scripts, not the copy's."""
    skills_folder = plugin / "skills"
    skills = sorted(path for path in skills_folder.iterdir() if path.is_dir()) if skills_folder.is_dir() else []
    siblings = sibling_skill_folders([skill.name for skill in skills])
    for skill in skills:
        written = copy / "skills" / f"{ANTIGRAVITY_PREFIX}{skill.name}"
        shutil.copytree(skill, written,
                        copy_function=lambda source, destination: copy_converting(source, destination, siblings, plugin))
        if (written / "SKILL.md").is_file():
            rewrite_name_field(written / "SKILL.md")
    agents = plugin / "agents"
    if agents.is_dir():
        (copy / "agents").mkdir()
        for agent in sorted(agents.iterdir()):
            named = f"{ANTIGRAVITY_PREFIX}{agent.name}" if agent.suffix == ".md" else agent.name
            copy_converting(str(agent), str(copy / "agents" / named), siblings, plugin)
            if agent.suffix == ".md":
                rewrite_name_field(copy / "agents" / named)


def build_antigravity_copy(snapshot: Path, jidoka_home: Path, building: Path) -> Path:
    """Builds the plugin the way `antigravity plugin install` would leave it, in a new folder inside building.

    The plugin folder of the snapshot is copied as files and never links, without the launcher and the scripts, which
    stay in the snapshot where the hooks and the skills name them, the lap mod and its helpers, the types they use,
    Claude Code's manifest and hooks file, and the skills and agents, which are written under their `jidoka-` names.
    The manifest and the hooks go at the root, where Antigravity reads them.
    """
    plugin = snapshot / PLUGIN_DIR
    copy = building / PLUGIN_DIR

    def left_out(folder: str, names: list[str]) -> set[str]:
        relative = Path(folder).relative_to(plugin)
        if relative == Path("."):
            return {".claude-plugin", "skills", "agents", "types", "bin", "scripts"} & set(names)
        if relative == Path("hooks"):
            return {name for name in names if name == "hooks.json" or name.endswith(".ts")}
        return set()

    shutil.copytree(plugin, copy, symlinks=False, ignore=left_out)
    write_antigravity_skills_and_agents(plugin, copy)
    for name, content in [("plugin.json", antigravity_manifest(plugin)),
                          ("hooks.json", antigravity_hooks(plugin / "hooks" / "hooks.json", plugin, jidoka_home))]:
        (copy / name).write_text(json.dumps(content, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return copy


def antigravity_copy_version(copy: Path) -> str | None:
    """The version in the profile copy's plugin.json, or None when the copy is missing, is a link, or has no readable
    manifest with a version."""
    if copy.is_symlink() or not copy.is_dir():
        return None
    try:
        version = read_json_object(copy / "plugin.json").get("version")
    except InstallerError:
        return None
    return version if isinstance(version, str) else None


def ensure_antigravity_copy(snapshot: Path, jidoka_home: Path, profile: Path) -> None:
    """Writes the plugin into the profile's plugins folder, replacing a copy of another version and leaving a copy
    of the snapshot's version as it is, so a second run at the same version touches nothing."""
    target = profile / ANTIGRAVITY_PLUGINS / PLUGIN_NAME
    if antigravity_copy_version(target) == read_version(snapshot):
        return
    built_in_place(target, lambda building: build_antigravity_copy(snapshot, jidoka_home, building), Replacing())


def enable_in_antigravity_config(profile: Path) -> None:
    """Sets plugins.jidoka.enabled in the profile's config.json, keeping every other key, and writes nothing when it
    is set already."""
    config_file = profile / ANTIGRAVITY_CONFIG
    held = read_json_object(config_file) if config_file.exists() else {}
    plugins = held.get("plugins", {})
    if not isinstance(plugins, dict):
        raise InstallerError(f"{config_file} holds a plugins value that is not a JSON object")
    entry = plugins.get(PLUGIN_NAME, {})
    if not isinstance(entry, dict):
        raise InstallerError(f"{config_file} holds a {PLUGIN_NAME} plugin entry that is not a JSON object")
    if entry.get("enabled") is True:
        return
    held["plugins"] = {**plugins, PLUGIN_NAME: {**entry, "enabled": True}}
    written = config_file.with_name(f".{config_file.name}.tmp")
    written.write_text(json.dumps(held, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    written.chmod(0o600)
    os.replace(written, config_file)


def find_antigravity_profiles(t3_userdata: Path) -> list[Path]:
    """The T3 Antigravity profiles, one folder for each T3 instance under providers/antigravity, that hold the config
    folder Antigravity reads its plugins from."""
    folder = t3_userdata / T3_ANTIGRAVITY_PROFILES
    if not folder.is_dir():
        return []
    return sorted(path for path in folder.iterdir() if (path / ANTIGRAVITY_CONFIG_DIR).is_dir())


def install_into_antigravity(snapshot: Path, jidoka_home: Path, profile: Path) -> None:
    ensure_antigravity_copy(snapshot, jidoka_home, profile)
    enable_in_antigravity_config(profile)


def read_pushover(home: Path) -> dict:
    """The Pushover file as it stands, or an empty object when it is missing or not a JSON object."""
    try:
        held = json.loads((home / PUSHOVER_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return held if isinstance(held, dict) else {}


def ask_for_pushover(home: Path, terminal: Terminal | None) -> str:
    """Asks the person at the terminal for the Pushover keys, writes them to <jidoka-home>/pushover.json and
    returns the line to print.

    The keys are asked here and nowhere else, so no model ever sees them. An empty answer leaves the file as
    it was, and without a terminal nothing is asked.
    """
    if terminal is None:
        return (f"Pushover keys were not asked, because this is not a terminal. Run install.py in one to set "
                f"them. {'Pushover is set up.' if read_pushover(home) else 'Pushover is off.'}")
    held = read_pushover(home)
    user_key = terminal.ask("Pushover user key (Enter to " + ("keep what is set" if held else "skip Pushover")
                            + "): ").strip()
    if not user_key:
        return "Pushover left as it was."
    app_token = terminal.ask_secret("Pushover application token (typing is hidden): ").strip()
    if not app_token:
        return "Pushover left as it was, because no application token was given."
    ui_url = terminal.ask(f"Address jidoka-ui answers at, which each message links to; for a phone, the tailnet "
                          f"address that tailscale serve gives it (Enter for {DEFAULT_UI_URL}): ").strip()
    kept = {key: value for key, value in held.items() if key not in ("user_key", "app_token", "ui_url")}
    written = {"user_key": user_key, "app_token": app_token, "ui_url": ui_url or DEFAULT_UI_URL, **kept}
    home.mkdir(parents=True, exist_ok=True)
    path = home / PUSHOVER_FILE
    path.write_text(json.dumps(written, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    path.chmod(0o600)
    return f"Pushover is set up in {path}."


def install(folders: Folders, python_version: tuple[int, int], python: str, terminal: Terminal | None,
            missing_on_host: Callable[[str], list[str]]) -> None:
    config_dirs, jidoka_home, t3_userdata = folders.config_dirs, folders.jidoka_home, folders.t3_userdata
    missing = find_every_gap(python_version, shutil.which, missing_on_host)
    if missing:
        raise InstallerError("these are missing, and the installer installs none of them: " + ", ".join(missing))
    tools = locate_tools(shutil.which)
    if not PLUGIN_FOLDER.is_dir():
        raise InstallerError(f"the plugin folder {PLUGIN_FOLDER} does not exist")
    refuse_if_dirty(tools.git, PLUGIN_FOLDER)
    version = read_version(PLUGIN_FOLDER)
    source_repo = main_worktree(tools.git, PLUGIN_FOLDER.parent)
    previous = load_settings(jidoka_home)
    refuse_incomplete_routes(previous)
    snapshot = ensure_snapshot(tools.git, PLUGIN_FOLDER, jidoka_home, version)
    ui = publish_ui(tools.git, tools.dotnet, checkout_root(tools.git, PLUGIN_FOLDER), jidoka_home, previous)
    unnamed = unnamed_config_dirs(previous, config_dirs)
    record(jidoka_home,
           OwnedSettings(python, config_dirs, machine_routes.default_routes(tools.codex is not None), source_repo, ui.record),
           previous)
    print(f"Recorded {python} and {len(config_dirs)} config dir(s) in {jidoka_home}")
    print(ui.line)
    for config_dir in config_dirs:
        install_into_claude(tools.claude, config_dir, snapshot)
        print(f"Installed jidoka {version} into {config_dir}")
    if tools.codex is not None:
        install_into_codex(tools.codex, ensure_codex_snapshot(snapshot, jidoka_home, version))
        print(f"Installed jidoka {version} into Codex")
    profiles = find_antigravity_profiles(t3_userdata)
    if not profiles:
        print(f"Antigravity was skipped, because {t3_userdata} holds no T3 Antigravity profile.")
    for profile in profiles:
        install_into_antigravity(snapshot, jidoka_home, profile)
        print(f"Installed jidoka {version} into Antigravity profile {profile}")
    print(ask_for_pushover(jidoka_home, terminal))
    if unnamed:
        print("These config dirs were recorded by an earlier run and not named in this one, so they still run the "
              "plugin from their earlier source. Name them to move them to the snapshot:\n"
              + "\n".join(f"  {path}" for path in unnamed))


def main(argv: list[str], missing_on_host: Callable[[str], list[str]]) -> int:
    parser = argparse.ArgumentParser(prog="install.py", description="Install or update jidoka's plugin on this machine.")
    parser.add_argument("--config-dir", action="append", required=True, metavar="PATH",
                        help="a Claude config dir to install into; repeat it for each one")
    parser.add_argument("--jidoka-home", default="~/.jidoka", help="the folder that holds jidoka's per-machine state")
    parser.add_argument("--t3-userdata", default="~/.t3/userdata", metavar="PATH",
                        help="the T3 userdata folder whose Antigravity profiles get a copy of the plugin")
    args = parser.parse_args(argv)
    config_dirs = [Path(path).expanduser().resolve() for path in args.config_dir]
    terminal = Terminal(input, getpass.getpass) if sys.stdin.isatty() and sys.stdout.isatty() else None
    try:
        folders = Folders(config_dirs, Path(args.jidoka_home).expanduser().resolve(),
                          Path(args.t3_userdata).expanduser().resolve())
        install(folders, sys.version_info[:2], sys.executable, terminal, missing_on_host)
    except (InstallerError, OSError) as err:
        print(f"install.py: {err}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:], missing_on_windows if os.name == "nt" else no_missing_on_this_host))
