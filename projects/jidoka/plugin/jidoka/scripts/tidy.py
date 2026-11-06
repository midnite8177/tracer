"""Tidy, the stage of a pass after test cleanup, which runs no-comments and unslop over the epic's files in tidy
batches, side by side, without asking anyone.

The scheduler calls `to_run` once every task of an epic is closed and its test cleanup is done. When the epic branch
differs from main in files outside every app's acceptance folder, which is protected, it cuts a detached worktree at
.worktrees/tidy-<epic> from the epic branch's head and hands the scheduler one `tidy` action for each tidy batch, each
for a worker on the local tier. A batch is a slice of those files, sorted by path, of at most BATCH_FILES files and,
unless it holds one file, at most BATCH_BYTES bytes at the epic branch's head, so no worker runs out of effort before
it has read its files. The batches share the worktree and its head, and each has a scratch folder of its own,
.scratch/batch-<n>. Each action also holds `base`, the commit where the epic branch left main, so a worker can see what
the epic changed in its batch's files, from the base to the head. Each worker follows the two skills in their
unattended mode over its batch alone, asks no question, starts no workers, commits nothing, and lists the work it found
outside its files in its scratch folder's discovered-work report, which `settle` files in the epic, once for each
title.

The manager reports the tidy once, after every batch's worker ended done. `settle` takes their word: it refuses, and
writes nothing, when the worktree changed a path outside the epic's files that the epic's head already holds (a new
file is accepted, unless it lies in an acceptance folder), or when the worktree is gone or at another head than the
workers started from. Otherwise it commits the change as one commit, "No comments and unslop", fast-forwards the epic
branch to it under the merge lock, and with BEADS_ACTOR set to jidoka records on the epic `tidy.state` (done) and posts
a comment. A tidy that changes nothing makes no commit. Validation clears `tidy.state` when it ends red, so the next
pass tidies again.

An epic on the local-model trial tidies twice in its first pass, as tidy_trial.py says; it calls `to_run_as` with the
stage and the `TidyRoute` of each tidy, and `settle_recording` for the tidy that lands.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

import discovered
import pass_support
import routes
from commands import env_as_factory, read_bead, run, set_metadata
from pass_support import (MAIN_BRANCH, Committed, PassError, Stage, StageToRun, accepts_any_change, every_file,
                          worktree_at)
from settings_reader import Settings

STATE_KEY = "tidy.state"
ACTION = "tidy"
AREA = "tidy"
BATCH_FILES = 4
BATCH_BYTES = 40_000
BATCH_FOLDER_PREFIX = "batch-"


class TidyError(PassError):
    """A reason the tidy writes nothing more, worded for the person who reads stderr."""


STAGE = Stage(name="tidy", action=ACTION, prefix="tidy-", state_key=STATE_KEY,
              commit_message="No comments and unslop", allowed_kind="files the epic added or changed",
              may_add_files=True, files_key="files", wants=every_file, report=None, error=TidyError)
LOCAL_STAGE = replace(STAGE, prefix="local-tidy-")


@dataclass(frozen=True)
class SizedFile:
    """A file of the epic and its size in bytes at the epic branch's head."""
    path: str
    size: int


@dataclass(frozen=True)
class TidyRoute:
    """Which route one tidy of the local-model trial is for, which its actions name: `route`, and for a native tidy
    `native_route`, the native route of the local tier."""
    route: str
    native_route: routes.Route | None

    def fields(self) -> dict:
        if self.native_route is None:
            return {"route": self.route}
        return {"route": self.route, "native_route": self.native_route.as_dict()}


@dataclass(frozen=True)
class TidyToRun:
    """The tidy a pass owes: the stage over every file of the epic, which the settle checks the worktree against, the
    tidy batches its workers take, in order, the epic's base, and the route of the tidy when the local-model trial runs
    it, which every action names."""
    stage: StageToRun
    batches: list[list[str]]
    base: str
    route: TidyRoute | None

    def scratch_of(self, number: int) -> Path:
        return self.stage.scratch / f"{BATCH_FOLDER_PREFIX}{number}"

    def scratch_folders(self) -> list[Path]:
        return [self.scratch_of(number) for number in range(1, len(self.batches) + 1)]

    def actions(self) -> list[dict]:
        named = self.route.fields() if self.route is not None else {}
        return [{**self.stage.fields(), "batch": number, "scratch": str(self.scratch_of(number)),
                 "base": self.base, self.stage.stage.files_key: files, **named}
                for number, files in enumerate(self.batches, 1)]


def worktree_of(epic: str, main_tree: Path) -> Path:
    return STAGE.worktree_of(epic, main_tree)


def batches_of(files: list[SizedFile], most_files: int, most_bytes: int) -> list[list[str]]:
    """The files in batches, in path order. A batch takes the next file while it holds fewer than `most_files` files
    and the file keeps its total within `most_bytes`. A file larger than `most_bytes` gets a batch of its own."""
    batches: list[list[str]] = []
    total = 0
    for each in sorted(files, key=lambda sized: sized.path):
        if not batches or len(batches[-1]) >= most_files or total + each.size > most_bytes:
            batches.append([])
            total = 0
        batches[-1].append(each.path)
        total += each.size
    return batches


