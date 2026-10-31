"""The skeleton of a pass stage whose worker edits files in a detached worktree of its own, as the test cleanup, the
tidy and the review's fix do, with the error, the metadata count and the parking that every stage of a pass shares.

What is owed, the read of it that cuts no worktree, the cut, and the settle that refuses a worktree the worker no
longer holds are the `Stage` record's skeleton. No stage owns these. Each stage keeps its own metadata keys in its own
module, and this module holds no key.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import git_exclude
import park
import private_docs
from commands import (HUMAN_LABEL, SCRATCH_FOLDER, NotAWholeNumber, capture, count_in, env_as_factory, head_of,
                      metadata_of, run, set_metadata)
from epic_branch import (EditedCheckout, EpicBranchLeftTheHead, fast_forward, refuse_edited_checkout,
                         required_head)
from land import merge_locked
from merge_gate import is_protected, protected_folders
from worktrees import added_since_head, cut_detached, remove_worktree, stage_without_scratch, stage_worktree

MAIN_BRANCH = "main"
DONE = "done"


class PassError(Exception):
    """A reason a stage writes nothing more, worded for the person who reads stderr. Each stage raises a subclass of
    its own, so one except clause takes them all."""


def count_of(shown: dict, key: str) -> int:
    """The whole number the epic's metadata holds under the key, or none when it holds nothing."""
    try:
        return count_in(metadata_of(shown), key)
    except NotAWholeNumber as error:
        raise PassError(f"on the epic, {error}") from error


@dataclass(frozen=True)
class Stage:
    """A stage of a pass whose worker edits files in a detached worktree of its own: its name in a refusal, the
    action it prints, the prefix of its worktree's folder, the metadata key that records it done (none for a stage that
    is owed by other means), the commit it settles with, which files of the epic it may touch and how the action
    names them, whether its worker may also add a file that is not at the epic's head, the report its worker writes
    in the scratch folder (none when the stage has no report), and the error it raises."""
    name: str
    action: str
    prefix: str
    state_key: str | None
    commit_message: str
    allowed_kind: str
    may_add_files: bool
    files_key: str
    wants: Callable[[str], bool]
    report: str | None
    error: type[PassError]

    def worktree_of(self, epic: str, main_tree: Path) -> Path:
        return stage_worktree(self.prefix, epic, main_tree)

    def is_done(self, shown: dict) -> bool:
        return self.state_key is not None and metadata_of(shown).get(self.state_key) == DONE


@dataclass(frozen=True)
class StageToRun:
    """What a stage owes: the commit its worker starts from, the worktree where one belongs, and the files it may
    touch."""
    stage: Stage
    epic: str
    branch: str
    head: str
    worktree: Path
    files: list[str]

    @property
    def scratch(self) -> Path:
        return self.worktree / SCRATCH_FOLDER

    def fields(self) -> dict:
        printed = {"action": self.stage.action, "epic": self.epic, "branch": self.branch, "head": self.head,
                   "worktree": str(self.worktree), "scratch": str(self.scratch)}
        if self.stage.report is not None:
            printed["report"] = str(self.scratch / self.stage.report)
        printed[self.stage.files_key] = self.files
        return printed


@dataclass(frozen=True)
class Committed:
    """What settling a stage's worktree did: the commit the epic branch now ends with, or its old head when the worker
    changed nothing, and the paths the commit changed."""
    head: str
    changed: list[str]

    def fields(self) -> dict:
        return {"head": self.head, "changed": self.changed}

    def comment(self, subject: str) -> str:
        """The comment on the epic that says what the stage named by `subject` changed."""
        if not self.changed:
            return f"{subject} changed no file, and the epic branch stays at {self.head}."
        return "\n".join([f"{subject} changed {len(self.changed)} files, in the commit {self.head}:",
                          *(f"- {path}" for path in self.changed)])


def every_file(path: str) -> bool:
    return True


def accepts_any_change(changed: list[str]) -> None:
    """The check of a stage whose worker reports nothing that the change must agree with."""


def owed(stage: Stage, epic: str, shown: dict, branch: str, settings: dict, main_tree: Path) -> StageToRun | None:
    """The stage this pass still owes, or None when it is done or the epic holds no file for it. It cuts no worktree:
    the path in the result is where one belongs."""
    if stage.is_done(shown):
        return None
    head = required_head(branch, main_tree, stage.error)
    files = [path for path in epic_files(head, settings, main_tree) if stage.wants(path)]
    if not files:
        return None
    return StageToRun(stage, epic, branch, head, stage.worktree_of(epic, main_tree), files)


def to_run(stage: Stage, epic: str, shown: dict, branch: str, settings: dict, home: Path,
           main_tree: Path) -> StageToRun | None:
    """The stage this pass still owes, with its worktree cut at the epic branch's head for the worker."""
    found = owed(stage, epic, shown, branch, settings, main_tree)
    if found is not None:
        worktree_at(found.worktree, found.head, home, main_tree)
    return found


def refuse_a_lost_worktree(found: StageToRun) -> None:
    """Refuses to settle a worktree that is gone or at another head than the one the worker started from, because a
    fresh cut would hold none of the worker's edits."""
    if not found.worktree.is_dir() or head_of("HEAD", found.worktree) != found.head:
        raise found.stage.error(f"the worktree {found.worktree} of the {found.stage.name} is gone or is not at "
                                f"{found.head}, so the worker's edits are not in it and nothing was written")


