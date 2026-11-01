#!/usr/bin/env python3
"""Lands a bead's branch on local main as one commit.

Behind the merge lock, the script rebuilds the branch on main's head, runs
the full suite on it, and squashes it to one commit with the message it was
given. The full suite is every app's full-suite command in app order, worked
out from the apps in the repo settings each time, and every command runs even
after one fails. An app with no test command has no full-suite command, so
before the full suite runs the script prints one line on stdout for each such
app. The bead's recorded targeted tests must
have passed, but they do not run again, because the full suite holds them.
The script fast-forwards main in the checkout that has main checked out,
closes the bead with the commit's sha in the reason, and removes the bead's
worktree and branch. It never pushes and never opens a pull request.

The full suite leaves out the hand-run tests, the groups the apps in the repo
settings list under hand_run. After exit 0, 4 or 5, a rerun that finds the branch
already on main included, the script lists each group with its app, its
reason and the command that runs it, after the rest of its output on the
same stream, so the human can run them. It lists nothing when no app has a
group.

Exit codes:
  0  landed and closed.
  1  refused or failed before the fast-forward, with main unchanged. The script
     refuses a repo with no repo settings, or settings in which no app has a
     test command, before it takes the merge lock.
  3  waiting, because uncommitted edits in main's checkout touch files the
     bead changed. The caller runs the script again later; the script does
     not sleep on it.
  4  main has the commit but a closing step failed. The sha is printed and
     the failed steps are named. Running the script again with the same
     arguments finds the branch already on main and repeats the closing steps.
  5  the full suite failed on the rebased branch, and main is unchanged.
     Each failing command is printed with its exit code and output. The
     branch stays rebased on main, where the fix goes.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

import settings_reader
from commands import (COMMAND_TIMEOUT_SECONDS, CommandError, bd_list, capture, head_of, metadata_of, read_bead, run,
                      worktree_list)
from full_suite import FullSuiteFailed, run_full_suite
from settings_reader import SuiteCommand

LOCK_POLL_SECONDS = 0.1
WAITING_ON_EDITS_EXIT_CODE = 3
PARTLY_LANDED_EXIT_CODE = 4
FULL_SUITE_FAILED_EXIT_CODE = 5


class LandingError(Exception):
    """A reason the landing stops, worded for the person who reads the output."""


class WaitingOnEdits(Exception):
    def __init__(self, files: list[str]) -> None:
        super().__init__("uncommitted edits in main's checkout touch files the bead changed")
        self.files = files


@dataclass(frozen=True)
class LandingSettings:
    full_suite: list[SuiteCommand]
    hand_run: list[settings_reader.HandRunGroup]
    untested_apps: list[str]


@dataclass(frozen=True)
class Landed:
    """The commit that is on main, and the closing steps that did not succeed."""
    sha: str
    failed_steps: list[str]


def lock_holder(lock: Path) -> str:
    try:
        recorded = lock.read_text(encoding="utf-8").strip()
    except (OSError, ValueError):
        recorded = ""
    return f"held by process {recorded}" if recorded else "holder not recorded"


def merge_lock(home: Path) -> Path:
    """The one lock that landing and the merge gate take before they move a branch."""
    return home / "locks" / "merge.lock"


def take_lock(lock: Path, waiting_on: TextIO) -> None:
    """Creates the lock file exclusively, polling until the holder removes it, and says once on `waiting_on` that it
    waits."""
    lock.parent.mkdir(parents=True, exist_ok=True)
    announced = False
    while True:
        try:
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if not announced:
                print(f"waiting for the merge lock at {lock}, {lock_holder(lock)}", file=waiting_on, flush=True)
                announced = True
            time.sleep(LOCK_POLL_SECONDS)
            continue
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(f"{os.getpid()}\n")
        return


def acquire_lock(lock: Path) -> None:
    """Takes the lock, saying on stdout that it waits, as the landing script's output allows."""
    take_lock(lock, sys.stdout)


def release_lock(lock: Path) -> None:
    try:
        lock.unlink()
    except FileNotFoundError:
        pass


@contextmanager
def merge_locked(home: Path) -> Iterator[None]:
    """Holds the merge lock for the block. It says on stderr that it waits, because a caller that prints a JSON
    document on stdout must not have a line in it."""
    lock = merge_lock(home)
    take_lock(lock, sys.stderr)
    try:
        yield
    finally:
        release_lock(lock)


def main_checkout(repo: Path) -> Path:
    """The checkout that has main checked out, found from the worktree list of any checkout of the repo."""
    for tree in worktree_list(repo):
        if tree.branch == "main":
            return tree.path
    raise LandingError("no checkout has main checked out")


