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

Green puts the epic at the acceptance gate with one comment that starts with
"Acceptance gate:" and lists the commits the epic branch holds that main
lacks, the figures, and each hand-run group with the command that runs it.
Then it sets the epic's `gate.state` to waiting and adds the human label,
last, so a labeled epic always has its comment.

Red files one task in the epic, with the failing commands and the end of
their output, the track simple and the area of the first failing command's
app. The scheduler then opens its lap, and the next pass begins.
"""
from __future__ import annotations

import json
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import park
import private_docs
import targeted_tests
from bench import WORKTREE_FOLDER, hide_worktrees
from commands import capture, env_as_factory, head_of, run, run_test_command
from handoff import TRACK
from land import acquire_lock, edited_paths, merge_lock, release_lock
from merge_gate import checked_out_branch
from repo_settings import full_suite_command

GATE_STATE_KEY = "gate.state"
WAITING = "waiting"
HUMAN_LABEL = park.HUMAN_LABEL
GATE_COMMENT_HEADING = "Acceptance gate:"
WORKTREE_PREFIX = "validation-"
MAIN_BRANCH = "main"
OUTPUT_TAIL_LINES = 40
DOTNET_SKIPPED = re.compile(r"[A-Za-z]+!\s+-\s+Failed:\s*\d+,\s*Passed:\s*\d+,\s*Skipped:\s*(\d+),\s*Total:\s*\d+")
UNITTEST_SKIPPED = re.compile(r"^(?:OK|FAILED) \([^)]*\bskipped=(\d+)", re.MULTILINE)
HAND_RUN_FIELDS = ("app", "name", "reason", "command")
UNKNOWN_FIGURES = "no test count in its output"


class ValidationError(Exception):
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
class Validated:
    """What a validation did: the commit it validated, each command's run, and the task it filed when red."""
    head: str
    runs: list[CommandRun]
    filed: str | None

    @property
    def green(self) -> bool:
        return all(each.passed for each in self.runs)

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
        return {"result": "pass" if self.green else "fail", "head": self.head, "tests": self.tests,
                "skipped": self.skipped, "seconds": self.seconds, "filed": self.filed}


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


def merged_worktree(epic: str, epic_head: str, home: Path, main_tree: Path) -> tuple[Path, str]:
    """Cuts the validation worktree from the epic branch's head and merges main into it; returns it and its head."""
    path = main_tree / WORKTREE_FOLDER / f"{WORKTREE_PREFIX}{epic}"
    if path.exists():
        run(["git", "worktree", "remove", "--force", str(path)], main_tree, None)
    hide_worktrees(main_tree)
    run(["git", "worktree", "add", "-q", "--detach", str(path), epic_head], main_tree, None)
    try:
        private_docs.share(main_tree, path.resolve(), home)
        targeted_tests.bring_in_base_branch(MAIN_BRANCH, path, targeted_tests.Integration.MERGE)
    except targeted_tests.MergeConflict as conflict:
        remove_worktree(path, main_tree)
        raise ValidationError(f"merging {MAIN_BRANCH} into the epic branch conflicts in "
                              f"{', '.join(conflict.files)}, so validation ran no tests and wrote nothing. Merge "
                              f"{MAIN_BRANCH} into the epic branch by hand, then run the scheduler again") from conflict
    except (targeted_tests.TestRunError, private_docs.ClashError) as error:
        remove_worktree(path, main_tree)
        raise ValidationError(str(error)) from error
    head = head_of("HEAD", path)
    if head is None:
        remove_worktree(path, main_tree)
        raise ValidationError(f"{path} has no commit after the merge of {MAIN_BRANCH}")
    return path, head


def remove_worktree(path: Path, main_tree: Path) -> None:
    capture(["git", "worktree", "remove", "--force", str(path)], main_tree, None)


def move_epic_branch(branch: str, old: str, new: str, home: Path, main_tree: Path) -> None:
    """Fast-forwards the epic branch from old to new under the merge lock, bringing the main checkout along."""
    if old == new:
        return
    lock = merge_lock(home)
    acquire_lock(lock)
    try:
        checked_out = checked_out_branch(main_tree) == branch
        if checked_out:
            edited = sorted(edited_paths(main_tree))
            if edited:
                raise ValidationError(f"the main checkout {main_tree} has {branch} checked out with uncommitted "
                                      f"edits: {', '.join(edited)}. Commit or discard them, then run the "
                                      "scheduler again")
        done = capture(["git", "update-ref", f"refs/heads/{branch}", new, old], main_tree, None)
        if done.returncode != 0:
            raise ValidationError(f"{branch} moved from {old} while the suite ran, so validation changed "
                                  f"nothing. Run the scheduler again: {done.stderr.strip()}")
        if checked_out:
            run(["git", "read-tree", "-m", "-u", old, new], main_tree, None)
    finally:
        release_lock(lock)