def sizes_at(head: str, files: list[str], main_tree: Path) -> list[SizedFile]:
    """Each file with its size in the commit, read from git, so the batches stay the same while the head does."""
    listed = run(["git", "--literal-pathspecs", "ls-tree", "-r", "-l", "-z", head, "--", *files], main_tree, None)
    sizes = {}
    for entry in filter(None, listed.split("\0")):
        described, path = entry.split("\t", 1)
        size = described.split()[3]
        sizes[path] = int(size) if size.isdigit() else 0
    return [SizedFile(path, sizes.get(path, 0)) for path in files]


def base_of(head: str, main_tree: Path) -> str:
    """The epic's base: the commit where the epic branch left main."""
    return run(["git", "merge-base", MAIN_BRANCH, head], main_tree, None).strip()


def diff_of(base: str, head: str, files: list[str], main_tree: Path) -> str:
    """What the epic changed in the files, from its base to the head."""
    return run(["git", "--literal-pathspecs", "diff", base, head, "--", *files], main_tree, None)


def tidy_of(found: StageToRun, route: TidyRoute | None, main_tree: Path) -> TidyToRun:
    batches = batches_of(sizes_at(found.head, found.files, main_tree), BATCH_FILES, BATCH_BYTES)
    return TidyToRun(found, batches, base_of(found.head, main_tree), route)


def to_run(epic: str, shown: dict, branch: str, settings: Settings, home: Path, main_tree: Path) -> TidyToRun | None:
    """The tidy this pass still owes, or None when it is done or the epic holds no file to tidy. The worktree is cut
    again from the epic branch's head when its folder is gone, and each batch's scratch folder is made in it."""
    return to_run_as(STAGE, None, epic, shown, branch, settings, home, main_tree)


def to_run_as(stage: Stage, route: TidyRoute | None, epic: str, shown: dict, branch: str, settings: Settings,
              home: Path, main_tree: Path) -> TidyToRun | None:
    """The tidy that the stage, whose worktree is its own, still owes. Each action also names the `route`."""
    found = pass_support.owed(stage, epic, shown, branch, settings, main_tree)
    if found is None:
        return None
    worktree_at(found.worktree, found.head, home, main_tree)
    owed = tidy_of(found, route, main_tree)
    for folder in owed.scratch_folders():
        folder.mkdir(exist_ok=True)
    return owed


def batch_folders(scratch: Path) -> list[Path]:
    """The scratch folder of every batch that the tidy's worktree holds, in batch order. The settle reads the folders
    `to_run` made, so it depends on no recomputation of the batches."""
    numbered = []
    for folder in scratch.glob(f"{BATCH_FOLDER_PREFIX}*"):
        number = folder.name[len(BATCH_FOLDER_PREFIX):]
        if folder.is_dir() and number.isdigit():
            numbered.append((int(number), folder))
    return [folder for _, folder in sorted(numbered)]


def discovered_work(folders: list[Path]) -> list[discovered.Finding]:
    """The work the tidy's workers discovered, every batch's report in batch order, with a title an earlier batch
    already listed left out.

    The tidy has no task to block, so a finding placed `blocks` refuses the report, as an unusable report does.
    """
    try:
        findings = [finding for folder in folders for finding in discovered.read_findings(folder)]
        if discovered.blockers_in(findings):
            raise discovered.DiscoveryError(f"the tidy has no task to block, so no finding is placed "
                                            f"{discovered.BLOCKS}; place each one {discovered.EPIC} or "
                                            f"{discovered.OUTSIDE}")
    except discovered.DiscoveryError as error:
        raise TidyError(f"the tidy's discovered work cannot be filed, so nothing was written: {error}") from error
    titles: set[str] = set()
    kept = []
    for finding in findings:
        if finding.title not in titles:
            titles.add(finding.title)
            kept.append(finding)
    return kept


def settle(epic: str, branch: str, settings: Settings, home: Path, main_tree: Path) -> Committed:
    return settle_recording(epic, branch, settings, home, main_tree, lambda settled: [])


def settle_recording(epic: str, branch: str, settings: Settings, home: Path, main_tree: Path,
                     recorded: Callable[[Committed], list[tuple[str, str]]]) -> Committed:
    """Commits what the tidy's workers left as one commit on the epic branch, records that the tidy is done together
    with the metadata that `recorded` gives for the commit, and files the work the workers discovered. The findings
    are read before the commit, because settling removes the worktree that holds them, and a report that cannot be
    used refuses the settle."""
    shown = read_bead(epic, main_tree)
    found = pass_support.owed_in_worktree(STAGE, epic, shown, branch, settings, main_tree)
    findings = discovered_work(batch_folders(found.scratch))
    settled = pass_support.settle_worktree(found, accepts_any_change, settings, home, main_tree)
    env = env_as_factory()
    run(["bd", "comment", epic, settled.comment(STAGE.commit_message)], main_tree, env)
    run(["bd", "update", epic, *set_metadata((STATE_KEY, pass_support.DONE), *recorded(settled))], main_tree, env)
    discovered.file_findings(findings, epic, AREA, epic, main_tree)
    return settled