def landing_settings(checkout: Path, home: Path) -> LandingSettings:
    try:
        main_tree = settings_reader.main_worktree(checkout, COMMAND_TIMEOUT_SECONDS)
        settings = settings_reader.read_settings(home, main_tree)
        return LandingSettings(list(settings.full_suite()), list(settings.hand_run()), list(settings.untested_apps()))
    except settings_reader.SettingsError as error:
        raise LandingError(str(error)) from error


def print_hand_run(groups: list[settings_reader.HandRunGroup], stream: TextIO) -> None:
    if not groups:
        return
    print("Hand-run tests, which landing never runs. Run each one yourself:", file=stream)
    for group in groups:
        print(f"  {group.app}, {group.name}: {group.reason}", file=stream)
        print(f"    {group.command}", file=stream)


def tracker_ids(checkout: Path) -> set[str]:
    return {str(item["id"]) for item in bd_list(["--all", "--limit", "0"], checkout) if "id" in item}


def bead_ids_in(message: str, bead: str, checkout: Path) -> list[str]:
    """Every id of the landing bead or of a bead in the tracker, closed ones included, that the message holds."""
    held = []
    for known in sorted(tracker_ids(checkout) | {bead}):
        if re.search(rf"(?<![A-Za-z0-9_]){re.escape(known)}(?![A-Za-z0-9_-])", message):
            held.append(known)
    return held


def recorded_tests(bead: str, checkout: Path) -> dict[str, str]:
    metadata = metadata_of(read_bead(bead, checkout))
    return {key: str(metadata.get(f"tests.{key}", "")) for key in ("command", "base", "result")}


def edited_paths(checkout: Path) -> set[str]:
    """Every path git status reports in the checkout, untracked files included and both sides of a rename."""
    status = run(["git", "status", "--porcelain", "-z", "--untracked-files=all"], checkout, None)
    entries = status.split("\0")
    paths: set[str] = set()
    index = 0
    while index < len(entries):
        entry = entries[index]
        index += 1
        if len(entry) < 4:
            continue
        paths.add(entry[3:])
        if entry[0] in "RC" or entry[1] in "RC":
            # The next field is the other path of the rename or copy; left in the loop it would read as an entry.
            paths.add(entries[index])
            index += 1
    return paths


def changed_paths(base: str, branch: str, checkout: Path) -> set[str]:
    """Every path the branch changed since it left base, both sides of a rename included."""
    listed = run(["git", "diff", "--name-only", "--no-renames", "-z", f"{base}...{branch}"], checkout, None)
    return {path for path in listed.split("\0") if path}


def refuse_overlapping_edits(branch: str, checkout: Path) -> None:
    overlap = sorted(edited_paths(checkout) & changed_paths("main", branch, checkout))
    if overlap:
        raise WaitingOnEdits(overlap)


def check_recorded(tests: dict[str, str]) -> None:
    if not tests["command"] or not tests["base"] or not tests["result"]:
        raise LandingError("the bead has no tests recorded; run the tests and record them first")
    if tests["result"] != "pass":
        raise LandingError(f"the recorded tests did not pass, the recorded result is {tests['result']}")


def rebase_on_main(worktree: Path) -> None:
    done = capture(["git", "rebase", "main"], worktree, None)
    if done.returncode == 0:
        return
    capture(["git", "rebase", "--abort"], worktree, None)
    raise LandingError("the branch conflicts with main, so the rebase was aborted and main is unchanged\n"
                       f"{done.stdout.strip()}\n{done.stderr.strip()}".rstrip())


def subject(message: str) -> str:
    """The first line of the message that has any text."""
    for line in message.splitlines():
        if line.strip():
            return line.strip()
    return ""


def landed_commit(branch: str, message: str, checkout: Path) -> str | None:
    """The branch's tip when an earlier run already put it on main with this message, else None.

    A branch that never got a commit is also an ancestor of main, so the subject has to match as well.
    """
    tip = head_of(branch, checkout)
    if tip is None:
        raise LandingError(f"branch {branch} does not exist")
    if capture(["git", "merge-base", "--is-ancestor", tip, "main"], checkout, None).returncode != 0:
        return None
    tip_subject = subject(run(["git", "log", "-1", "--format=%B", tip], checkout, None))
    return tip if tip_subject == subject(message) else None


