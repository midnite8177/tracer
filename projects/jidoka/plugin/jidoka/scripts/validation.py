"""Validation, the stage that takes a finished epic to the acceptance gate, or back to the build.

The scheduler calls it once every task of an epic is closed. It cuts a
detached worktree at .worktrees/validation-<epic> from the epic branch's
head, merges main into it, and runs every command of the repo settings' full
suite there, one after another, whatever an earlier command did. The full
suite leaves out the hand-run tests, which validation never runs. The output
of the commands goes to stderr. A merge that conflicts with main is aborted,
and validation stops with the conflicting files and writes nothing.

Under the merge lock, the one land.py and the merge gate take, validation
then fast-forwards the epic branch to the merged head, so the next pass
builds on main's work, red or green. It refuses while the main checkout has
the epic branch checked out with uncommitted edits, and when the epic branch
moved while the suite ran. With BEADS_ACTOR set to jidoka it records on the
epic `validation.result` (pass or fail), `validation.head` (the commit it
validated), `validation.seconds`, `validation.tests` and `validation.skipped`,
the figures summed over the commands, and posts a comment that gives them for
each command. A command's figures come from its output, as the targeted
tests read it: dotnet test's summary lines and unittest's "Ran N tests" and
"skipped=N". Output in neither shape counts no tests and no skips.

Green ends the pass clean through pass_ledger.py, and puts the epic at the acceptance gate, through gate.py, with
one comment that starts with
"Acceptance gate:" and lists the commits the epic branch holds that main
lacks, the figures, the Tests removed table from the epic's `cleanup.removed`
metadata when a test cleanup removed any test, the review's findings of low confidence from `review.low`, which
were never fixed, and each hand-run group with the command that runs it.
Then it sets the epic's `gate.state` to waiting and adds the human label,
last, so a labeled epic always has its comment.

A red result ends the pass through pass_ledger.py, so the next pass starts
with a test cleanup and a tidy again. Red files one task in the epic, with the failing commands and the end of
their output, the track simple and the area of the first failing command's
app. The scheduler then opens its lap, and the next pass begins.

An epic that holds holdouts is not at the gate when its suite is green. It
sets `validation.holdouts` and `validation.result` to pending and keeps the
validation worktree, and holdouts_run.py takes the epic from there. A red
suite runs no holdouts, because the pass goes back to the build anyway.
"""
from __future__ import annotations

import json
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import gate
import holdouts
import pass_ledger
import private_docs
import targeted_tests
from commands import env_as_factory, head_of, run, run_test_command, set_metadata
from epic_branch import required_head
from epic_reader import VALIDATED_HEAD_KEY
from epic_task import file_task
from epics import HOLDOUTS_PENDING_KEY, PENDING
from pass_support import MAIN_BRANCH, PassError, move_epic_branch, worktree_at
from report_text import tail_of
from worktrees import cut_detached, remove_worktree, stage_worktree
from repo_settings import full_suite_command

WORKTREE_PREFIX = "validation-"
DOTNET_SKIPPED = re.compile(r"[A-Za-z]+!\s+-\s+Failed:\s*\d+,\s*Passed:\s*\d+,\s*Skipped:\s*(\d+),\s*Total:\s*\d+")
UNITTEST_SKIPPED = re.compile(r"^(?:OK|FAILED) \([^)]*\bskipped=(\d+)", re.MULTILINE)
HAND_RUN_FIELDS = ("app", "name", "reason", "command")
UNKNOWN_FIGURES = "no test count in its output"
RESULT_KEY = "validation.result"
RUNS_KEY = "validation.runs"
PASS = "pass"
FAIL = "fail"


class ValidationError(PassError):
    """A reason validation writes nothing more, worded for the person who reads stderr."""


@dataclass(frozen=True)
class SuiteCommand:
    """One command of the full suite, and the app whose tests it runs."""
    app: str
    command: str


@dataclass(frozen=True)
class HandRunGroup:
    """A group of an app's tests that the full suite leaves out, and the command the human runs it with."""
    app: str
    name: str
    reason: str
    command: str


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


@dataclass(frozen=True)
class KeptWorktree:
    """The validation worktree that stays for the run of the epic's holdouts, and how many holdouts the epic has."""
    path: Path
    holdouts: int


