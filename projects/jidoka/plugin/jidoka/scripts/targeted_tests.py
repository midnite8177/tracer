#!/usr/bin/env python3
"""Runs an app's targeted tests on a bead's worktree merged with a base branch, and records the run on the bead.

The base branch is main for bench work and the epic branch for a lap. The
command is the app's test command from the repo settings, followed by its
test_target with the one <...> placeholder replaced by the filter given, which
the script quotes or escapes for the shell so that a filter such as A|B reaches
the test command whole. The script merges the base branch into the worktree, or with --rebase rebases the
worktree's branch onto it, which a lap does so that the epic branch stays one
commit per task. It runs the command once, and when the base branch moved
during the run it brings the base branch in again and runs the command once
more. It sets the metadata keys tests.command, tests.base (the sha the run
brought in) and tests.result (pass or fail), then posts one comment on the
bead that quotes the command, the result, the base branch and that sha. The
only commit it makes is the merge commit git makes, and a rebase makes none.

A run that executed no tests records nothing. The script reads that from the
output: dotnet test's summary lines, summed over the test assemblies, or its
"No test matches the given testcase filter" with no summary line, and
unittest's "Ran N tests". Output in neither shape is judged by the exit code.

Exit codes:
  0  the tests passed, and the pass is recorded.
  1  refused or stopped. When it stops before a run is recorded, nothing is
     set on the bead: no repo settings, settings with no untested_apps list,
     an unknown or incomplete app, an app with no test command, a
     test_target without one placeholder, a base branch that does not
     exist, a merge or rebase conflict with the base branch, or a failed git
     command. A conflict aborts the merge or rebase and names the files.
     The script refuses an app with no test command before it merges the
     base branch, and says to build a test project for it at the
     bench and then run /jidoka:onboard to record its command. When bd
     fails while recording, the metadata may be set without the comment.
  3  the tests failed, and the failure is recorded.
  4  the filter needs fixing, and nothing is recorded. It starts with the
     text the test_target puts before its placeholder, or the run executed
     no tests. Run it again with a corrected filter. When the run executed
     no tests and the app has hand-run tests, the message names each group,
     because its test_target leaves them out and no filter reaches them.
"""
from __future__ import annotations

import argparse
import enum
import re
import sys
from dataclasses import dataclass, replace
from pathlib import Path

import settings_reader
import target_placeholder
from commands import COMMAND_TIMEOUT_SECONDS, CommandError, capture, head_of, run, run_test_command
from runner_summary import tests_executed

TESTS_FAILED_EXIT_CODE = 3
FILTER_REFUSED_EXIT_CODE = 4
ONE_EXPRESSION = ("The filter is one expression for the test_target, not a list of filters. To select several "
                  "tests, join them with the test command's own syntax for or, such as A|B for dotnet test")


class Integration(enum.Enum):
    """How the base branch comes into the worktree before a run: a merge at the bench, a rebase on a lap."""
    MERGE = "merge"
    REBASE = "rebase"

    @property
    def participle(self) -> str:
        return "merged with" if self is Integration.MERGE else "rebased onto"

    @property
    def gerund(self) -> str:
        return "merging" if self is Integration.MERGE else "rebasing"


class TestRunError(Exception):
    """A reason the script records no result, worded for the person who reads the output."""


class FilterRefused(Exception):
    """A filter that selects no tests or repeats the test_target's text, worded for the builder who fixes it."""


class MergeConflict(TestRunError):
    """A merge or rebase of the worktree on the base branch that conflicted, with the conflicting files, after the
    abort."""

    def __init__(self, message: str, files: list[str]):
        super().__init__(message)
        self.files = files


class NoTestsExecuted(Exception):
    """A run whose output shows it executed no tests, on the worktree with the base branch brought in at base."""

    def __init__(self, base: str):
        super().__init__(base)
        self.base = base


@dataclass(frozen=True)
class TestRun:
    """One run of the test command on the worktree with the base branch brought in at the sha base."""
    base: str
    exit_code: int

    @property
    def passed(self) -> bool:
        return self.exit_code == 0

    @property
    def result(self) -> str:
        return "pass" if self.passed else "fail"


@dataclass(frozen=True)
class TestOutcome:
    """The command, the base branch and how it came in, the run the bead records, and the earlier run it replaced
    when the base branch moved during that run."""
    command: str
    base_branch: str
    how: Integration
    recorded: TestRun
    replaced: TestRun | None

    def comment(self) -> str:
        verdict = "passed" if self.recorded.passed else "failed"
        lines = [f"Targeted tests {verdict} with exit code {self.recorded.exit_code}, "
                 f"on the worktree {self.how.participle} {self.base_branch} at {self.recorded.base}.",
                 "Command:",
                 self.command]
        if self.replaced is not None:
            lines.append(f"{self.base_branch} moved during an earlier run on {self.replaced.base}, which exited "
                         f"{self.replaced.exit_code}, so this is the rerun.")
        return "\n".join(lines)


