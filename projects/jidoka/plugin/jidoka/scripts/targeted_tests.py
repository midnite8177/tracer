#!/usr/bin/env python3
"""Runs an app's targeted tests on a bead's worktree merged with main, and records the run on the bead.

The command is the app's test command from the repo settings, followed by its
test_target with the one <...> placeholder replaced by the filter given. The
script merges main into the worktree, runs the command once, and when main
moved during the run it merges again and runs the command once more. It sets
the metadata keys tests.command, tests.base and tests.result (pass or fail),
then posts one comment on the bead that quotes the command, the result and
the main sha the run merged in. The only commit it makes is the merge commit
git makes.

Exit codes:
  0  the tests passed, and the pass is recorded.
  1  refused or stopped. When it stops before a run is recorded, nothing is
     set on the bead: no repo settings, an unknown or incomplete app, a
     test_target without one placeholder, a merge conflict with main, or a
     failed git command. When bd fails while recording, the metadata may be
     set without the comment.
  3  the tests failed, and the failure is recorded.
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import repo_settings
from commands import COMMAND_TIMEOUT_SECONDS, CommandError, capture, head_of, run, run_test_command

MAIN_REF = "refs/heads/main"
TESTS_FAILED_EXIT_CODE = 3
PLACEHOLDER = re.compile(r"<[^<>]+>")


class TestRunError(Exception):
    """A reason the script records no result, worded for the person who reads the output."""


@dataclass(frozen=True)
class App:
    """The part of an app's repo settings that names its tests."""
    name: str
    test: str
    test_target: str


@dataclass(frozen=True)
class TestRun:
    """One run of the test command on the worktree merged with main at base."""
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
    """The command, the run the bead records, and the earlier run it replaced when main moved during that run."""
    command: str
    recorded: TestRun
    replaced: TestRun | None

    def comment(self) -> str:
        verdict = "passed" if self.recorded.passed else "failed"
        lines = [f"Targeted tests {verdict} with exit code {self.recorded.exit_code}, "
                 f"on the worktree merged with main at {self.recorded.base}.",
                 "Command:",
                 self.command]
        if self.replaced is not None:
            lines.append(f"Main moved during an earlier run on {self.replaced.base}, which exited "
                         f"{self.replaced.exit_code}, so this is the rerun.")
        return "\n".join(lines)


def app_settings(home: Path, main_tree: Path, name: str) -> App:
    path = repo_settings.settings_path(home, main_tree)
    if not path.is_file():
        raise TestRunError(f"no settings for {main_tree} in {path.parent}. Run /jidoka:onboard to record them")
    try:
        settings = repo_settings.load(path)
    except repo_settings.SettingsError as error:
        raise TestRunError(str(error)) from error
    apps = settings.get("apps")
    if not isinstance(apps, list):
        raise TestRunError(f"{path} holds no list of apps")
    for index, entry in enumerate(apps):
        if isinstance(entry, dict) and entry.get("name") == name:
            problems = repo_settings.app_problems(index, entry)
            if problems:
                raise TestRunError(f"the repo settings for app {name!r} are incomplete: {'; '.join(problems)}")
            return App(name, entry["test"], entry["test_target"])
    names = ", ".join(str(entry.get("name")) for entry in apps if isinstance(entry, dict))
    raise TestRunError(f"the repo settings have no app named {name!r}; the apps are {names}")


def test_command(app: App, test_filter: str) -> str:
    placeholders = PLACEHOLDER.findall(app.test_target)
    if len(placeholders) != 1:
        raise TestRunError(f"the test_target of app {app.name!r} is {app.test_target!r}, which needs exactly "
                           f"one <...> placeholder for the filter and has {len(placeholders)}")
    # A replacement string would read backslashes in the filter as escapes and \1 as a group reference.
    return f"{app.test} {PLACEHOLDER.sub(lambda _: test_filter, app.test_target)}"


def main_head(worktree: Path) -> str:
    head = head_of(MAIN_REF, worktree)
    if head is None:
        raise TestRunError("the repo has no main branch to merge into the worktree")
    return head


def merge_main(worktree: Path) -> str:
    """Returns the main sha merged in.

    On a conflict it aborts the merge, so the worktree is as it was, and raises TestRunError naming the files.
    """
    base = main_head(worktree)
    done = capture(["git", "merge", "--no-edit", base], worktree, None)
    if done.returncode == 0:
        return base
    conflicted = run(["git", "diff", "--name-only", "--diff-filter=U"], worktree, None).split()
    capture(["git", "merge", "--abort"], worktree, None)
    if conflicted:
        raise TestRunError("the worktree conflicts with main, so the script aborted the merge and ran no tests. "
                           "Conflicting files:\n" + "\n".join(f"  {name}" for name in conflicted))
    raise TestRunError(f"git merge main failed: {done.stderr.strip() or done.stdout.strip()}")


def run_tests(command: str, worktree: Path) -> int:
    done = run_test_command(command, worktree)
    sys.stdout.write(done.stdout)
    sys.stdout.write(done.stderr)
    sys.stdout.flush()
    return done.returncode


def run_on_merged_head(command: str, worktree: Path) -> TestOutcome:
    base = merge_main(worktree)
    first = TestRun(base, run_tests(command, worktree))
    if main_head(worktree) == base:
        return TestOutcome(command, first, None)
    print("main moved during the run, so the tests run again on the worktree merged with main")
    try:
        second_base = merge_main(worktree)
    except TestRunError as error:
        raise TestRunError(f"the run on main at {base} exited {first.exit_code} and is not recorded, "
                           f"because main moved during it and the merge again failed: {error}") from error
    return TestOutcome(command, TestRun(second_base, run_tests(command, worktree)), first)


def record(bead: str, outcome: TestOutcome, main_tree: Path) -> None:
    run(["bd", "update", bead,
         "--set-metadata", f"tests.command={outcome.command}",
         "--set-metadata", f"tests.base={outcome.recorded.base}",
         "--set-metadata", f"tests.result={outcome.recorded.result}"], main_tree, None)
    run(["bd", "comment", bead, outcome.comment()], main_tree, None)


def targeted_tests(bead: str, worktree: Path, app: str, test_filter: str, home: Path) -> TestRun:
    try:
        main_tree = repo_settings.main_worktree(worktree, COMMAND_TIMEOUT_SECONDS)
    except repo_settings.SettingsError as error:
        raise TestRunError(str(error)) from error
    command = test_command(app_settings(home, main_tree, app), test_filter)
    print(f"running: {command}", flush=True)
    outcome = run_on_merged_head(command, worktree)
    record(bead, outcome, main_tree)
    return outcome.recorded


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run an app's targeted tests on a bead's worktree merged with main, and record the run.")
    parser.add_argument("--bead", required=True)
    parser.add_argument("--worktree", type=Path, required=True)
    parser.add_argument("--app", required=True, help="the app's name in the repo settings")
    parser.add_argument("--filter", required=True, help="the value that replaces the test_target placeholder")
    parser.add_argument("--jidoka-home", type=Path, required=True)
    args = parser.parse_args()

    try:
        recorded = targeted_tests(args.bead, args.worktree.resolve(), args.app, args.filter,
                                  args.jidoka_home.expanduser().resolve())
    except (TestRunError, CommandError) as error:
        print(f"targeted_tests: {error}", file=sys.stderr)
        return 1
    print(f"targeted_tests: {recorded.result}, exit code {recorded.exit_code}, "
          f"on main at {recorded.base}, recorded on {args.bead}")
    return 0 if recorded.passed else TESTS_FAILED_EXIT_CODE


if __name__ == "__main__":
    sys.exit(main())
