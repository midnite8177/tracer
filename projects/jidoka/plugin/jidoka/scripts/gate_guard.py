"""The acceptance gate's hold on an epic whose human label came off without a decision.

An epic waits at the gate with `gate.state` waiting and the human label. The human decides through gate.py, which
leaves the gate: a merge or a drop closes the epic, and a send back takes `gate.state` off. Taking the label off by
hand decides nothing, and the epic would otherwise sit at the gate with no label to tell the human it waits. The
scheduler parks it again when it finds the label gone, and the gate comment stays the record of what the epic holds.
"""
from __future__ import annotations

from pathlib import Path

from commands import HUMAN_LABEL, is_labeled_for_human
from epics import at_the_gate, is_closed
from pass_support import park_epic


def is_unlabeled_at_the_gate(shown: dict) -> bool:
    return not is_closed(shown) and at_the_gate(shown) and not is_labeled_for_human(shown)


def park_again(epic: str, main_tree: Path) -> None:
    """Puts the human label back on the epic, with a comment that says what the human decides at the gate."""
    park_epic(epic, f"{epic} still waits at the acceptance gate: taking the {HUMAN_LABEL} label off is no decision. "
                    "Merge it, send it back with notes, or drop it, with /jidoka:accept.", {}, main_tree)
