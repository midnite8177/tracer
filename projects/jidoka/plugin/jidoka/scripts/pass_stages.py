"""The stages of a finished epic's pass, in their order, and the report modes that settle them.

The order is test cleanup, tidy, the review's fix, review, validation, and the run of the holdouts that validation
leaves waiting. The scheduler asks this module to take the epic through its pass and which stage a `report-*` mode
settles, and it prints what the module returns and what a mode's `settle` returns. A stage's own work around its
settling sits behind its mode's `settle`, so the scheduler reads no stage by name.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import cleanup
import holdouts_run
import review
import tidy
import validation
from epic_reader import Epic
from epics import state_of


class Settled(Protocol):
    """What a settled stage returns: the fields the scheduler prints under the stage's key."""

    def fields(self) -> dict: ...


@dataclass(frozen=True)
class ReportMode:
    """A `report-*` mode: the key its settled fields print under, the name its workers' ledger rows carry as their
    stage, its help, and the call that settles the stage."""
    key: str
    stage: str
    help: str
    settle: Callable[[str, str, dict, Path, Path], Settled]


REPORT_MODES = {
    "report-cleanup": ReportMode("cleanup", cleanup.ACTION,
                                 "take the test cleanup worker's report, and print the next moves", cleanup.settle),
    "report-tidy": ReportMode("tidy", tidy.ACTION,
                              "take the tidy worker's word that it is done, and print the next moves", tidy.settle),
    "report-review": ReportMode("review", review.REVIEW_ACTION,
                                "take the reports of the review's lanes, and print the next moves", review.settle),
    "report-fix": ReportMode("fix", review.FIX_ACTION,
                             "take the fix worker's word that it is done, and print the next moves",
                             review.settle_fix),
}


@dataclass(frozen=True)
class PassRun:
    """What a finished epic's pass did in one call: the actions of the stage it still owes, or else the validation it
    ran and the run of the holdouts that validation left waiting."""
    actions: list[dict]
    validated: validation.Validated | None
    holdouts: holdouts_run.HoldoutsToRun | None


def run_pass(epic: Epic, settings: dict, home: Path, main_tree: Path) -> PassRun:
    """Takes a finished epic through its pass in order: the first stage it still owes, and when it owes none, its
    validation."""
    actions = pass_stage_actions(epic, settings, home, main_tree)
    if actions:
        return PassRun(actions, None, None)
    validated = validation.validate(epic.id, epic.branch, settings, home, main_tree)
    return PassRun([], validated, holdouts_run.waiting_on(epic.id, validated))


def holdouts_owed(epic: Epic, home: Path, main_tree: Path) -> holdouts_run.HoldoutsToRun | None:
    """The run of the holdouts that an epic waits on, when no human label holds it; None when it waits on none. This
    is the run a restarted manager hands out again."""
    state = state_of(epic.shown)
    if state.labeled_for_human or not state.awaiting_holdouts:
        return None
    return holdouts_run.holdouts_to_run(epic.id, epic.shown, home, main_tree)


def pass_stage_actions(epic: Epic, settings: dict, home: Path, main_tree: Path) -> list[dict]:
    """The actions of the first stage of the pass that a finished epic still owes, in the order test cleanup, tidy,
    fix, review; empty when only validation is left. A fix owed comes before a review, so the fix of one review is
    never reviewed as the next one's diff."""
    branch = epic.branch
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
