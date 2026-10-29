"""What the gate script and the gate page both ask about an epic: whether the human can accept it, and whether main or
the epic branch moved since validation.

An epic awaits acceptance when it waits at the gate, or when it is parked on the question the pass cap asks and still
holds open tasks. Validation checked one commit of the epic branch, merged with main. Main moved when it holds a commit
that validated commit lacks, or when no validation is recorded, and the epic branch moved when its head is no longer
the validated commit. The merge runs the full suite again after either move, and the page warns of it.
"""
from __future__ import annotations

from pathlib import Path

import pass_ledger
from commands import MAIN_REF
from epic_branch import branch_head, required_head
from epic_reader import BRANCH_KEY, EPIC_TYPE, read_epic, recorded_branch, validated_head
from epics import GATE_STATE_KEY, WAITING, at_the_gate, is_closed
from merge_gate import contains


def is_parked_at_the_cap(shown: dict, main_tree: Path) -> bool:
    """True when the epic waits on the question the pass cap asks and still holds open tasks."""
    return pass_ledger.asked_at_the_cap(shown) and bool(read_epic(shown, main_tree).tasks)


def awaits_acceptance(shown: dict, main_tree: Path) -> bool:
    """True when the human can accept the epic: it waits at the gate, or it is parked at the pass cap with open tasks."""
    return at_the_gate(shown) or is_parked_at_the_cap(shown, main_tree)


def branch_and_head_at_the_gate(epic: str, shown: dict, main_tree: Path, error: type[Exception]) -> tuple[str, str]:
    """The epic branch the open epic records, and its head; raises the caller's error when the bead is not an epic, is
    closed or does not await acceptance, records no epic branch, or records one that does not exist."""
    if shown.get("issue_type") != EPIC_TYPE:
        raise error(f"{epic} is not an epic")
    if is_closed(shown) or not awaits_acceptance(shown, main_tree):
        raise error(f"{epic} does not wait at the acceptance gate or at the pass cap: it needs {GATE_STATE_KEY}="
                    f"{WAITING} or the question the pass cap asks, with open tasks")
    branch = recorded_branch(shown)
    if not branch:
        raise error(f"{epic} records no epic branch as its {BRANCH_KEY} metadata")
    return branch, required_head(branch, main_tree, error)


def main_moved_since_validation(metadata: dict, main_tree: Path) -> bool:
    """True when main holds a commit that the commit validation checked lacks, or when no validation is recorded."""
    validated = validated_head(metadata)
    return not validated or not contains(MAIN_REF, validated, main_tree)


def branch_moved_since_validation(metadata: dict, branch: str, main_tree: Path) -> bool:
    """True when the epic branch moved past the commit validation checked, as a restored test moves it."""
    return branch_head(branch, main_tree) != validated_head(metadata)


def moved_since_validation(metadata: dict, branch: str, main_tree: Path) -> bool:
    """True when the merge runs the full suite again: main moved, the epic branch moved, or no validation is
    recorded."""
    return main_moved_since_validation(metadata, main_tree) or branch_moved_since_validation(metadata, branch,
                                                                                            main_tree)
