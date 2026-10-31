"""The merge worker of a validation, and the settling of its report.

Validation runs its suite on main merged into the epic branch, in its own worktree. `to_run` makes that merge before
validation runs. When it conflicts, as it does once another epic landed on the same lines, the worktree stays at the
epic branch's head and the scheduler prints a `merge` action with no task: the epic, its branch, the worktree, the
files that conflict and the reason. The action is repeated on every call until it is reported. The epic records
`validation.merge`, the epic head and main's head the merge is owed on, when the action is first printed, and
validation takes it off when it records its verdict, so every reader asks the epic and not the file system whether a
merge worker is owed. The manager starts a merge worker in the worktree. The worker merges main, resolves the
conflicts, adds the resolved paths and commits the merge, and ends `done` or `failed`. It runs no tests, because
validation's full suite follows.

`report-merge` settles the report. A `done` whose worktree holds a finished merge of main into the epic branch counts
nothing, and the next validation runs the full suite on that merge and moves the epic branch there. Any other
`done`, and a `failed`, is a try of the merge worker: `validation.mergetries` goes up by one, a comment says why, and
the worktree goes back to the epic branch's head so the worker starts again. The try that reaches caps.MERGE_TRY_CAP
parks the epic with the human label and a question, and the count starts again, so a human who takes the label off
gives the worker a new set of tries. A cutoff is no try. A merge that validates clears the count.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import caps
import merge_gate
import notify
import park
import private_docs
import targeted_tests
from commands import (NONE_YET, SCRATCH_FOLDER, capture, env_as_factory, head_of, metadata_of, read_bead, run,
                      set_metadata, unset_metadata)
from epic_branch import branch_head, required_head
from epic_reader import recorded_branch
from pass_support import MAIN_BRANCH, PassError, count_of, park_epic, worktree_at
from settings_reader import Settings
from worktrees import cut_detached, remove_worktree, stage_without_scratch, stage_worktree, unmerged_files

WORKTREE_PREFIX = "validation-"
MERGE_KEY = "validation.merge"
TRIES_KEY = "validation.mergetries"
STAGE = "validation-merge"
SCRIPT = "scheduler"
MERGE_BY_HAND = "Merge main by hand"
RUN_AGAIN = "Run the merge worker again"
OPTIONS = [{"name": MERGE_BY_HAND, "confidence": 60}, {"name": RUN_AGAIN, "confidence": 40}]


class MergeError(PassError):
    """A reason the merge of a validation writes nothing more, worded for the person who reads stderr."""


@dataclass(frozen=True)
class MergeToRun:
    """The merge of main into the epic branch that a merge worker makes in the validation worktree, which waits at
    the epic branch's head: the epic, its branch and head, main's head, the worktree and the files that conflict.
    The files are empty while a merge the worker began has none left to resolve."""
    epic: str
    branch: str
    head: str
    base: str
    worktree: Path
    files: list[str]

    @property
    def reason(self) -> str:
        if not self.files:
            return f"the merge of {MAIN_BRANCH} into {self.branch} is begun and not committed"
        return f"merging {MAIN_BRANCH} into {self.branch} conflicts in {', '.join(self.files)}"

    @property
    def marker(self) -> str:
        return f"{self.head}:{self.base}"

    def fields(self) -> dict:
        return {"action": "merge", "epic": self.epic, "branch": self.branch, "head": self.head, "base": self.base,
                "worktree": str(self.worktree), "scratch": str(self.worktree / SCRATCH_FOLDER),
                "reason": self.reason, "files": self.files}


@dataclass(frozen=True)
class Merged:
    """What a merge worker's done left: whether the worktree holds the finished merge, and its head when it does."""
    reconciled: bool
    head: str | None

    def fields(self) -> dict:
        return {"reconciled": self.reconciled, "head": self.head}


@dataclass(frozen=True)
class Waiting:
    """The merge an epic's validation waits on: the epic branch and its head, and the worktree the worker merges in."""
    branch: str
    head: str
    worktree: Path


def worktree_of(epic: str, main_tree: Path) -> Path:
    """The validation worktree of the epic, where main is merged into the epic branch and the suite then runs."""
    return stage_worktree(WORKTREE_PREFIX, epic, main_tree)


def is_merging(path: Path) -> bool:
    """True when the worktree is in the middle of a merge, with conflicts to resolve or a merge to commit."""
    return capture(["git", "rev-parse", "--quiet", "--verify", "MERGE_HEAD"], path, None).returncode == 0


