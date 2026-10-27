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
when the worktree changed a path that is not a test the epic added or changed, or when the changed paths and the
reported files differ. Otherwise it commits the change as one commit, "Test cleanup", fast-forwards the epic
branch to it under the merge lock, and with BEADS_ACTOR set to jidoka records on the epic `cleanup.state` (done)
and `cleanup.removed`, every deletion of the epic's passes, and posts a comment that lists them. Validation clears
`cleanup.state` when it ends red, so the next pass cleans again, and the gate comment's Tests removed table reads
`cleanup.removed`, as validation.py describes.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import git_exclude
import merge_gate
import private_docs
from bench import WORKTREE_FOLDER, hide_worktrees
from commands import bd_show, capture, env_as_factory, head_of, run
from validation import CLEANUP_STATE_KEY as STATE_KEY
from validation import MAIN_BRANCH, REMOVED_KEY, SCRATCH_FOLDER, move_epic_branch, remove_worktree

DONE = "done"
ACTION = "test-cleanup"
REPORT = "test-cleanup.json"
WORKTREE_PREFIX = "cleanup-"
COMMIT_MESSAGE = "Test cleanup"
TEST_FOLDERS = ("test", "tests", "__tests__")
TEST_NAME_PARTS = (".test.", ".spec.")
TEST_FILE_ENDINGS = ("_test.py", "Tests.cs", "Test.cs", "_test.go")
TEST_FILE_PREFIXES = ("test_",)
REPORT_FIELDS = ("test", "file", "covered_by")


class CleanupError(Exception):
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
class CleanupToRun:
    """The cleanup a worker makes: the commit it starts from, its worktree, and the tests it may touch."""
    epic: str
    branch: str
    head: str
    worktree: Path
    tests: list[str]

    @property
    def report(self) -> Path:
        return self.worktree / SCRATCH_FOLDER / REPORT

    def fields(self) -> dict:
        return {"action": ACTION, "epic": self.epic, "branch": self.branch, "head": self.head,
                "worktree": str(self.worktree), "scratch": str(self.report.parent), "report": str(self.report),
                "tests": self.tests}


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


def worktree_of(epic: str, main_tree: Path) -> Path:
    return main_tree / WORKTREE_FOLDER / f"{WORKTREE_PREFIX}{epic}"


def epic_tests(branch_head: str, settings: dict, main_tree: Path) -> list[str]:
    """The test files the epic added or changed, outside every acceptance folder, sorted."""
    folders = merge_gate.protected_folders(settings)
    listed = run(["git", "diff", "--name-only", "--diff-filter=AM", f"{MAIN_BRANCH}...{branch_head}"], main_tree,
                 None).splitlines()
    return sorted(path for path in listed if is_test_path(path)
                  and not any(folder == PurePosixPath(path) or folder in PurePosixPath(path).parents
                              for folder in folders))


def removed_before(shown: dict) -> list[Removal]:
    """The deletions earlier passes recorded on the epic."""
    metadata = shown.get("metadata") if isinstance(shown.get("metadata"), dict) else {}
    value = metadata.get(REMOVED_KEY)
    if value in (None, ""):
        return []
    try:
        listed = json.loads(value) if isinstance(value, str) else value
        return [Removal(str(each["test"]), str(each["file"]), str(each["covered_by"])) for each in listed]
    except (ValueError, KeyError, TypeError) as error:
        raise CleanupError(f"the {REMOVED_KEY} metadata of the epic cannot be read: {error!r}") from error


def is_done(shown: dict) -> bool:
    metadata = shown.get("metadata")
    return isinstance(metadata, dict) and metadata.get(STATE_KEY) == DONE


