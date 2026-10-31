#!/usr/bin/env python3
"""The merge gate, the last stage of a lap: it merges the lap into the epic branch only when the lap's record
supports it.

No model takes part. Under the merge lock, the one land.py takes, the gate
makes these checks in order:
  the record: the latest targeted run recorded on the task passed, and its
    base is the epic branch's head;
  the lap's head contains the epic branch's head;
  the lap's head has a commit the epic branch lacks;
  the lap changed no protected path, a path inside the acceptance folder of
    an app in the repo settings, unless the task is the spec task its epic
    records;
  a task that makes acceptance specs pass has a red run of them, recorded
    before the build, and a green run of them on the lap's head
    (spec_runs.py);
  the spec task's lap, run in its worktree, leaves every new spec failing as
    a check, never as a build or driver error, and every other spec passing
    (spec_task_gate.py);
  the main checkout does not have the epic branch checked out with
    uncommitted edits.
A run on an older epic head, or a lap head without the epic branch's head,
means the epic branch moved since the targeted run. The gate then raises
EpicBranchMoved, and the targeted tests run again. A lap with no commit of
its own raises EmptyLap, and the build ends with a try. Any other failed
check raises GateRefused, naming the check. A refusal writes nothing.

When every check passes, the gate fast-forwards the epic branch to the
lap's head with git update-ref, which refuses when the branch has left the
head the checks read. When the main checkout has the epic branch checked
out, its files follow. Then, with BEADS_ACTOR set to jidoka, the gate closes
the task with the commit's sha in the reason, and once the task is closed
sets its lap.stage to merged, removes the lap's worktree and deletes the
lap branch. Each closing step runs on its own, so one failure stops no
other. While the task is still open its worktree and branch stay, so
reporting the build done again repeats the run, the gate and the closing.

`merge_gate.py <task>` runs the gate on the task's lap, reading the lap
branch and worktree from the task's lap metadata and the epic branch from
its epic. The home is --jidoka-home, else $JIDOKA_HOME, else ~/.jidoka.

Exit codes:
  0  merged and closed; the sha is printed.
  1  refused, naming the check, or a git or bd command failed, with the
     reason on stderr.
  2  a usage error.
  3  the epic branch moved since the targeted run; run the targeted tests
     again.
  4  the epic branch has the commit, but a closing step failed; the sha is
     printed and the failed steps are named.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import lap_record
import epic_reader
import protected_paths
from protected_paths import is_protected, protected_folders
import settings_reader
import spec_runs
import spec_task_gate
import specs
from commands import (COMMAND_TIMEOUT_SECONDS, CommandError, bd_show, capture, env_as_factory, metadata_of,
                      parent_of, read_bead, run)
from epic_branch import (EditedCheckout, EpicBranchLeftTheHead, EpicBranchMoved, branch_head, fast_forward,
                         refuse_edited_checkout, required_head)
from epic_reader import BRANCH_KEY, recorded_branch
from land import LandingError, acquire_lock, attempt, changed_paths, check_recorded, merge_lock, recorded_tests, \
    release_lock

EPIC_BRANCH_MOVED_EXIT_CODE = 3
PARTLY_MERGED_EXIT_CODE = 4


class GateRefused(Exception):
    """A failed check of the gate, worded for the person who reads the task's comments."""


class EmptyLap(Exception):
    """A lap whose head holds no commit the epic branch lacks, so its build left nothing to merge."""


@dataclass(frozen=True)
class LapToMerge:
    """The task, its lap branch and worktree, and the epic branch the lap merges into."""
    task: str
    branch: str
    worktree: Path
    epic_branch: str


@dataclass(frozen=True)
class Merged:
    """The commit the epic branch now has, and the closing steps that did not succeed."""
    sha: str
    failed_steps: list[str]


def protected_changes(settings: dict, epic_head: str, lap_head: str, main_tree: Path) -> list[str]:
    """The paths the lap changed inside an acceptance folder."""
    folders = protected_folders(settings)
    return sorted(path for path in changed_paths(epic_head, lap_head, main_tree)
                  if is_protected(path, folders))


def contains(commit: str, head: str, main_tree: Path) -> bool:
    return capture(["git", "merge-base", "--is-ancestor", commit, head], main_tree, None).returncode == 0