def back_to(path: Path, head: str) -> None:
    """Puts the validation worktree back at the head with no merge begun and nothing left of a worker's edits, apart
    from the scratch folder."""
    env = env_as_factory()
    capture(["git", "merge", "--abort"], path, env)
    run(["git", "reset", "--quiet", "--hard", head], path, env)
    run(["git", "clean", "--quiet", "--force", "-d"], path, env)


def finished_merge(path: Path, epic_head: str, main_tree: Path) -> bool:
    """True when the validation worktree holds the epic head and main's head with no merge in progress, whether a merge
    worker committed the merge or main was already in the epic branch."""
    if not path.is_dir():
        return False
    head = head_of("HEAD", path)
    base = head_of(f"refs/heads/{MAIN_BRANCH}", main_tree)
    if head is None or base is None or is_merging(path):
        return False
    return merge_gate.contains(epic_head, head, main_tree) and merge_gate.contains(base, head, main_tree)


def merged_worktree(epic: str, epic_head: str, main_tree: Path) -> tuple[Path, str]:
    """The validation worktree where main is merged into the epic branch, and its head. Refuses when the worktree holds
    no such merge, which `to_run` settles before validation runs."""
    path = worktree_of(epic, main_tree)
    head = head_of("HEAD", path) if finished_merge(path, epic_head, main_tree) else None
    if head is None:
        raise MergeError(f"{path} holds no finished merge of {MAIN_BRANCH} into the epic branch, so {epic} was not "
                         "validated. Run the scheduler again")
    return path, head


def marker_cleared() -> list[str]:
    """The arguments of a `bd update` that take the merge marker off the epic, because a validated merge owes no merge
    worker."""
    return unset_metadata(MERGE_KEY)


def fold_into_merge(path: Path, epic_head: str) -> None:
    """Amends the merge commit with whatever a merge worker left outside it, except the scratch folder. The epic head
    itself is never amended."""
    if head_of("HEAD", path) != epic_head and stage_without_scratch(path):
        run(["git", "commit", "--quiet", "--amend", "--no-edit"], path, env_as_factory())


def conflicting_files(path: Path, epic_head: str) -> list[str]:
    """The files that merging main into the epic head conflicts in, found in the validation worktree, which is left at
    the epic head. Empty when the merge goes through."""
    back_to(path, epic_head)
    try:
        targeted_tests.bring_in_base_branch(MAIN_BRANCH, path, targeted_tests.Integration.MERGE)
    except targeted_tests.MergeConflict as conflict:
        return conflict.files
    except targeted_tests.TestRunError:
        return []
    back_to(path, epic_head)
    return []


def merge_main(epic: str, epic_head: str, home: Path, main_tree: Path) -> list[str]:
    """Cuts the validation worktree afresh from the epic head and merges main into it; returns the files that conflict.

    A merge that goes through leaves the worktree at the merge. One that conflicts is aborted, and the worktree stays at
    the epic head with no merge begun, for a merge worker.
    """
    path = worktree_of(epic, main_tree)
    if path.exists():
        run(["git", "worktree", "remove", "--force", str(path)], main_tree, None)
    try:
        cut_detached(path, epic_head, home, main_tree)
    except private_docs.ClashError as error:
        raise MergeError(str(error)) from error
    try:
        targeted_tests.bring_in_base_branch(MAIN_BRANCH, path, targeted_tests.Integration.MERGE)
    except targeted_tests.MergeConflict as conflict:
        worktree_at(path, epic_head, home, main_tree)
        return conflict.files
    except targeted_tests.TestRunError as error:
        remove_worktree(path, main_tree)
        raise MergeError(str(error)) from error
    if head_of("HEAD", path) is None:
        remove_worktree(path, main_tree)
        raise MergeError(f"{path} has no commit after the merge of {MAIN_BRANCH}")
    return []


def owes_merge(shown: dict) -> bool:
    """True when the epic records that its validation waits on a merge worker."""
    return MERGE_KEY in metadata_of(shown)


def owed(merge: MergeToRun, shown: dict, main_tree: Path) -> MergeToRun:
    """Records on the epic the merge it owes, unless it records that one already, and returns the merge."""
    if metadata_of(shown).get(MERGE_KEY) != merge.marker:
        run(["bd", "update", merge.epic, *set_metadata((MERGE_KEY, merge.marker))], main_tree, env_as_factory())
    return merge


