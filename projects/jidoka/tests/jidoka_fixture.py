"""Builds the throwaway pieces the installer, release and launcher tests run against.

A checkout is a temporary git repo holding copies of install.py, release.py
and plugin/. The claude, codex and bd stand-ins are small executables in a
bin folder that becomes the whole PATH, so a test decides which tools exist.
The claude and codex stand-ins append one JSON line per call to a log file.

A fake beads workspace is a store of fake_bd.py, the bd stand-in that the
tests of the scripts that read and write beads put first on the PATH,
because every call of real bd opens its database and takes a second or more.

A stealth beads workspace is a copy of one that bd init made in a template
repo, because bd init takes seconds and a copy takes milliseconds. What plain
bd init commits is copied the same way from a template of its own. A suite
run through run_suite.py makes each template once, in the folder its workers
share; any other process makes its own the first time a test asks for one.
"""
import atexit
import functools
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import fake_bd
from run_suite import SHARED_FOLDER

PROJECT = Path(__file__).resolve().parents[1]
SHIPPED = ["install.py", "release.py"]
STARTING_VERSION = "0.1.0"
TEMPLATE_WAIT_SECONDS = 300
TEMPLATE_POLL_SECONDS = 0.2


class FixtureError(Exception):
    pass


class Bd(Enum):
    """The bd a test's PATH holds: none, a stub that exits 0 whatever it is asked, or the real one."""
    NONE = "none"
    STUB = "stub"
    REAL = "real"


@dataclass(frozen=True)
class ToolsOnPath:
    """Which tools the PATH of a test run holds."""
    git: bool
    bd: Bd
    claude: bool
    codex: bool


ALL_TOOLS = ToolsOnPath(git=True, bd=Bd.STUB, claude=True, codex=True)
WITHOUT_CODEX = ToolsOnPath(git=True, bd=Bd.STUB, claude=True, codex=False)


def run(args: list, cwd: Path) -> str:
    done = subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf-8")
    if done.returncode != 0:
        raise FixtureError(f"{' '.join(args)} failed in {cwd}: {done.stderr.strip()}")
    return done.stdout


def git_commit_all(repo: Path, message: str) -> None:
    run(["git", "add", "-A"], repo)
    run(["git", "commit", "-q", "-m", message], repo)


def init_repo(repo: Path) -> None:
    """Makes an empty git repo that can commit."""
    repo.mkdir(parents=True, exist_ok=True)
    run(["git", "init", "-q"], repo)
    run(["git", "config", "user.email", "fixture@example.com"], repo)
    run(["git", "config", "user.name", "Fixture"], repo)


def make_beads_template(template: Path) -> None:
    """Runs bd init in a new repo and keeps what it wrote: .beads, its info/exclude lines and its git config."""
    repo = template / "repo"
    init_repo(repo)
    exclude = repo / ".git" / "info" / "exclude"
    exclude_before = exclude.read_text(encoding="utf-8") if exclude.exists() else ""
    config_before = set(run(["git", "config", "--local", "--list"], repo).splitlines())
    run([real_tool("bd"), "init", "--stealth", "--non-interactive"], repo)
    exclude_after = exclude.read_text(encoding="utf-8")
    if not exclude_after.startswith(exclude_before):
        raise FixtureError(f"bd init rewrote {exclude} instead of adding to it")
    added_config = [line.split("=", 1) for line in run(["git", "config", "--local", "--list"], repo).splitlines()
                    if line not in config_before]
    shutil.move(repo / ".beads", template / "beads")
    (template / "exclude").write_text(exclude_after[len(exclude_before):], encoding="utf-8")
    (template / "config.json").write_text(json.dumps(added_config), encoding="utf-8")
    shutil.rmtree(repo)


def take_template_lock(lock: Path, template: Path) -> bool:
    """Creates the lock file exclusively and returns True, or returns False once another process made the template.

    It polls while another process holds the lock, and gives up when the template never appears.
    """
    deadline = time.monotonic() + TEMPLATE_WAIT_SECONDS
    while True:
        try:
            os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            return True
        except FileExistsError:
            if template.exists():
                return False
            if time.monotonic() > deadline:
                raise FixtureError(f"no beads template appeared in {TEMPLATE_WAIT_SECONDS} s while {lock} was held")
            time.sleep(TEMPLATE_POLL_SECONDS)


def shared_template(name: str, make) -> Path:
    """The folder a template named name lives in, which make fills at most once per suite run.

    Workers of one run share a folder, and the first to create the lock file in it makes the template
    while the others wait for it to appear. A process outside such a run uses a folder of its own.
    """
    shared = os.environ.get(SHARED_FOLDER)
    if shared is None:
        shared = tempfile.mkdtemp(prefix=f"jidoka-{name}-")
        atexit.register(shutil.rmtree, shared, True)
    template = Path(shared) / name
    lock = Path(shared) / f"{name}.lock"
    if take_template_lock(lock, template):
        try:
            if not template.exists():
                partial = Path(tempfile.mkdtemp(prefix=f"{name}-", dir=shared))
                make(partial)
                partial.rename(template)
        finally:
            lock.unlink()
    return template


