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
import notify
import park
import validation
from commands import (NONE_YET, SCRATCH_FOLDER, env_as_factory, head_of, metadata_of, read_bead, run, set_metadata,
                      unset_metadata)
from epic_branch import branch_head, required_head
from epic_reader import recorded_branch
from pass_support import MAIN_BRANCH, count_of, park_epic
from validation import MERGE_KEY, ValidationError
from worktrees import remove_worktree

TRIES_KEY = "validation.mergetries"
STAGE = "validation-merge"
SCRIPT = "scheduler"
MERGE_BY_HAND = "Merge main by hand"
RUN_AGAIN = "Run the merge worker again"
OPTIONS = [{"name": MERGE_BY_HAND, "confidence": 60}, {"name": RUN_AGAIN, "confidence": 40}]


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
    epic_head = required_head(branch, main_tree, ValidationError)
    base = head_of(f"refs/heads/{MAIN_BRANCH}", main_tree) or ""
    path = validation.worktree_of(epic, main_tree)
    if path.exists():
        if validation.finished_merge(path, epic_head, main_tree):
            return None
        if validation.is_merging(path):
            return owed(MergeToRun(epic, branch, epic_head, base, path, validation.unmerged_files(path)), shown,
                        main_tree)
    conflicts = validation.merge_main(epic, epic_head, home, main_tree)
    if not conflicts:
        return None
    return owed(MergeToRun(epic, branch, epic_head, base, path, conflicts), shown, main_tree)


def waiting_on(epic: str, shown: dict, main_tree: Path) -> Waiting:
    """The merge the epic waits on; refuses when the epic records none or its worktree is gone."""
    worktree = validation.worktree_of(epic, main_tree)
    branch = recorded_branch(shown)
    head = branch_head(branch, main_tree) if branch else None
    if head is None or not worktree.is_dir() or not owes_merge(shown):
        raise ValidationError(f"{epic} waits on no merge worker, so nothing was written")
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
    files = validation.conflicting_files(waiting.worktree, waiting.head)
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
        validation.back_to(waiting.worktree, waiting.head)
    return parked


def count_ended_run(epic: str, ended: str, why: str | None, main_tree: Path) -> bool:
    """Counts a merge worker that ended `failed` as a try; a worker that was cut off counts nothing. Returns True when
    it parked the epic."""
    shown = read_bead(epic, main_tree)
    waiting = waiting_on(epic, shown, main_tree)
    if ended != "failed":
        return False
    return count_try(epic, shown, waiting, why or "the merge worker ended failed with no reason", main_tree)


def settle(epic: str, branch: str, settings: dict, home: Path, main_tree: Path) -> Merged:
    """Takes the merge worker's done: a finished merge waits for the next validation, and anything else is a try."""
    shown = read_bead(epic, main_tree)
    waiting = waiting_on(epic, shown, main_tree)
    if not validation.finished_merge(waiting.worktree, waiting.head, main_tree):
        why = f"the validation worktree holds no finished merge of {MAIN_BRANCH} into {waiting.branch}"
        if count_try(epic, shown, waiting, why, main_tree):
            notify.announce(notify.EPIC_PARKED, epic, home, main_tree, SCRIPT)
        return Merged(False, None)
    validation.fold_into_merge(waiting.worktree, waiting.head)
    if count_of(shown, TRIES_KEY):
        run(["bd", "update", epic, *unset_metadata(TRIES_KEY)], main_tree, env_as_factory())
    return Merged(True, head_of("HEAD", waiting.worktree))
