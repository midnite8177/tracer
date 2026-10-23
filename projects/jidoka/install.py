#!/usr/bin/env python3
"""Installs jidoka's plugin on this machine, and updates it when run again.

Jeff runs it in a terminal and names the Claude config dirs to install into.
It checks for git, bd, claude and Python 3.10 or later and installs none of
them. It records the Python it runs under, the config dirs and a native route
for each tier in <jidoka-home>, then adds the plugin folder next to this file
as a local marketplace and installs the plugin at user scope into each named
config dir, and into Codex when codex is on the PATH. It refuses while the
plugin folder has uncommitted changes, so what gets installed is a commit.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

MIN_PYTHON = (3, 10)
REQUIRED_TOOLS = ["git", "bd", "claude"]
MARKETPLACE = "jidoka"
PLUGIN_ID = "jidoka@jidoka"
PLUGIN_FOLDER = Path(__file__).resolve().parent / "plugin"
PLUGIN_MANIFEST = Path("jidoka") / ".claude-plugin" / "plugin.json"
OWNED_SETTINGS = ["python", "config_dirs", "routes"]


class InstallerError(Exception):
    pass


@dataclass(frozen=True)
class Route:
    """How one tier runs. A null model, version and effort mean the harness's own default."""
    harness: str
    model: str | None
    version: str | None
    effort: str | None


@dataclass(frozen=True)
class Tools:
    git: str
    claude: str
    codex: str | None


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


def locate_tools(which: Callable[[str], str | None]) -> Tools:
    git, claude = which("git"), which("claude")
    if git is None or claude is None:
        raise InstallerError("git and claude must be on the PATH")
    return Tools(git, claude, which("codex"))


def default_routes(codex_present: bool) -> dict[str, Route]:
    second = Route("codex", None, None, None) if codex_present else Route("claude", "opus", "5.5", "high")
    return {
        "light": Route("claude", "haiku", "5.5", "medium"),
        "standard": Route("claude", "sonnet", "5.5", "high"),
        "deep": Route("claude", "opus", "5.5", "high"),
        "second": second,
        "local": Route("claude", "sonnet", "5.5", "medium"),
    }


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
    return str(version)


def load_settings(home: Path) -> dict:
    path = home / "settings.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as err:
        raise InstallerError(f"{path} is not valid JSON: {err}") from err
    if not isinstance(data, dict):
        raise InstallerError(f"{path} does not hold a JSON object")
    return data


def record(home: Path, python: str, config_dirs: list[Path], routes: dict[str, Route], previous: dict) -> None:
    home.mkdir(parents=True, exist_ok=True)
    (home / "python").write_text(python + "\n", encoding="utf-8", newline="\n")
    kept = {key: value for key, value in previous.items() if key not in OWNED_SETTINGS}
    settings = {
        "python": python,
        "config_dirs": [str(path) for path in config_dirs],
        "routes": {tier: asdict(route) for tier, route in routes.items()},
        **kept,
    }
    (home / "settings.json").write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n",
                                        encoding="utf-8", newline="\n")


def run_tool(executable: str, args: list[str], env: dict[str, str]) -> None:
    done = subprocess.run([executable, *args], capture_output=True, text=True, encoding="utf-8", env=env)
    if done.returncode != 0:
        shown = " ".join([Path(executable).stem, *args])
        detail = (done.stderr.strip() or done.stdout.strip() or "no output")
        raise InstallerError(f"`{shown}` failed with exit {done.returncode}: {detail}")


def install_into_claude(claude: str, config_dir: Path) -> None:
    env = {**os.environ, "CLAUDE_CONFIG_DIR": str(config_dir)}
    run_tool(claude, ["plugin", "marketplace", "add", str(PLUGIN_FOLDER)], env)
    run_tool(claude, ["plugin", "marketplace", "update", MARKETPLACE], env)
    run_tool(claude, ["plugin", "install", PLUGIN_ID, "--scope", "user"], env)
    run_tool(claude, ["plugin", "update", PLUGIN_ID, "--scope", "user"], env)


def install_into_codex(codex: str) -> None:
    run_tool(codex, ["plugin", "marketplace", "add", str(PLUGIN_FOLDER)], dict(os.environ))
    run_tool(codex, ["plugin", "add", PLUGIN_ID], dict(os.environ))


def install(config_dirs: list[Path], jidoka_home: Path, python_version: tuple[int, int], python: str) -> None:
    missing = find_missing(python_version, shutil.which)
    if missing:
        raise InstallerError("these are missing, and the installer installs none of them: " + ", ".join(missing))
    tools = locate_tools(shutil.which)
    if not PLUGIN_FOLDER.is_dir():
        raise InstallerError(f"the plugin folder {PLUGIN_FOLDER} does not exist")
    refuse_if_dirty(tools.git, PLUGIN_FOLDER)
    version = read_version(PLUGIN_FOLDER)
    previous = load_settings(jidoka_home)
    record(jidoka_home, python, config_dirs, default_routes(tools.codex is not None), previous)
    print(f"Recorded {python} and {len(config_dirs)} config dir(s) in {jidoka_home}")
    for config_dir in config_dirs:
        install_into_claude(tools.claude, config_dir)
        print(f"Installed jidoka {version} into {config_dir}")
    if tools.codex is not None:
        install_into_codex(tools.codex)
        print(f"Installed jidoka {version} into Codex")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="install.py", description="Install or update jidoka's plugin on this machine.")
    parser.add_argument("--config-dir", action="append", required=True, metavar="PATH",
                        help="a Claude config dir to install into; repeat it for each one")
    parser.add_argument("--jidoka-home", default="~/.jidoka", help="the folder that holds jidoka's per-machine state")
    args = parser.parse_args(argv)
    config_dirs = [Path(path).expanduser().resolve() for path in args.config_dir]
    try:
        install(config_dirs, Path(args.jidoka_home).expanduser().resolve(), sys.version_info[:2], sys.executable)
    except (InstallerError, OSError) as err:
        print(f"install.py: {err}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
