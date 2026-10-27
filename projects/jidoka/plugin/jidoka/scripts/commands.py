"""Runs the git, bd and test commands that jidoka's scripts call, with failures worded for the person who reads the output."""
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

COMMAND_TIMEOUT_SECONDS = 120


class CommandError(Exception):
    """A command that could not start, ran past the timeout, or exited nonzero where success was required."""


@dataclass(frozen=True)
class Worktree:
    """A worktree of the repo: its path as git prints it, and its branch, or an empty string when it has none."""
    path: Path
    branch: str


def capture(args: list[str], cwd: Path, env: dict[str, str] | None) -> subprocess.CompletedProcess:
    """Runs the command in env, or in the inherited environment when env is None."""
    try:
        return subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=COMMAND_TIMEOUT_SECONDS)
    except OSError as error:
        raise CommandError(f"cannot run {args[0]}: {error}") from error
    except subprocess.TimeoutExpired as error:
        raise CommandError(f"{' '.join(args[:3])} did not finish in {COMMAND_TIMEOUT_SECONDS} seconds") from error


def run(args: list[str], cwd: Path, env: dict[str, str] | None) -> str:
    """The command's stdout, run in env, or in the inherited environment when env is None.

    A nonzero exit raises CommandError with its stderr.
    """
    done = capture(args, cwd, env)
    if done.returncode != 0:
        detail = done.stderr.strip() or done.stdout.strip()
        raise CommandError(f"{' '.join(args[:3])} failed: {detail}")
    return done.stdout


def env_as_git_user(main_tree: Path) -> dict[str, str]:
    """The environment bd runs in, with BEADS_ACTOR set to the repo's git user.name."""
    name = capture(["git", "config", "user.name"], main_tree, None).stdout.strip()
    if not name:
        raise CommandError(f"git config user.name is not set in {main_tree}, and jidoka writes to the beads "
                           "under that name. Set it with git config user.name \"<your name>\"")
    return {**os.environ, "BEADS_ACTOR": name}


def head_of(ref: str, cwd: Path) -> str | None:
    """The sha of the commit the ref names, or None when it names no commit."""
    done = capture(["git", "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"], cwd, None)
    return done.stdout.strip() if done.returncode == 0 else None


def worktree_list(cwd: Path) -> list[Worktree]:
    """Every worktree of the repo that cwd is in, the main checkout first."""
    listing = run(["git", "worktree", "list", "--porcelain"], cwd, None)
    found: list[Worktree] = []
    for line in listing.splitlines():
        if line.startswith("worktree "):
            found.append(Worktree(Path(line[len("worktree "):]), ""))
        elif line.startswith("branch refs/heads/") and found:
            found[-1] = Worktree(found[-1].path, line[len("branch refs/heads/"):])
    return found


def bd_show(bead: str, cwd: Path) -> dict | None:
    """The bead as bd show --json prints it, or None when the output holds no bead."""
    output = run(["bd", "show", bead, "--json"], cwd, None)
    try:
        parsed = json.loads(output)
    except ValueError:
        return None
    if not isinstance(parsed, list) or not parsed or not isinstance(parsed[0], dict):
        return None
    return parsed[0]


def run_test_command(command: str, cwd: Path) -> subprocess.CompletedProcess:
    """Runs a test command line from the repo settings through the shell.

    It has no timeout, because a test suite can run far longer than any git or bd command.
    """
    try:
        return subprocess.run(command, cwd=cwd, shell=True, capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
    except OSError as error:
        raise CommandError(f"cannot run the tests: {error}") from error
