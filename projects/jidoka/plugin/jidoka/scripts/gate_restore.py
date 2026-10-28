"""Putting a test that the test cleanup removed back on the epic branch, when the human asks for it at the gate.

The epic's `cleanup.removed` names the test and its file but no commit, so the restore looks for the commit on the
epic branch, one whose subject is the cleanup's "Test cleanup" and that took the test's definition out of the file,
the newest first. A cleanup can take several tests out of one file, so the restore puts back only the named test's
lines: the definition line, the decorator or attribute lines right above it, and the lines below it that are blank,
indented deeper or a closing bracket at its own indent, with the blank lines that separated it from its neighbor. It
takes back only lines that the cleanup commit removed. A file that the cleanup deleted whole comes back whole, less
the other tests it removed from that file and still records.

The restored lines go in by a three-way merge onto the file as the epic branch now holds it, in a detached worktree at
.worktrees/restore-<epic>, as one commit, "Restore <test>", and the epic branch fast-forwards to it under the merge
lock. A merge that conflicts writes nothing. Validation never ran the restored test, so the gate's merge runs the full
suite again on an epic branch that moved past the commit validation checked.
"""
from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

import cleanup
from cleanup import Removal
from commands import capture, head_of, run
from pass_support import MAIN_BRANCH, move_epic_branch
from worktrees import cut_detached, remove_worktree, stage_worktree

WORKTREE_PREFIX = "restore-"
CLOSING = ("}", ")", "]", "{")
MARKERS = ("@", "[")


class RestoreError(Exception):
    """A reason the restore writes nothing, worded for the person who reads stderr."""


@dataclass(frozen=True)
class EpicHead:
    """The epic, its epic branch and the commit the branch is at, which a restore builds on and moves the branch
    from."""
    epic: str
    branch: str
    head: str


@dataclass(frozen=True)
class Removed:
    """Where a cleanup commit took the test out: the commit, the file's lines before and after it, the line of the
    test's definition, and the lines the commit removed."""
    commit: str
    before: list[str]
    after: list[str] | None
    at: int
    removed: set[int]


def removal_named(removals: list[Removal], test: str, file: str | None) -> Removal:
    matching = [each for each in removals if each.test == test and (file is None or each.file == file)]
    if not matching:
        where = f" from {file}" if file is not None else ""
        raise RestoreError(f"the test cleanup records no removed test named {test}{where}")
    if len(matching) > 1:
        raise RestoreError(f"the test cleanup removed a test named {test} from "
                           f"{', '.join(each.file for each in matching)}. Name the file with --file")
    return matching[0]


def name_in_code(test: str) -> str:
    """The part of a test's name that its definition line holds: the last part of a dotted or :: path."""
    if " " in test:
        return test
    return re.split(r"::|\.", test)[-1]


def version_at(commit: str, path: str, main_tree: Path) -> str | None:
    shown = capture(["git", "show", f"{commit}:{path}"], main_tree, None)
    return shown.stdout if shown.returncode == 0 else None


def removed_lines(before: list[str], after: list[str] | None) -> set[int]:
    if after is None:
        return set(range(len(before)))
    removed: set[int] = set()
    for tag, start, end, _, _ in SequenceMatcher(None, before, after, autojunk=False).get_opcodes():
        if tag in ("delete", "replace"):
            removed.update(range(start, end))
    return removed


def definition_in(lines: list[str], removed: set[int], test: str) -> int | None:
    pattern = re.compile(rf"(?<!\w){re.escape(name_in_code(test))}(?!\w)")
    return next((index for index in sorted(removed) if pattern.search(lines[index])), None)


def cleanup_commits(head: str, main_tree: Path) -> list[str]:
    """The test cleanup's commits on the epic branch that main lacks, the newest first."""
    listed = run(["git", "log", "--format=%H %s", f"{MAIN_BRANCH}..{head}"], main_tree, None).splitlines()
    return [line.split(" ", 1)[0] for line in listed if line.partition(" ")[2] == cleanup.STAGE.commit_message]


def where_removed(removal: Removal, head: str, main_tree: Path) -> Removed:
    for commit in cleanup_commits(head, main_tree):
        before = version_at(f"{commit}^", removal.file, main_tree)
        if before is None:
            continue
        before_lines = before.splitlines(keepends=True)
        after = version_at(commit, removal.file, main_tree)
        after_lines = None if after is None else after.splitlines(keepends=True)
        removed = removed_lines(before_lines, after_lines)
        at = definition_in(before_lines, removed, removal.test)
        if at is not None:
            return Removed(commit, before_lines, after_lines, at, removed)
    raise RestoreError(f"no Test cleanup commit on the epic branch took {removal.test} out of {removal.file}")


