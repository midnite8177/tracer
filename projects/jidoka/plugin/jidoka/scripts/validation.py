"""Validation, the stage that takes a finished epic to the acceptance gate, or back to the build.

The scheduler calls it through holdouts_run.validate once every task of an epic is closed. It cuts a
detached worktree at .worktrees/validation-<epic> from the epic branch's
head, merges main into it, and runs every command of the repo settings' full
suite there, one after another, whatever an earlier command did. The full
suite leaves out the hand-run tests, which validation never runs. The output
of the commands goes to stderr. A merge that conflicts with main is aborted: the worktree stays at the epic branch's
head for a merge worker, validation_merge.py decides whether the epic owes one and takes its report, and validation runs
on the merge the worker finished. It refuses a worktree that holds no finished merge of main.

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

Green ends the pass clean through pass_ledger.py and puts the epic at the acceptance gate through
gate_items.reach_the_gate, which writes the gate comment. Validation owns the hand-run groups line of that comment,
each group with the command that runs it.

A red result ends the pass through pass_ledger.py, so the next pass starts
with a test cleanup and a tidy again. Red files one task in the epic, with the failing commands and the end of
their output, the track simple and the area of the first failing command's
app. The scheduler then opens its lap, and the next pass begins.

A caller that runs more checks after a green suite asks `run_suite` to keep the
validation worktree, and records its own verdict through `record` instead of
settling. holdouts_run.py does that for an epic that holds holdouts, and owns
everything that waiting writes. A red suite is never kept, because the pass
goes back to the build anyway.
"""
from __future__ import annotations

import json
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import gate_items
import merge_gate
import pass_ledger
import private_docs
import targeted_tests
from commands import capture, env_as_factory, head_of, run, run_test_command, set_metadata, unset_metadata
from epic_branch import required_head
from epic_reader import VALIDATED_HEAD_KEY
from epic_task import NewTask, file_task
from lap_record import SIMPLE_TRACK
from pass_support import MAIN_BRANCH, PassError, move_epic_branch, worktree_at
from report_text import tail_of
from worktrees import cut_detached, remove_worktree, stage_without_scratch, stage_worktree
from settings_reader import HandRunGroup, SettingsError, apps_of, stored_hand_run_groups

WORKTREE_PREFIX = "validation-"
DOTNET_SKIPPED = re.compile(r"[A-Za-z]+!\s+-\s+Failed:\s*\d+,\s*Passed:\s*\d+,\s*Skipped:\s*(\d+),\s*Total:\s*\d+")
UNITTEST_SKIPPED = re.compile(r"^(?:OK|FAILED) \([^)]*\bskipped=(\d+)", re.MULTILINE)
UNKNOWN_FIGURES = "no test count in its output"
RESULT_KEY = "validation.result"
RUNS_KEY = "validation.runs"
TESTS_KEY = "validation.tests"
SKIPPED_KEY = "validation.skipped"
SECONDS_KEY = "validation.seconds"
MERGE_KEY = "validation.merge"
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
class Validated:
    """What a validation did: the commit it validated, each command's run, and the tasks it filed when red. Its
    result is the suite's own, pass or fail."""
    head: str
    runs: list[CommandRun]
    filed: list[str]

    @property
    def green(self) -> bool:
        return all(each.passed for each in self.runs)

    @property
    def result(self) -> str:
        return PASS if self.green else FAIL

    @property
    def headline(self) -> str:
        return "Validation passed." if self.green else "Validation failed."

    def fields(self) -> dict:
        return fields_of(self.result, self.head, self.runs, self.filed)


@dataclass(frozen=True)
class SuiteRun:
    """A suite run that is not yet recorded: what it validated, the hand-run groups its gate comment lists, and the
    worktree it kept when asked to and the suite was green."""
    validated: Validated
    hand_run: list[HandRunGroup]
    kept: Path | None


