"""Test cleanup, the first stage of a pass, which deletes the tests the epic added or changed that add neither
confidence nor communication.

The scheduler calls `to_run` once every task of an epic is closed and before validation. When the epic branch holds
tests the epic added or changed, it cuts a detached worktree at .worktrees/cleanup-<epic> from the epic branch's
head and hands the scheduler a test-cleanup action for a worker on the deep tier. The tests the epic added or
changed are the files of the three-dot diff from main that look like tests, leaving out every app's acceptance
folder, which is protected. An epic with no such file has no cleanup, and its pass goes straight to validation.

The worker deletes tests in the worktree, commits nothing, and lists every deletion in `test-cleanup.json` in the
worktree's scratch folder: a JSON list of {"test", "file", "covered_by"}, where `covered_by` names the kept test or
acceptance spec that covers the same behavior. `settle` takes that report. It refuses, and writes nothing, when the
report is missing or unusable, when a deletion names no covering test or names a test that was itself deleted,
when the worktree changed a path that is not a test the epic added or changed, when the changed paths and the
reported files differ, or when the worktree is gone or at another head than the worker started from, because a worktree
cut again would hold none of the worker's deletions. Otherwise it commits the change as one commit, "Test cleanup",
fast-forwards the epic branch to it under the merge lock, and with BEADS_ACTOR set to jidoka records on the epic
`cleanup.state` (done) and `cleanup.removed`, every deletion of the epic's passes, and posts a comment that lists
them. Validation clears `cleanup.state` when it ends red, so the next pass cleans again, and the gate comment's Tests
removed table reads `cleanup.removed`.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import pass_support
from commands import env_as_factory, metadata_of, read_bead, run, set_metadata
from pass_support import PassError, Stage, StageToRun
from report_text import listed_report

STATE_KEY = "cleanup.state"
REMOVED_KEY = "cleanup.removed"
ACTION = "test-cleanup"
REPORT = "test-cleanup.json"
TEST_FOLDERS = ("test", "tests", "__tests__")
TEST_NAME_PARTS = (".test.", ".spec.")
TEST_FILE_ENDINGS = ("_test.py", "Tests.cs", "Test.cs", "_test.go")
TEST_FILE_PREFIXES = ("test_",)
REPORT_FIELDS = ("test", "file", "covered_by")


class CleanupError(PassError):
    """A reason the cleanup writes nothing more, worded for the person who reads stderr."""


@dataclass(frozen=True)
class Removal:
    """One deleted test, the file it was in, and the kept test or acceptance spec that covers its behavior."""
    test: str
    file: str
    covered_by: str

    def fields(self) -> dict:
        return {"test": self.test, "file": self.file, "covered_by": self.covered_by}


@dataclass(frozen=True)
class Cleaned:
    """What a settled cleanup did: the commit the epic branch now ends with, or its old head when nothing was
    removed, and the deletions."""
    head: str
    removed: list[Removal]

    def fields(self) -> dict:
        return {"head": self.head, "removed": [each.fields() for each in self.removed]}


def is_test_path(path: str) -> bool:
    pure = PurePosixPath(path)
    name = pure.name
    return (any(part in TEST_FOLDERS for part in pure.parts[:-1]) or name.startswith(TEST_FILE_PREFIXES)
            or name.endswith(TEST_FILE_ENDINGS) or any(part in name for part in TEST_NAME_PARTS))


STAGE = Stage(name="test cleanup", action=ACTION, prefix="cleanup-", state_key=STATE_KEY,
              commit_message="Test cleanup", allowed_kind="tests the epic added or changed", files_key="tests",
              wants=is_test_path, report=REPORT, error=CleanupError)


def removed_before(shown: dict) -> list[Removal]:
    """The deletions earlier passes recorded on the epic."""
    value = metadata_of(shown).get(REMOVED_KEY)
    if value in (None, ""):
        return []
    try:
        listed = json.loads(value) if isinstance(value, str) else value
        return [Removal(str(each["test"]), str(each["file"]), str(each["covered_by"])) for each in listed]
    except (ValueError, KeyError, TypeError) as error:
        raise CleanupError(f"the {REMOVED_KEY} metadata of the epic cannot be read: {error!r}") from error


def removed_lines(shown: dict) -> list[str]:
    """The gate comment's Tests removed table from the deletions the epic records, or no line when none."""
    rows = [f"| {each.test} | {each.file} | {each.covered_by} |" for each in removed_before(shown)]
    if not rows:
        return []
    return ["", "Tests removed:", "| Test | File | Covered by |", "| --- | --- | --- |", *rows]


def to_run(epic: str, shown: dict, branch: str, settings: dict, home: Path, main_tree: Path) -> StageToRun | None:
    """The cleanup this pass still owes, or None when it is done or the epic holds no test to clean. The worktree is
    cut again from the epic branch's head when its folder is gone."""
    return pass_support.to_run(STAGE, epic, shown, branch, settings, home, main_tree)


def removals_of(report: Path) -> list[Removal]:
    listed = listed_report(report, f"the cleanup report {report}", CleanupError)
    removals = []
    for number, each in enumerate(listed, 1):
        if not isinstance(each, dict) or not all(isinstance(each.get(field), str) and each[field].strip()
                                                 for field in REPORT_FIELDS):
            raise CleanupError(f"entry {number} of the cleanup report must name its test, file and covered_by, so "
                               "nothing was written")
        removals.append(Removal(each["test"].strip(), each["file"].strip(), each["covered_by"].strip()))
    deleted = {each.test for each in removals}
    for each in removals:
        if each.covered_by in deleted:
            raise CleanupError(f"{each.test} names {each.covered_by} as its covering test, and that test was "
                               "deleted too, so nothing was written")
    return removals


def settle(epic: str, branch: str, settings: dict, home: Path, main_tree: Path) -> Cleaned:
    """Takes the cleanup worker's report: commits its deletions as one commit on the epic branch and records them."""
    shown = read_bead(epic, main_tree)
    found = pass_support.owed_in_worktree(STAGE, epic, shown, branch, settings, main_tree)
    removals = removals_of(found.scratch / REPORT)
    reported = sorted({each.file for each in removals})

    def agrees_with_report(changed: list[str]) -> None:
        if reported != changed:
            raise CleanupError(f"the cleanup report names the files {', '.join(reported) or 'none'} and the "
                               f"worktree changed {', '.join(changed) or 'none'}, so nothing was written")

    head = pass_support.settle_worktree(found, agrees_with_report, home, main_tree).head
    kept = removed_before(shown) + removals
    env = env_as_factory()
    run(["bd", "comment", epic, comment_of(removals, head)], main_tree, env)
    run(["bd", "update", epic, *set_metadata((STATE_KEY, pass_support.DONE),
                                             (REMOVED_KEY, json.dumps([each.fields() for each in kept])))],
        main_tree, env)
    return Cleaned(head, removals)


def comment_of(removals: list[Removal], head: str) -> str:
    if not removals:
        return f"Test cleanup removed no test, and the epic branch stays at {head}."
    return "\n".join([f"Test cleanup removed {len(removals)} tests, in the commit {head}:",
                      *(f"- {each.test} ({each.file}), covered by {each.covered_by}" for each in removals)])