def indent_of(line: str) -> int:
    return len(line) - len(line.lstrip())


def continues(line: str, level: int) -> bool:
    if not line.strip():
        return True
    return indent_of(line) > level or (indent_of(line) == level and line.lstrip().startswith(CLOSING))


def test_block(lines: list[str], at: int, removed: set[int]) -> set[int]:
    """The lines of the test whose definition is at the line, among the removed lines, with the blank lines that
    separated it from the test before it, or else from the test after it."""
    level = indent_of(lines[at])
    start = at
    while start - 1 in removed and lines[start - 1].strip() and indent_of(lines[start - 1]) == level \
            and lines[start - 1].lstrip().startswith(MARKERS):
        start -= 1
    end = at + 1
    while end in removed and continues(lines[end], level):
        end += 1
    while end - 1 > at and not lines[end - 1].strip():
        end -= 1
    block = set(range(start, end))
    above = start
    while above - 1 in removed and not lines[above - 1].strip():
        above -= 1
    below = end
    while above == start and below in removed and not lines[below].strip():
        below += 1
    return block | set(range(above, start)) | set(range(end, below))


def restored_text(found: Removed, others: list[Removal]) -> str:
    """The file as the cleanup commit left it, with the test's lines put back."""
    block = test_block(found.before, found.at, found.removed)
    if found.after is None:
        others_lines = found.removed - block
        dropped: set[int] = set()
        for other in others:
            at = definition_in(found.before, others_lines, other.test)
            if at is not None:
                dropped |= test_block(found.before, at, others_lines)
        return "".join(line for index, line in enumerate(found.before) if index not in dropped)
    kept: list[str] = []
    matcher = SequenceMatcher(None, found.before, found.after, autojunk=False)
    for tag, start, end, after_start, after_end in matcher.get_opcodes():
        if tag == "equal":
            kept += found.after[after_start:after_end]
            continue
        kept += [found.before[index] for index in range(start, end) if index in block]
        kept += found.after[after_start:after_end]
    return "".join(kept)


def merged_onto(current: str | None, base: str | None, restored: str, removal: Removal) -> str:
    """The restored test merged onto the file as the epic branch holds it now."""
    if current == base:
        return restored
    with tempfile.TemporaryDirectory() as folder:
        paths = [Path(folder) / name for name in ("current", "base", "restored")]
        for path, text in zip(paths, (current or "", base or "", restored)):
            path.write_text(text, encoding="utf-8")
        merged = capture(["git", "merge-file", "-p", *(str(path) for path in paths)], Path(folder), None)
    if merged.returncode != 0:
        raise RestoreError(f"putting {removal.test} back conflicts with what the epic branch changed in "
                           f"{removal.file} since the test cleanup, so nothing was written")
    return merged.stdout


def commit_restore(removal: Removal, text: str, at: EpicHead, home: Path, main_tree: Path) -> str:
    """Commits the file with the test back in a detached worktree at the head, and fast-forwards the epic branch."""
    path = stage_worktree(WORKTREE_PREFIX, at.epic, main_tree)
    if path.exists():
        remove_worktree(path, main_tree)
    cut_detached(path, at.head, home, main_tree)
    try:
        target = path / removal.file
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        run(["git", "add", "--", removal.file], path, None)
        run(["git", "commit", "--quiet", "--message", f"Restore {removal.test}"], path, None)
        restored = head_of("HEAD", path) or at.head
        move_epic_branch(at.branch, at.head, restored, home, main_tree)
    finally:
        remove_worktree(path, main_tree)
    return restored


def restore(removal: Removal, removals: list[Removal], at: EpicHead, home: Path, main_tree: Path) -> str:
    """Puts the removed test back on the epic branch as one commit and returns it."""
    found = where_removed(removal, at.head, main_tree)
    others = [each for each in removals if each != removal and each.file == removal.file]
    restored = restored_text(found, others)
    base = None if found.after is None else "".join(found.after)
    text = merged_onto(version_at(at.head, removal.file, main_tree), base, restored, removal)
    return commit_restore(removal, text, at, home, main_tree)