def merged_commits(branch_head: str, main_tree: Path) -> list[str]:
    """One line for each commit the epic branch holds that main lacks, merge commits left out, oldest first."""
    listed = run(["git", "log", "--no-merges", "--reverse", "--format=%h %s", f"{MAIN_BRANCH}..{branch_head}"],
                 main_tree, None)
    return listed.splitlines()


def figures_lines(validated: Validated) -> list[str]:
    return [f"Validation of {validated.head}: {validated.tests} tests, {validated.skipped} skipped, "
            f"{validated.seconds} s.",
            *(f"- {each.suite.app}: {each.suite.command}, {each.figures()}" for each in validated.runs)]


def gate_comment(epic: str, branch: str, validated: Validated, hand_run: list[HandRunGroup],
                 main_tree: Path) -> str:
    commits = merged_commits(validated.head, main_tree)
    lines = [f"{GATE_COMMENT_HEADING} {epic} waits for the human, on the epic branch {branch} at {validated.head}.",
             "", "Merged into the epic branch:", *(f"- {commit}" for commit in commits), "",
             *figures_lines(validated)]
    if hand_run:
        lines += ["", "Hand-run tests, which validation never runs. Run each one yourself before you trust the "
                      "branch:"]
        for group in hand_run:
            lines += [f"- {group.app}, {group.name}: {group.reason}", f"  {group.command}"]
    return "\n".join(lines)


def record(epic: str, validated: Validated, main_tree: Path) -> None:
    env = env_as_factory()
    run(["bd", "comment", epic, "\n".join([f"Validation {'passed' if validated.green else 'failed'}.",
                                           *figures_lines(validated)])], main_tree, env)
    run(["bd", "update", epic, "--set-metadata", f"validation.result={'pass' if validated.green else 'fail'}",
         "--set-metadata", f"validation.head={validated.head}",
         "--set-metadata", f"validation.seconds={validated.seconds}",
         "--set-metadata", f"validation.tests={validated.tests}",
         "--set-metadata", f"validation.skipped={validated.skipped}"], main_tree, env)


def reach_the_gate(epic: str, branch: str, validated: Validated, hand_run: list[HandRunGroup],
                   main_tree: Path) -> None:
    env = env_as_factory()
    run(["bd", "comment", epic, gate_comment(epic, branch, validated, hand_run, main_tree)], main_tree, env)
    run(["bd", "update", epic, "--set-metadata", f"{GATE_STATE_KEY}={WAITING}", f"--add-label={HUMAN_LABEL}"],
        main_tree, env)


def tail_of(output: str) -> str:
    return "\n".join(output.strip().splitlines()[-OUTPUT_TAIL_LINES:])


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
    env = env_as_factory()
    app = failed[0].suite.app
    created = run(["bd", "create", "--title", f"Make the {app} full suite pass on the epic branch",
                   "--type", "task", "--parent", epic, "--description", failure_description(failed), "--json"],
                  main_tree, env)
    try:
        task = str(json.loads(created)["id"])
    except (ValueError, KeyError, TypeError) as error:
        raise ValidationError(f"bd create did not print the id of the task it made: {created.strip()[:200]!r}") \
            from error
    run(["bd", "update", task, "--set-metadata", f"lap.track={TRACK}", "--set-metadata", f"lap.area={app}"],
        main_tree, env)
    return task


def validate(epic: str, branch: str, settings: dict, home: Path, main_tree: Path) -> Validated:
    """Validates the epic branch merged with main, moves the branch there, and records the verdict on the epic."""
    commands = suite_commands(settings)
    hand_run = hand_run_groups(settings)
    epic_head = head_of(f"refs/heads/{branch}", main_tree)
    if epic_head is None:
        raise ValidationError(f"the epic branch {branch} does not exist")
    worktree, merged_head = merged_worktree(epic, epic_head, home, main_tree)
    try:
        runs = [run_command(suite, worktree) for suite in commands]
    finally:
        remove_worktree(worktree, main_tree)
    move_epic_branch(branch, epic_head, merged_head, home, main_tree)
    validated = Validated(merged_head, runs, None)
    record(epic, validated, main_tree)
    if validated.green:
        reach_the_gate(epic, branch, validated, hand_run, main_tree)
        return validated
    return Validated(merged_head, runs, file_failure(epic, [each for each in runs if not each.passed], main_tree))
