"""Runs the git, bd and test commands that jidoka's scripts call, with failures worded for the person who reads the output."""
from __future__ import annotations

import subprocess
from pathlib import Path

COMMAND_TIMEOUT_SECONDS = 120


class CommandError(Exception):
    """A command that could not start, ran past the timeout, or exited nonzero where success was required."""


def capture(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=COMMAND_TIMEOUT_SECONDS)
    except OSError as error:
        raise CommandError(f"cannot run {args[0]}: {error}") from error
    except subprocess.TimeoutExpired as error:
        raise CommandError(f"{' '.join(args[:3])} did not finish in {COMMAND_TIMEOUT_SECONDS} seconds") from error


def run(args: list[str], cwd: Path) -> str:
    """The command's stdout; a nonzero exit raises CommandError with its stderr."""
    done = capture(args, cwd)
    if done.returncode != 0:
        detail = done.stderr.strip() or done.stdout.strip()
        raise CommandError(f"{' '.join(args[:3])} failed: {detail}")
    return done.stdout


def run_test_command(command: str, cwd: Path) -> subprocess.CompletedProcess:
    """Runs a test command line from the repo settings through the shell.

    It has no timeout, because a test suite can run far longer than any git or bd command.
    """
    try:
        return subprocess.run(command, cwd=cwd, shell=True, capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
    except OSError as error:
        raise CommandError(f"cannot run the tests: {error}") from error