def to_run(epic: str, shown: dict, branch: str, settings: dict, home: Path, main_tree: Path) -> CleanupToRun | None:
    """The cleanup this pass still owes, or None when it is done or the epic holds no test to clean. The worktree is
    cut again from the epic branch's head when its folder is gone."""
    if is_done(shown):
        return None
    head = head_of(f"refs/heads/{branch}", main_tree)
    if head is None:
        raise CleanupError(f"the epic branch {branch} does not exist")
    tests = epic_tests(head, settings, main_tree)
    if not tests:
        return None
    path = worktree_of(epic, main_tree)
    if path.is_dir() and head_of("HEAD", path) != head:
        remove_worktree(path, main_tree)
    if not path.is_dir():
        capture(["git", "worktree", "prune"], main_tree, None)
        hide_worktrees(main_tree)
        run(["git", "worktree", "add", "-q", "--detach", str(path), head], main_tree, None)
        try:
            private_docs.share(main_tree, path.resolve(), home)
        except private_docs.ClashError as error:
            remove_worktree(path, main_tree)
            raise CleanupError(str(error)) from error
    git_exclude.add(git_exclude.exclude_file(main_tree), [git_exclude.exclude_line(SCRATCH_FOLDER, True)])
    (path / SCRATCH_FOLDER).mkdir(exist_ok=True)
    return CleanupToRun(epic, branch, head, path, tests)


def removals_of(report: Path) -> list[Removal]:
    try:
        listed = json.loads(report.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise CleanupError(f"the cleanup report {report} is missing or is not JSON ({error}), so nothing was "
                           "written") from error
    if not isinstance(listed, list):
        raise CleanupError(f"the cleanup report {report} is not a JSON list, so nothing was written")
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


def changed_paths(worktree: Path) -> list[str]:
    """Every path the worktree changed from its head, outside the scratch folder."""
    env = env_as_factory()
    run(["git", "add", "--all"], worktree, env)
    run(["git", "reset", "--quiet", "--", SCRATCH_FOLDER], worktree, env)
    return sorted(run(["git", "diff", "--cached", "--name-only"], worktree, env).splitlines())


def settle(epic: str, branch: str, settings: dict, home: Path, main_tree: Path) -> Cleaned:
    """Takes the cleanup worker's report: commits its deletions as one commit on the epic branch and records them."""
    shown = bd_show(epic, main_tree)
    if shown is None:
        raise CleanupError(f"bd show printed nothing usable for {epic}")
    owed = to_run(epic, shown, branch, settings, home, main_tree)
    if owed is None:
        raise CleanupError(f"{epic} waits on no test cleanup, so nothing was written")
    removals = removals_of(owed.report)
    changed = changed_paths(owed.worktree)
    stray = [path for path in changed if path not in owed.tests]
    if stray:
        raise CleanupError(f"the cleanup changed paths that are not tests the epic added or changed: "
                           f"{', '.join(stray)}, so nothing was written")
    reported = sorted({each.file for each in removals})
    if reported != changed:
        raise CleanupError(f"the cleanup report names the files {', '.join(reported) or 'none'} and the worktree "
                           f"changed {', '.join(changed) or 'none'}, so nothing was written")
    head = owed.head
    if changed:
        run(["git", "commit", "--quiet", "--message", COMMIT_MESSAGE], owed.worktree, env_as_factory())
        head = head_of("HEAD", owed.worktree) or owed.head
        move_epic_branch(branch, owed.head, head, home, main_tree)
    remove_worktree(owed.worktree, main_tree)
    kept = removed_before(shown) + removals
    env = env_as_factory()
    run(["bd", "comment", epic, comment_of(removals, head)], main_tree, env)
    run(["bd", "update", epic, "--set-metadata", f"{STATE_KEY}={DONE}",
         "--set-metadata", f"{REMOVED_KEY}={json.dumps([each.fields() for each in kept])}"], main_tree, env)
    return Cleaned(head, removals)


def comment_of(removals: list[Removal], head: str) -> str:
    if not removals:
        return f"Test cleanup removed no test, and the epic branch stays at {head}."
    return "\n".join([f"Test cleanup removed {len(removals)} tests, in the commit {head}:",
                      *(f"- {each.test} ({each.file}), covered by {each.covered_by}" for each in removals)])