def untested(app: settings_reader.App) -> TestRunError:
    return TestRunError(f"{app.name} has no test command. Build a test project for it at the bench, "
                        "then run /jidoka:onboard to record its command.")


def app_settings(home: Path, main_tree: Path, name: str) -> settings_reader.App:
    path = settings_reader.settings_path(home, main_tree)
    try:
        settings = settings_reader.require_settings(home, main_tree)
        if not settings_reader.apps_of(settings):
            raise TestRunError(f"{path} holds no list of apps")
        if not isinstance(settings.get("untested_apps"), list):
            raise TestRunError(f"{path} holds no untested_apps list of the apps with no test command. "
                               "Run /jidoka:onboard to record it")
        app = settings_reader.app_named(settings, name)
    except settings_reader.SettingsError as error:
        raise TestRunError(str(error)) from error
    if app.targeted_command is None:
        raise untested(app)
    return app


def test_command(app: settings_reader.App, test_filter: str) -> str:
    target = app.test_target
    if target is None:
        raise untested(app)
    placeholders = list(target_placeholder.PLACEHOLDER.finditer(target))
    if len(placeholders) != 1:
        raise TestRunError(f"the test_target of app {app.name!r} is {target!r}, which needs exactly "
                           f"one <...> placeholder for the filter and has {len(placeholders)}")
    refuse_a_repeated_prefix(app, test_filter, target[:placeholders[0].start()])
    command = replace(app, test_target=target_placeholder.filled(target, test_filter)).targeted_command
    if command is None:
        raise untested(app)
    return command


def refuse_a_repeated_prefix(app: settings_reader.App, test_filter: str, prefix: str) -> None:
    """Raises FilterRefused when the filter starts with text the test_target already puts before it.

    The text is the whole prefix, such as "--filter FullyQualifiedName~" or "-k ", or the part of it after
    its last whitespace, such as "FullyQualifiedName~", because a filter copied from a working command line
    often carries that part. An empty part repeats nothing, so a test_target of only the placeholder never
    refuses.
    """
    whole = prefix.lstrip()
    last_word = re.split(r"\s", prefix)[-1]
    for repeated in (whole, last_word):
        if repeated and test_filter.startswith(repeated):
            raise FilterRefused(
                f"the filter {test_filter!r} starts with {repeated!r}, which the test_target of app "
                f"{app.name!r}, {app.test_target!r}, already puts before the filter, so the command would "
                f"hold it twice. Nothing ran; pass \"{test_filter[len(repeated):]}\" instead")


def base_head(base_branch: str, worktree: Path) -> str:
    head = head_of(f"refs/heads/{base_branch}", worktree)
    if head is None:
        raise TestRunError(f"the repo has no branch {base_branch} to merge into the worktree")
    return head


def bring_in_base_branch(base_branch: str, worktree: Path, how: Integration) -> str:
    """Returns the sha of the base branch, merged into the worktree or the worktree rebased onto it.

    On a conflict it aborts, so the worktree is as it was, and raises MergeConflict naming the files.
    """
    base = base_head(base_branch, worktree)
    if how is Integration.MERGE:
        done = capture(["git", "merge", "--no-edit", base], worktree, None)
        abort = ["git", "merge", "--abort"]
    else:
        done = capture(["git", "rebase", base], worktree, None)
        abort = ["git", "rebase", "--abort"]
    if done.returncode == 0:
        return base
    conflicted = run(["git", "diff", "--name-only", "--diff-filter=U"], worktree, None).split()
    capture(abort, worktree, None)
    if conflicted:
        raise MergeConflict(f"{how.gerund} {base_branch} conflicts with the worktree, so the script aborted and "
                            "ran no tests. Conflicting files:\n" + "\n".join(f"  {name}" for name in conflicted),
                            conflicted)
    raise TestRunError(f"git {how.value} {base_branch} failed: {done.stderr.strip() or done.stdout.strip()}")


def run_tests(command: str, worktree: Path, base: str) -> TestRun:
    """Runs the command on the worktree with the base branch brought in at the sha base.

    It raises NoTestsExecuted for a run that tested nothing, whatever its exit code, and reads output in
    no known shape by the exit code alone.
    """
    done = run_test_command(command, worktree)
    sys.stdout.write(done.stdout)
    sys.stdout.write(done.stderr)
    sys.stdout.flush()
    if tests_executed(f"{done.stdout}\n{done.stderr}") == 0:
        raise NoTestsExecuted(base)
    return TestRun(base, done.returncode)


