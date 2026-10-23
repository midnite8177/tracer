#!/usr/bin/env python3
"""Installs jidoka's plugin on this machine, and updates it when run again.

Jeff runs it in a terminal and names the Claude config dirs to install into.
It checks for git, bd, claude and Python 3.10 or later and installs none of
them. It refuses while the plugin folder next to this file has uncommitted
changes, so what gets installed is a commit. It writes that commit's plugin
to <jidoka-home>/plugins/<version>/, a snapshot, because Claude Code runs a
plugin from a folder marketplace in place and an edit to the checkout would
otherwise change the scripts under a running session. It records the Python
it runs under, the config dirs and a native route for each tier in
<jidoka-home>, then adds the snapshot as a local marketplace and installs the
plugin at user scope into each named config dir, and into Codex when codex is
on the PATH. A snapshot is never rewritten. A version whose snapshot came
from different plugin content is refused until release.py gives the change
a new version.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path, PureWindowsPath

MIN_PYTHON = (3, 10)
REQUIRED_TOOLS = ["git", "bd", "claude"]
MARKETPLACE = "jidoka"
PLUGIN_ID = "jidoka@jidoka"
PLUGIN_FOLDER = Path(__file__).resolve().parent / "plugin"
PLUGIN_MANIFEST = Path("jidoka") / ".claude-plugin" / "plugin.json"
TREE_FILE = "plugin-tree-id"
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
    if not isinstance(version, str) or not version or not version.isprintable() or version in (".", "..") \
            or Path(version).name != version or PureWindowsPath(version).name != version:
        raise InstallerError(f"{manifest} holds the version {version!r}, which cannot name a snapshot folder")
    return version


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


def plugin_tree_id(git: str, plugin_folder: Path) -> str:
    found = git_run(git, plugin_folder, ["rev-parse", "HEAD:./"])
    if found.returncode != 0:
        raise InstallerError(f"git could not read the plugin folder at HEAD: {found.stderr.strip()}")
    return found.stdout.strip()


def extract_archive(archive: bytes, destination: Path) -> None:
    """Unpacks a tar stream into destination. Where Python has tar filters, a member or link that leaves destination is refused."""
    try:
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            if hasattr(tarfile, "data_filter"):
                tar.extractall(destination, filter="data")
            else:
                tar.extractall(destination)
    except tarfile.TarError as err:
        raise InstallerError(f"the plugin archive could not be unpacked: {err}") from err


def write_snapshot(git: str, plugin_folder: Path, tree: str, target: Path) -> None:
    """Builds the snapshot beside target and renames it into place, so target is never half written."""
    target.parent.mkdir(parents=True, exist_ok=True)
    for stale in target.parent.glob(f".{target.name}-*"):
        shutil.rmtree(stale, ignore_errors=True)
    building = Path(tempfile.mkdtemp(prefix=f".{target.name}-", dir=target.parent))
    try:
        archived = subprocess.run([git, "-C", str(plugin_folder), "archive", "--format=tar", "HEAD", "--", "."],
                                  capture_output=True)
        if archived.returncode != 0:
            raise InstallerError(f"git archive failed in {plugin_folder}: {archived.stderr.decode('utf-8', 'replace').strip()}")
        extract_archive(archived.stdout, building)
        (building / TREE_FILE).write_text(tree + "\n", encoding="utf-8", newline="\n")
        building.chmod(0o755)
        if target.exists():
            raise InstallerError(f"{target} appeared while the snapshot was being built, and a snapshot is never rewritten")
        building.rename(target)
    except BaseException:
        shutil.rmtree(building, ignore_errors=True)
        raise


def ensure_snapshot(git: str, plugin_folder: Path, jidoka_home: Path, version: str) -> Path:
    """The folder <jidoka-home>/plugins/<version>/, written from HEAD unless it already holds this plugin content."""
    tree = plugin_tree_id(git, plugin_folder)
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


def install_into_codex(codex: str, snapshot: Path) -> None:
    run_tool(codex, ["plugin", "marketplace", "add", str(snapshot)], dict(os.environ))
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
    snapshot = ensure_snapshot(tools.git, PLUGIN_FOLDER, jidoka_home, version)
    unnamed = unnamed_config_dirs(previous, config_dirs)
    record(jidoka_home, python, config_dirs, default_routes(tools.codex is not None), previous)
    print(f"Recorded {python} and {len(config_dirs)} config dir(s) in {jidoka_home}")
    for config_dir in config_dirs:
        install_into_claude(tools.claude, config_dir, snapshot)
        print(f"Installed jidoka {version} into {config_dir}")
    if tools.codex is not None:
        install_into_codex(tools.codex, snapshot)
        print(f"Installed jidoka {version} into Codex")
    if unnamed:
        print("These config dirs were recorded by an earlier run and not named in this one, so they still run the "
              "plugin from their earlier source. Name them to move them to the snapshot:\n"
              + "\n".join(f"  {path}" for path in unnamed))


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