@functools.cache
def beads_template() -> Path:
    return shared_template("beads-template", make_beads_template)


def make_bd_init_template(template: Path) -> None:
    """Runs plain bd init in a new repo and keeps its .beads and every other file of the commit bd init made."""
    repo = template / "repo"
    init_repo(repo)
    run([real_tool("bd"), "init", "--non-interactive"], repo)
    committed = run(["git", "ls-files"], repo).splitlines()
    others = [path for path in committed if not path.startswith(".beads/")]
    if not others or run(["git", "status", "--porcelain"], repo):
        raise FixtureError(f"bd init in {repo} did not commit its files and leave a clean status")
    shutil.move(repo / ".beads", template / "beads")
    for path in others:
        (template / "files" / path).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(repo / path, template / "files" / path)
    shutil.rmtree(repo)


@functools.cache
def bd_init_template() -> Path:
    return shared_template("bd-init-template", make_bd_init_template)


def add_stealth_beads(repo: Path) -> None:
    """Gives a git repo what `bd init --stealth --non-interactive` gives it, by copying the template.

    Every copy keeps the template's bead id prefix and database name, whatever the repo's folder is called.
    """
    template = beads_template()
    shutil.copytree(template / "beads", repo / ".beads", symlinks=True)
    exclude = repo / ".git" / "info" / "exclude"
    exclude.parent.mkdir(exist_ok=True)
    with open(exclude, "a", encoding="utf-8", newline="") as fh:
        fh.write((template / "exclude").read_text(encoding="utf-8"))
    for key, value in json.loads((template / "config.json").read_text(encoding="utf-8")):
        run(["git", "config", key, value], repo)


def add_fake_beads(repo: Path, bin_dir: Path) -> Path:
    """Gives a git repo an empty fake beads store and writes the fake bd into bin_dir, returning the fake's path.

    The store's .beads folder gets the info/exclude line bd init writes, so git status shows it nowhere, and its
    bead ids start with the repo folder's name.
    """
    fake_bd.new_store(repo / fake_bd.STORE, repo.name)
    exclude = repo / ".git" / "info" / "exclude"
    exclude.parent.mkdir(exist_ok=True)
    with open(exclude, "a", encoding="utf-8", newline="") as fh:
        fh.write("\n.beads/\n")
    bin_dir.mkdir(parents=True, exist_ok=True)
    fake = bin_dir / "bd"
    write_executable(fake, f'#!/bin/sh\nexec "{sys.executable}" "{Path(fake_bd.__file__).resolve()}" "$@"\n')
    return fake


def path_with(bin_dir: Path) -> str:
    """The caller's PATH with bin_dir first, so the tools in it stand in for the installed ones."""
    return f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"


def add_committed_beads(repo: Path) -> None:
    """Gives a git repo the template's beads workspace and commits it, as a repo that shares its beads through git.

    The workspace's own .gitignore keeps the Dolt data out, so git tracks only its config and text files.
    """
    template = beads_template()
    shutil.copytree(template / "beads", repo / ".beads", symlinks=True)
    for key, value in json.loads((template / "config.json").read_text(encoding="utf-8")):
        run(["git", "config", key, value], repo)
    run(["git", "add", "--", ".beads"], repo)
    run(["git", "commit", "-q", "-m", "Track the beads"], repo)


def add_committed_bd_init(repo: Path) -> None:
    """Gives a git repo what plain `bd init` commits, as a repo that shares its beads through git, and commits it.

    That is the workspace, bd's blocks in CLAUDE.md and AGENTS.md, its skill, its Claude Code and Codex hook files
    and its .gitignore block. The repo gets no core.hooksPath, so its commits run no bd hook.
    """
    template = bd_init_template()
    shutil.copytree(template / "beads", repo / ".beads", symlinks=True)
    shutil.copytree(template / "files", repo, symlinks=True, dirs_exist_ok=True)
    run(["git", "add", "-A"], repo)
    run(["git", "commit", "-q", "-m", "Track the beads"], repo)


def build_checkout(repo: Path) -> None:
    """Makes a committed git repo that holds copies of the scripts and the plugin folder."""
    init_repo(repo)
    for name in SHIPPED:
        shutil.copy2(PROJECT / name, repo / name)
    shutil.copytree(PROJECT / "plugin", repo / "plugin", symlinks=True,
                    ignore=shutil.ignore_patterns("__pycache__"))
    manifest = repo / "plugin" / "jidoka" / ".claude-plugin" / "plugin.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["version"] = STARTING_VERSION
    manifest.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n")
    git_commit_all(repo, "Start")


def commit_count(repo: Path) -> int:
    return int(run(["git", "rev-list", "--count", "HEAD"], repo).strip())