@dataclass(frozen=True)
class Validated:
    """What a validation did: the commit it validated, each command's run, the tasks it filed when red, the worktree
    it keeps when the suite is green and the epic holds holdouts, and how many holdouts ended red."""
    head: str
    runs: list[CommandRun]
    filed: list[str]
    kept: KeptWorktree | None
    red_holdouts: int

    @property
    def green(self) -> bool:
        return all(each.passed for each in self.runs)

    @property
    def result(self) -> str:
        if not self.green or self.red_holdouts:
            return FAIL
        return PENDING if self.kept is not None else PASS

    @property
    def headline(self) -> str:
        return {FAIL: "Validation failed.", PASS: "Validation passed.",
                PENDING: "Validation passed the full suite, and its holdouts run next."}[self.result]

    @property
    def tests(self) -> int:
        return sum(each.tests or 0 for each in self.runs)

    @property
    def skipped(self) -> int:
        return sum(each.skipped for each in self.runs)

    @property
    def seconds(self) -> float:
        return round(sum(each.seconds for each in self.runs), 3)

    def fields(self) -> dict:
        return {"result": self.result, "head": self.head, "tests": self.tests, "skipped": self.skipped,
                "seconds": self.seconds, "filed": self.filed[0] if self.filed else None, "filed_all": self.filed}


def suite_commands(settings: dict) -> list[SuiteCommand]:
    """The full-suite command of every app that has a test command, in the order of the repo settings."""
    return [SuiteCommand(str(app["name"]), full_suite_command(app)) for app in settings.get("apps") or []
            if isinstance(app, dict) and app.get("test") is not None]


def hand_run_groups(settings: dict) -> list[HandRunGroup]:
    listed = settings.get("hand_run")
    if not (isinstance(listed, list) and all(isinstance(group, dict) and all(
            isinstance(group.get(key), str) for key in HAND_RUN_FIELDS) for group in listed)):
        raise ValidationError("the repo settings hold no hand_run list of the tests validation leaves out. "
                              "Run /jidoka:onboard again to record it")
    return [HandRunGroup(*(group[key] for key in HAND_RUN_FIELDS)) for group in listed]


def skipped_in(output: str) -> int:
    return sum(int(count) for count in DOTNET_SKIPPED.findall(output) + UNITTEST_SKIPPED.findall(output))


def run_command(suite: SuiteCommand, worktree: Path) -> CommandRun:
    print(f"running: {suite.command}", file=sys.stderr, flush=True)
    started = time.monotonic()
    done = run_test_command(suite.command, worktree)
    seconds = time.monotonic() - started
    output = f"{done.stdout}{done.stderr}"
    sys.stderr.write(output)
    sys.stderr.flush()
    return CommandRun(suite, done.returncode, seconds, targeted_tests.tests_executed(output), skipped_in(output),
                      output)


def worktree_of(epic: str, main_tree: Path) -> Path:
    return stage_worktree(WORKTREE_PREFIX, epic, main_tree)


def merged_worktree(epic: str, epic_head: str, home: Path, main_tree: Path) -> tuple[Path, str]:
    """Cuts the validation worktree from the epic branch's head and merges main into it; returns it and its head."""
    path = worktree_of(epic, main_tree)
    if path.exists():
        run(["git", "worktree", "remove", "--force", str(path)], main_tree, None)
    try:
        cut_detached(path, epic_head, home, main_tree)
    except private_docs.ClashError as error:
        raise ValidationError(str(error)) from error
    try:
        targeted_tests.bring_in_base_branch(MAIN_BRANCH, path, targeted_tests.Integration.MERGE)
    except targeted_tests.MergeConflict as conflict:
        remove_worktree(path, main_tree)
        raise ValidationError(f"merging {MAIN_BRANCH} into the epic branch conflicts in "
                              f"{', '.join(conflict.files)}, so validation ran no tests and wrote nothing. Merge "
                              f"{MAIN_BRANCH} into the epic branch by hand, then run the scheduler again") from conflict
    except targeted_tests.TestRunError as error:
        remove_worktree(path, main_tree)
        raise ValidationError(str(error)) from error
    head = head_of("HEAD", path)
    if head is None:
        remove_worktree(path, main_tree)
        raise ValidationError(f"{path} has no commit after the merge of {MAIN_BRANCH}")
    return path, head


def figures_lines(validated: Validated) -> list[str]:
    return [f"Validation of {validated.head}: {validated.tests} tests, {validated.skipped} skipped, "
            f"{validated.seconds} s.",
            *(f"- {each.suite.app}: {each.suite.command}, {each.figures()}" for each in validated.runs)]


def hand_run_lines(hand_run: list[HandRunGroup]) -> list[str]:
    """The lines that tell the human which tests validation leaves out and how to run each, or no line when none."""
    if not hand_run:
        return []
    lines = ["", "Hand-run tests, which validation never runs. Run each one yourself before you trust the branch:"]
    for group in hand_run:
        lines += [f"- {group.app}, {group.name}: {group.reason}", f"  {group.command}"]
    return lines