def run_on_integrated_head(command: str, worktree: Path, base_branch: str, how: Integration) -> TestOutcome:
    base = bring_in_base_branch(base_branch, worktree, how)
    first = run_tests(command, worktree, base)
    if base_head(base_branch, worktree) == base:
        return TestOutcome(command, base_branch, how, first, None)
    print(f"{base_branch} moved during the run, so the tests run again on the worktree {how.participle} "
          f"{base_branch}")
    try:
        second_base = bring_in_base_branch(base_branch, worktree, how)
    except MergeConflict as error:
        raise MergeConflict(f"the run on {base_branch} at {base} exited {first.exit_code} and is not recorded, "
                            f"because {base_branch} moved during it and {how.gerund} it again failed: {error}",
                            error.files) from error
    except TestRunError as error:
        raise TestRunError(f"the run on {base_branch} at {base} exited {first.exit_code} and is not recorded, "
                           f"because {base_branch} moved during it and {how.gerund} it again failed: "
                           f"{error}") from error
    return TestOutcome(command, base_branch, how, run_tests(command, worktree, second_base), first)


def record(bead: str, outcome: TestOutcome, main_tree: Path, env: dict[str, str] | None) -> None:
    run(["bd", "update", bead,
         "--set-metadata", f"tests.command={outcome.command}",
         "--set-metadata", f"tests.base={outcome.recorded.base}",
         "--set-metadata", f"tests.result={outcome.recorded.result}"], main_tree, env)
    run(["bd", "comment", bead, outcome.comment()], main_tree, env)


def targeted_tests(bead: str, worktree: Path, base_branch: str, how: Integration, app: str, test_filter: str,
                   home: Path, env: dict[str, str] | None) -> TestRun:
    """Runs and records the tests, writing to the bead in env, or in the inherited environment when env is None."""
    try:
        main_tree = settings_reader.main_worktree(worktree, COMMAND_TIMEOUT_SECONDS)
    except settings_reader.SettingsError as error:
        raise TestRunError(str(error)) from error
    settings = app_settings(home, main_tree, app)
    command = test_command(settings, test_filter)
    print(f"running: {command}", flush=True)
    try:
        outcome = run_on_integrated_head(command, worktree, base_branch, how)
    except NoTestsExecuted as error:
        raise FilterRefused(f"the run on the worktree {how.participle} {base_branch} at {error.base} executed no "
                            f"tests, so "
                            f"nothing is recorded on the bead. Check the --filter {test_filter!r} against the "
                            f"test_target of app {app!r}, {settings.test_target!r}, and the output above. "
                            f"{ONE_EXPRESSION}{left_out(settings)}") from error
    record(bead, outcome, main_tree, env)
    return outcome.recorded


def left_out(app: settings_reader.App) -> str:
    """Names the hand-run groups the test_target leaves out, because a filter that names one of them runs nothing."""
    if not app.hand_run:
        return ""
    groups = "".join(f"\n  {group.name}: {group.reason}\n    {group.command}" for group in app.hand_run)
    return (". No filter reaches these hand-run tests, because the test_target leaves them out. "
            f"The human runs them:{groups}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run an app's targeted tests on a bead's worktree merged with a base branch, and record the run.")
    parser.add_argument("--bead", required=True)
    parser.add_argument("--worktree", type=Path, required=True)
    parser.add_argument("--base", required=True, help="the branch to bring into the worktree, such as main")
    parser.add_argument("--rebase", action="store_true",
                        help="rebase the worktree onto the base branch, where without it the base branch is merged in")
    parser.add_argument("--app", required=True, help="the app's name in the repo settings")
    parser.add_argument("--filter", required=True, help="the value that replaces the test_target placeholder")
    parser.add_argument("--jidoka-home", type=Path, required=True)
    args = parser.parse_args()

    try:
        how = Integration.REBASE if args.rebase else Integration.MERGE
        recorded = targeted_tests(args.bead, args.worktree.resolve(), args.base, how, args.app, args.filter,
                                  args.jidoka_home.expanduser().resolve(), None)
    except FilterRefused as error:
        print(f"targeted_tests: {error}", file=sys.stderr)
        return FILTER_REFUSED_EXIT_CODE
    except (TestRunError, CommandError) as error:
        print(f"targeted_tests: {error}", file=sys.stderr)
        return 1
    print(f"targeted_tests: {recorded.result}, exit code {recorded.exit_code}, "
          f"on {args.base} at {recorded.base}, recorded on {args.bead}")
    return 0 if recorded.passed else TESTS_FAILED_EXIT_CODE


if __name__ == "__main__":
    sys.exit(main())