def real_tool(name: str) -> str:
    found = shutil.which(name)
    if found is None:
        raise FixtureError(f"{name} must be installed to run these tests")
    return found


def write_executable(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")
    path.chmod(0o755)


def write_recorder(path: Path, name: str, log: Path, fail_on: str) -> None:
    """Writes a tool that logs its arguments and CLAUDE_CONFIG_DIR, and fails when an argument equals fail_on."""
    write_executable(path, "\n".join([
        f"#!{sys.executable}",
        "import json, os, sys",
        f"with open({str(log)!r}, 'a', encoding='utf-8') as fh:",
        f"    fh.write(json.dumps({{'tool': {name!r}, 'argv': sys.argv[1:], "
        "'config_dir': os.environ.get('CLAUDE_CONFIG_DIR')}) + '\\n')",
        f"if {fail_on!r} in sys.argv[1:]:",
        "    print('the fake refuses this call', file=sys.stderr)",
        "    sys.exit(1)",
        ""]))


def write_codex(path: Path, log: Path, state: Path, fail_on: str) -> None:
    """Writes a codex that logs its arguments, keeps its marketplaces in state, and fails when an argument equals fail_on.

    It answers `plugin marketplace add <source>`, `plugin marketplace remove <name>`,
    `plugin marketplace list --json` and `plugin add <plugin>@<marketplace>`. An add
    takes the marketplace name from the source's .claude-plugin/marketplace.json.
    """
    write_executable(path, "\n".join([
        f"#!{sys.executable}",
        "import json, os, sys",
        "from pathlib import Path",
        "argv = sys.argv[1:]",
        f"with open({str(log)!r}, 'a', encoding='utf-8') as fh:",
        "    fh.write(json.dumps({'tool': 'codex', 'argv': argv, "
        "'config_dir': os.environ.get('CLAUDE_CONFIG_DIR')}) + '\\n')",
        f"if {fail_on!r} in argv:",
        "    print('the fake refuses this call', file=sys.stderr)",
        "    sys.exit(1)",
        f"state = Path({str(state)!r})",
        "marketplaces = json.loads(state.read_text(encoding='utf-8')) if state.exists() else {}",
        "def refuse(message):",
        "    print(f'Error: {message}', file=sys.stderr)",
        "    sys.exit(1)",
        "if argv[:3] == ['plugin', 'marketplace', 'add']:",
        "    source = argv[3]",
        "    manifest = Path(source) / '.claude-plugin' / 'marketplace.json'",
        "    name = json.loads(manifest.read_text(encoding='utf-8'))['name']",
        "    if marketplaces.get(name, source) != source:",
        "        refuse(f\"marketplace '{name}' is already added from a different source; remove it before adding this source\")",
        "    marketplaces[name] = source",
        "elif argv[:3] == ['plugin', 'marketplace', 'remove']:",
        "    if argv[3] not in marketplaces:",
        "        refuse(f\"marketplace '{argv[3]}' is not added\")",
        "    del marketplaces[argv[3]]",
        "elif argv[:4] == ['plugin', 'marketplace', 'list', '--json']:",
        "    print(json.dumps({'marketplaces': [",
        "        {'name': name, 'root': source, 'marketplaceSource': {'sourceType': 'local', 'source': source}}",
        "        for name, source in marketplaces.items()]}))",
        "elif argv[:2] == ['plugin', 'add']:",
        "    marketplace = argv[2].partition('@')[2]",
        "    if marketplace not in marketplaces:",
        "        refuse(f\"marketplace '{marketplace}' is not added\")",
        "else:",
        "    refuse('the fake codex does not know this command')",
        "state.write_text(json.dumps(marketplaces), encoding='utf-8')",
        ""]))


def write_shim(path: Path, target: str) -> None:
    write_executable(path, f'#!/bin/sh\nexec "{target}" "$@"\n')


def build_bin(bin_dir: Path, tools: ToolsOnPath, log: Path, claude_fails_on: str, codex_state: Path,
              codex_fails_on: str) -> None:
    """Fills bin_dir with the tools the test wants on its PATH. The git and real bd entries run the real programs."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    if tools.git:
        write_shim(bin_dir / "git", real_tool("git"))
    if tools.bd == Bd.STUB:
        write_executable(bin_dir / "bd", "#!/bin/sh\nexit 0\n")
    elif tools.bd == Bd.REAL:
        write_shim(bin_dir / "bd", real_tool("bd"))
    if tools.claude:
        write_recorder(bin_dir / "claude", "claude", log, claude_fails_on)
    if tools.codex:
        write_codex(bin_dir / "codex", log, codex_state, codex_fails_on)


def read_log(log: Path) -> list:
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line]


def script_env(bin_dir: Path, home_dir: Path) -> dict:
    return {"PATH": str(bin_dir), "HOME": str(home_dir), "USERPROFILE": str(home_dir)}


def run_script(repo: Path, script: str, args: list, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(repo / script), *args],
                          capture_output=True, text=True, encoding="utf-8", env=env, cwd=repo)