def runs_as_text(runs: list[CommandRun]) -> str:
    return json.dumps([{"app": each.suite.app, "command": each.suite.command, "exit_code": each.exit_code,
                        "seconds": each.seconds, "tests": each.tests, "skipped": each.skipped} for each in runs])


def runs_of(value: object) -> list[CommandRun]:
    """The runs a validation recorded on the epic, without their output."""
    try:
        listed = json.loads(value) if isinstance(value, str) else value
        return [CommandRun(SuiteCommand(str(each["app"]), str(each["command"])), int(each["exit_code"]),
                           float(each["seconds"]), None if each["tests"] is None else int(each["tests"]),
                           int(each["skipped"]), "") for each in listed]
    except (ValueError, KeyError, TypeError) as error:
        raise ValidationError(f"the {RUNS_KEY} metadata of the epic cannot be read: {error!r}") from error


def record(epic: str, validated: Validated, main_tree: Path) -> None:
    env = env_as_factory()
    run(["bd", "comment", epic, "\n".join([validated.headline, *figures_lines(validated)])], main_tree, env)
    waiting = set_metadata((HOLDOUTS_PENDING_KEY, PENDING)) if validated.kept is not None else []
    run(["bd", "update", epic, *set_metadata((RESULT_KEY, validated.result), (VALIDATED_HEAD_KEY, validated.head),
                                             ("validation.seconds", validated.seconds),
                                             ("validation.tests", validated.tests),
                                             ("validation.skipped", validated.skipped),
                                             (RUNS_KEY, runs_as_text(validated.runs))), *waiting], main_tree, env)


def reach_the_gate(epic: str, branch: str, validated: Validated, hand_run: list[HandRunGroup],
                   main_tree: Path) -> None:
    pass_ledger.end_clean_pass(epic, main_tree)
    gate.reach_the_gate(epic, branch, validated.head, figures_lines(validated), hand_run_lines(hand_run), main_tree)


def failure_description(failed: list[CommandRun]) -> str:
    sections = ["## What", "",
                f"Validation ran the full suite on the epic branch after it merged {MAIN_BRANCH}, and "
                f"{'this command' if len(failed) == 1 else 'these commands'} failed:"]
    for failure in failed:
        sections += ["", f"`{failure.suite.command}` exited {failure.exit_code}. The end of its output:", "",
                     "```", tail_of(failure.output), "```"]
    sections += ["", "## Demo", "",
                 f"{'The command' if len(failed) == 1 else 'Each command'} above exits 0 on the epic branch.", "",
                 "## Seams", "", "The failing full-suite commands, run as processes from the repo root."]
    return "\n".join(sections)


def file_failure(epic: str, failed: list[CommandRun], main_tree: Path) -> str:
    """Files the task that says what failed, with the track and area the scheduler needs to open its lap."""
    app = failed[0].suite.app
    return file_task(epic, f"Make the {app} full suite pass on the epic branch", failure_description(failed), app,
                     None, main_tree)


def validate(epic: str, branch: str, settings: dict, home: Path, main_tree: Path) -> Validated:
    """Validates the epic branch merged with main, moves the branch there, and records the verdict on the epic.

    An epic with holdouts whose suite is green keeps its worktree and waits for the holdouts to run.
    """
    commands = suite_commands(settings)
    hand_run = hand_run_groups(settings)
    epic_holdouts = holdouts.read(epic, main_tree)
    epic_head = required_head(branch, main_tree, ValidationError)
    worktree, merged_head = merged_worktree(epic, epic_head, home, main_tree)
    try:
        runs = [run_command(suite, worktree) for suite in commands]
        move_epic_branch(branch, epic_head, merged_head, home, main_tree)
    except BaseException:
        remove_worktree(worktree, main_tree)
        raise
    kept = None
    if epic_holdouts and all(each.passed for each in runs):
        worktree_at(worktree, merged_head, home, main_tree)
        kept = KeptWorktree(worktree, len(epic_holdouts))
    else:
        remove_worktree(worktree, main_tree)
    validated = Validated(merged_head, runs, [], kept, 0)
    record(epic, validated, main_tree)
    if kept is not None:
        return validated
    if validated.green:
        reach_the_gate(epic, branch, validated, hand_run, main_tree)
        return validated
    filed = file_failure(epic, [each for each in runs if not each.passed], main_tree)
    pass_ledger.end_pass(epic, main_tree)
    return Validated(merged_head, runs, [filed], None, 0)