def owed_in_worktree(stage: Stage, epic: str, shown: dict, branch: str, settings: dict,
                     main_tree: Path) -> StageToRun:
    """The stage a worker's report settles, read without cutting a worktree. It refuses when the stage is owed no
    more, or when its worktree is gone or at another head."""
    found = owed(stage, epic, shown, branch, settings, main_tree)
    if found is None:
        raise stage.error(f"{epic} waits on no {stage.name}, so nothing was written")
    refuse_a_lost_worktree(found)
    return found


def settle_worktree(found: StageToRun, check: Callable[[list[str]], None], settings: dict, home: Path,
                    main_tree: Path) -> Committed:
    """Takes what the stage's worker left in its worktree: stages it, refuses a path inside an acceptance folder and
    a path the stage may not touch, lets `check` refuse the changed paths, commits them as one commit, moves the epic
    branch to it and removes the worktree. Nothing is committed when nothing changed."""
    changed = changed_within(found.worktree, found.files, protected_folders(settings), found.stage.name,
                             found.stage.allowed_kind, found.stage.may_add_files)
    check(changed)
    head = found.head
    if changed:
        run(["git", "commit", "--quiet", "--message", found.stage.commit_message], found.worktree, env_as_factory())
        head = head_of("HEAD", found.worktree) or found.head
        move_epic_branch(found.branch, found.head, head, home, main_tree)
    remove_worktree(found.worktree, main_tree)
    return Committed(head, changed)


def epic_files(branch_head: str, settings: dict, main_tree: Path) -> list[str]:
    """The files the epic added or changed, outside every acceptance folder, sorted."""
    folders = protected_folders(settings)
    listed = run(["git", "diff", "--name-only", "--diff-filter=AM", f"{MAIN_BRANCH}...{branch_head}"], main_tree,
                 None).splitlines()
    return sorted(path for path in listed if not is_protected(path, folders))


def park_epic(epic: str, comment: str, metadata: dict[str, str], main_tree: Path) -> None:
    """Parks the epic on the human: the comment says why, the metadata is set, and the human label goes on last, so a
    labeled epic always has its comment."""
    env = env_as_factory()
    run(["bd", "comment", epic, comment], main_tree, env)
    run(["bd", "update", epic, *set_metadata(*metadata.items()), f"--add-label={HUMAN_LABEL}"], main_tree, env)


def park_epic_on_question(epic: str, question: park.Question, metadata: dict[str, str], home: Path,
                          main_tree: Path) -> None:
    """Parks the epic on the human with the question in the one question format: its page is written, its comment
    holds the whole question, and the epic's metadata gets the options and the recommendation beside `metadata`."""
    try:
        page = park.write_page(epic, question, home, main_tree)
    except park.QuestionError as error:
        raise PassError(str(error)) from error
    closing = f"The epic stays parked while it carries the {HUMAN_LABEL} label."
    park_epic(epic, park.question_comment(question, page, closing),
              {**metadata, park.OPTIONS_KEY: park.options_json(question.options),
               park.RECOMMENDED_KEY: question.recommended}, main_tree)


def worktree_at(path: Path, head: str, home: Path, main_tree: Path) -> None:
    """Cuts the detached worktree at the head, again when it holds another commit, with its scratch folder."""
    if path.is_dir() and head_of("HEAD", path) != head:
        remove_worktree(path, main_tree)
    if not path.is_dir():
        capture(["git", "worktree", "prune"], main_tree, None)
        try:
            cut_detached(path, head, home, main_tree)
        except private_docs.ClashError as error:
            raise PassError(str(error)) from error
    git_exclude.add(git_exclude.exclude_file(main_tree), [git_exclude.exclude_line(SCRATCH_FOLDER, True)])
    (path / SCRATCH_FOLDER).mkdir(exist_ok=True)


def changed_within(worktree: Path, allowed: list[str], protected: list[PurePosixPath], stage: str,
                   allowed_kind: str, may_add_files: bool) -> list[str]:
    """Every path the stage's worktree changed, refusing when one lies in a protected folder, whatever the stage may
    add, and when one is not among the allowed paths. A path that is not at the worktree's head is a new file, which
    `may_add_files` allows. `stage` and `allowed_kind` word the refusal."""
    changed = stage_without_scratch(worktree)
    barred = [path for path in changed if is_protected(path, protected)]
    if barred:
        raise PassError(f"the {stage} changed paths inside an acceptance folder: {', '.join(barred)}, so nothing was "
                        "written")
    added = set(added_since_head(worktree)) if may_add_files else set()
    stray = [path for path in changed if path not in allowed and path not in added]
    if stray:
        raise PassError(f"the {stage} changed paths that are not {allowed_kind}: {', '.join(stray)}, so nothing was "
                        "written")
    return changed


def move_epic_branch(branch: str, old: str, new: str, home: Path, main_tree: Path) -> None:
    """Fast-forwards the epic branch from old to new under the merge lock, bringing the main checkout along."""
    if old == new:
        return
    with merge_locked(home):
        try:
            refuse_edited_checkout(branch, main_tree)
        except EditedCheckout as edited:
            raise PassError(f"{edited}. Commit or discard them, then run the scheduler again") from edited
        try:
            fast_forward(branch, old, new, main_tree)
        except EpicBranchLeftTheHead as left:
            raise PassError(f"{left} while a stage ran, so nothing changed. Run the scheduler again") from left