def total_tests(runs: list[CommandRun]) -> int:
    return sum(each.tests or 0 for each in runs)


def total_skipped(runs: list[CommandRun]) -> int:
    return sum(each.skipped for each in runs)


def total_seconds(runs: list[CommandRun]) -> float:
    return round(sum(each.seconds for each in runs), 3)


def fields_of(result: str, head: str, runs: list[CommandRun], filed: list[str]) -> dict:
    """The fields the scheduler prints for a validation, whoever settled its result."""
    return {"result": result, "head": head, "tests": total_tests(runs), "skipped": total_skipped(runs),
            "seconds": total_seconds(runs), "filed": filed[0] if filed else None, "filed_all": filed}


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


def worktree_of(epic: str, main_tree: Path) -> Path:
    return stage_worktree(WORKTREE_PREFIX, epic, main_tree)


def is_merging(path: Path) -> bool:
    """True when the worktree is in the middle of a merge, with conflicts to resolve or a merge to commit."""
    return capture(["git", "rev-parse", "--quiet", "--verify", "MERGE_HEAD"], path, None).returncode == 0


def unmerged_files(path: Path) -> list[str]:
    return run(["git", "diff", "--name-only", "--diff-filter=U"], path, None).split()


def back_to(path: Path, head: str) -> None:
    """Puts the validation worktree back at the head with no merge begun and nothing left of a worker's edits, apart
    from the scratch folder."""
    env = env_as_factory()
    capture(["git", "merge", "--abort"], path, env)
    run(["git", "reset", "--quiet", "--hard", head], path, env)
    run(["git", "clean", "--quiet", "--force", "-d"], path, env)


def finished_merge(path: Path, epic_head: str, main_tree: Path) -> bool:
    """True when the validation worktree holds the epic head and main's head with no merge in progress, whether a merge
    worker committed the merge or main was already in the epic branch."""
    if not path.is_dir():
        return False
    head = head_of("HEAD", path)
    base = head_of(f"refs/heads/{MAIN_BRANCH}", main_tree)
    if head is None or base is None or is_merging(path):
        return False
    return merge_gate.contains(epic_head, head, main_tree) and merge_gate.contains(base, head, main_tree)


def fold_into_merge(path: Path, epic_head: str) -> None:
    """Amends the merge commit with whatever a merge worker left outside it, except the scratch folder. The epic head
    itself is never amended."""
    if head_of("HEAD", path) != epic_head and stage_without_scratch(path):
        run(["git", "commit", "--quiet", "--amend", "--no-edit"], path, env_as_factory())


def conflicting_files(path: Path, epic_head: str) -> list[str]:
    """The files that merging main into the epic head conflicts in, found in the validation worktree, which is left at
    the epic head. Empty when the merge goes through."""
    back_to(path, epic_head)
    try:
        targeted_tests.bring_in_base_branch(MAIN_BRANCH, path, targeted_tests.Integration.MERGE)
    except targeted_tests.MergeConflict as conflict:
        return conflict.files
    except targeted_tests.TestRunError:
        return []
    back_to(path, epic_head)
    return []


def merge_main(epic: str, epic_head: str, home: Path, main_tree: Path) -> list[str]:
    """Cuts the validation worktree afresh from the epic head and merges main into it; returns the files that conflict.

    A merge that goes through leaves the worktree at the merge. One that conflicts is aborted, and the worktree stays at
    the epic head with no merge begun, for a merge worker.
    """
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
        worktree_at(path, epic_head, home, main_tree)
        return conflict.files
    except targeted_tests.TestRunError as error:
        remove_worktree(path, main_tree)
        raise ValidationError(str(error)) from error
    if head_of("HEAD", path) is None:
        remove_worktree(path, main_tree)
        raise ValidationError(f"{path} has no commit after the merge of {MAIN_BRANCH}")
    return []


