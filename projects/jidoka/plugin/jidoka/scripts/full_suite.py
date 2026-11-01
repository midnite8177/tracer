"""Runs the full suite, the one way landing, the gate and validation run it, and reads each command's figures.

The full suite is a list of commands, one for each app that has a test command. `run_commands` runs every command in a
worktree, one after another, whatever an earlier command did, and gives a `CommandRun` for each: how it exited, how long
it took, how many tests and skips its output counts, and the output itself. `run_full_suite` runs them for landing and
the gate, and raises `FullSuiteFailed` naming the commands that failed. A command's figures come from its output, as
the targeted tests read it: dotnet test's summary lines and unittest's "Ran N tests" and "skipped=N". Output in neither
shape counts no tests and no skips. A change to how a suite runs or is read is made here.
"""
from __future__ import annotations

import re
import sys
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from commands import run_finished
from runner_summary import tests_executed
from settings_reader import SuiteCommand

DOTNET_SKIPPED = re.compile(r"[A-Za-z]+!\s+-\s+Failed:\s*\d+,\s*Passed:\s*\d+,\s*Skipped:\s*(\d+),\s*Total:\s*\d+")
UNITTEST_SKIPPED = re.compile(r"^(?:OK|FAILED) \([^)]*\bskipped=(\d+)", re.MULTILINE)
UNKNOWN_FIGURES = "no test count in its output"


@dataclass(frozen=True)
class CommandRun:
    """One run of a full-suite command: how it exited, how long it took, and what its output counted."""
    suite: SuiteCommand
    exit_code: int
    seconds: float
    tests: int | None
    skipped: int
    output: str

    @property
    def passed(self) -> bool:
        return self.exit_code == 0

    def figures(self) -> str:
        if self.tests is None:
            return f"exit code {self.exit_code}, {UNKNOWN_FIGURES}, {self.seconds:.1f} s"
        return f"exit code {self.exit_code}, {self.tests} tests, {self.skipped} skipped, {self.seconds:.1f} s"


class FullSuiteFailed(Exception):
    def __init__(self, failures: list[CommandRun]) -> None:
        super().__init__("the full suite failed on the branch rebased on main, so nothing landed and main is unchanged")
        self.failures = failures


def skipped_in(output: str) -> int:
    return sum(int(count) for count in DOTNET_SKIPPED.findall(output) + UNITTEST_SKIPPED.findall(output))


def run_command(suite: SuiteCommand, worktree: Path, announced_on: TextIO, output_on: TextIO | None) -> CommandRun:
    """Runs one command in the worktree, saying on `announced_on` which command it runs, and copies the command's
    output to `output_on` unless that is None."""
    print(f"running: {suite.command}", file=announced_on, flush=True)
    started = time.monotonic()
    finished = run_finished(suite.command, worktree)
    seconds = time.monotonic() - started
    if output_on is not None:
        output_on.write(finished.output)
        output_on.flush()
    return CommandRun(suite, finished.exit_code, seconds, tests_executed(finished.output),
                      skipped_in(finished.output), finished.output)


def run_commands(commands: Iterable[SuiteCommand], worktree: Path, announced_on: TextIO,
                 output_on: TextIO | None) -> list[CommandRun]:
    """Runs every command in the worktree, whatever an earlier one did, in the order given."""
    return [run_command(suite, worktree, announced_on, output_on) for suite in commands]


def run_full_suite(commands: list[SuiteCommand], worktree: Path) -> None:
    """Runs every command in the worktree, saying on stdout which one runs, and raises FullSuiteFailed naming each one
    that failed."""
    runs = run_commands(commands, worktree, sys.stdout, None)
    failures = [each for each in runs if not each.passed]
    if failures:
        raise FullSuiteFailed(failures)