def check(lap: LapToMerge, settings: dict, epic_head: str, lap_head: str, main_tree: Path) -> None:
    try:
        tests = recorded_tests(lap.task, main_tree)
        check_recorded(tests)
    except LandingError as error:
        raise GateRefused(f"the record does not support the merge: {error}") from error
    if tests["base"] != epic_head:
        raise EpicBranchMoved(f"the latest targeted run merged in {lap.epic_branch} at {tests['base']}, and "
                              f"{lap.epic_branch} is now at {epic_head}")
    if not contains(epic_head, lap_head, main_tree):
        raise EpicBranchMoved(f"the lap's head {lap_head} does not contain {lap.epic_branch} at {epic_head}")
    if not run(["git", "rev-list", f"{epic_head}..{lap_head}"], main_tree, None).strip():
        raise EmptyLap(f"no commits on the lap that {lap.epic_branch} lacks")
    task = read_bead(lap.task, main_tree)
    epic = protected_paths.epic_of_task(task, main_tree)
    is_spec_task = protected_paths.is_spec_task(task, epic)
    protected = [] if is_spec_task else protected_changes(settings, epic_head, lap_head, main_tree)
    if protected:
        raise GateRefused("the lap changed protected paths, inside an app's acceptance folder: "
                          + ", ".join(protected))
    unrun = spec_runs.refusal(task, lap_head)
    if unrun:
        raise GateRefused(f"the task's spec runs do not support the merge: {unrun}")
    unjudged = (spec_task_gate.refusal(task, epic, settings, lap.worktree, main_tree)
                if is_spec_task and epic is not None else None)
    if unjudged:
        raise GateRefused(f"the spec task's specs do not support the merge: {unjudged}")
    try:
        refuse_edited_checkout(lap.epic_branch, main_tree)
    except EditedCheckout as edited:
        raise GateRefused(str(edited)) from edited


def close_out(lap: LapToMerge, sha: str, main_tree: Path) -> Merged:
    env = env_as_factory()
    failed: list[str] = []
    closed = attempt("bd close", ["bd", "close", lap.task, "--reason", f"{sha}: merged into {lap.epic_branch}"],
                     main_tree, env, failed)
    if closed:
        attempt("bd update", ["bd", "update", lap.task, *lap_record.recording_merge()], main_tree, env,
                failed)
        if lap.worktree.exists():
            attempt("git worktree remove", ["git", "worktree", "remove", "--force", str(lap.worktree)], main_tree,
                    None, failed)
        attempt("git branch -D", ["git", "branch", "-D", lap.branch], main_tree, None, failed)
    return Merged(sha, failed)


def merge(lap: LapToMerge, settings: dict, home: Path, main_tree: Path) -> Merged:
    lock = merge_lock(home)
    acquire_lock(lock)
    try:
        epic_head = required_head(lap.epic_branch, main_tree, GateRefused)
        lap_head = branch_head(lap.branch, main_tree)
        if lap_head is None:
            raise GateRefused(f"the lap branch {lap.branch} does not exist")
        check(lap, settings, epic_head, lap_head, main_tree)
        try:
            fast_forward(lap.epic_branch, epic_head, lap_head, main_tree)
        except EpicBranchLeftTheHead as left:
            raise EpicBranchMoved(f"{left} while the gate checked the lap") from left
        return close_out(lap, lap_head, main_tree)
    finally:
        release_lock(lock)


def lap_of(task: str, main_tree: Path) -> LapToMerge:
    shown = read_bead(task, main_tree)
    metadata = metadata_of(shown)
    branch, worktree = lap_record.branch_of(metadata), lap_record.workspace_of(metadata)
    if not branch or not worktree:
        raise GateRefused(f"{task} records no lap branch or worktree, so it has no lap to merge")
    parent = parent_of(shown)
    epic = bd_show(parent, main_tree) if parent else None
    epic_branch = recorded_branch(epic or {})
    if not epic_branch:
        raise GateRefused(f"the epic of {task} records no epic branch as its {BRANCH_KEY} metadata")
    return LapToMerge(task, branch, Path(worktree), epic_branch)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="merge_gate.py", description="Merge a task's lap into its epic branch "
                                                                       "when the lap's record supports it.")
    parser.add_argument("task")
    parser.add_argument("--jidoka-home", help="the folder that holds jidoka's per-machine state")
    args = parser.parse_args(argv)

    try:
        main_tree = settings_reader.main_worktree(Path.cwd(), COMMAND_TIMEOUT_SECONDS)
        home = settings_reader.jidoka_home(args.jidoka_home)
        settings = settings_reader.read_settings(home, main_tree)
        lap = lap_of(args.task, main_tree)
        merged = merge(lap, settings, home, main_tree)
    except EpicBranchMoved as moved:
        print(f"merge_gate: {moved}. Run the targeted tests again", file=sys.stderr)
        return EPIC_BRANCH_MOVED_EXIT_CODE
    except (GateRefused, EmptyLap) as refused:
        print(f"merge_gate: refused: {refused}", file=sys.stderr)
        return 1
    except (CommandError, settings_reader.SettingsError, specs.SpecsError, epic_reader.EpicReadError,
            OSError) as error:
        print(f"merge_gate: {error}", file=sys.stderr)
        return 1
    print(merged.sha)
    if merged.failed_steps:
        print(f"merge_gate: {lap.epic_branch} has the commit, but these steps failed:", file=sys.stderr)
        for step in merged.failed_steps:
            print(f"  {step}", file=sys.stderr)
        return PARTLY_MERGED_EXIT_CODE
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