def merged_worktree(epic: str, epic_head: str, main_tree: Path) -> tuple[Path, str]:
    """The validation worktree where main is merged into the epic branch, and its head. Refuses when the worktree holds
    no such merge, which validation_merge.to_run settles before validation runs."""
    path = worktree_of(epic, main_tree)
    head = head_of("HEAD", path) if finished_merge(path, epic_head, main_tree) else None
    if head is None:
        raise ValidationError(f"{path} holds no finished merge of {MAIN_BRANCH} into the epic branch, so {epic} was not "
                              "validated. Run the scheduler again")
    return path, head


def figures_lines(head: str, runs: list[CommandRun]) -> list[str]:
    return [f"Validation of {head}: {total_tests(runs)} tests, {total_skipped(runs)} skipped, "
            f"{total_seconds(runs)} s.",
            *(f"- {each.suite.app}: {each.suite.command}, {each.figures()}" for each in runs)]


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


def record(epic: str, validated: Validated, headline: str, result: str, more_metadata: list[str],
           main_tree: Path) -> None:
    """Comments the headline and the figures on the epic and records the validation, with `result` as its result and
    `more_metadata` written in the same update. A validated merge owes no merge worker, so the update takes the merge
    marker off."""
    env = env_as_factory()
    run(["bd", "comment", epic, "\n".join([headline, *figures_lines(validated.head, validated.runs)])], main_tree, env)
    run(["bd", "update", epic, *set_metadata((RESULT_KEY, result), (VALIDATED_HEAD_KEY, validated.head),
                                             (SECONDS_KEY, total_seconds(validated.runs)),
                                             (TESTS_KEY, total_tests(validated.runs)),
                                             (SKIPPED_KEY, total_skipped(validated.runs)),
                                             (RUNS_KEY, runs_as_text(validated.runs))), *more_metadata,
        *unset_metadata(MERGE_KEY)], main_tree, env)


def reach_the_gate(epic: str, branch: str, head: str, figures: list[str], hand_run: list[HandRunGroup],
                   main_tree: Path) -> None:
    pass_ledger.end_clean_pass(epic, main_tree)
    gate_items.reach_the_gate(epic, branch, head, figures, hand_run_lines(hand_run), main_tree)


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


def run_suite(epic: str, branch: str, settings: dict, home: Path, main_tree: Path, keep_when_green: bool) -> SuiteRun:
    """Validates the epic branch merged with main, moves the branch there, and records nothing.

    The worktree stays, cut again at the merged head, when `keep_when_green` is set and every command passed.
    """
    commands = suite_commands(settings)
    hand_run = hand_run_groups(settings)
    epic_head = required_head(branch, main_tree, ValidationError)
    worktree, merged_head = merged_worktree(epic, epic_head, main_tree)
    try:
        runs = [run_command(suite, worktree) for suite in commands]
        move_epic_branch(branch, epic_head, merged_head, home, main_tree)
    except BaseException:
        remove_worktree(worktree, main_tree)
        raise
    validated = Validated(merged_head, runs, [])
    if keep_when_green and validated.green:
        worktree_at(worktree, merged_head, home, main_tree)
        return SuiteRun(validated, hand_run, worktree)
    remove_worktree(worktree, main_tree)
    return SuiteRun(validated, hand_run, None)


def settle(epic: str, branch: str, suite: SuiteRun, main_tree: Path) -> Validated:
    """Records the suite's own verdict on the epic, then puts a green epic at the gate and files a task for a red one."""
    validated = suite.validated
    record(epic, validated, validated.headline, validated.result, [], main_tree)
    if validated.green:
        reach_the_gate(epic, branch, validated.head, figures_lines(validated.head, validated.runs), suite.hand_run,
                       main_tree)
        return validated
    filed = file_failure(epic, [each for each in validated.runs if not each.passed], main_tree)
    pass_ledger.end_pass(epic, main_tree)
    return Validated(validated.head, validated.runs, [filed])