def to_run(epic: str, shown: dict, branch: str, home: Path, main_tree: Path) -> MergeToRun | None:
    """The merge a merge worker owes validation, or None when main is merged into the epic branch in the validation
    worktree. It makes that merge when the worktree holds none, and a merge that conflicts is the one it returns."""
    epic_head = required_head(branch, main_tree, MergeError)
    base = head_of(f"refs/heads/{MAIN_BRANCH}", main_tree) or ""
    path = worktree_of(epic, main_tree)
    if path.exists():
        if finished_merge(path, epic_head, main_tree):
            return None
        if is_merging(path):
            return owed(MergeToRun(epic, branch, epic_head, base, path, unmerged_files(path)), shown, main_tree)
    conflicts = merge_main(epic, epic_head, home, main_tree)
    if not conflicts:
        return None
    return owed(MergeToRun(epic, branch, epic_head, base, path, conflicts), shown, main_tree)


def waiting_on(epic: str, shown: dict, main_tree: Path) -> Waiting:
    """The merge the epic waits on; refuses when the epic records none or its worktree is gone."""
    worktree = worktree_of(epic, main_tree)
    branch = recorded_branch(shown)
    head = branch_head(branch, main_tree) if branch else None
    if head is None or not worktree.is_dir() or not owes_merge(shown):
        raise MergeError(f"{epic} waits on no merge worker, so nothing was written")
    return Waiting(branch, head, worktree)


def question_text(epic: str, waiting: Waiting, tries: int, files: list[str], why: str) -> str:
    conflicts = f" It conflicts in {', '.join(files)}." if files else ""
    return "\n".join([
        f"{park.QUESTION_PREFIX}the merge worker failed {tries} of {caps.MERGE_TRY_CAP} tries to merge {MAIN_BRANCH} "
        f"into {waiting.branch}, so validation of {epic} ran no tests and the epic is parked.{conflicts}", "",
        f"The last try failed because {why}.", "",
        *(f"- {each['name']} ({each['confidence']}%)" for each in OPTIONS), "",
        f"Recommended: {MERGE_BY_HAND}. Merge {MAIN_BRANCH} into {waiting.branch} yourself, then take the human label "
        "off the epic, and validation runs on the merged branch. Taking the label off without a merge gives the merge "
        f"worker {caps.MERGE_TRY_CAP} new tries."])


def park_at_the_cap(epic: str, waiting: Waiting, tries: int, why: str, main_tree: Path) -> None:
    files = conflicting_files(waiting.worktree, waiting.head)
    park_epic(epic, question_text(epic, waiting, tries, files, why),
              {TRIES_KEY: str(NONE_YET), park.OPTIONS_KEY: json.dumps(OPTIONS), park.RECOMMENDED_KEY: MERGE_BY_HAND},
              main_tree)
    remove_worktree(waiting.worktree, main_tree)


def count_try(epic: str, shown: dict, waiting: Waiting, why: str, main_tree: Path) -> bool:
    """Counts a failed try of the merge worker; returns True when it parked the epic."""
    tries = count_of(shown, TRIES_KEY) + 1
    parked = caps.count_against_cap(
        epic, tries, caps.MERGE_TRY_CAP, lambda: park_at_the_cap(epic, waiting, tries, why, main_tree),
        f"Merge try {tries} of {caps.MERGE_TRY_CAP} failed: {why}. The merge worker starts again.",
        set_metadata((TRIES_KEY, tries)), main_tree)
    if not parked:
        back_to(waiting.worktree, waiting.head)
    return parked


def count_ended_run(epic: str, ended: str, why: str | None, main_tree: Path) -> bool:
    """Counts a merge worker that ended `failed` as a try; a worker that was cut off counts nothing. Returns True when
    it parked the epic."""
    shown = read_bead(epic, main_tree)
    waiting = waiting_on(epic, shown, main_tree)
    if ended != "failed":
        return False
    return count_try(epic, shown, waiting, why or "the merge worker ended failed with no reason", main_tree)


def settle(epic: str, branch: str, settings: Settings, home: Path, main_tree: Path) -> Merged:
    """Takes the merge worker's done: a finished merge waits for the next validation, and anything else is a try."""
    shown = read_bead(epic, main_tree)
    waiting = waiting_on(epic, shown, main_tree)
    if not finished_merge(waiting.worktree, waiting.head, main_tree):
        why = f"the validation worktree holds no finished merge of {MAIN_BRANCH} into {waiting.branch}"
        if count_try(epic, shown, waiting, why, main_tree):
            notify.announce(notify.EPIC_PARKED, epic, home, main_tree, SCRIPT)
        return Merged(False, None)
    fold_into_merge(waiting.worktree, waiting.head)
    if count_of(shown, TRIES_KEY):
        run(["bd", "update", epic, *unset_metadata(TRIES_KEY)], main_tree, env_as_factory())
    return Merged(True, head_of("HEAD", waiting.worktree))
