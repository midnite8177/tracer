"""Tidy, the stage of a pass after test cleanup, which runs no-comments, with comment-sicko, and unslop over the
whole epic's diff without asking anyone.

The scheduler calls `to_run` once every task of an epic is closed and its test cleanup is done. When the epic branch
differs from main in files outside every app's acceptance folder, which is protected, it cuts a detached worktree at
.worktrees/tidy-<epic> from the epic branch's head and hands the scheduler a `tidy` action for a worker on the local
tier. The worker runs the two skills in their unattended mode, asks no question, edits only those files, and commits
nothing. `settle` takes its word that it is done: it refuses, and writes nothing, when the worktree changed a path
outside those files. Otherwise it commits the change as one commit, "No comments and unslop", fast-forwards the epic
branch to it under the merge lock, and with BEADS_ACTOR set to jidoka records on the epic `tidy.state` (done) and posts
a comment. A tidy that changes nothing makes no commit. Validation clears `tidy.state` when it ends red, so the next
pass tidies again.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import cleanup
import git_exclude
import merge_gate
import private_docs
from bench import WORKTREE_FOLDER, hide_worktrees
from commands import bd_show, capture, env_as_factory, head_of, run
from validation import MAIN_BRANCH, SCRATCH_FOLDER, move_epic_branch, remove_worktree
from validation import TIDY_STATE_KEY as STATE_KEY

DONE = "done"
ACTION = "tidy"
WORKTREE_PREFIX = "tidy-"
COMMIT_MESSAGE = "No comments and unslop"


class TidyError(Exception):
    """A reason the tidy writes nothing more, worded for the person who reads stderr."""


@dataclass(frozen=True)
class TidyToRun:
    """The tidy a worker makes: the commit it starts from, its worktree, and the files it may touch."""
    epic: str
    branch: str
    head: str
    worktree: Path
    files: list[str]

    def fields(self) -> dict:
        return {"action": ACTION, "epic": self.epic, "branch": self.branch, "head": self.head,
                "worktree": str(self.worktree), "scratch": str(self.worktree / SCRATCH_FOLDER),
                "files": self.files}


@dataclass(frozen=True)
class Tidied:
    """What a settled tidy did: the commit the epic branch now ends with, or its old head when nothing changed, and
    the files the commit changed."""
    head: str
    changed: list[str]

    def fields(self) -> dict:
        return {"head": self.head, "changed": self.changed}


def worktree_of(epic: str, main_tree: Path) -> Path:
    return main_tree / WORKTREE_FOLDER / f"{WORKTREE_PREFIX}{epic}"


def epic_files(branch_head: str, settings: dict, main_tree: Path) -> list[str]:
    """The files the epic added or changed, outside every acceptance folder, sorted."""
    folders = merge_gate.protected_folders(settings)
    listed = run(["git", "diff", "--name-only", "--diff-filter=AM", f"{MAIN_BRANCH}...{branch_head}"], main_tree,
                 None).splitlines()
    return sorted(path for path in listed
                  if not any(folder == PurePosixPath(path) or folder in PurePosixPath(path).parents
                             for folder in folders))


def is_done(shown: dict) -> bool:
    metadata = shown.get("metadata")
    return isinstance(metadata, dict) and metadata.get(STATE_KEY) == DONE


def to_run(epic: str, shown: dict, branch: str, settings: dict, home: Path, main_tree: Path) -> TidyToRun | None:
    """The tidy this pass still owes, or None when it is done or the epic holds no file to tidy. The worktree is cut
    again from the epic branch's head when its folder is gone."""
    if is_done(shown):
        return None
    head = head_of(f"refs/heads/{branch}", main_tree)
    if head is None:
        raise TidyError(f"the epic branch {branch} does not exist")
    files = epic_files(head, settings, main_tree)
    if not files:
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
            raise TidyError(str(error)) from error
    git_exclude.add(git_exclude.exclude_file(main_tree), [git_exclude.exclude_line(SCRATCH_FOLDER, True)])
    (path / SCRATCH_FOLDER).mkdir(exist_ok=True)
    return TidyToRun(epic, branch, head, path, files)


def settle(epic: str, branch: str, settings: dict, home: Path, main_tree: Path) -> Tidied:
    """Commits what the tidy worker left as one commit on the epic branch and records that the tidy is done."""
    shown = bd_show(epic, main_tree)
    if shown is None:
        raise TidyError(f"bd show printed nothing usable for {epic}")
    owed = to_run(epic, shown, branch, settings, home, main_tree)
    if owed is None:
        raise TidyError(f"{epic} waits on no tidy, so nothing was written")
    changed = cleanup.changed_paths(owed.worktree)
    stray = [path for path in changed if path not in owed.files]
    if stray:
        raise TidyError(f"the tidy changed paths that are not files the epic added or changed: "
                        f"{', '.join(stray)}, so nothing was written")
    head = owed.head
    if changed:
        run(["git", "commit", "--quiet", "--message", COMMIT_MESSAGE], owed.worktree, env_as_factory())
        head = head_of("HEAD", owed.worktree) or owed.head
        move_epic_branch(branch, owed.head, head, home, main_tree)
    remove_worktree(owed.worktree, main_tree)
    env = env_as_factory()
    run(["bd", "comment", epic, comment_of(changed, head)], main_tree, env)
    run(["bd", "update", epic, "--set-metadata", f"{STATE_KEY}={DONE}"], main_tree, env)
    return Tidied(head, changed)


def comment_of(changed: list[str], head: str) -> str:
    if not changed:
        return f"No comments and unslop changed no file, and the epic branch stays at {head}."
    return "\n".join([f"No comments and unslop changed {len(changed)} files, in the commit {head}:",
                      *(f"- {path}" for path in changed)])
