"""Validation, the stage that takes a finished epic to the acceptance gate, or back to the build.

The scheduler calls it through holdouts_run.validate once every task of an epic is closed. It runs every command of
the repo settings' full suite, one after another, whatever an earlier command did, in the validation worktree, where
validation_merge.py has merged main into the epic branch. The full suite leaves out the hand-run tests, which
validation never runs. The output of the commands goes to stderr. It refuses a worktree that holds no finished merge
of main.

Under the merge lock, the one land.py and the merge gate take, validation
then fast-forwards the epic branch to the merged head, so the next pass
builds on main's work, red or green. It refuses while the main checkout has
the epic branch checked out with uncommitted edits, and when the epic branch
moved while the suite ran. With BEADS_ACTOR set to jidoka it records on the
epic `validation.result` (the result its caller gives), `validation.head` (the commit it validated),
`validation.seconds`, `validation.tests` and `validation.skipped`,
the figures summed over the commands, and posts a comment that gives them for
each command. A command's figures come from its output, as the targeted
tests read it: dotnet test's summary lines and unittest's "Ran N tests" and
"skipped=N". Output in neither shape counts no tests and no skips.

validation_specs.py plans the acceptance specs the epic's tasks record before the suite runs, so that a spec of an app
the repo settings cannot run refuses at once. When every command passed, it runs them, side by side on the machine's
free slots, in the same worktree. The epic records `validation.specs`, how many specs ran, and
`validation.spec_seconds`, how long the run took, beside the suite's figures, and the comment gives them in a line of
their own. The specs do not count in `validation.tests`. A suite that fails runs no spec.

A spec run that took longer than the `spec_seconds_limit` of an app with specs in it is over the limit, as
spec_time_limit.py says. The epic records the slowest specs in `validation.slow_specs`, and the comment lists them.
`record` files nothing: its caller, `settle` or holdouts_run.validate, files the design finding that names the app's
protocol driver, or adds the epic's sighting to the open one. An overrun does not fail the validation.

Green ends the pass clean through pass_ledger.py and puts the epic at the acceptance gate through
gate_items.reach_the_gate, which writes the gate comment. Validation owns the hand-run groups line of that comment,
each group with the command that runs it.

A red result ends the pass through pass_ledger.py, so the next pass starts
with a test cleanup and a tidy again. A red suite files one task in the epic, with the failing commands and the end of
their output, the track simple and the area of the first failing command's
app. A red spec files one task in the epic for each failing spec, which names the spec, with the end of its output,
the track simple and the spec's app. The scheduler then opens its lap, and the next pass begins.

A caller that runs more checks after a green suite asks `run_suite` to keep the
validation worktree, and records its own verdict through `record` instead of
settling. holdouts_run.py does that for an epic that holds holdouts, and owns
everything that waiting writes. A red suite is never kept, because the pass
goes back to the build anyway.
"""
from __future__ import annotations

import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import gate_items
import pass_ledger
import spec_time_limit
import targeted_tests
import validation_merge
import validation_specs
from commands import env_as_factory, run, run_test_command
from epic_branch import required_head
from epic_task import NewTask, file_task
from lap_record import SIMPLE_TRACK
from pass_support import MAIN_BRANCH, PassError, move_epic_branch, worktree_at
from report_text import shortened_title, tail_of
from worktrees import remove_worktree
from settings_reader import HandRunGroup, SettingsError, apps_of, stored_hand_run_groups
from recorded_validation import CommandRun, RecordedValidation, SuiteCommand
from spec_time_limit import OverTheLimit
from validation_specs import NO_SPECS, SpecsRun, TimedSpecRun

DOTNET_SKIPPED = re.compile(r"[A-Za-z]+!\s+-\s+Failed:\s*\d+,\s*Passed:\s*\d+,\s*Skipped:\s*(\d+),\s*Total:\s*\d+")
UNITTEST_SKIPPED = re.compile(r"^(?:OK|FAILED) \([^)]*\bskipped=(\d+)", re.MULTILINE)
PASS = "pass"
FAIL = "fail"


class ValidationError(PassError):
    """A reason validation writes nothing more, worded for the person who reads stderr."""


@dataclass(frozen=True)
class Validated:
    """What a validation did: the commit it validated, each command's run, the run of the acceptance specs, the apps
    whose specs ran over their time limit, and the tasks it filed when red. Its result is the suite's and the specs'
    own, pass or fail; a spec run over the limit does not fail it."""
    head: str
    runs: list[CommandRun]
    specs: SpecsRun
    slow: list[OverTheLimit]
    filed: list[str]

    @property
    def green(self) -> bool:
        return all(each.passed for each in self.runs) and self.specs.passed

    @property
    def result(self) -> str:
        return PASS if self.green else FAIL

    @property
    def headline(self) -> str:
        return "Validation passed." if self.green else "Validation failed."

    def recorded(self, result: str) -> RecordedValidation:
        """The record this validation leaves on the epic, with `result` as its result."""
        return RecordedValidation(result, self.head, self.runs, self.specs.figures, self.slow)

    def fields(self) -> dict:
        return self.recorded(self.result).fields(self.filed)


@dataclass(frozen=True)
class SuiteRun:
    """A suite run that is not yet recorded: what it validated, the hand-run groups its gate comment lists, and the
    worktree it kept when asked to and the suite was green."""
    validated: Validated
    hand_run: list[HandRunGroup]
    kept: Path | None


