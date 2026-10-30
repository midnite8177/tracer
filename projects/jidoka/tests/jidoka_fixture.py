"""Builds the throwaway pieces the installer, release and launcher tests run against.

A checkout is a temporary git repo holding copies of install.py, release.py
and plugin/. The claude, codex and bd stand-ins are small executables in a
bin folder that becomes the whole PATH, so a test decides which tools exist.
The claude, codex and dotnet stand-ins append one JSON line per call to a log file.
On Windows each stand-in is a .exe launcher with its script packed behind it, because only a .exe starts by name there.

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
import io
import json
import os
import platform
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from importlib.util import find_spec
from pathlib import Path, PurePath

import fake_bd
import windows_file_holders
from run_suite import SHARED_FOLDER

WINDOWS = os.name == "nt"
PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "plugin" / "jidoka" / "scripts"))
import processes  # noqa: E402
import windows_processes  # noqa: E402
SHIPPED = ["install.py", "release.py"]
STARTING_VERSION = "0.1.0"
TEMPLATE_WAIT_SECONDS = 300
TEMPLATE_POLL_SECONDS = 0.2
REMOVAL_WAIT_SECONDS = 10
REMOVAL_POLL_SECONDS = 0.2


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


def make_writable_and_retry(function, path: str, error: BaseException) -> None:
    """Handles a failed removal of one path by opening the path and its folder for writing, then trying once more.

    Git writes its object files read-only, and a read-only file or a read-only folder keeps its parent from
    removing it on Windows (WinError 5) and for a read-only folder elsewhere.
    """
    if not isinstance(error, PermissionError):
        raise error
    parent = Path(path).parent
    if parent.is_dir():
        parent.chmod(0o700)
    if Path(path).is_dir():
        Path(path).chmod(0o700)
    else:
        Path(path).chmod(stat.S_IWRITE | stat.S_IREAD)
    function(path)


def remove_tree(folder: Path) -> None:
    """Removes the folder and everything in it, git's read-only object files included.

    A process that is ending can still hold a file for a moment (WinError 32 on Windows), so a removal that
    is refused is tried again until REMOVAL_WAIT_SECONDS pass. A folder that is not there is left alone.
    """
    deadline = time.monotonic() + REMOVAL_WAIT_SECONDS
    while True:
        try:
            if sys.version_info >= (3, 12):
                shutil.rmtree(folder, onexc=make_writable_and_retry)
            else:
                shutil.rmtree(folder, onerror=lambda function, path, info: make_writable_and_retry(function, path, info[1]))
            return
        except FileNotFoundError:
            return
        except PermissionError:
            if time.monotonic() > deadline:
                raise
            time.sleep(REMOVAL_POLL_SECONDS)


def remove_tree_quietly(folder: Path) -> None:
    """Removes the folder as remove_tree does, for a process that is ending and has nobody to tell when it cannot."""
    try:
        remove_tree(folder)
    except OSError:
        pass


def is_real_bd(program: str) -> bool:
    """True when the program is the bd the machine's PATH finds, named bare or by the path that finds.

    A fake bd that a test names by its own path is not it, and keeps the home the test gives it.
    """
    found = shutil.which("bd")
    return program == "bd" or (found is not None and program == found)


@functools.cache
def bd_home() -> Path:
    """A folder for bd to treat as the user's home, removed when the process ends.

    On Windows the environment has USERPROFILE and no HOME, so bd takes ~ literally and writes
    ~/.config/bd/config.yaml inside the repo it runs in. With a HOME and a USERPROFILE of their own, bd
    writes its config there, and never touches the user's own.
    """
    folder = Path(tempfile.mkdtemp(prefix="jidoka-bd-home-"))
    atexit.register(remove_tree_quietly, folder)
    return folder


def home_variables(home: Path | str) -> dict:
    """HOME and USERPROFILE, both naming home. Windows programs read the second and the others the first."""
    return {"HOME": str(home), "USERPROFILE": str(home)}


def bd_environment(environ: dict) -> dict:
    """The environment with HOME and USERPROFILE both set to the home that bd runs in."""
    return {**environ, **home_variables(bd_home())}


def environment_for(program: str, environ: dict) -> dict:
    """The environment the program runs in, which is the bd home for the real bd and environ as given for any other program."""
    return bd_environment(environ) if is_real_bd(program) else environ


def run(args: list, cwd: Path) -> str:
    return run_with_env(args, cwd, environment_for(args[0], os.environ.copy()))


def run_with_env(args: list, cwd: Path, env: dict) -> str:
    """Runs the program with exactly the environment env holds, and returns its output."""
    done = subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf-8", env=env)
    if done.returncode != 0:
        raise FixtureError(f"{' '.join(args)} failed in {cwd}: {done.stderr.strip()}")
    return done.stdout


def git_commit_all(repo: Path, message: str) -> None:
    run(["git", "add", "-A"], repo)
    run(["git", "commit", "-q", "-m", message], repo)


def init_repo(repo: Path) -> None:
    """Makes an empty git repo that can commit.

    A commit starts git's automatic maintenance as a detached process, which can still be writing
    into .git when a test removes the repo's folder, so the repo turns that maintenance off.
    """
    repo.mkdir(parents=True, exist_ok=True)
    run(["git", "init", "-q"], repo)
    run(["git", "config", "maintenance.auto", "false"], repo)
    run(["git", "config", "gc.auto", "0"], repo)
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
    let_bd_go_of(repo)
    exclude_after = exclude.read_text(encoding="utf-8")
    if not exclude_after.startswith(exclude_before):
        raise FixtureError(f"bd init rewrote {exclude} instead of adding to it")
    added_config = [line.split("=", 1) for line in run(["git", "config", "--local", "--list"], repo).splitlines()
                    if line not in config_before]
    shutil.move(repo / ".beads", template / "beads")
    (template / "exclude").write_text(exclude_after[len(exclude_before):], encoding="utf-8")
    (template / "config.json").write_text(json.dumps(added_config), encoding="utf-8")
    remove_tree(repo)


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
        atexit.register(remove_tree_quietly, Path(shared))
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
    let_bd_go_of(repo)
    committed = run(["git", "ls-files"], repo).splitlines()
    others = [path for path in committed if not path.startswith(".beads/")]
    if not others or run(["git", "status", "--porcelain"], repo):
        raise FixtureError(f"bd init in {repo} did not commit its files and leave a clean status")
    shutil.move(repo / ".beads", template / "beads")
    for path in others:
        (template / "files" / path).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(repo / path, template / "files" / path)
    remove_tree(repo)


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
    return write_forwarder(bin_dir / "bd", [sys.executable, str(Path(fake_bd.__file__).resolve())])


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


def link_target(link: Path) -> Path:
    """What the symbolic link points at. Windows prints an absolute target with a \\\\?\\ prefix, which this drops."""
    return Path(os.readlink(link).removeprefix("\\\\?\\"))


def beads_in_or_above(folder: Path, top: Path) -> bool:
    """True when the folder, or a folder above it up to and including top, holds a .beads."""
    for candidate in [folder, *folder.parents]:
        if (candidate / ".beads").is_dir():
            return True
        if candidate == top:
            return False
    return False


def folder_without_beads_above(parents: list, top: Path) -> Path:
    """A new empty folder under the first of parents that holds no .beads itself and has none in any folder above it
    up to and including top.

    The session_start hook looks for .beads from a folder up to the top of its repo, and a folder outside any repo
    has no top, so it looks to the drive root. A .beads in the user's home or in the temporary folder, as a Windows
    account that uses beads has, would make a folder that is not a repo look like a beads repo. The hook looks to the
    drive root, so a caller that wants a folder outside beads passes the drive root as top.
    """
    for parent in parents:
        if beads_in_or_above(parent, top):
            continue
        try:
            return Path(tempfile.mkdtemp(dir=parent))
        except OSError:
            continue
    raise FixtureError("no folder to build a non-repo folder in is free of a .beads above it")


def commit_count(repo: Path) -> int:
    return int(run(["git", "rev-list", "--count", "HEAD"], repo).strip())


SLEEP_FOR_AN_HOUR = "import time; time.sleep(3600)"


def process_is_running(pid: int) -> bool:
    """True while the process exists and is no zombie, which no longer runs anything."""
    if WINDOWS:
        done = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH", "/FO", "CSV"], capture_output=True,
                              text=True)
        return f'"{pid}"' in done.stdout
    done = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True)
    state = done.stdout.strip()
    return state != "" and not state.startswith("Z")


def end_process(pid: int) -> None:
    """Ends the process and the processes it started, and does nothing when it is gone."""
    if WINDOWS:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
    else:
        subprocess.run(["kill", "-9", str(pid)], capture_output=True)


def end_orphans_in(folder: Path) -> None:
    """Ends each orphan process whose working folder is the folder or one under it, and this process is left alone."""
    for pid in processes.orphans_in(folder, os.getpid()):
        end_process(pid)


def comparable(path: Path) -> str:
    """The path in the form two paths to one folder share: resolved, so a short 8.3 name and a link give the long
    real name, and in the letter case the platform compares by."""
    try:
        return os.path.normcase(str(path.resolve()))
    except OSError:
        return os.path.normcase(str(path))


def is_inside(folder: Path | None, root: str) -> bool:
    """True when the folder is the comparable root or a folder under it."""
    if folder is None:
        return False
    here = comparable(folder)
    return here == root or here.startswith(root.rstrip(os.sep) + os.sep)


def own_lineage() -> set[int]:
    """The id of this process and of every process above it, which a test must never end."""
    if WINDOWS:
        table = windows_processes.process_table()

        def parent_of(pid: int) -> int | None:
            return table[pid].parent if pid in table else None
    else:
        parent_of = processes.parent_of
    lineage: set[int] = set()
    pid: int | None = os.getpid()
    while pid is not None and pid > 0 and pid not in lineage:
        lineage.add(pid)
        pid = parent_of(pid)
    return lineage


def holders_in(folder: Path, spared: set[int]) -> list[int]:
    """The processes, other than the spared ones, whose working folder is the folder or a folder under it, and on
    Windows also those that hold a file open under it.

    A process counts whether or not its parent still runs; processes.orphans_in finds only an orphan. bd can leave
    a database server that works elsewhere and still holds files in the folder, which on Windows keeps the folder
    from being removed.
    """
    if WINDOWS:
        root = comparable(folder)
        in_folder = {pid for pid in windows_processes.process_table()
                     if pid not in spared and is_inside(windows_processes.current_folder_of(pid), root)}
        found = in_folder | windows_file_holders.holders_under(folder)
    else:
        found = set(processes.pids_with_cwd_in(folder))
    return sorted(found - spared)


def let_bd_go_of(folder: Path) -> None:
    """Ends each process that runs in the folder or holds a file open in it, except this process and the ones above it.

    On Windows a process that runs in a folder or holds a file in it keeps the folder from being removed, and bd
    leaves some running: its database server, and processes whose parent ended or still runs.
    """
    for pid in holders_in(folder, own_lineage()):
        end_process(pid)


def remove_bd_folder(folder: Path) -> None:
    """Ends the processes that run in a folder real bd ran in, then removes the folder and everything in it."""
    let_bd_go_of(folder)
    remove_tree(folder)


def bd_folder(add_cleanup: Callable[..., object]) -> Path:
    """A new temporary folder for a test that runs real bd in it, which add_cleanup (a test's addCleanup, or a
    class's addClassCleanup) removes through remove_bd_folder when the test ends."""
    folder = Path(tempfile.mkdtemp())
    add_cleanup(remove_bd_folder, folder)
    return folder


def real_tool(name: str) -> str:
    found = shutil.which(name)
    if found is None:
        raise FixtureError(f"{name} must be installed to run these tests")
    return found


def executable_file(path: Path, windows: bool) -> Path:
    """The file an executable called path is stored in. Windows starts a program by name only from a .exe."""
    return path.with_name(path.name + ".exe") if windows else path


def system_variables(environ: dict, windows: bool) -> dict:
    """The variables of environ that a Python started with a bare environment needs on Windows, and none elsewhere.

    Python there cannot seed its hash randomization without SystemRoot, and its temporary files go to TEMP or TMP.
    """
    if not windows:
        return {}
    wanted = {"SYSTEMROOT", "TEMP", "TMP"}
    return {name: value for name, value in environ.items() if name.upper() in wanted}


def launcher_exe() -> bytes:
    """The console launcher that pip ships for the console scripts it installs on Windows."""
    spec = find_spec("pip")
    if spec is None or spec.origin is None:
        raise FixtureError("pip must be installed to build the fake executables of a Windows test run")
    bits = 64 if sys.maxsize > 2 ** 32 else 32
    arm = "-arm" if bits == 64 and platform.machine().lower() == "arm64" else ""
    launcher = Path(spec.origin).parent / "_vendor" / "distlib" / f"t{bits}{arm}.exe"
    if not launcher.is_file():
        raise FixtureError(f"pip has no launcher at {launcher}")
    return launcher.read_bytes()


def pack_launcher(launcher: bytes, interpreter: str, script: str) -> bytes:
    """A launcher exe with a shebang line and a zip of the script behind it, in the layout pip gives its own scripts.

    The launcher starts the interpreter named on the shebang line with its own path as the script, and Python
    runs the __main__.py of the zip it finds behind the launcher.
    """
    shebang = f'"{interpreter}"' if " " in interpreter else interpreter
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as packed:
        packed.writestr("__main__.py", script.encode("utf-8"))
    return launcher + b"#!" + shebang.encode("utf-8") + b"\n" + archive.getvalue()


def shell_script_main(shell: str) -> str:
    """The Python script that runs the .sh file beside its launcher with the shell and the launcher's arguments."""
    return "\n".join([
        "import subprocess, sys",
        "from pathlib import Path",
        f"sys.exit(subprocess.call([{shell!r}, str(Path(sys.argv[0]).with_suffix('.sh')), *sys.argv[1:]]))",
        ""])


def real_shell() -> str:
    """The sh of the machine. It is the first one on the PATH, else the one Git for Windows keeps beside its git."""
    found = shutil.which("sh")
    if found is not None:
        return found
    beside_git = Path(real_tool("git")).resolve().parent.parent / "usr" / "bin" / "sh.exe"
    if beside_git.is_file():
        return str(beside_git)
    raise FixtureError("sh must be installed to run these tests")


def write_executable(path: Path, text: str) -> Path:
    """Writes a program that starts the way its first line says, and returns the file it is stored in.

    On Windows a program cannot start from a shebang line, so the file is a launcher exe. A Python script runs
    behind it, and a shell script runs through the sh of Git for Windows from a .sh file beside it.
    """
    stored = executable_file(path, WINDOWS)
    if not WINDOWS:
        stored.write_text(text, encoding="utf-8", newline="\n")
        stored.chmod(0o755)
        return stored
    first, _, body = text.partition("\n")
    if not first.startswith("#!"):
        raise FixtureError(f"{path} must start with a shebang line")
    if first[2:].strip() == sys.executable:
        script = body
    else:
        stored.with_suffix(".sh").write_text(text, encoding="utf-8", newline="\n")
        script = shell_script_main(real_shell())
    stored.write_bytes(pack_launcher(launcher_exe(), sys.executable, script))
    return stored


def write_forwarder(path: Path, command: list) -> Path:
    """Writes a program that runs command with its own arguments after the command's, and returns its file."""
    if not WINDOWS:
        words = " ".join(f'"{word}"' for word in command)
        return write_executable(path, f"#!/bin/sh\nexec {words} \"$@\"\n")
    return write_executable(path, "\n".join([
        f"#!{sys.executable}",
        "import subprocess, sys",
        f"sys.exit(subprocess.call([*{command!r}, *sys.argv[1:]]))",
        ""]))


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


def write_dotnet(path: Path, log: Path) -> None:
    """Writes a dotnet that logs its arguments, its folder and JIDOKA_HOME.

    `publish <project> ... --output <folder>` writes JidokaUi.Web.dll into the folder, with a copy of the project file
    beside it. `<app> --port <port>` prints a line and answers HTTP on that port of the loopback until it is killed,
    as a published jidoka-ui does.
    """
    write_executable(path, "\n".join([
        f"#!{sys.executable}",
        "import http.server, json, os, shutil, sys",
        "from pathlib import Path",
        "argv = sys.argv[1:]",
        f"with open({str(log)!r}, 'a', encoding='utf-8') as fh:",
        "    fh.write(json.dumps({'tool': 'dotnet', 'argv': argv, 'cwd': os.getcwd(), "
        "'jidoka_home': os.environ.get('JIDOKA_HOME')}) + '\\n')",
        "if argv[:1] == ['publish']:",
        "    output = Path(argv[argv.index('--output') + 1])",
        "    output.mkdir(parents=True, exist_ok=True)",
        "    (output / 'JidokaUi.Web.dll').write_text('published\\n', encoding='utf-8')",
        "    shutil.copy(argv[1], output / Path(argv[1]).name)",
        "    sys.exit(0)",
        "port = int(argv[argv.index('--port') + 1])",
        "class Answer(http.server.BaseHTTPRequestHandler):",
        "    def do_GET(self):",
        "        self.send_response(200)",
        "        self.end_headers()",
        "        self.wfile.write(b'jidoka-ui\\n')",
        "    def log_message(self, format, *args):",
        "        pass",
        "server = http.server.HTTPServer(('127.0.0.1', port), Answer)",
        "print('listening', flush=True)",
        "server.serve_forever()",
        ""]))


def write_shim(path: Path, target: str) -> None:
    write_forwarder(path, [target])


def write_stub(path: Path) -> None:
    """Writes a program that exits 0 whatever it is asked."""
    if WINDOWS:
        write_executable(path, f"#!{sys.executable}\nimport sys\nsys.exit(0)\n")
    else:
        write_executable(path, "#!/bin/sh\nexit 0\n")


def build_bin(bin_dir: Path, tools: ToolsOnPath, log: Path, claude_fails_on: str, codex_state: Path,
              codex_fails_on: str) -> None:
    """Fills bin_dir with the tools the test wants on its PATH. The git and real bd entries run the real programs."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    if tools.git:
        write_shim(bin_dir / "git", real_tool("git"))
    if tools.bd == Bd.STUB:
        write_stub(bin_dir / "bd")
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


def git_bash() -> str:
    """The bash.exe that Git for Windows keeps beside its sh.exe."""
    return str(Path(real_shell()).with_name("bash.exe"))


def git_bash_variable(windows: bool) -> dict:
    """The variable that tells the installer where Git Bash is on Windows, where the git on a test's PATH is a fake
    that has no Git Bash beside it, and nothing elsewhere."""
    if not windows:
        return {}
    return {"CLAUDE_CODE_GIT_BASH_PATH": git_bash()}


def bash_script(launcher: PurePath, arguments: list) -> str:
    """The text of a script that runs the launcher under the bash that reads it, each word single-quoted for the shell.

    bash.exe does not read the backslash escapes in the command line that Python writes, so an argument that holds a
    double quote loses it. The arguments travel in a file, where the shell's own quoting holds.
    """
    words = " ".join(shlex.quote(str(word)) for word in [launcher.as_posix(), *arguments])
    return f'exec "$BASH" {words}\n'


@functools.cache
def launch_folder() -> Path:
    """The folder that holds the scripts bash_command writes, removed when the process ends."""
    folder = tempfile.mkdtemp(prefix="jidoka-launch-")
    atexit.register(remove_tree_quietly, Path(folder))
    return Path(folder)


def bash_command(bash: str, launcher: PurePath, arguments: list) -> list:
    """The command that runs the launcher through bash with every argument as it was given. Bash reads a script
    file, by a path with forward slashes, that holds the launcher and the arguments."""
    handle, name = tempfile.mkstemp(suffix=".sh", dir=launch_folder())
    with os.fdopen(handle, "wb") as written:
        written.write(bash_script(launcher, arguments).encode("utf-8"))
    return [bash, Path(name).as_posix()]


def launch_command(launcher: Path, arguments: list) -> list:
    """The command that starts the jidoka-run launcher with arguments: through Git Bash on Windows, where a shell
    script cannot start by itself, and as the file itself elsewhere."""
    if WINDOWS:
        return bash_command(git_bash(), launcher, arguments)
    return [str(launcher), *arguments]


def run_launcher(launcher: Path, arguments: list, stdin: str | None, env: dict, cwd: Path | None,
                 timeout: float | None) -> subprocess.CompletedProcess:
    """Runs the jidoka-run launcher with arguments to the end and returns its result, output decoded as UTF-8. The
    stdin text, when there is some, is what the launcher reads."""
    return subprocess.run(launch_command(launcher, arguments), input=stdin, capture_output=True, text=True,
                          encoding="utf-8", timeout=timeout, env=env, cwd=cwd)


def script_env(bin_dir: Path, home_dir: Path) -> dict:
    return {"PATH": str(bin_dir), **home_variables(home_dir),
            **system_variables(os.environ, WINDOWS), **git_bash_variable(WINDOWS)}


def run_script(repo: Path, script: str, args: list, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(repo / script), *args],
                          capture_output=True, text=True, encoding="utf-8", env=env, cwd=repo)
