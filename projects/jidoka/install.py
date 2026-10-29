#!/usr/bin/env python3
"""Installs jidoka's plugin on this machine, and updates it when run again.

Jeff runs it in a terminal and names the Claude config dirs to install into.
It checks for git, bd, claude and Python 3.10 or later and installs none of
them. It refuses while the plugin folder next to this file has uncommitted
changes, so what gets installed is a commit. It writes that commit's plugin
to <jidoka-home>/plugins/<version>/, a snapshot, because Claude Code runs a
plugin from a folder marketplace in place and an edit to the checkout would
otherwise change the scripts under a running session. It records the Python
it runs under, the config dirs, a native route for each tier, except for a
tier whose route is already recorded, which /jidoka:setup may have set, and
jidoka's source repo in <jidoka-home>, then adds the snapshot as a local marketplace
and installs the plugin at user scope into each named config dir, and into
Codex when codex is on the PATH. A snapshot is never rewritten. A version
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
import shutil
import subprocess
import sys
import tarfile
import tempfile
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path, PureWindowsPath

PLUGIN_FOLDER = Path(__file__).resolve().parent / "plugin"
sys.path.append(str(PLUGIN_FOLDER / "jidoka" / "scripts"))
# A bytecode file written into the plugin folder would count as an uncommitted change to what gets installed.
WRITES_BYTECODE = sys.dont_write_bytecode
sys.dont_write_bytecode = True
import routes as machine_routes  # noqa: E402

sys.dont_write_bytecode = WRITES_BYTECODE

MIN_PYTHON = (3, 10)
REQUIRED_TOOLS = ["git", "bd", "claude"]
MARKETPLACE = "jidoka"
PLUGIN_ID = "jidoka@jidoka"
PLUGIN_MANIFEST = Path("jidoka") / ".claude-plugin" / "plugin.json"
TREE_FILE = "plugin-tree-id"
OWNED_SETTINGS = ["python", "config_dirs", "routes", "source_repo", "ui"]
PUSHOVER_FILE = "pushover.json"
UI_FOLDER = Path("projects") / "jidoka-ui"
UI_WEB_PROJECT = Path("src") / "JidokaUi.Web" / "JidokaUi.Web.csproj"
UI_APP = "JidokaUi.Web.dll"
UI_PORT = 5099
DEFAULT_UI_URL = f"http://localhost:{UI_PORT}"


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
class Terminal:
    """The person at the keyboard: `ask` shows what they type, `ask_secret` hides it."""
    ask: Callable[[str], str]
    ask_secret: Callable[[str], str]


@dataclass(frozen=True)
class Tools:
    git: str
    claude: str
    codex: str | None
    dotnet: str | None


@dataclass(frozen=True)
class OwnedSettings:
    """The machine settings that the installer owns and writes on every run; ui is None when there is no record to
    keep."""
    python: str
    config_dirs: list[Path]
    routes: dict[str, Route]
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


def locate_tools(which: Callable[[str], str | None]) -> Tools:
    git, claude = which("git"), which("claude")
    if git is None or claude is None:
        raise InstallerError("git and claude must be on the PATH")
    return Tools(git, claude, which("codex"), which("dotnet"))


def default_routes(codex_present: bool) -> dict[str, Route]:
    return {tier: Route(**route) for tier, route in machine_routes.default_routes(codex_present).items()}


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
    path = home / machine_routes.SETTINGS_FILE
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as err:
        raise InstallerError(f"{path} is not valid JSON: {err}") from err
    if not isinstance(data, dict):
        raise InstallerError(f"{path} does not hold a JSON object")
    return data


def record(home: Path, owned: OwnedSettings, previous: dict) -> None:
    home.mkdir(parents=True, exist_ok=True)
    (home / "python").write_text(owned.python + "\n", encoding="utf-8", newline="\n")
    kept = {key: value for key, value in previous.items() if key not in OWNED_SETTINGS}
    earlier_routes = previous.get("routes")
    settings = {
        "python": owned.python,
        "config_dirs": [str(path) for path in owned.config_dirs],
        "routes": {**{tier: asdict(route) for tier, route in owned.routes.items()},
                   **(earlier_routes if isinstance(earlier_routes, dict) else {})},
        "source_repo": str(owned.source_repo),
        **({"ui": owned.ui} if owned.ui is not None else {}),
        **kept,
    }
    (home / machine_routes.SETTINGS_FILE).write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n",
                                        encoding="utf-8", newline="\n")


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


def write_snapshot(git: str, plugin_folder: Path, tree: str, target: Path) -> None:
    """Builds the snapshot beside target and renames it into place, so target is never half written."""
    building = building_beside(target)
    try:
        extract_head(git, plugin_folder, building)
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


def write_published_ui(git: str, dotnet: str, ui_folder: Path, target: Path) -> None:
    """Publishes what HEAD holds of jidoka-ui beside target and renames the result into place, so target is never
    half written and an uncommitted edit never reaches the app the factory starts."""
    building = building_beside(target)
    try:
        source = building / "source"
        output = building / "app"
        extract_head(git, ui_folder, source)
        run_tool(dotnet, ["publish", str(source / UI_WEB_PROJECT), "--configuration", "Release",
                          "--output", str(output)], dict(os.environ))
        if not (output / UI_APP).is_file():
            raise InstallerError(f"dotnet publish wrote no {UI_APP} in {output}")
        output.rename(target)
    finally:
        shutil.rmtree(building, ignore_errors=True)


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
    """The source Codex has for the jidoka marketplace, or None when Codex has no marketplace by that name."""
    listed = run_tool(codex, ["plugin", "marketplace", "list", "--json"], env)
    try:
        marketplaces = json.loads(listed)["marketplaces"]
        for marketplace in marketplaces:
            if marketplace["name"] == MARKETPLACE:
                return marketplace["marketplaceSource"]["source"]
    except (ValueError, KeyError, TypeError) as err:
        raise InstallerError("`codex plugin marketplace list --json` printed a list the installer cannot read: "
                             + listed.strip()) from err
    return None


def install_into_codex(codex: str, snapshot: Path) -> None:
    """Codex refuses to add a marketplace whose name it already has from another source,
    so this first removes a jidoka marketplace that points at an older snapshot."""
    env = dict(os.environ)
    source = codex_marketplace_source(codex, env)
    if source is not None and source != str(snapshot):
        run_tool(codex, ["plugin", "marketplace", "remove", MARKETPLACE], env)
    run_tool(codex, ["plugin", "marketplace", "add", str(snapshot)], env)
    run_tool(codex, ["plugin", "add", PLUGIN_ID], env)


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


def install(config_dirs: list[Path], jidoka_home: Path, python_version: tuple[int, int], python: str,
            terminal: Terminal | None) -> None:
    missing = find_missing(python_version, shutil.which)
    if missing:
        raise InstallerError("these are missing, and the installer installs none of them: " + ", ".join(missing))
    tools = locate_tools(shutil.which)
    if not PLUGIN_FOLDER.is_dir():
        raise InstallerError(f"the plugin folder {PLUGIN_FOLDER} does not exist")
    refuse_if_dirty(tools.git, PLUGIN_FOLDER)
    version = read_version(PLUGIN_FOLDER)
    source_repo = main_worktree(tools.git, PLUGIN_FOLDER.parent)
    previous = load_settings(jidoka_home)
    snapshot = ensure_snapshot(tools.git, PLUGIN_FOLDER, jidoka_home, version)
    ui = publish_ui(tools.git, tools.dotnet, checkout_root(tools.git, PLUGIN_FOLDER), jidoka_home, previous)
    unnamed = unnamed_config_dirs(previous, config_dirs)
    record(jidoka_home,
           OwnedSettings(python, config_dirs, default_routes(tools.codex is not None), source_repo, ui.record),
           previous)
    print(f"Recorded {python} and {len(config_dirs)} config dir(s) in {jidoka_home}")
    print(ui.line)
    for config_dir in config_dirs:
        install_into_claude(tools.claude, config_dir, snapshot)
        print(f"Installed jidoka {version} into {config_dir}")
    if tools.codex is not None:
        install_into_codex(tools.codex, snapshot)
        print(f"Installed jidoka {version} into Codex")
    print(ask_for_pushover(jidoka_home, terminal))
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
    terminal = Terminal(input, getpass.getpass) if sys.stdin.isatty() and sys.stdout.isatty() else None
    try:
        install(config_dirs, Path(args.jidoka_home).expanduser().resolve(), sys.version_info[:2], sys.executable,
                terminal)
    except (InstallerError, OSError) as err:
        print(f"install.py: {err}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