def suite_commands(settings: dict) -> list[SuiteCommand]:
    """The full-suite command of every app that has a test command, in the order of the repo settings."""
    return [SuiteCommand(app.name, command) for app in apps_of(settings)
            if (command := app.full_suite_command) is not None]


def hand_run_groups(settings: dict) -> list[HandRunGroup]:
    """The hand-run groups of the stored settings; raises ValidationError when the settings hold no usable list."""
    try:
        return stored_hand_run_groups(settings)
    except SettingsError as error:
        raise ValidationError(str(error)) from error


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


def hand_run_lines(hand_run: list[HandRunGroup]) -> list[str]:
    """The lines that tell the human which tests validation leaves out and how to run each, or no line when none."""
    if not hand_run:
        return []
    lines = ["", "Hand-run tests, which validation never runs. Run each one yourself before you trust the branch:"]
    for group in hand_run:
        lines += [f"- {group.app}, {group.name}: {group.reason}", f"  {group.command}"]
    return lines


def record(epic: str, recorded: RecordedValidation, headline: str, more_metadata: list[str], main_tree: Path) -> None:
    """Comments the headline and the figures on the epic and records the validation, with `more_metadata` written in
    the same update, which also takes the merge marker off. It files nothing."""
    env = env_as_factory()
    run(["bd", "comment", epic, "\n".join(recorded.comment_lines(headline))], main_tree, env)
    run(["bd", "update", epic, *recorded.metadata(), *more_metadata, *validation_merge.marker_cleared()], main_tree,
        env)


def reach_the_gate(epic: str, branch: str, recorded: RecordedValidation, hand_run: list[HandRunGroup],
                   main_tree: Path) -> None:
    pass_ledger.end_clean_pass(epic, main_tree)
    gate_items.reach_the_gate(epic, branch, recorded.head, recorded.figures_lines(), hand_run_lines(hand_run),
                              main_tree)


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
    task = NewTask(f"Make the {app} full suite pass on the epic branch", failure_description(failed), app,
                   SIMPLE_TRACK)
    return file_task(epic, task, None, env_as_factory(), main_tree)


def spec_failure_description(failed: TimedSpecRun) -> str:
    return "\n".join(["## What", "",
                      f"Validation ran the acceptance spec \"{failed.name}\" of the {failed.app} app on the epic branch "
                      f"after it merged {MAIN_BRANCH}, and it failed. The end of its output:", "",
                      "```", tail_of(failed.output), "```", "",
                      "## Demo", "", f"The spec \"{failed.name}\" passes on the epic branch.", "",
                      "## Seams", "", f"The spec \"{failed.name}\", run alone with the {failed.app} app's spec command "
                      "from the repo root."])


def file_spec_failure(epic: str, failed: TimedSpecRun, main_tree: Path) -> str:
    """Files the task that names the failing spec, with the track and area the scheduler needs to open its lap."""
    task = NewTask(shortened_title(f"Make the spec pass: {failed.name}"), spec_failure_description(failed), failed.app,
                   SIMPLE_TRACK)
    return file_task(epic, task, None, env_as_factory(), main_tree)


def run_suite(epic: str, branch: str, settings: dict, home: Path, main_tree: Path, keep_when_green: bool) -> SuiteRun:
    """Validates the epic branch merged with main, moves the branch there, and records nothing.

    The acceptance specs are planned before the suite, so that settings which cannot run them refuse at once, and run
    after it, only when every command passed. The worktree stays, cut again at the merged head, when `keep_when_green`
    is set and the suite and the specs passed.
    """
    commands = suite_commands(settings)
    hand_run = hand_run_groups(settings)
    spec_jobs = validation_specs.specs_to_run(epic, settings, main_tree)
    epic_head = required_head(branch, main_tree, ValidationError)
    worktree, merged_head = validation_merge.merged_worktree(epic, epic_head, main_tree)
    try:
        runs = [run_command(suite, worktree) for suite in commands]
        spec_run = NO_SPECS
        if all(each.passed for each in runs):
            spec_run = validation_specs.run_all(spec_jobs, epic, worktree, home, main_tree)
        move_epic_branch(branch, epic_head, merged_head, home, main_tree)
    except BaseException:
        remove_worktree(worktree, main_tree)
        raise
    validated = Validated(merged_head, runs, spec_run, spec_time_limit.over_the_limit(settings, spec_run), [])
    if keep_when_green and validated.green:
        worktree_at(worktree, merged_head, home, main_tree)
        return SuiteRun(validated, hand_run, worktree)
    remove_worktree(worktree, main_tree)
    return SuiteRun(validated, hand_run, None)


def settle(epic: str, branch: str, suite: SuiteRun, main_tree: Path) -> Validated:
    """Records the suite's own verdict on the epic, then puts a green epic at the gate and files a task for a red one."""
    validated = suite.validated
    recorded = validated.recorded(validated.result)
    record(epic, recorded, validated.headline, [], main_tree)
    spec_time_limit.file_design_findings(epic, validated.slow, main_tree)
    if validated.green:
        reach_the_gate(epic, branch, recorded, suite.hand_run, main_tree)
        return validated
    failed_commands = [each for each in validated.runs if not each.passed]
    filed = [file_failure(epic, failed_commands, main_tree)] if failed_commands else []
    filed += [file_spec_failure(epic, each, main_tree) for each in validated.specs.failed]
    pass_ledger.end_pass(epic, main_tree)
    return Validated(validated.head, validated.runs, validated.specs, validated.slow, filed)