def squash_onto_main(bead: str, branch: str, worktree: Path, message: str, checkout: Path,
                     settings: LandingSettings) -> str:
    """Rebuilds the branch as one commit on main's head and fast-forwards main to it; returns the new sha."""
    check_recorded(recorded_tests(bead, checkout))
    refuse_overlapping_edits(branch, checkout)
    rebase_on_main(worktree)
    for app in settings.untested_apps:
        print(f"No tests for {app}: it has no test command, so the full suite skips it.", flush=True)
    run_full_suite(settings.full_suite, worktree)
    run(["git", "reset", "--soft", "main"], worktree, None)
    run(["git", "commit", "-q", "-m", message], worktree, None)
    run(["git", "merge", "--ff-only", branch], checkout, None)
    return run(["git", "rev-parse", "HEAD"], checkout, None).strip()


def attempt(name: str, args: list[str], cwd: Path, env: dict[str, str] | None, failed: list[str]) -> bool:
    """Runs one closing step in env, or in the inherited environment when env is None, and notes its failure."""
    try:
        run(args, cwd, env)
    except (LandingError, CommandError) as error:
        failed.append(f"{name}: {error}")
        return False
    return True


def close_out(bead: str, branch: str, worktree: Path, message: str, sha: str, checkout: Path) -> Landed:
    """Closes the bead and removes its worktree and branch, each step on its own so one failure stops no other.

    The branch is the only way a rerun finds the landed work, so it stays while the bead is still open.
    """
    failed: list[str] = []
    closed = attempt("bd close", ["bd", "close", bead, "--reason", f"{sha}: {subject(message)}"], checkout, None,
                     failed)
    if worktree.exists():
        # The commit is on main, so the worktree holds only the scratch folder and untracked files, which git refuses
        # to remove without --force.
        attempt("git worktree remove", ["git", "worktree", "remove", "--force", str(worktree)], checkout, None,
                failed)
    if closed:
        attempt("git branch -D", ["git", "branch", "-D", branch], checkout, None, failed)
    return Landed(sha, failed)


def land(bead: str, branch: str, worktree: Path, message: str, checkout: Path,
         settings: LandingSettings) -> Landed:
    sha = landed_commit(branch, message, checkout)
    if sha is None:
        sha = squash_onto_main(bead, branch, worktree, message, checkout, settings)
    return close_out(bead, branch, worktree, message, sha, checkout)


def refuse_bad_message(message: str, bead: str, checkout: Path) -> None:
    if not message.strip():
        raise LandingError("the message is empty")
    found = bead_ids_in(message, bead, checkout)
    if found:
        raise LandingError(f"the message holds a bead id, {', '.join(found)}. Say what changed instead")


def main() -> int:
    parser = argparse.ArgumentParser(description="Land a bead's branch on local main as one commit.")
    parser.add_argument("--repo", type=Path, required=True, help="any path inside the repo")
    parser.add_argument("--bead", required=True)
    parser.add_argument("--branch", required=True)
    parser.add_argument("--worktree", type=Path, required=True)
    parser.add_argument("--message", required=True)
    parser.add_argument("--jidoka-home", type=Path, required=True)
    args = parser.parse_args()

    try:
        checkout = main_checkout(args.repo)
        refuse_bad_message(args.message, args.bead, checkout)
        settings = landing_settings(checkout, args.jidoka_home)
    except (LandingError, CommandError) as error:
        print(f"land: {error}", file=sys.stderr)
        return 1

    lock = merge_lock(args.jidoka_home)
    acquire_lock(lock)
    try:
        landed = land(args.bead, args.branch, args.worktree, args.message, checkout, settings)
    except WaitingOnEdits as waiting:
        print(f"land: {waiting}. Main is unchanged. Commit or set aside:")
        for name in waiting.files:
            print(f"  {name}")
        return WAITING_ON_EDITS_EXIT_CODE
    except FullSuiteFailed as failed:
        print(f"land: {failed}. The failing commands:", file=sys.stderr)
        for failure in failed.failures:
            print(f"\n{failure.suite.command}\nexited {failure.exit_code}:\n{failure.output.rstrip()}",
                  file=sys.stderr)
        print_hand_run(settings.hand_run, sys.stderr)
        return FULL_SUITE_FAILED_EXIT_CODE
    except (LandingError, CommandError) as error:
        print(f"land: {error}", file=sys.stderr)
        return 1
    finally:
        release_lock(lock)
    print(landed.sha)
    if landed.failed_steps:
        print("land: main has the commit, but these steps failed. Run the same command again to repeat them.",
              file=sys.stderr)
        for step in landed.failed_steps:
            print(f"  {step}", file=sys.stderr)
        print_hand_run(settings.hand_run, sys.stderr)
        return PARTLY_LANDED_EXIT_CODE
    print_hand_run(settings.hand_run, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
