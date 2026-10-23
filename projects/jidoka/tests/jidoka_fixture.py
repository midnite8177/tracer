"""Builds the throwaway pieces the installer, release and launcher tests run against.

A checkout is a temporary git repo holding copies of install.py, release.py
and plugin/. The claude, codex and bd stand-ins are small executables in a
bin folder that becomes the whole PATH, so a test decides which tools exist.
Each stand-in appends one JSON line per call to a log file.
"""
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
SHIPPED = ["install.py", "release.py"]
STARTING_VERSION = "0.1.0"


class FixtureError(Exception):
    pass


class Bd(Enum):
    NONE = "none"
    FAKE = "fake"
    REAL = "real"


@dataclass(frozen=True)
class ToolsOnPath:
    """Which tools the PATH of a test run holds."""
    git: bool
    bd: Bd
    claude: bool
    codex: bool


ALL_TOOLS = ToolsOnPath(git=True, bd=Bd.FAKE, claude=True, codex=True)
WITHOUT_CODEX = ToolsOnPath(git=True, bd=Bd.FAKE, claude=True, codex=False)


def run(args: list, cwd: Path) -> str:
    done = subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf-8")
    if done.returncode != 0:
        raise FixtureError(f"{' '.join(args)} failed in {cwd}: {done.stderr.strip()}")
    return done.stdout


def git_commit_all(repo: Path, message: str) -> None:
    run(["git", "add", "-A"], repo)
    run(["git", "commit", "-q", "-m", message], repo)


def build_checkout(repo: Path) -> None:
    """Makes a committed git repo that holds copies of the scripts and the plugin folder."""
    repo.mkdir(parents=True, exist_ok=True)
    run(["git", "init", "-q"], repo)
    run(["git", "config", "user.email", "fixture@example.com"], repo)
    run(["git", "config", "user.name", "Fixture"], repo)
    for name in SHIPPED:
        shutil.copy2(PROJECT / name, repo / name)
    shutil.copytree(PROJECT / "plugin", repo / "plugin", symlinks=True)
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


def write_shim(path: Path, target: str) -> None:
    write_executable(path, f'#!/bin/sh\nexec "{target}" "$@"\n')


def build_bin(bin_dir: Path, tools: ToolsOnPath, log: Path, claude_fails_on: str) -> None:
    """Fills bin_dir with the tools the test wants on its PATH. The git and real bd entries run the real programs."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    if tools.git:
        write_shim(bin_dir / "git", real_tool("git"))
    if tools.bd == Bd.FAKE:
        write_executable(bin_dir / "bd", "#!/bin/sh\nexit 0\n")
    elif tools.bd == Bd.REAL:
        write_shim(bin_dir / "bd", real_tool("bd"))
    if tools.claude:
        write_recorder(bin_dir / "claude", "claude", log, claude_fails_on)
    if tools.codex:
        write_recorder(bin_dir / "codex", "codex", log, "")


def read_log(log: Path) -> list:
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line]


def script_env(bin_dir: Path, home_dir: Path) -> dict:
    return {"PATH": str(bin_dir), "HOME": str(home_dir), "USERPROFILE": str(home_dir)}


def run_script(repo: Path, script: str, args: list, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(repo / script), *args],
                          capture_output=True, text=True, encoding="utf-8", env=env, cwd=repo)
