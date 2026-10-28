"""The stages of a finished epic's pass, in their order, and the report modes that settle them.

The scheduler asks this module which stage the epic still owes and which stage a `report-*` mode settles, and it
prints what the mode's `settle` returns. A stage's own work around its settling, such as the tidy's discovered work,
sits behind its mode's `settle`, so the scheduler reads no stage by name.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import cleanup
import discovered
import review
import tidy
from commands import SCRATCH_FOLDER
from epic_reader import Epic, recorded_branch

TIDY_AREA = "tidy"


class Settled(Protocol):
    """What a settled stage returns: the fields the scheduler prints under the stage's key."""

    def fields(self) -> dict: ...


@dataclass(frozen=True)
class ReportMode:
    """A `report-*` mode: the key its settled fields print under, its help, and the call that settles the stage."""
    key: str
    help: str
    settle: Callable[[str, str, dict, Path, Path], Settled]


def tidy_findings(epic: str, main_tree: Path) -> list[discovered.Finding]:
    """The work the tidy worker discovered.

    The tidy has no task to block, so a finding placed `blocks` refuses the report, as an unusable report does.
    """
    try:
        findings = discovered.read_findings(tidy.worktree_of(epic, main_tree) / SCRATCH_FOLDER)
        if discovered.blockers_in(findings):
            raise discovered.DiscoveryError(f"the tidy has no task to block, so no finding is placed "
                                            f"{discovered.BLOCKS}; place each one {discovered.EPIC} or "
                                            f"{discovered.OUTSIDE}")
    except discovered.DiscoveryError as error:
        raise tidy.TidyError(f"the tidy's discovered work cannot be filed, so nothing was written: {error}") \
            from error
    return findings


def settle_tidy(epic: str, branch: str, settings: dict, home: Path, main_tree: Path) -> tidy.Tidied:
    """Settles the tidy, and files the work its worker discovered. The findings are read first, because settling
    removes the worktree that holds them, and a report that cannot be used refuses the settle."""
    findings = tidy_findings(epic, main_tree)
    settled = tidy.settle(epic, branch, settings, home, main_tree)
    discovered.file_findings(findings, epic, TIDY_AREA, epic, main_tree)
    return settled


REPORT_MODES = {
    "report-cleanup": ReportMode("cleanup", "take the test cleanup worker's report, and print the next moves",
                                 cleanup.settle),
    "report-tidy": ReportMode("tidy", "take the tidy worker's word that it is done, and print the next moves",
                              settle_tidy),
    "report-review": ReportMode("review", "take the reports of the review's lanes, and print the next moves",
                                review.settle),
    "report-fix": ReportMode("fix", "take the fix worker's word that it is done, and print the next moves",
                             review.settle_fix),
}


def pass_stage_actions(epic: Epic, settings: dict, home: Path, main_tree: Path) -> list[dict]:
    """The actions of the first stage of the pass that a finished epic still owes, in the order test cleanup, tidy,
    fix, review; empty when only validation is left. A fix owed comes before a review, so the fix of one review is
    never reviewed as the next one's diff."""
    branch = recorded_branch(epic)
    cleaned = cleanup.to_run(epic.id, epic.shown, branch, settings, home, main_tree)
    if cleaned is not None:
        return [cleaned.fields()]
    tidied = tidy.to_run(epic.id, epic.shown, branch, settings, home, main_tree)
    if tidied is not None:
        return [tidied.fields()]
    fixing = review.fix_to_run(epic.id, epic.shown, branch, settings, home, main_tree)
    if fixing is not None:
        return [fixing.fields()]
    reviewing = review.to_run(epic.id, epic.shown, branch, settings, home, main_tree)
    return reviewing.actions() if reviewing is not None else []
